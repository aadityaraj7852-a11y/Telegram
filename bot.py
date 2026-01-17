import os
import json
import random
import requests
import threading
from flask import Flask

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# ======================
# ENV
# ======================
TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")  # Example: @mockrise

DOC_ID = "1it0nkWpfm6OuOFrG7wQRR7ge9T67ToFb3z_VVEn3uiA"
DATA_URL = f"https://docs.google.com/document/d/{DOC_ID}/export?format=txt"

PORT = int(os.getenv("PORT", "10000"))

# ======================
# Flask Server (Render port open)
# ======================
app_web = Flask(__name__)

@app_web.get("/")
def home():
    return "✅ Bot is alive"

def run_web():
    app_web.run(host="0.0.0.0", port=PORT)

# ======================
# Google Doc JSON (BOM Fix)
# ======================
def fetch_quiz_data():
    r = requests.get(DATA_URL, timeout=15)
    r.raise_for_status()

    # ✅ BOM FIX
    text = r.content.decode("utf-8-sig").strip()
    data = json.loads(text)

    if not isinstance(data, list) or len(data) == 0:
        raise ValueError("❌ Quiz JSON list खाली है")

    return data

async def send_quiz_to(chat_id, context: ContextTypes.DEFAULT_TYPE):
    quiz_list = fetch_quiz_data()
    q = random.choice(quiz_list)

    await context.bot.send_poll(
        chat_id=chat_id,
        question=q["question"],
        options=q["options"],
        type="quiz",
        correct_option_id=int(q["correct_index"]),
        explanation=q.get("explanation", ""),
        is_anonymous=True
    )

# ======================
# Auto job: हर 20 मिनट
# ======================
async def auto_quiz_job(context: ContextTypes.DEFAULT_TYPE):
    if not CHANNEL_ID:
        return
    try:
        await send_quiz_to(CHANNEL_ID, context)
        print("✅ Auto quiz sent to channel")
    except Exception as e:
        print("❌ Auto quiz error:", e)

# ======================
# Commands
# ======================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "✅ Bot चालू है!\n\n"
        "Commands:\n"
        "/quiz - 1 Quiz Poll\n"
        "/quiz5 - 5 Quiz Poll\n"
        "/check - Doc test\n\n"
        "✅ Auto: हर 20 मिनट में channel पर quiz (अगर CHANNEL_ID सेट है)"
    )

async def check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        quiz_list = fetch_quiz_data()
        await update.message.reply_text(f"✅ Google Doc OK! कुल Questions: {len(quiz_list)}")
    except Exception as e:
        await update.message.reply_text(f"❌ Google Doc Error:\n{e}")

async def quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await send_quiz_to(update.effective_chat.id, context)
    except Exception as e:
        await update.message.reply_text(f"❌ Quiz Error:\n{e}")

async def quiz5(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        for _ in range(5):
            await send_quiz_to(update.effective_chat.id, context)
    except Exception as e:
        await update.message.reply_text(f"❌ Quiz5 Error:\n{e}")

# ======================
# Main
# ======================
def main():
    if not TOKEN:
        raise ValueError("❌ BOT_TOKEN missing!")

    # ✅ Render के लिए Web server start
    threading.Thread(target=run_web, daemon=True).start()

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("check", check))
    app.add_handler(CommandHandler("quiz", quiz))
    app.add_handler(CommandHandler("quiz5", quiz5))

    # ✅ हर 20 मिनट
    app.job_queue.run_repeating(auto_quiz_job, interval=1200, first=30)

    print("✅ Bot running...")
    app.run_polling()

if __name__ == "__main__":
    main()
