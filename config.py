import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))
_admin_raw = os.getenv("ADMIN_IDS", "")
EXTRA_ADMIN_IDS = [int(x.strip()) for x in _admin_raw.split(",") if x.strip().isdigit()]

COIN_PER_CORRECT = int(os.getenv("COIN_PER_CORRECT", "10"))
SPEED_BONUS = int(os.getenv("SPEED_BONUS", "5"))
QUESTION_TIME = int(os.getenv("QUESTION_TIME", "20"))
DEFAULT_QUIZ_LENGTH = 20
