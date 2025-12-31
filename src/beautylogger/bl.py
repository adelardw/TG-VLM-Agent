from loguru import logger
import colorama
import sys

colorama.init()

logger.remove()

logger.add(
    sys.stdout,
    format="<green>{time:HH:mm:ss}</green> | <level>{level.icon} {level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    level="DEBUG",
    colorize=True,
    enqueue=True,
    backtrace=True,
    diagnose=True,
)

logger.add(
    "logs/debug.log", 
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}", # Формат без цветов
    level="DEBUG",   
    rotation="10 MB", 
    retention="7 days", 
    compression="zip", 
    enqueue=True,
    encoding="utf-8"  
)


logger.level("INFO", color="<bold><green>")
logger.level("CRITICAL", color="<bold><red>")
logger.level("DEBUG", color="<bold><yellow>")

logger.level("CRITICAL", icon="⛔")
logger.level("DEBUG", icon="⚠️") 
logger.level("INFO", icon="ℹ️")