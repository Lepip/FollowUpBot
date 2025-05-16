from utils.database import Database
from bot.questionnaire import StageOperator
from bot.prompt_engineer import PromptEngineer
# from bot.smart import MistralAPI
# from utils.config import cfg
import logging
log = logging.getLogger(__name__)


class MessageHandler:
    def generate(self, messages):
        for message in messages:
            print(message)
        user_input = input("Please enter doctor answer: ")
        return user_input


class ConversationManager:
    async def __init__(self, chat_id, conv_id):
        async with Database() as db:
            self.chat_id = chat_id
            self.conv_id = conv_id
            self.stage_id, self.batch_id, self.is_started, self.have_questions = await db.get_conv_stage(chat_id, conv_id)
            self.if_yes = False
            self.questionnaire = StageOperator()
            # self.llm = MistralAPI(cfg['mistral_token'], cfg['mistral_model'])
            self.llm = MessageHandler()
            self.load_stage()

    def load_stage(self, stage_id=None, batch_id=None):
        if stage_id is None:
            stage_id = self.stage_id
        if batch_id is None:
            batch_id = self.batch_id
        self.stage_id = stage_id
        self.batch_id = batch_id
        self.stage = PromptEngineer.get_stage(self.stage_id)
        self.questionnaire.set(self.stage["questions"], self.batch_id)
        self.if_yes = self.questionnaire.get_current_batch().batch_if_yes is not None

    async def add_answer(self, answer):
        with Database() as db:
            await db.add_message(self.conv_id, answer, "assistant")
        return answer

    async def get_response(self, message):
        if not self.is_started:
            self.is_started = True
            self.have_questions = False
            with Database() as db:
                await db.start_conv(self.chat_id, self.conv_id)
                initial_system = PromptEngineer.initial_system_prompt()
                await db.add_message(self.conv_id, initial_system, "system")
                start_message = PromptEngineer.initial_response()
                await db.add_message(self.conv_id, start_message, "assistant")
            return start_message
        
        if not self.have_questions:
            self.have_questions = True
            self.batch_id = 0
            self.chat_id = 0
            self.load_stage()
            res = await self.add_questions_system()
            if not res:
                log.error("Error adding initial questions")
                return None
            answer = await self.get_chatbot_answer()
            return await self.add_answer(answer)
        
        if self.if_yes:
            answer = await self.get_chatbot_answer()
            answer_if = False
            has_tag = False
            if "\\yes" in answer.lower():
                answer_if = True
                has_tag = True
            if "\\no" in answer.lower():
                answer_if = False
                has_tag = True
            if not has_tag:
                return await self.add_answer(answer)
            await self.add_answer(answer)
            res = await self.add_questions_system(answer_if)
            if not res:
                return None
            answer = await self.get_chatbot_answer()
            return await self.add_answer(answer)
        else:
            answer = await self.get_chatbot_answer()
            if "\\done" in answer.lower():
                res = self.add_questions_system()
                if not res:
                    return None
                answer = await self.get_chatbot_answer()
            return await self.add_answer(answer)

    async def add_questions_system(self, answered_yes=False):
        questions, if_yes = self.questionnaire.get(answered_yes)
        if questions is None:
            return False
        self.if_yes = if_yes
        self.batch_id = self.questionnaire.get_current_batch_id()
        if not if_yes:
            questions_prompt = PromptEngineer.construct_questions_prompt(questions, self.stage["name"])
            with Database() as db:
                await db.add_message(questions_prompt, "system")
            return True
        else:
            if_question_prompt = PromptEngineer.construct_if_question_prompt(questions, self.stage["name"])
            with Database() as db:
                await db.add_message(if_question_prompt, "system")
            return True

        
    async def get_chatbot_answer(self):
        with Database() as db:
            messages = await db.get_messages(self.chat_id)
        answer = await self.llm.generate(messages)
        return answer

        

