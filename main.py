import telebot
import json
import time
from flask import Flask
from threading import Thread

# --- अपनी डीटेल्स यहाँ डालें ---
BOT_TOKEN = "7654075050:AAFt3hMFSYcoHPRcrNUfGGVpy859hjKotok"
CHANNEL_ID = "@mockrise"

# -------- 1. KEEP ALIVE SERVER --------
app = Flask('')

@app.route('/')
def home()  :
    return "Bot is alive!"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

# -------- 2. TELEGRAM BOT --------
bot = telebot.TeleBot(BOT_TOKEN)

print("Bot is running with Numbering System...")

@bot.message_handler(content_types=['text'])
def handle_json(message):
    try:
        data = json.loads(message.text)

        if not isinstance(data, list):
            bot.reply_to(message, "❌ Error: JSON लिस्ट [] से शुरू होना चाहिए।")
            return

        bot.reply_to(message, f"⏳ {len(data)} प्रश्न नंबरिंग के साथ प्रोसेस हो रहे हैं...")
        success_count = 0

        for i, item in enumerate(data):
            try:
                question_text = item.get("question", "").strip()
                options = item.get("options", [])
                correct_id = item.get("correct_index")
                original_explanation = item.get("explanation", "").strip()

                q_num = i + 1
                numbered_question = f"Q{q_num}. {question_text}"

                if not question_text or not options or correct_id is None:
                    continue

                if len(numbered_question) > 250:
                    bot.send_message(CHANNEL_ID, numbered_question)
                    poll_question = f"Q{q_num}: ☝️ ऊपर दिए गए प्रश्न का उत्तर चुनें:"
                else:
                    poll_question = numbered_question

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
                        f"📝 Solution {q_num}:\n{original_explanation}",
                        reply_to_message_id=sent_poll.message_id
                    )

                success_count += 1
                time.sleep(3)

            except Exception as e:
                error_msg = str(e)
                bot.reply_to(message, f"⚠️ Q{i+1} में एरर: {error_msg[:100]}")

        bot.reply_to(message, f"✅ काम पूरा! {success_count} प्रश्न भेज दिए गए।")

    except json.JSONDecodeError:
        bot.reply_to(message, "❌ JSON फॉर्मेट गलत है।")
    except Exception as e:
        bot.reply_to(message, f"❌ बड़ी त्रुटि: {e}")

# -------- 3. BOT START --------
keep_alive()
print("Bot is running...")
bot.infinity_polling()
