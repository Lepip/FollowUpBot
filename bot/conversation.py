from utils.database import Database
from bot.questionnaire import StageOperator
from bot.prompt_engineer import PromptEngineer
from bot.smart import MistralAPI
from utils.config import cfg
import logging
log = logging.getLogger(__name__)


class MessageHandler:
    def generate(self, messages):
        for message in messages:
            print(message)
        user_input = input("Please enter doctor answer: ")
        return user_input


class ConversationManager:
    def __init__(self):
        pass

    async def initialize(self, chat_id):
        self.questionnaire = StageOperator()
        await self.load(chat_id)

    async def load(self, chat_id):
        async with Database() as db:
            self.chat_id = chat_id
            self.have_questions = False
            self.stage_id, self.batch_id, self.is_started, self.is_concluded, self.set_theme = await db.get_conv_stage(chat_id)
            self.load_stage()

    def load_stage(self, stage_id=None, batch_id=None):
        if stage_id is None:
            stage_id = self.stage_id
        if batch_id is None:
            batch_id = self.batch_id
        self.stage_id = stage_id
        self.batch_id = batch_id
        self.stage = PromptEngineer.get_stage(self.stage_id)
        if self.stage == {}:
            return False
        if self.batch_id < 0:
            self.have_questions = False
        else:
            self.is_started = True
            self.have_questions = True
        self.questionnaire.set(self.stage["questions"], self.batch_id)
        self.if_yes = self.questionnaire.get_current_batch().batch_if_yes is not None
        return True

    async def add_answer(self, answer):
        async with Database() as db:
            await db.add_message(self.chat_id, answer, "assistant")
        return answer

    async def add_user_message(self, message):
        async with Database() as db:
            await db.add_message(self.chat_id, message, "user")

    async def end_convesation(self):
        self.is_concluded = True
        async with Database() as db:
            await db.end_conv(self.chat_id)

    async def restart_conversation(self):
        self.is_concluded = False
        self.is_started = False
        async with Database() as db:
            await db.restart_conv(self.chat_id)
        await self.load(self.chat_id)

    async def get_chatbot_answer(self, llm):
        async with Database() as db:
            messages = await db.get_messages(self.chat_id)
        answer = llm.generate(messages)
        log.info(f"LLM Answer: {answer}")
        return answer
    
    async def get_messages(self):
        async with Database() as db:
            messages = await db.get_messages(self.chat_id)
        message_logs = []
        for message in messages:
            message_logs.append(f"{message['role']}: {message['content']}")
        return message_logs
    
    async def update_db(self):
        async with Database() as db:
            self.batch_id = self.questionnaire.get_current_batch_id()
            await db.set_conv_stage(self.chat_id, self.stage_id, self.batch_id, self.is_started, self.is_concluded, self.set_theme)

    async def get_response(self, message, llm):
        if self.is_concluded:
            await self.update_db()
            return None

        if message is not None:
            await self.add_user_message(f"Пациент: \"{message}\"")
        
        if not self.is_started:
            self.is_started = True
            self.have_questions = False
            async with Database() as db:
                await db.start_conv(self.chat_id)
                initial_system = PromptEngineer.initial_system_prompt()
                await db.add_message(self.chat_id, initial_system, "system")
                start_message = PromptEngineer.initial_response()
                await db.add_message(self.chat_id, start_message, "assistant")
            await self.update_db()
            return start_message
        
        if not self.set_theme:
            self.set_theme = True
            theme_message = PromptEngineer.initial_theme_prompt()
            async with Database() as db:
                await db.add_message(self.chat_id, theme_message, "assistant")
            await self.update_db()
            return theme_message

        if not self.have_questions:
            self.have_questions = True
            self.batch_id = -1
            self.chat_id = 0
            self.load_stage()
            res = await self.add_questions_system()
            if not res:
                log.error("Error adding initial questions")
                await self.update_db()
                return None
            answer = await self.get_chatbot_answer(llm)
            await self.update_db()
            return await self.add_answer(answer)
        
        if self.if_yes:
            answer = await self.get_chatbot_answer(llm)
            answer_if = False
            has_tag = False
            if "\\yes" in answer.lower():
                answer_if = True
                has_tag = True
            if "\\no" in answer.lower():
                answer_if = False
                has_tag = True
            if not has_tag:
                await self.update_db()
                return await self.add_answer(answer)
            await self.add_answer(answer)
            res = await self.add_questions_system(answer_if)
            if not res:
                self.end_convesation()
                await self.update_db()
                return None
            answer = await self.get_chatbot_answer(llm)
            await self.update_db()
            return await self.add_answer(answer)
        else:
            answer = await self.get_chatbot_answer(llm)
            self.add_answer(answer)
            if "\\done" in answer.lower():
                res = self.add_questions_system()
                if not res:
                    self.end_convesation()
                    await self.update_db()
                    return None
                answer = await self.get_chatbot_answer(llm)
            await self.update_db()    
            return await self.add_answer(answer)

    def get_final_response(self):
        return PromptEngineer.last_response()

    async def add_questions_system(self, answered_yes=False):
        questions, if_yes = self.questionnaire.get(answered_yes)
        if questions is None:
            log.error(f"No questions to add, stage: {self.stage}")
            return False
        self.if_yes = if_yes
        self.batch_id = self.questionnaire.get_current_batch_id()
        if not if_yes:
            questions_prompt = PromptEngineer.construct_questions_prompt(questions, self.stage["name"])
            async with Database() as db:
                await db.add_message(self.chat_id, questions_prompt, "user")
            return True
        else:
            if_question_prompt = PromptEngineer.construct_if_question_prompt(questions, self.stage["name"])
            async with Database() as db:
                await db.add_message(self.chat_id, if_question_prompt, "user")
            return True

        

