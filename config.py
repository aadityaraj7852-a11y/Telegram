import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")

# 👑 Owners ki setting
OWNER_ID = int(os.getenv("OWNER_ID", "0")) # Pehla / Main Owner
SECOND_OWNER_ID = int(os.getenv("SECOND_OWNER_ID", "0")) # Ek aur naya owner yahan add hoga

_admin_raw = os.getenv("ADMIN_IDS", "")
EXTRA_ADMIN_IDS = [int(x.strip()) for x in _admin_raw.split(",") if x.strip().isdigit()]

# Naye owner ko automatically admin powers dene ke liye
if SECOND_OWNER_ID != 0 and SECOND_OWNER_ID not in EXTRA_ADMIN_IDS:
    EXTRA_ADMIN_IDS.append(SECOND_OWNER_ID)

# ⚙️ Quiz Settings
COIN_PER_CORRECT = int(os.getenv("COIN_PER_CORRECT", "10"))
SPEED_BONUS = int(os.getenv("SPEED_BONUS", "5"))
QUESTION_TIME = int(os.getenv("QUESTION_TIME", "20"))
DEFAULT_QUIZ_LENGTH = 20

# Minimum subjects required before a user can start a solo practice quiz
MIN_SUBJECTS_FOR_SOLO = int(os.getenv("MIN_SUBJECTS_FOR_SOLO", "3"))
