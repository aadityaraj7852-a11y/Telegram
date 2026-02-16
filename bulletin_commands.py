import requests
import re
from datetime import datetime

BULLETIN_URL = "https://dipr.rajasthan.gov.in/pages/sm/government-order/attachments/14928/85/10/2583"

def register_commands(bot):

    @bot.message_handler(commands=['bulletin'])
    def ask_date(message):
        msg = bot.reply_to(message, "📅 Date भेजो (DD-MM-YYYY):")
        bot.register_next_step_handler(msg, send_by_date)

    def send_by_date(message):
        try:
            date_text = message.text.strip()
            date_obj = datetime.strptime(date_text, "%d-%m-%Y")
            date_str = date_obj.strftime("%d-%m-%Y")

            r = requests.get(BULLETIN_URL)
            links = re.findall(r'href="([^"]+\.pdf)"', r.text, re.IGNORECASE)

            for link in links:
                if date_str in link:
                    if link.startswith("/"):
                        link = "https://dipr.rajasthan.gov.in" + link

                    file_data = requests.get(link).content
                    bot.send_document(message.chat.id, file_data, caption=f"📄 Bulletin {date_str}")
                    return

            bot.reply_to(message, "❌ उस तारीख का PDF नहीं मिला")

        except:
            bot.reply_to(message, "❌ Format गलत है. DD-MM-YYYY भेजो")
