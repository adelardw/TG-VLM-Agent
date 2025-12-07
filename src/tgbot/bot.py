from aiogram.types import KeyboardButton, ReplyKeyboardRemove
from aiogram.utils.chat_action import ChatActionSender
from aiogram.fsm.context import FSMContext
from aiogram import F
from aiogram.utils.keyboard import ReplyKeyboardBuilder
from aiogram import Bot, Dispatcher, Router, types
from aiogram.filters import CommandStart, Command
from aiogram.types import FSInputFile
from aiogram.fsm.storage.memory import MemoryStorage
from beautylogger import logger
import io
import numpy as np
import soundfile as sf
import librosa
from datetime import datetime
from vega.vega_stream import VEGA
from agents import tgc_mas
from graphs import tgc_default
import numpy as np
from tgbot.bot_shemas import BotStates
from tgbot.utils import (split_long_message,
                         grant_trial_subscription,
                         grant_30days_subscription,
                         check_subscription)

import os
from src.users_cache import cache_db, thread_memory
from config import API_TOKEN, ADMIN_ID, WHITE_LIST, TIMEZONE
from src.tools.notification_tools import scheduler


storage=MemoryStorage()
bot = Bot(token=API_TOKEN)
dp = Dispatcher(storage=storage)
router = Router()
vega = VEGA()
dp.include_router(router)



async def run_default_assistant(message: types.Message, text: str, user_id: str):
    """
    Функция запускает граф tgc_default и отправляет ответ пользователю.
    """
    try:
        thread_info = thread_memory.check_and_init_thread(user_id=user_id, message_datetime=message.date)
        local_context = thread_memory.get_local_history(thread_info['thread_id'])

        thread_memory.add_message_to_history(thread_info['thread_id'], role='user', content=text)

        config = {"configurable": {"thread_id": thread_info['thread_id']}}
        
        default_input = {
            "make_history_summary": thread_info['make_history_summary'],
            "user_id": user_id,
            "thread_id": thread_info['thread_id'],
            "previous_thread_id": thread_info['previous_thread_id'],
            "local_context": local_context,
            "image_url": None,
            'user_message': text
        }

        async with ChatActionSender.typing(bot=bot, chat_id=message.chat.id):
            answer_state = await tgc_default.ainvoke(default_input, config=config)
        
        assistant_response = answer_state.get('generation', 'Извините, я задумался.')
        thread_memory.add_message_to_history(thread_info['thread_id'], role='assistant', content=assistant_response)
        
        chunks = split_long_message(assistant_response)
        for chunk in chunks:
            chunk = chunk.replace('**',"*")
            await message.answer(chunk, parse_mode="Markdown")
            
    except Exception as e:
        logger.error(f'[BUG in Default Assistant] {e}', exc_info=True)
        await message.answer("Произошла ошибка при обработке сообщения.")

async def voice_message_to_numpy(bot: Bot, file_id: str, target_sr: int) -> np.ndarray:
    """
    Идеально подходит для обработки голосовых сообщений Telegram (OGG).
    """
    file_info = await bot.get_file(file_id)
    file_content = await bot.download_file(file_info.file_path)
    audio_buffer = io.BytesIO(file_content.read())

    audio_np, original_sr = sf.read(audio_buffer)


    if audio_np.ndim > 1:
        audio_np = librosa.to_mono(audio_np.T)


    if original_sr != target_sr:
        audio_np = librosa.resample(y=audio_np, orig_sr=original_sr, target_sr=target_sr)

    return audio_np

