from utils.database import Database
from bot.questionnaire import StageOperator
from bot.prompt_engineer import PromptEngineer
from bot.answers_analyzer import analyze_answers
from utils.config import cfg
import logging
log = logging.getLogger(__name__)

class ConversationManager:
    def __init__(self):
        self.analysis = None

    async def initialize(self, chat_id):
        self.questionnaire = StageOperator()
        await self.load(chat_id)
    
    async def progress_stage(self):
        log.debug(f"Progressing stage: {self.stage_id}")
        self.stage_id += 1
        self.batch_id = -1
        self.load_stage()
        self.have_questions = True
        return await self.add_questions_system(recursive=True)

    async def load(self, chat_id):
        async with Database() as db:
            self.chat_id = chat_id
            self.have_questions = False
            self.stage_id, self.batch_id, self.is_started, self.is_concluded, self.set_theme = await db.get_conv_stage(chat_id)
            self.load_stage()

    async def add_message(self, message, role):
       async with Database() as db:
           await db.add_message(self.chat_id, message, role, self.stage_id)

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
        await self.add_message(answer, "assistant")
        return answer

    async def add_user_message(self, message):
        await self.add_message(message, "user")

    async def end_convesation(self, llm):
        self.is_concluded = True
        self.analysis = await analyze_answers(self.chat_id, llm)
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
        log.debug(f"Getting a response to message {message}")
        if self.is_concluded:
            await self.update_db()
            if not self.analysis:
                self.analysis = await analyze_answers(self.chat_id, llm)
            return None

        if message is not None:
            log.debug("Added user message to db")
            await self.add_user_message(f"Пациент: \"{message}\"")
        
        if not self.is_started:
            log.debug("Starting a conversation")
            self.is_started = True
            self.have_questions = False
            async with Database() as db:
                await db.start_conv(self.chat_id)
                initial_system = PromptEngineer.initial_system_prompt()
                await db.add_message(self.chat_id, initial_system, "system", self.stage_id)
                start_message = PromptEngineer.initial_response()
                await db.add_message(self.chat_id, start_message, "assistant", self.stage_id)
            await self.update_db()
            return start_message
        
        if not self.set_theme:
            log.debug("Setting a theme")
            self.set_theme = True
            theme_message = PromptEngineer.initial_theme_prompt()
            await self.add_message(theme_message, "system")
            await self.update_db()
            return theme_message

        if not self.have_questions:
            log.debug("Adding initial questions")
            self.batch_id = -1
            self.stage_id = 0
            self.load_stage()
            self.have_questions = True
            res = await self.add_questions_system()
            if not res:
                log.error("Error adding initial questions")
                await self.update_db()
                return None
            answer = await self.get_chatbot_answer(llm)
            await self.update_db()
            return await self.add_answer(answer)
        
        if self.if_yes:
            log.debug("Getting a response to if_yes")
            answer = await self.get_chatbot_answer(llm)
            answer_if = False
            has_tag = False
            if "\\yes" in answer.lower():
                log.debug("Found \\yes tag")
                answer_if = True
                has_tag = True
            if "\\no" in answer.lower():
                log.debug("Found \\no tag")
                answer_if = False
                has_tag = True
            if not has_tag:
                await self.update_db()
                return await self.add_answer(answer)
            await self.add_answer(answer)
            res = await self.add_questions_system(answer_if)
            if not res:
                await self.end_convesation(llm)
                await self.update_db()
                return None
            answer = await self.get_chatbot_answer(llm)
            await self.update_db()
            return await self.add_answer(answer)
        else:
            answer = await self.get_chatbot_answer(llm)
            result = await self.add_answer(answer)
            log.debug("Checking for done")
            if "\\done" in answer.lower():
                log.debug("Found \\done tag")
                res = await self.add_questions_system()
                if not res:
                    await self.end_convesation(llm)
                    await self.update_db()
                    return None
                answer = await self.get_chatbot_answer(llm) 
                result = await self.add_answer(answer)
            await self.update_db()
            return result

    def get_final_response(self):
        return PromptEngineer.last_response()

    async def add_questions_system(self, answered_yes=False, recursive = False):
        questions, if_yes = self.questionnaire.get(answered_yes)
        if questions is None and recursive:
            return False
        if questions is None:
            return await self.progress_stage()
        self.if_yes = if_yes
        self.batch_id = self.questionnaire.get_current_batch_id()
        if not if_yes:
            questions_prompt = PromptEngineer.construct_questions_prompt(questions, self.stage["name"])
            await self.add_message(questions_prompt, "user")
            return True
        else:
            if_question_prompt = PromptEngineer.construct_if_question_prompt(questions, self.stage["name"])
            await self.add_message(if_question_prompt, "user")
            return True

        

