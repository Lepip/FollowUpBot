import html
import logging

from aiogram import Bot, Dispatcher, executor, types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from utils.config import cfg
from utils.database import Database
from bot.prompt_engineer import PromptEngineer
from bot.conversation import ConversationManager
from bot.smart import MistralAPI

debug_is_possible = False
DEBUG = cfg['debug']
bot = Bot(token=cfg['bot_token'], parse_mode='HTML')
storage = MemoryStorage()
mistral_api = MistralAPI(cfg['mistral_token'], cfg['mistral_model'])

dp = Dispatcher(bot, storage=storage)

logging.basicConfig(level=logging.INFO, 
                    handlers=[
                        logging.StreamHandler(),
                        logging.FileHandler('bot.log')
                    ])
log = logging.getLogger(__name__)

doUpdateQuestions = False

@dp.message_handler(commands="debug")
async def handle_start_command(message: types.Message):
    global DEBUG
    if debug_is_possible:
        DEBUG = not DEBUG
        if DEBUG:
            await message.reply(f"Debug on")
        else:
            await message.reply(f"Debug off")
    else:
        await message.reply("Debug mode is unavailable")

class ConversationStates(StatesGroup):
    in_conversation = State()

@dp.message_handler(commands="start")
async def handle_start_command(message: types.Message):
    await message.reply(
        "Follow Up Bot.\n\n"
        "Использование: начните разговор и общайтесь с ИИ для заполнения опросника.\n"
        "Команды:\n"
        "* <code>/restart</code> — Перезапустить/начать разговор.\n"
        "* <code>/status</code> — Показать текущий статус разговора.\n"
    )

async def get_answer(conversation, user_text=None):
    answer = await conversation.get_response(user_text, mistral_api)
    return answer

@dp.message_handler(commands=['restart'])
async def restart_conversation(message: types.Message, state: FSMContext):
    await ConversationStates.in_conversation.set()
    conversation = ConversationManager()
    await conversation.initialize(message.chat.id)
    await state.update_data(conversation=conversation)
    data = await state.get_data()
    conversation = data.get("conversation")
    await conversation.restart_conversation()
    await message.reply(await get_answer(conversation))
    data.update(conversation=conversation)
    await state.update_data(data)

@dp.message_handler(state=ConversationStates.in_conversation, content_types=types.ContentTypes.TEXT)
async def handle_in_conversation(message: types.Message, state: FSMContext):
    if message.text == "/status":
        await check_status(message, state)
        return
    if message.text == "/restart":
        await restart_conversation(message, state)
        return
    data = await state.get_data()
    conversation = data.get("conversation")
    if conversation.is_concluded:
        await message.reply("Разговор закончен, отправьте /restart для начала нового.")
    else:
        answer = await get_answer(conversation, message.text)
        if answer is None:
            await message.reply(conversation.get_final_response())
            await state.finish()
            return
        await message.reply(answer)
    data.update(conversation=conversation)
    await state.update_data(data)

@dp.message_handler(commands=['status'], state=ConversationStates.in_conversation)
async def check_status(message: types.Message, state: FSMContext):
    data = await state.get_data()
    if "conversation" not in data:
        await message.reply("Разговор не начат.")
        return
    conversation = data.get("conversation")
    status = "Текущий статус:\n\n"
    if 'name' in conversation.stage:
        status += f"Этап: {conversation.stage['name']}\n"
    status += f"Начат ли разговор: {conversation.is_started}\n"
    status += f"Закончен ли разговор: {conversation.is_concluded}\n"
    messages = await conversation.get_messages()
    status += f"История диалога: {messages}\n"


@dp.message_handler(content_types=types.ContentTypes.TEXT)
async def handle_outside_conversation(message: types.Message, state: FSMContext):
    conversation = ConversationManager()
    await conversation.initialize(message.chat.id)
    if conversation.is_concluded:
        await message.reply("Разговор закончен, отправьте /restart для начала нового.")
    else:
        await ConversationStates.in_conversation.set()
        answer = await get_answer(conversation, message.text)
        if answer is None:
            await message.reply(conversation.get_final_response())
            await state.finish()
            return
        await message.reply(answer)
        await state.update_data(conversation=conversation)

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
