import os
import json
import requests
import threading
import re
from flask import Flask

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

TOKEN = os.getenv("BOT_TOKEN")

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

    # single number: "5"
    if re.fullmatch(r"\d+", args_text):
        n = int(args_text)
        return n, n

    # range: "1-10"
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


# ✅ /check command
async def check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        quiz_list = fetch_quiz_data()

        total = len(quiz_list)
        first_no = quiz_list[0].get("no", 1)
        last_no = quiz_list[-1].get("no", total)

        await update.message.reply_text(
            "✅ Google Doc OK!\n"
            f"📌 Total Questions: {total}\n"
            f"🔢 First: Q{first_no}\n"
            f"🔢 Last: Q{last_no}\n\n"
            "✅ Use:\n"
            "/quiz 1-10\n"
            "/quiz 5\n"
            "/quiz"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Check Error:\n{e}")


# ✅ /quiz command
async def quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        chat_id = update.effective_chat.id
        quiz_list = fetch_quiz_data()
        total = len(quiz_list)

        # ✅ /quiz (all)
        if not context.args:
            send_list = quiz_list[:MAX_SEND]
            await update.message.reply_text(f"✅ Total Questions: {total}\n✅ भेज रहा हूँ: {len(send_list)}")

            for q in send_list:
                if "question" not in q or "options" not in q or "correct_index" not in q:
                    continue
                await send_poll(chat_id, q, context)
            return

        # ✅ /quiz 1-10 OR /quiz 5
        args_text = " ".join(context.args)
        start, end = parse_range(args_text)

        if start is None:
            await update.message.reply_text(
                "⚠️ सही format:\n"
                "/quiz 1-10\n"
                "/quiz 5\n"
                "/quiz"
            )
            return

        if start < 1 or end < 1:
            await update.message.reply_text("⚠️ नंबर 1 से शुरू होते हैं।")
            return

        if start > end:
            start, end = end, start

        if start > total:
            await update.message.reply_text(f"❌ अभी कुल Questions {total} हैं।")
            return

        if end > total:
            end = total

        selected = quiz_list[start - 1:end]

        if len(selected) > MAX_SEND:
            selected = selected[:MAX_SEND]
            await update.message.reply_text(f"⚠️ एक बार में max {MAX_SEND} भेज सकता हूँ ✅")

        await update.message.reply_text(f"✅ यहां रहे आपके क्वेश्चन: Q{start} से Q{end} तक ({len(selected)})")

        for q in selected:
            if "question" not in q or "options" not in q or "correct_index" not in q:
                continue
            await send_poll(chat_id, q, context)

    except Exception as e:
        await update.message.reply_text(f"❌ Quiz Error:\n{e}")


def main():
    if not TOKEN:
        raise ValueError("❌ BOT_TOKEN missing! Render Environment में set करो")

    threading.Thread(target=run_web, daemon=True).start()

    app = Application.builder().token(TOKEN).build()

    # ✅ Commands
    app.add_handler(CommandHandler("check", check))
    app.add_handler(CommandHandler("quiz", quiz))

    print("✅ Bot running...")
    app.run_polling()


if __name__ == "__main__":
    main()
