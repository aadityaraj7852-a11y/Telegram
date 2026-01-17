import os
import json
import random
import requests
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

TOKEN = os.getenv("BOT_TOKEN")

DOC_ID = "1it0nkWpfm6OuOFrG7wQRR7ge9T67ToFb3z_VVEn3uiA"
DATA_URL = f"https://docs.google.com/document/d/{DOC_ID}/export?format=txt"

def fetch_quiz_data():
    r = requests.get(DATA_URL, timeout=15)
    r.raise_for_status()

    # ✅ BOM FIX
    text = r.content.decode("utf-8-sig").strip()

    data = json.loads(text)

    if not isinstance(data, list) or len(data) == 0:
        raise ValueError("❌ Quiz JSON list खाली है")

    return data

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "✅ Rajasthan GK Quiz Bot चालू है!\n\n"
        "Commands:\n"
        "/quiz - Google Doc से 1 Quiz Poll\n"
        "/quiz5 - 5 Quiz Poll\n"
        "/check - Google Doc JSON test\n"
    )

async def check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        quiz_list = fetch_quiz_data()
        await update.message.reply_text(f"✅ Google Doc OK! कुल Questions: {len(quiz_list)}")
    except Exception as e:
        await update.message.reply_text(f"❌ Google Doc Error:\n{e}")

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
    try:
        await send_quiz(update.effective_chat.id, context)
    except Exception as e:
        await update.message.reply_text(f"❌ Quiz भेजने में दिक्कत:\n{e}")

async def quiz5(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        chat_id = update.effective_chat.id
        for _ in range(5):
            await send_quiz(chat_id, context)
    except Exception as e:
        await update.message.reply_text(f"❌ Quiz5 Error:\n{e}")

def main():
    if not TOKEN:
        raise ValueError("❌ BOT_TOKEN missing! Render Environment में set करो")

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("quiz", quiz))
    app.add_handler(CommandHandler("quiz5", quiz5))
    app.add_handler(CommandHandler("check", check))

    print("✅ Bot Running...")
    app.run_polling()

if __name__ == "__main__":
    main()
