from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.redis import RedisJobStore
from src.beautylogger import logger
job_stores = {
    'default': RedisJobStore(
        jobs_key='tg_bot:jobs', 
        run_times_key='tg_bot:run_times', 
        host='localhost', 
        port=6379, 
        db=7 
    )
}

scheduler = AsyncIOScheduler(jobstores=job_stores, timezone="Europe/Moscow")

async def send_telegram_notification(
    user_id: int, 
    summary: str, 
    description: str,
    start_str: str,     
    end_str: str,       
    location: str       
):
    from src.tgbot.bot import bot 

    try:
        text = (
            f"🔔 <b>Напоминание: {summary}</b>\n\n"
            f"🕒 Время: {start_str} - {end_str}\n"
            f"📍 Место: {location}\n"
            f"📝 {description}"
        )
        
        await bot.send_message(chat_id=user_id, text=text, parse_mode="HTML")
        logger.info(f"✅ [SCHEDULER] Уведомление отправлено юзеру {user_id}")
        
    except Exception as e:
        logger.error(f"🔥 [SCHEDULER ERROR] Ошибка отправки: {e}", exc_info=True)