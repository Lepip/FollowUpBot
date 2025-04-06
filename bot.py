import html
import logging

from aiogram import Bot, Dispatcher, executor, types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from utils.config import cfg
from utils.database import Database
from utils.middleware import AlbumMiddleware

debug_is_possible = False
debug = False
bot = Bot(token=cfg['bot_token'], parse_mode='HTML')
storage = MemoryStorage()

dp = Dispatcher(bot, storage=storage)

logging.basicConfig(filename='bot.log', level=logging.INFO)


@dp.message_handler(commands="debug")
async def handle_start_command(message: types.Message):
    global debug
    if debug_is_possible:
        debug = not debug
        if debug:
            await message.reply(f"Debug on")
        else:
            await message.reply(f"Debug off")
    else:
        await message.reply("Debug mode is unavailable")

class ConversationState(StatesGroup):
    waiting_for_answer = State()
    closed = State()

async def init_conversation(message: types.Message, state: FSMContext):
    logging.info("Startintg conversation.")
    await message.answer("Разговор начинается.")
    async with Database() as db:
        is_closed = await db.is_concluded(message.chat.id)
        if (is_closed is None) or is_closed:
            await state.finish()
            logging.warning(f"Couldn't start conversation: it's closed: {is_closed}.")
            await message.answer("Не удалось начать текущий разговор. Он уже закончен. Проверьте <code>/status</code>.")
            return
        conv_id, _ = await db.get_current_conv(message.chat.id)
        next_question = await db.get_next_question(conv_id)
        if next_question is None:
            await db.set_status(conv_id, True, True)
            logging.warning(f"Couldn't start conversation: no questions.")
            await message.answer("Не удалось начать текущий разговор. Он уже закончен. Проверьте <code>/status</code>.")
            await state.finish()
            return
    await state.update_data(current_question_id=next_question['question_id'])
    await message.answer(next_question['question_text'])
    await ConversationState.waiting_for_answer.set()
    logging.info(f"Started conversation. Asked a question: {next_question['question_text']}")


@dp.message_handler(commands="start")
async def handle_start_command(message: types.Message):
    await message.reply(
        "Welcome to the Follow Up Bot.\n\n"
        "Usage: start a conversation and chat with the bot.\n"
        "Possible commands (parameters in \"[]\" are optional):\n"
        "* <code>/new [conversation_name]</code> — starts a new conversation.\n"
        "* <code>/delete [conversation_name]</code> — delete a conversation.\n"
        "* <code>/select [conversation_name]</code> — select another conversation.\n"
        "* <code>/restart</code> — restart this conversation.\n"
        "* <code>/status</code> — show current questions, answers and status of the conversation.\n"
    )

def format_questions(questions):
    formatted = []
    for ind, q in enumerate(questions):
        answer = f"{q['answer']}" if q['answer'] else "без ответа"
        formatted.append(f"{ind}. {q['question_text']}\nОтвет: {answer}")
    return "\n".join(formatted)

async def answer_status(message: types.Message):
    async with Database() as db:
        questions = await db.get_questions(message.chat.id)
        is_concluded = await db.is_concluded(message.chat.id)
    question_list = format_questions(questions)
    status = "Закончен" if is_concluded else "В процессе"
    await message.answer(f"Статус текущего разговора:\n{question_list}\nЭтап разговора: {status}")

@dp.message_handler(commands='status')
async def cmd_status(message: types.Message):
    await answer_status(message)

class NewConversationState(StatesGroup):
    waiting_for_name = State()
    waiting_for_questions = State()

async def create_new_conv(message: types.Message, conv_name: str):
    async with Database() as db:
        conv_id = await db.new_conv(message.chat.id, conv_name)
        await db.set_current_conv(message.chat.id, conv_id)
    await message.answer(f"Создан новый разговор: {conv_name}. Отправьте список вопросов, по одному в строке.")
    await NewConversationState.waiting_for_questions.set()

@dp.message_handler(commands='new')
async def cmd_new(message: types.Message, state: FSMContext):
    args = message.get_args()
    if not args:
        await message.answer("Отправьте название нового разговора.")
        await NewConversationState.waiting_for_name.set()
        return
    await create_new_conv(message, args.strip())

@dp.message_handler(state=NewConversationState.waiting_for_name)
async def process_name(message: types.Message, state: FSMContext):
    conv_name = message.text.strip()
    await create_new_conv(message, conv_name)

@dp.message_handler(state=NewConversationState.waiting_for_questions)
async def process_questions(message: types.Message, state: FSMContext):
    questions = message.text.strip().split('\n')
    async with Database() as db:
        await db.set_questions(message.chat.id, questions)
    await message.answer("Вопросы сохранены.")
    await answer_status(message)
    await state.finish()
    await init_conversation(message, state)

