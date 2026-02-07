import telebot
import json
import time
import os
import requests
import re
from flask import Flask
from threading import Thread

# --- अपनी डीटेल्स ---
BOT_TOKEN = "7654075050:AAFt3hMFSYcoHPRcrNUfGGVpy859hjKotok"
CHANNEL_ID = "@mockrise"

# -------- KEEP ALIVE SERVER --------
app = Flask('')

@app.route('/')
def home():
    return "Bot is alive and running!"

def run():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run)
    t.daemon = True
    t.start()

# -------- TELEGRAM BOT --------
bot = telebot.TeleBot(BOT_TOKEN)

waiting_for_link = {}

# --- START COMMAND ---
@bot.message_handler(commands=['start'])
def start(message):
    waiting_for_link[message.chat.id] = True
    bot.reply_to(message, "Website link भेजिए जिसमें MCQ JSON हो।")

# --- FUNCTION: BLOGGER PAGE से rawData निकालना ---
def extract_json_from_blog(url):
    r = requests.get(url, timeout=20)
    html = r.text

    # rawData = [ ... ];
    match = re.search(r'let\s+rawData\s*=\s*(\[[\s\S]*?\]);', html)

    if not match:
        return None

    json_text = match.group(1)
    data = json.loads(json_text)
    return data

# --- HANDLE MESSAGES ---
@bot.message_handler(content_types=['text'])
def handle_message(message):
    chat_id = message.chat.id
    text = message.text.strip()

    if waiting_for_link.get(chat_id):

        try:
            bot.reply_to(message, "JSON पढ़ रहा हूँ...")

            data = extract_json_from_blog(text)

            if not data:
                bot.reply_to(message, "JSON नहीं मिला। Post format check करो।")
                return

            total_questions = len(data)
            bot.reply_to(message, f"कुल {total_questions} MCQ मिले। चैनल में भेज रहा हूँ...")

            success_count = 0

            for item in data:
                try:
                    question_text = item.get("question", "").strip()
                    options = item.get("option", [])
                    answer_letter = item.get("answer", "").upper()
                    explanation = item.get("solution", "").strip()

                    # ABCD → index
                    correct_id = "ABCD".find(answer_letter)

                    if not question_text or not options or correct_id == -1:
                        continue

                    sent_poll = bot.send_poll(
                        chat_id=CHANNEL_ID,
                        question=question_text,
                        options=options,
                        type='quiz',
                        correct_option_id=correct_id,
                        explanation=explanation[:190] if explanation else "",
                        is_anonymous=True
                    )

                    if explanation and len(explanation) > 190:
                        bot.send_message(
                            CHANNEL_ID,
                            f"Solution:\n{explanation}",
                            reply_to_message_id=sent_poll.message_id
                        )

                    success_count += 1
                    time.sleep(3)

                except Exception as e:
                    print(e)

            bot.send_message(chat_id, f"Done! {success_count} प्रश्न भेज दिए गए।")
            waiting_for_link[chat_id] = False

        except Exception as e:
            bot.reply_to(message, f"Error: {e}")

    else:
        bot.reply_to(message, "पहले /start दबाएँ।")

# -------- START BOT --------
if __name__ == "__main__":
    keep_alive()
    print("Bot is starting...")
    bot.infinity_polling(timeout=20, long_polling_timeout=10)
