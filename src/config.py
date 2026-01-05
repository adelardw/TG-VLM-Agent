from dotenv import load_dotenv, find_dotenv
import os
import pytz

load_dotenv(find_dotenv('.env'))

API_TOKEN = os.getenv('TG_API_KEY', None)
ADMIN_ID = os.getenv('ADMIN_ID', None)
WHITE_LIST = os.getenv('WHITE_LIST', '').split(',')
TIMEZONE = pytz.timezone(os.getenv('TIMEZONE'))
OPEN_ROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY')
TEXT_IMAGE_MODEL = os.getenv('TEXT_IMAGE_MODEL')
IMAGE_GEN_MODEL = os.getenv('IMAGE_GEN_MODEL')
EMBED_MODEL = os.getenv('EMBED_MODEL')

FIRST_NAME_STEM_RU = os.getenv("FIRST_NAME_STEM_RU")
LAST_NAME_STEM_RU = os.getenv("LAST_NAME_STEM_RU")
PATRONYMIC_STEM_RU = os.getenv("PATRONYMIC_STEM_RU")


FIRST_NAME_STEM_EN = os.getenv("FIRST_NAME_STEM_EN")
LAST_NAME_STEM_EN = os.getenv("LAST_NAME_STEM_EN")
PATRONYMIC_STEM_EN = os.getenv("PATRONYMIC_STEM_EN")

SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/gmail.readonly"
]
CRED_SECRET_PATH = 'client_secret_904283687947-8fb2fnhou4u4ot6shucdk42cncukttho.apps.googleusercontent.com.json'
TOKEN_PATH = 'token.json'

