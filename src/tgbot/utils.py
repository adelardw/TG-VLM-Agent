import redis
from datetime import datetime,timedelta
from beautylogger import logger
from config import TIMEZONE,ADMIN_ID, WHITE_LIST

TELEGRAM_MAX_MESSAGE_LENGTH = 4096
TELEGRAM_MAX_MESSAGE_CAPTION = 1024

def split_short_long_message(text: str, max_length_caption: int = TELEGRAM_MAX_MESSAGE_CAPTION,
                             second_part_percent_value_threshold: int = 0.3):
    '''
    second_part_percent_value_threshold - размер второй части сплита от max_length_caption
    если вторая часть больше second_part_percent_value_threshold*second_part_percent_value_threshold, то
    есть смысл разбивать пост и прикладывать картинку
    иначе - нет, картинка в кэшэ
    '''

    if len(text) <= max_length_caption:
        return text, None
    elif len(text) >= (1 + second_part_percent_value_threshold)*max_length_caption:
        short_part_part = text[: max_length_caption]
        pos_space_num = short_part_part.rfind(' ')
        if pos_space_num != -1:
            short_part = text[:pos_space_num]
            long_part = text[pos_space_num:]
            return short_part, long_part
        else:
            return None
    else:

        return None

def split_long_message(text: str, max_length: int = TELEGRAM_MAX_MESSAGE_LENGTH) -> list[str]:
    """
    "Умно" разбивает длинное сообщение на несколько частей, не разрывая слова.
    Возвращает список сообщений (частей).
    """
    if len(text) <= max_length:
        return [text]

    chunks = []
    current_chunk = ""
    words = text.split(' ')

    for word in words:
        if len(current_chunk) + len(word) + 1 > max_length:
            chunks.append(current_chunk.strip())
            current_chunk = ""

        current_chunk += word + " "

    if current_chunk:
        chunks.append(current_chunk.strip().replace("*"," "))

    return chunks


def find_cache(id_user: str, cache: redis.StrictRedis):
    if cache.get(id_user):
        return True
    else:
        False



def check_subscription(user_id: int, cache: redis.StrictRedis) -> tuple[bool, datetime | None]:
    """
    Проверяет активную подписку пользователя.
    Возвращает кортеж: (статус_подписки, дата_окончания | None).
    """
    if str(user_id) not in WHITE_LIST:
        sub_end_date_str = cache.get(f"sub_end_date_{user_id}")
        if sub_end_date_str:
            sub_end_date_str = sub_end_date_str.decode()
            sub_end_date = datetime.fromisoformat(sub_end_date_str)
            if datetime.now(TIMEZONE) < sub_end_date:
                return True, sub_end_date 
            else:
                return False, sub_end_date
        return False, None 
    else:
        sub_end_date_admin = datetime(9999,12,31,23,59)
        return True, sub_end_date_admin

def grant_trial_subscription(user_id: int, cache: redis.StrictRedis):
    """
    Выдает пользователю пробную подписку на 1 день.
    """
    end_date = datetime.now(TIMEZONE) + timedelta(days=1)
    cache.set(f"sub_end_date_{user_id}", end_date.isoformat())
    logger.info(f"Пользователю {user_id} выдана пробная подписка до {end_date.isoformat()}")

def grant_30days_subscription(user_id: int, cache: redis.StrictRedis):
    """
    Выдает пользователю пробную подписку на 1 день.
    """
    end_date = datetime.now(TIMEZONE) + timedelta(days=30)
    cache.set(f"sub_end_date_{user_id}", end_date.isoformat())
    logger.info(f"Пользователю {user_id} выдана пробная подписка до {end_date.isoformat()}")