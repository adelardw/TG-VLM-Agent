from aiogram.types import KeyboardButton, ReplyKeyboardRemove
from aiogram.utils.chat_action import ChatActionSender
import base64
from aiogram.fsm.context import FSMContext
from aiogram import F
from aiogram.utils.keyboard import ReplyKeyboardBuilder
from aiogram import Bot, Dispatcher, Router, types
from aiogram.filters import CommandStart, Command
from aiogram.types import FSInputFile, InputMediaPhoto, BufferedInputFile
from aiogram.fsm.storage.memory import MemoryStorage
from beautylogger import logger
import io
import numpy as np
import soundfile as sf
import librosa
from .middleware import AlbumMiddleware
from datetime import datetime, timedelta
from time import perf_counter
from vega.vega_stream import VEGA
from agents import tgc_mas
from graphs import tgc_default
import numpy as np
from tgbot.bot_shemas import BotStates
from tgbot.utils import (prepare_messages,
                         grant_trial_subscription,
                         grant_30days_subscription,
                         check_subscription,
                         encode_image_to_base64, clean_assistant_answer)

import os
from src.users_cache import cache_db, thread_memory
from config import API_TOKEN, ADMIN_ID, WHITE_LIST, TIMEZONE
from src.tools.notification_tools import scheduler
from aiogram.exceptions import TelegramBadRequest

storage=MemoryStorage()
bot = Bot(token=API_TOKEN)
dp = Dispatcher(storage=storage)
router = Router()
vega = VEGA()
dp.include_router(router)

router.message.middleware(AlbumMiddleware(latency=0.6))


def decode_data_uri(uri: str) -> BufferedInputFile:
    header, encoded_data = uri.split(',', 1)
    mime_type = header.split(';')[0].split('/')[-1]
    image_bytes = base64.b64decode(encoded_data)
    return BufferedInputFile(image_bytes, filename=f"image.{mime_type}")

async def _safe_answer(message: types.Message, text: str):
    """Вспомогательная функция для отправки текста с фолбеком Markdown"""
    if not text.strip():
        return
    try:
        await message.answer(text, parse_mode="Markdown")
    except TelegramBadRequest:
        await message.answer(text, parse_mode=None)

async def send_chunked_message(message: types.Message, text: str, image_links: list[str] = None):
    """
    Отправляет ответ пользователю, используя авторскую логику разбиения.
    """
    if image_links is None:
        image_links = []

    text = clean_assistant_answer(text)
    text = text.replace("***", "*").replace("**", "*").replace("#", "")

    message_chunks, need_photo_to_msg_chunk = prepare_messages(text)

    if not image_links:
        for chunk in message_chunks:
            await _safe_answer(message, chunk)
        return

    media_group = []
    for link in image_links[:10]:
        try:
            if link.startswith('data:image/'):
                photo_file = decode_data_uri(link)
                media_group.append(InputMediaPhoto(media=photo_file))
            elif link.startswith(('http://', 'https://')):
                media_group.append(InputMediaPhoto(media=link))
        except Exception as e:
            logger.error(f"Ошибка подготовки медиа: {e}")

    if media_group:
        caption_chunk = message_chunks[0]
        
        if len(caption_chunk) > 1024:
            caption = caption_chunk[:1020] + "..."
            remaining_text = caption_chunk[1020:]
            message_chunks[0] = caption
            message_chunks.insert(1, remaining_text)
        else:
            caption = caption_chunk

        try:
            if len(media_group) > 1:
                media_group[0].caption = caption
                media_group[0].parse_mode = "Markdown"
                await message.answer_media_group(media=media_group)
            else:
                await message.answer_photo(
                    photo=media_group[0].media, 
                    caption=caption, 
                    parse_mode="Markdown"
                )
        except TelegramBadRequest:
            if len(media_group) > 1:
                media_group[0].parse_mode = None
                await message.answer_media_group(media=media_group)
            else:
                await message.answer_photo(photo=media_group[0].media, caption=caption, parse_mode=None)
        
        for chunk in message_chunks[1:]:
            await _safe_answer(message, chunk)
    else:
        for chunk in message_chunks:
            await _safe_answer(message, chunk)


async def process_message_content(bot: Bot, message: types.Message, album: list[types.Message] = None):
    """
    Собирает ВСЕ фото в список.
    Ищет ОДНУ подпись (так как в ТГ одна подпись на альбом).
    """
    text_content = ""
    images_list = []

    if album:
        for msg in album:
            if not text_content and msg.caption:
                text_content = msg.caption
            
            if msg.photo:
                photo_info = msg.photo[-1]
                file_io = await bot.download(photo_info.file_id)
                base64_img = encode_image_to_base64(file_io)
                images_list.append(f"data:image/jpeg;base64,{base64_img}")

    elif message.photo:
        text_content = message.caption or ""
        
        photo_info = message.photo[-1]
        file_io = await bot.download(photo_info.file_id)
        base64_img = encode_image_to_base64(file_io)
        images_list.append(f"data:image/jpeg;base64,{base64_img}")

    elif message.text:
        text_content = message.text

    return text_content.strip(), images_list