@router.message(CommandStart())
async def init(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    is_subscribed, end_time = check_subscription(user_id,cache_db)
    builder = ReplyKeyboardBuilder()
    if is_subscribed and end_time:
        await cmd_menu(message)
    elif not is_subscribed and not end_time:
        builder.row(KeyboardButton(text="Прочитать пользовательское соглашение"))
        await message.answer('Привет! Я голосовой ассистент VEGA, который помогает c такими проблемами'\
                            "1. Вы можете поставить какие - то уведомления о каких - то событиях"\
                            "2. Посмотреть прогноз погоды в Вашем городе"\
                            "3. Сделать саммари новостей из интенета по задаваемой Вами тематике"\
                            'Вы можете со мной общаться c использованием текста или голосовых сообщений.',
                            reply_markup=builder.as_markup(resize_keyboard=True))

    elif is_subscribed and not end_time:
        await cmd_menu(message)

    elif not is_subscribed and end_time:
        builder.row(KeyboardButton(text="Оплатить"))
        await message.answer("Срок вашей подписки истек. Чтобы продолжить, пожалуйста, оформите новую.",
                             reply_markup=builder.as_markup(resize_keyboard=True))


@router.message(Command('menu'))
async def cmd_menu(message: types.Message):
    user_id = str(message.from_user.id)
    is_subscribed, _ = check_subscription(user_id, cache_db)

    builder = ReplyKeyboardBuilder()
    
    if not is_subscribed:
        builder.row(KeyboardButton(text="Оплатить"))
        text_msg = "Ваша подписка неактивна."
    else:
        if user_id in WHITE_LIST:
            builder.row(KeyboardButton(text="[AGENTIC MODE]"))
        builder.row(KeyboardButton(text="Прочитать пользовательское соглашение"))
        text_msg = "Меню открыто. Вы можете просто писать мне сообщения или отправлять голосовые."

    await message.answer(
        text_msg,
        reply_markup=builder.as_markup(resize_keyboard=True)
    )

@router.message(F.text=='Прочитать пользовательское соглашение')
async def user_confidence_state(message: types.Message, state: FSMContext):
    await message.answer('Пожалуйста, ознакомьтесь с политикой конфиденциальности и пользовательским соглашением')
    abs_path = os.path.abspath(os.path.curdir)

    confidence = FSInputFile(os.path.join(abs_path, 'confidence.md'))
    acceptions = FSInputFile(os.path.join(abs_path, 'user_accept.md'))

    await message.answer_document(confidence)
    await message.answer_document(acceptions)

    user_id = message.from_user.id
    builder = ReplyKeyboardBuilder()

    builder.row(KeyboardButton(text="Принять"))
    builder.row(KeyboardButton(text="Отказаться"))

    await message.answer(
            "Выберите действие:",
            reply_markup=builder.as_markup(resize_keyboard=True))


@router.message(F.text =='Оплатить')
async def billing(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    if ...: # Acception Logic Web Telegram Hook
        grant_30days_subscription(user_id, cache_db)
    else:
        ...
        await ""

@router.message(F.text == 'Принять')
async def accept(message: types.Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    is_subscribed, end_date = check_subscription(user_id, cache_db)
    if not is_subscribed and not end_date:
        grant_trial_subscription(user_id, cache_db)

    await message.answer('Добро пожаловать! Будем рады фидбеку!! Это поможет нам стать лучше',
                         reply_markup=ReplyKeyboardRemove())

    await cmd_menu(message)


@router.message(F.text == 'Отказаться')
async def reject(message: types.Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    is_subscribed, end_date = check_subscription(user_id, cache_db)
    builder = ReplyKeyboardBuilder()
    if not is_subscribed and not end_date:
        await message.answer('Надумаете - приходите (Но мы Вам уже не рады!)',
                         reply_markup=ReplyKeyboardRemove())

        await init(message, state)
    elif not is_subscribed and end_date:
        builder.row(KeyboardButton(text="Оплатить"))
        await message.answer("Срок вашей подписки истек. Чтобы продолжить, пожалуйста, оформите новую.",
                     reply_markup=builder.as_markup(resize_keyboard=True))

    else:
        builder.row(KeyboardButton(text="Прочитать пользовательское соглашение"))
        await message.answer("Чтобы продолжить пользоваться сервисом, независимо от подписки, Вы должны принять соглашение",
                     reply_markup=builder.as_markup(resize_keyboard=True))



@router.message(F.text == '[AGENTIC MODE]')
async def send_message(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    is_subscribed, end_date = check_subscription(user_id, cache_db)
    builder = ReplyKeyboardBuilder()
    if is_subscribed:
        await message.answer(
            "🕵️ *Режим Агента активирован*\n"
            "Я выполняю задачи (поиск, календарь, погода).\n"
            "Нажмите кнопку ниже или напишите 'Меню' для возврата к обычному общению.",
            reply_markup=builder.as_markup(resize_keyboard=True),
            parse_mode="Markdown")
        await state.set_state(BotStates.chat)
    else:
        builder.row(KeyboardButton(text="Оплатить"))
        await message.answer("Срок вашей подписки истек. Чтобы продолжить, пожалуйста, оформите новую.",
                             reply_markup=builder.as_markup(resize_keyboard=True))


@router.message(BotStates.chat)
async def chat(message: types.Message, state: FSMContext, bot: Bot):
    user_id = message.from_user.id
    exit_commands = ['/menu', 'меню', 'menu', 'выход', 'выход из режима', 'stop', 'стоп']
    
    if message.voice:
        audio = await voice_message_to_numpy(bot, message.voice.file_id, 16000)
        text = vega.transcribe(audio)
    else:
        text = message.text
        
    if text.lower().strip() in exit_commands:

        await state.clear()
        await message.answer("Режим агента выключен. Возвращаюсь к памяти.", reply_markup=ReplyKeyboardRemove())
        await cmd_menu(message) 
        return

    try:
        await message.answer("⏳ Агент работает...")
        async with ChatActionSender.typing(bot=bot, chat_id=message.chat.id):
            answer = await tgc_mas.ainvoke({'user_id': user_id, 'input': text, 'date': datetime.now(TIMEZONE).isoformat()})
        chunks = split_long_message(answer)
        for chunk in chunks:
            chunk = chunk.replace('**',"*")
            await message.answer(chunk, parse_mode="Markdown")

    except Exception as e:
        logger.debug(f'[BUG] {e}')
        await cmd_menu(message)

    #await state.set_state(BotStates.main_menu)
    await cmd_menu(message)


@router.message(F.text | F.voice)
async def handle_any_message(message: types.Message, bot: Bot):
    """
    Этот хендлер ловит все текстовые и голосовые сообщения,
    которые не являются командами или кнопками меню.
    """
    user_id = str(message.from_user.id)
    is_subscribed, end_date = check_subscription(user_id, cache_db)

    if not is_subscribed:
        builder = ReplyKeyboardBuilder()
        builder.row(KeyboardButton(text="Оплатить"))
        await message.answer("Срок вашей подписки истек.", reply_markup=builder.as_markup(resize_keyboard=True))
        return
    
    if message.voice:
        wait_msg = await message.answer("Слушаю...")
        try:
            audio = await voice_message_to_numpy(bot, message.voice.file_id, 16000)
            text = vega.transcribe(audio)
            await bot.delete_message(chat_id=message.chat.id, message_id=wait_msg.message_id)
        except Exception as e:
            await message.answer("Не удалось распознать голос.")
            return
    else:
        text = message.text


    if not text:
        return


    await run_default_assistant(message, text, user_id)
    
async def main():
    logger.info('StartApp')
    scheduler.start()
    await dp.start_polling(bot)
    
    

