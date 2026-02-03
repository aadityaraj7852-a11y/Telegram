import os
import json
import requests
import threading
import re
from datetime import datetime
from zoneinfo import ZoneInfo
from flask import Flask

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes


# ======================
# ✅ ENV
# ======================
TOKEN = os.getenv("BOT_TOKEN")

CHANNEL_ID = os.getenv("CHANNEL_ID")   # Mockrise
UPSC_ID = "@upsc_hindi_quizz"          # UPSC channel direct


DOC_ID = "1it0nkWpfm6OuOFrG7wQRR7ge9T67ToFb3z_VVEn3uiA"
DATA_URL = f"https://docs.google.com/document/d/{DOC_ID}/export?format=txt"

PORT = int(os.getenv("PORT", "10000"))


# ======================
# ✅ Prompts
# ======================
MOCKRISE_PROMPT = "🔥 Mockrise Daily Quiz\nतैयारी जारी रखो 💪"
UPSC_PROMPT = "🇮🇳 UPSC Hindi Quiz\nआज का सवाल — दिमाग लगाओ 🧠"
PERSONAL_PROMPT = "📘 Practice Quiz"


# ======================
# ✅ Flask keep alive
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
IST = ZoneInfo("Asia/Kolkata")

def now_ist():
    return datetime.now(IST)


def fetch_quiz_data():
    r = requests.get(DATA_URL, timeout=15)
    r.raise_for_status()
    text = r.content.decode("utf-8-sig").strip()
    return json.loads(text)


def parse_range(text):
    text = text.strip()

    if re.fullmatch(r"\d+", text):
        n = int(text)
        return n, n

    m = re.fullmatch(r"(\d+)-(\d+)", text)
    if m:
        return int(m.group(1)), int(m.group(2))

    return None, None


# ======================
# ✅ Send Poll
# ======================
async def send_poll(chat_id, prompt, q, context):
    qno = q.get("no", "")
    prefix = f"Q{qno}. " if qno else ""

    await context.bot.send_message(chat_id, prompt)

    await context.bot.send_poll(
        chat_id=chat_id,
        question=prefix + q["question"],
        options=q["options"],
        type="quiz",
        correct_option_id=int(q["correct_index"]),
        explanation=q.get("explanation", "")
    )


async def send_range(chat_id, prompt, context, start=None, end=None):
    quiz_list = fetch_quiz_data()

    if start is None:
        selected = quiz_list
    else:
        selected = quiz_list[start-1:end]

    for q in selected:
        await send_poll(chat_id, prompt, q, context)


# ======================
# ✅ /check
# ======================
async def check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    total = len(fetch_quiz_data())

    await update.message.reply_text(
        "✅ BOT STATUS OK\n\n"
        f"📌 Total Questions: {total}\n"
        f"⏰ IST Time: {now_ist().strftime('%I:%M %p')}\n\n"
        "Commands:\n"
        "/quiz → personal\n"
        "/mockrise → channel\n"
        "/upsc → upsc channel"
    )


# ======================
# ✅ Personal Quiz
# ======================
async def quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    if not context.args:
        await send_range(chat_id, PERSONAL_PROMPT, context)
        return

    start, end = parse_range(" ".join(context.args))
    await send_range(chat_id, PERSONAL_PROMPT, context, start, end)


# ======================
# ✅ Mockrise Channel Only
# ======================
async def mockrise(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not CHANNEL_ID:
        await update.message.reply_text("❌ CHANNEL_ID set नहीं है")
        return

    if not context.args:
        await send_range(CHANNEL_ID, MOCKRISE_PROMPT, context)
        return

    start, end = parse_range(" ".join(context.args))
    await send_range(CHANNEL_ID, MOCKRISE_PROMPT, context, start, end)


# ======================
# ✅ UPSC Channel Only
# ======================
async def upsc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not UPSC_ID:
        await update.message.reply_text("❌ UPSC channel missing")
        return

    if not context.args:
        await send_range(UPSC_ID, UPSC_PROMPT, context)
        return

    start, end = parse_range(" ".join(context.args))
    await send_range(UPSC_ID, UPSC_PROMPT, context, start, end)


# ======================
# ✅ Main
# ======================
def main():
    threading.Thread(target=run_web, daemon=True).start()

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("check", check))
    app.add_handler(CommandHandler("quiz", quiz))
    app.add_handler(CommandHandler("mockrise", mockrise))
    app.add_handler(CommandHandler("upsc", upsc))

    print("✅ Manual Bot Running (No Auto Mode)")
    app.run_polling()


if __name__ == "__main__":
    main()