async def run_default_assistant(message: types.Message, text: str, user_id: str, images: list[str]):
    """
    Функция запускает граф tgc_default и отправляет ответ пользователю.
    """
    
    try:
        thread_info = thread_memory.check_and_init_thread(user_id=user_id, message_datetime=message.date)

        thread_memory.add_message_to_history(thread_info['thread_id'], role='user', content=text,
                                             metadata={'images': images, 'time': message.date.isoformat() } if images else 
                                                      {'time': message.date.isoformat()})
        local_context = thread_memory.get_local_history(thread_info['thread_id'])
        

        config = {"configurable": {"thread_id": thread_info['thread_id']}}
        
        default_input = {
            "make_history_summary": thread_info['make_history_summary'],
            "user_id": user_id,
            "thread_id": thread_info['thread_id'],
            "previous_thread_id": thread_info['previous_thread_id'],
            "local_context": local_context,
            "image_url": images or None,
            'user_message': text,
            "time": message.date
        }

        start = perf_counter()
        
        async with ChatActionSender.typing(bot=bot, chat_id=message.chat.id):
            answer_state = await tgc_default.ainvoke(default_input, config=config)
        
        end = perf_counter() - start

        schema_obj = answer_state.get('generation')
        web_images = answer_state.get('web_images', [])
        
        raw_text = schema_obj.final_answer if schema_obj else "Извините, я не смог сформулировать ответ."
        thread_memory.add_message_to_history(thread_info['thread_id'], role='assistant', content=raw_text,
                                             metadata={'time': (message.date + timedelta(seconds=int(end))).isoformat() })
        
        await send_chunked_message(message, raw_text, image_links=web_images)
            
    except Exception as e:
        logger.info(f'[BUG in Default Assistant] {e}')
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
        await message.answer('Привет! Я ассистент, который помогает с некоторыми рутинными задачами:'\
                            "1. Вы можете поставить какие - то уведомления о каких - то событиях"\
                            "2. Посмотреть прогноз погоды в Вашем городе"\
                            "3. Сделать саммари новостей из интенета по задаваемой Вами тематике"\
                            "4. Найти изображения в интернете."\
                            "5. Попросить меня проанализировать изображения."\
                            
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
            builder.row(KeyboardButton(text="[Agent On]"))
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



@router.message(F.text == '[Agent On]')
async def send_message(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    is_subscribed, end_date = check_subscription(user_id, cache_db)
    builder = ReplyKeyboardBuilder()
    if is_subscribed:
        builder.row(KeyboardButton(text="[Agent Off]"))
        await message.answer(
            "*Режим Агента активирован*\n"
            "Пока что я могу ставить напоминания о событиях.\n"
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
    exit_commands = ['/menu', 'меню', 'menu', 'выход', 'выход из режима', 'stop', 'стоп', '[agent off]']
    
    if message.voice:
        audio = await voice_message_to_numpy(bot, message.voice.file_id, 16000)
        text = vega.transcribe(audio)
    else:
        text = message.text
        
    if text.lower().strip() in exit_commands:

        await state.clear()
        await message.answer("Режим агента выключен.", reply_markup=ReplyKeyboardRemove())
        await cmd_menu(message) 
        return

    try:
        await message.answer("⏳ Агент работает...")
        async with ChatActionSender.typing(bot=bot, chat_id=message.chat.id):
            assistant_response = await tgc_mas.ainvoke({'user_id': user_id, 'input': text, 'date': datetime.now(TIMEZONE).isoformat()})
        
        await send_chunked_message(message, assistant_response)

    except Exception as e:
        logger.debug(f'[BUG] {e}')
        await cmd_menu(message) 


@router.message(F.text | F.voice | F.photo)
async def handle_any_message(message: types.Message, bot: Bot, state: FSMContext, album: list[types.Message] = None):
    """
    Обрабатывает всё: голос, текст, одно фото, альбом фото.
    """
    if await state.get_state() is not None:
        return

    user_id = str(message.from_user.id)
    is_subscribed, _ = check_subscription(user_id, cache_db)

    if not is_subscribed:
        builder = ReplyKeyboardBuilder()
        builder.row(KeyboardButton(text="Оплатить"))
        await message.answer("Подписка неактивна.", reply_markup=builder.as_markup(resize_keyboard=True))
        return
    

    text_content = ""
    images_list = []

    if message.voice:
        wait_msg = await message.answer("Слушаю...")
        try:
            async with ChatActionSender.typing(bot=bot, chat_id=message.chat.id):
                audio = await voice_message_to_numpy(bot, message.voice.file_id, 16000)
                text_content = vega.transcribe(audio)
            await bot.delete_message(chat_id=message.chat.id, message_id=wait_msg.message_id)
        except Exception:
            await message.answer("Не удалось распознать голос.")
            return
    else:
    
        text_content, images_list = await process_message_content(bot, message, album)


    if not text_content and not images_list:
        return

    await run_default_assistant(message, text_content, user_id, images=images_list)

    
async def main():
    logger.info('StartApp')
    scheduler.start()
    await dp.start_polling(bot)
    
    

