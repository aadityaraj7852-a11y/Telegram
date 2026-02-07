import telebot
import json
import time
import os  # पोर्ट के लिए जरूरी
from flask import Flask
from threading import Thread

# --- अपनी डीटेल्स यहाँ डालें ---
BOT_TOKEN = "7654075050:AAFt3hMFSYcoHPRcrNUfGGVpy859hjKotok"
CHANNEL_ID = "@mockrise"

# -------- 1. KEEP ALIVE SERVER (Fixed for Render) --------
app = Flask('')

@app.route('/')
def home():
    return "Bot is alive and running!"

def run():
    # Render हमेशा PORT एन्वायरमेंट वेरिएबल का इस्तेमाल करता है, डिफ़ॉल्ट 10000
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run)
    t.daemon = True # इसे daemon बनाने से मेन प्रोग्राम के साथ बंद होगा
    t.start()

# -------- 2. TELEGRAM BOT --------
bot = telebot.TeleBot(BOT_TOKEN)

@bot.message_handler(content_types=['text'])
def handle_json(message):
    try:
        data = json.loads(message.text)
        if not isinstance(data, list):
            bot.reply_to(message, "❌ Error: JSON लिस्ट [] से शुरू होना चाहिए।")
            return

        bot.reply_to(message, "🤖 Bot ready hai quiz ke liye...\n⏳ Quiz start ho raha hai...")
        success_count = 0

        for i, item in enumerate(data):
            try:
                question_text = item.get("question", "").strip()
                options = item.get("options", [])
                correct_id = item.get("correct_index")
                original_explanation = item.get("explanation", "").strip()

                if not question_text or not options or correct_id is None:
                    continue

                poll_question = question_text
                
                # एक्सप्लेनेशन की लिमिट 200 कैरेक्टर होती है
                if len(original_explanation) > 190:
                    poll_explanation = "विस्तृत व्याख्या नीचे देखें 👇"
                    send_full_explanation = True
                else:
                    poll_explanation = original_explanation
                    send_full_explanation = False

                sent_poll = bot.send_poll(
                    chat_id=CHANNEL_ID,
                    question=poll_question,
                    options=options,
                    type='quiz',
                    correct_option_id=correct_id,
                    explanation=poll_explanation,
                    is_anonymous=True
                )

                if send_full_explanation:
                    bot.send_message(
                        CHANNEL_ID,
                        f"📝 Solution:\n{original_explanation}",
                        reply_to_message_id=sent_poll.message_id
                    )

                success_count += 1
                time.sleep(3) # रेट लिमिट से बचने के लिए

            except Exception as e:
                bot.reply_to(message, f"⚠️ Question {i+1} में एरर: {str(e)[:100]}")

        bot.reply_to(message, f"✅ काम पूरा! {success_count} प्रश्न भेज दिए गए।")

    except json.JSONDecodeError:
        bot.reply_to(message, "❌ JSON फॉर्मेट गलत है।")
    except Exception as e:
        bot.reply_to(message, f"❌ बड़ी त्रुटि: {e}")

# -------- 3. BOT START --------
if __name__ == "__main__":
    keep_alive() # पहले वेब सर्वर शुरू करें
    print("Bot is starting...")
    bot.infinity_polling(timeout=20, long_polling_timeout=10)
