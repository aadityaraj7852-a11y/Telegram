import os
import json
import requests
import threading
import re
from flask import Flask

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")  # Example: @mockrise

DOC_ID = "1it0nkWpfm6OuOFrG7wQRR7ge9T67ToFb3z_VVEn3uiA"
DATA_URL = f"https://docs.google.com/document/d/{DOC_ID}/export?format=txt"

PORT = int(os.getenv("PORT", "10000"))
MAX_SEND = 50

# ✅ Flask server (Render port fix)
app_web = Flask(__name__)

@app_web.get("/")
def home():
    return "✅ Bot is alive"

def run_web():
    app_web.run(host="0.0.0.0", port=PORT)

def fetch_quiz_data():
    r = requests.get(DATA_URL, timeout=15)
    r.raise_for_status()

    # ✅ BOM FIX
    text = r.content.decode("utf-8-sig").strip()
    data = json.loads(text)

    if not isinstance(data, list) or len(data) == 0:
        raise ValueError("❌ Google Doc JSON खाली है")

    return data

def parse_range(args_text: str):
    args_text = args_text.strip()

    # "5"
    if re.fullmatch(r"\d+", args_text):
        n = int(args_text)
        return n, n

    # "1-10"
    m = re.fullmatch(r"(\d+)\s*-\s*(\d+)", args_text)
    if m:
        return int(m.group(1)), int(m.group(2))

    return None, None

async def send_poll(chat_id, q, context: ContextTypes.DEFAULT_TYPE):
    qno = q.get("no", "")
    prefix = f"Q{qno}. " if qno != "" else ""

    await context.bot.send_poll(
        chat_id=chat_id,
        question=prefix + q["question"],
        options=q["options"],
        type="quiz",
        correct_option_id=int(q["correct_index"]),
        explanation=q.get("explanation", ""),
        is_anonymous=True,
        allows_multiple_answers=False
    )

async def send_quiz_range(target_chat_id, context, start=None, end=None):
    quiz_list = fetch_quiz_data()
    total = len(quiz_list)

    # ✅ If no range => all
    if start is None and end is None:
        selected = quiz_list[:MAX_SEND]
        for q in selected:
            if "question" not in q or "options" not in q or "correct_index" not in q:
                continue
            await send_poll(target_chat_id, q, context)
        return

    # ✅ Range valid
    if start < 1 or end < 1:
        raise ValueError("नंबर 1 से शुरू होते हैं।")

    if start > end:
        start, end = end, start

    if start > total:
        raise ValueError(f"कुल Questions {total} हैं, लेकिन start {start} दिया है।")

    if end > total:
        end = total

    selected = quiz_list[start - 1:end]

    if len(selected) > MAX_SEND:
        selected = selected[:MAX_SEND]

    for q in selected:
        if "question" not in q or "options" not in q or "correct_index" not in q:
            continue
        await send_poll(target_chat_id, q, context)

# ✅ Normal: /quiz (अपने chat में)
async def quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        chat_id = update.effective_chat.id

        if not context.args:
            await update.message.reply_text("✅ आपके chat में Quiz भेज रहा हूँ...")
            await send_quiz_range(chat_id, context)
            return

        args_text = " ".join(context.args)
        start, end = parse_range(args_text)
        if start is None:
            await update.message.reply_text("⚠️ सही format:\n/quiz\n/quiz 1-10\n/quiz 5")
            return

        await update.message.reply_text(f"✅ आपके chat में Q{start}-Q{end} भेज रहा हूँ...")
        await send_quiz_range(chat_id, context, start, end)

    except Exception as e:
        await update.message.reply_text(f"❌ Error:\n{e}")

# ✅ Channel: /cquiz (channel में भेजेगा)
async def cquiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not CHANNEL_ID:
            await update.message.reply_text("❌ Render में CHANNEL_ID set नहीं है।")
            return

        if not context.args:
            await update.message.reply_text("✅ Channel में Quiz भेज रहा हूँ...")
            await send_quiz_range(CHANNEL_ID, context)
            return

        args_text = " ".join(context.args)
        start, end = parse_range(args_text)
        if start is None:
            await update.message.reply_text("⚠️ सही format:\n/cquiz\n/cquiz 1-10\n/cquiz 5")
            return

        await update.message.reply_text(f"✅ Channel में Q{start}-Q{end} भेज रहा हूँ...")
        await send_quiz_range(CHANNEL_ID, context, start, end)

    except Exception as e:
        await update.message.reply_text(f"❌ Channel Error:\n{e}")

def main():
    if not TOKEN:
        raise ValueError("❌ BOT_TOKEN missing! Render Environment में set करो")

    threading.Thread(target=run_web, daemon=True).start()

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("quiz", quiz))
    app.add_handler(CommandHandler("cquiz", cquiz))

    print("✅ Bot running...")
    app.run_polling()

if __name__ == "__main__":
    main()