class DeleteConvState(StatesGroup):
    waiting_for_name = State()

@dp.message_handler(commands='delete')
async def cmd_delete(message: types.Message, state: FSMContext):
    args = message.get_args()
    if args:
        conv_name = args.strip()
        async with Database() as db:
            await db.delete_conv_by_name(message.chat.id, conv_name)
        await message.answer(f"Разговор '{conv_name}' удален.")
    else:
        async with Database() as db:
            convs = await db.get_convs(message.chat.id)
        if convs:
            conv_list = "\n".join([f"{i+1}. {conv['conv_name']}" for i, conv in enumerate(convs)])
            await message.answer(f"Пожалуйста, выберите номер разговора для удаления:\n{conv_list}")
            await state.update_data(convs=convs)
            await DeleteConvState.waiting_for_name.set()
        else:
            await message.answer("У вас нет разговоров для удаления.")

@dp.message_handler(state=DeleteConvState.waiting_for_name)
async def process_delete_selection(message: types.Message, state: FSMContext):
    try:
        index = int(message.text.strip()) - 1
        data = await state.get_data()
        convs = data.get('convs')

        if 0 <= index < len(convs):
            conv_id = convs[index]['conv_id']
            async with Database() as db:
                await db.delete_conv(conv_id)
            await message.answer(f"Разговор '{convs[index]['conv_name']}' удален.")
        else:
            await message.answer("Неверный номер. Пожалуйста, выберите снова.")
    except ValueError:
        await message.answer("Пожалуйста, введите номер разговора.")

    await state.finish()

class SelectConvState(StatesGroup):
    waiting_for_name = State()

@dp.message_handler(commands='select')
async def cmd_select(message: types.Message, state: FSMContext):
    args = message.get_args()
    if args:
        conv_name = args.strip()
        async with Database() as db:
            await db.set_current_conv_by_name(message.chat.id, conv_name)
        await message.answer(f"Текущий разговор: '{conv_name}'.")
        await init_conversation(message, state)
    else:
        async with Database() as db:
            convs = await db.get_convs(message.chat.id)
        if convs:
            conv_list = "\n".join([f"{i+1}. {conv['conv_name']}" for i, conv in enumerate(convs)])
            await message.answer(f"Пожалуйста, выберите номер разговора:\n{conv_list}")
            await state.update_data(convs=convs)
            await SelectConvState.waiting_for_name.set()
        else:
            await message.answer("У вас нет разговоров.")

@dp.message_handler(state=SelectConvState.waiting_for_name)
async def process_set_selection(message: types.Message, state: FSMContext):
    try:
        index = int(message.text.strip()) - 1
        data = await state.get_data()
        convs = data.get('convs')

        if 0 <= index < len(convs):
            conv_id = convs[index]['conv_id']
            async with Database() as db:
                await db.set_current_conv(message.chat.id, conv_id)
            await message.answer(f"Текущий разговор: '{convs[index]['conv_name']}'")
            await state.finish()
            await init_conversation(message, state)
        else:
            await message.answer("Неверный номер. Выберите снова.")
    except ValueError:
        await message.answer("Введите номер разговора.")

    await state.finish()

async def ask_next_question(message: types.Message, conv_id: int, state: FSMContext):
    async with Database() as db:
        next_question = await db.get_next_question(conv_id)

    if next_question is None:
        async with Database() as db:
            await db.set_status(conv_id, True, True)
        await message.answer("Разговор закончен.")
        await state.finish()
        return

    await message.answer(next_question['question_text'])
    await state.update_data(current_question_id=next_question['question_id'])
    await ConversationState.waiting_for_answer.set()

@dp.message_handler(commands="restart")
async def cmd_restart(message: types.Message, state: FSMContext):
    async with Database() as db:
        conv_id = await db.get_current_conv(message.chat.id)
        await db.clear_answers(conv_id)
        await db.delete_chatlogs(conv_id)
    await message.answer("Текущий разговор перезапущен.")
    await init_conversation(message, state)

@dp.message_handler(state=ConversationState.waiting_for_answer)
async def regular_message(message: types.Message, state: FSMContext):
    data = await state.get_data()
    current_question_id = data.get('current_question_id')

    async with Database() as db:
        conv_id, _ = await db.get_current_conv(message.chat.id)
        await db.write_answer(conv_id, current_question_id, message.text)

    await ask_next_question(message, conv_id, state)

if __name__ == "__main__":
    # dp.middleware.setup(AlbumMiddleware())
    executor.start_polling(dp, skip_updates=True)
