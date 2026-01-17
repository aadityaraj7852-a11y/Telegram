import os
import json
import random
import requests
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

TOKEN = os.getenv("BOT_TOKEN")

# ✅ अपना Google Doc ID
DOC_ID = "1it0nkWpfm6OuOFrG7wQRR7ge9T67ToFb3z_VVEn3uiA"
DATA_URL = f"https://docs.google.com/document/d/{DOC_ID}/export?format=txt"

def fetch_quiz_data():
    r = requests.get(DATA_URL, timeout=15)
    r.raise_for_status()

    text = r.text.strip()

    # कभी-कभी doc में extra spaces/new lines आती हैं
    # इसलिए JSON parse try करेंगे
    data = json.loads(text)

    # validation
    if not isinstance(data, list) or len(data) == 0:
        raise ValueError("Quiz JSON list खाली है")

    return data

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "✅ Rajasthan GK Quiz Bot चालू है!\n\n"
        "Commands:\n"
        "/quiz - Google Doc से 1 Quiz Poll\n"
        "/quiz5 - 5 Quiz Poll\n"
    )

async def send_quiz(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    quiz_list = fetch_quiz_data()
    q = random.choice(quiz_list)

    await context.bot.send_poll(
        chat_id=chat_id,
        question=q["question"],
        options=q["options"],
        type="quiz",
        correct_option_id=int(q["correct_index"]),
        explanation=q.get("explanation", ""),
        is_anonymous=True,
        allows_multiple_answers=False
    )

async def quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_quiz(update.effective_chat.id, context)

async def quiz5(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    for _ in range(5):
        await send_quiz(chat_id, context)

def main():
    if not TOKEN:
        raise ValueError("❌ BOT_TOKEN missing! Render में Environment Variable set करो")

    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("quiz", quiz))
    app.add_handler(CommandHandler("quiz5", quiz5))

    print("✅ Bot Running...")
    app.run_polling()

if __name__ == "__main__":
    main()
