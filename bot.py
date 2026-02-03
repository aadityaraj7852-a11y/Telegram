import os
import json
import requests
import threading
import re
import random
from datetime import datetime
from zoneinfo import ZoneInfo
from flask import Flask

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes


# ======================
# ✅ ENV
# ======================
TOKEN = os.getenv("BOT_TOKEN")

# 👇 MOCKRISE channel (old)
CHANNEL_ID = os.getenv("CHANNEL_ID")  # @mockrise

# 👇 UPSC channel (NEW)
UPPSC_GROUP_ID = "@upsc_hindi_quizz"   # ✅ direct set (no env needed)

DOC_ID = "1it0nkWpfm6OuOFrG7wQRR7ge9T67ToFb3z_VVEn3uiA"
DATA_URL = f"https://docs.google.com/document/d/{DOC_ID}/export?format=txt"

PORT = int(os.getenv("PORT", "10000"))


# ======================
# ✅ Custom Prompts
# ======================
MOCKRISE_PROMPT = "🔥 Mockrise Daily Quiz\nतैयारी जारी रखो 💪"
UPSC_PROMPT = "🇮🇳 UPSC Hindi Quiz\nआज का सवाल — दिमाग लगाओ 🧠"


# ======================
# ✅ Limits
# ======================
MAX_SEND = 50


# ======================
# ✅ Timing
# ======================
IST = ZoneInfo("Asia/Kolkata")
AUTO_START_HOUR = 5
AUTO_END_HOUR = 23
AUTO_INTERVAL_SECONDS = 1800


# ======================
# ✅ Repeat Control
# ======================
SENT_STATE_FILE = "/tmp/sent_state.json"
sent_indexes = set()
sent_date_str = None


# ======================
# ✅ Flask
# ======================
app_web = Flask(__name__)

@app_web.get("/")
def home():
    return "Bot Running"

def run_web():
    app_web.run(host="0.0.0.0", port=PORT)


# ======================
# ✅ Helpers
# ======================
def now_ist():
    return datetime.now(IST)


def in_auto_time_window():
    t = now_ist()
    return AUTO_START_HOUR <= t.hour < AUTO_END_HOUR


def get_targets():
    targets = []

    if CHANNEL_ID:
        targets.append((CHANNEL_ID, MOCKRISE_PROMPT))

    if UPPSC_GROUP_ID:
        targets.append((UPPSC_GROUP_ID, UPSC_PROMPT))

    return targets


# ======================
# ✅ Fetch Quiz
# ======================
def fetch_quiz_data():
    r = requests.get(DATA_URL, timeout=15)
    r.raise_for_status()
    text = r.content.decode("utf-8-sig").strip()
    return json.loads(text)


def parse_range(args_text):
    if re.fullmatch(r"\d+", args_text):
        n = int(args_text)
        return n, n

    m = re.fullmatch(r"(\d+)-(\d+)", args_text)
    if m:
        return int(m.group(1)), int(m.group(2))

    return None, None


# ======================
# ✅ Send Poll
# ======================
async def send_poll(chat_id, prompt, q, context):
    qno = q.get("no", "")
    prefix = f"Q{qno}. " if qno else ""

    # 👇 custom intro message
    await context.bot.send_message(chat_id, prompt)

    await context.bot.send_poll(
        chat_id=chat_id,
        question=prefix + q["question"],
        options=q["options"],
        type="quiz",
        correct_option_id=int(q["correct_index"]),
        explanation=q.get("explanation", "")
    )


async def send_to_all_targets(q, context):
    for chat_id, prompt in get_targets():
        await send_poll(chat_id, prompt, q, context)


# ======================
# ✅ Range Sender
# ======================
async def send_quiz_range(target_chat_id, context, start=None, end=None):
    quiz_list = fetch_quiz_data()

    if start is None:
        selected = quiz_list[:MAX_SEND]
    else:
        selected = quiz_list[start-1:end]

    for q in selected:
        await send_poll(target_chat_id, "📘 Practice Quiz", q, context)


# ======================
# ✅ Commands
# ======================
async def quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    if not context.args:
        await send_quiz_range(chat_id, context)
        return

    start, end = parse_range(" ".join(context.args))
    await send_quiz_range(chat_id, context, start, end)


# 👇 Channel + UPSC
async def cquiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    quiz_list = fetch_quiz_data()

    if not context.args:
        selected = quiz_list[:MAX_SEND]
    else:
        start, end = parse_range(" ".join(context.args))
        selected = quiz_list[start-1:end]

    for q in selected:
        await send_to_all_targets(q, context)


# ======================
# ✅ AUTO JOB
# ======================
async def auto_quiz_job(context: ContextTypes.DEFAULT_TYPE):
    if not in_auto_time_window():
        return

    quiz_list = fetch_quiz_data()
    q = random.choice(quiz_list)

    await send_to_all_targets(q, context)

    print("Auto sent")


# ======================
# ✅ Main
# ======================
def main():
    threading.Thread(target=run_web, daemon=True).start()

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("quiz", quiz))
    app.add_handler(CommandHandler("cquiz", cquiz))

    app.job_queue.run_repeating(auto_quiz_job, interval=AUTO_INTERVAL_SECONDS, first=60)

    app.run_polling()


if __name__ == "__main__":
    main()
