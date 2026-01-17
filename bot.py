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
CHANNEL_ID = os.getenv("CHANNEL_ID")  # Example: @mockrise

DOC_ID = "1it0nkWpfm6OuOFrG7wQRR7ge9T67ToFb3z_VVEn3uiA"
DATA_URL = f"https://docs.google.com/document/d/{DOC_ID}/export?format=txt"

PORT = int(os.getenv("PORT", "10000"))

# ✅ Limits
MAX_SEND = 50

# ✅ Auto Timing (IST)
IST = ZoneInfo("Asia/Kolkata")
AUTO_START_HOUR = 5     # 5 AM
AUTO_END_HOUR = 23      # 11 PM
AUTO_INTERVAL_SECONDS = 1800  # ✅ 30 minutes

# ======================
# ✅ Repeat Control Storage
# ======================
SENT_STATE_FILE = "/tmp/sent_state.json"
sent_indexes = set()
sent_date_str = None


# ======================
# ✅ Flask Server (Render Web Service port fix)
# ======================
app_web = Flask(__name__)

@app_web.get("/")
def home():
    return "✅ Bot is alive"

def run_web():
    app_web.run(host="0.0.0.0", port=PORT)


# ======================
# ✅ Helpers
# ======================
def now_ist():
    return datetime.now(IST)

def in_auto_time_window():
    t = now_ist()
    # allowed 05:00:00 to 22:59:59
    return AUTO_START_HOUR <= t.hour < AUTO_END_HOUR

def load_sent_state():
    global sent_indexes, sent_date_str
    try:
        if os.path.exists(SENT_STATE_FILE):
            with open(SENT_STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            sent_date_str = data.get("date")
            sent_indexes = set(data.get("sent", []))
        else:
            sent_date_str = None
            sent_indexes = set()
    except Exception:
        sent_date_str = None
        sent_indexes = set()

def save_sent_state():
    try:
        data = {
            "date": sent_date_str,
            "sent": sorted(list(sent_indexes)),
        }
        with open(SENT_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except Exception:
        pass

def reset_if_new_day():
    global sent_date_str, sent_indexes
    today = now_ist().strftime("%Y-%m-%d")
    if sent_date_str != today:
        sent_date_str = today
        sent_indexes = set()
        save_sent_state()


# ======================
# ✅ Fetch Quiz Data (BOM fix)
# ======================
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

    # ✅ if no range => all
    if start is None and end is None:
        selected = quiz_list[:MAX_SEND]
        for q in selected:
            if "question" not in q or "options" not in q or "correct_index" not in q:
                continue
            await send_poll(target_chat_id, q, context)
        return

    # ✅ validate range
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


# ======================
# ✅ Commands
# ======================
async def check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        quiz_list = fetch_quiz_data()
        total = len(quiz_list)

        t = now_ist()
        window = "✅ ON (5AM-11PM)" if in_auto_time_window() else "⛔ OFF (Outside timing)"
        channel = CHANNEL_ID if CHANNEL_ID else "❌ Not Set"

        await update.message.reply_text(
            "✅ BOT STATUS OK\n\n"
            f"📌 Total Questions: {total}\n"
            f"⏰ Time (IST): {t.strftime('%d-%m-%Y %I:%M %p')}\n"
            f"🕒 Auto Window: {window}\n"
            f"📢 Channel: {channel}\n\n"
            "✅ Commands:\n"
            "/quiz 1-10\n"
            "/quiz 5\n"
            "/cquiz 1-10 (Channel)\n"
            "/cquiz (Channel)\n"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Check Error:\n{e}")


# /quiz -> अपने chat में
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


# /cquiz -> channel में manual भेजना
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


# ======================
# ✅ AUTO JOB (हर 30 मिनट | 5AM–11PM IST | No Repeat)
# ======================
async def auto_quiz_job(context: ContextTypes.DEFAULT_TYPE):
    if not CHANNEL_ID:
        return

    if not in_auto_time_window():
        return

    try:
        reset_if_new_day()
        quiz_list = fetch_quiz_data()

        available = [i for i in range(len(quiz_list)) if i not in sent_indexes]

        if not available:
            sent_indexes.clear()
            save_sent_state()
            available = list(range(len(quiz_list)))

        idx = random.choice(available)
        sent_indexes.add(idx)
        save_sent_state()

        q = quiz_list[idx]
        await send_poll(CHANNEL_ID, q, context)
        print("✅ Auto quiz sent:", idx + 1)

    except Exception as e:
        print("❌ Auto quiz error:", e)


# ======================
# ✅ Main
# ======================
def main():
    if not TOKEN:
        raise ValueError("❌ BOT_TOKEN missing! Render Environment में set करो")

    load_sent_state()
    reset_if_new_day()

    threading.Thread(target=run_web, daemon=True).start()

    app = Application.builder().token(TOKEN).build()

    # ✅ Commands
    app.add_handler(CommandHandler("check", check))
    app.add_handler(CommandHandler("quiz", quiz))
    app.add_handler(CommandHandler("cquiz", cquiz))

    # ✅ Auto every 30 minutes
    app.job_queue.run_repeating(auto_quiz_job, interval=AUTO_INTERVAL_SECONDS, first=60)

    print("✅ Bot running...")
    app.run_polling()


if __name__ == "__main__":
    main()
