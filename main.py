import telebot
import json
import time
import os
import threading
import requests
import re
from flask import Flask
from datetime import datetime, timedelta
from weasyprint import HTML
from jinja2 import Template

# ==========================================
# ⚙️ CONFIGURATION
# ==========================================

BOT_TOKEN = "7654075050:AAFt3hMFSYcoHPRcrNUfGGVpy859hjKotok"
MAIN_CHANNEL_ID = "@mockrise"

CHANNELS = {
    'mockrise': {'id': '@mockrise', 'name': 'MockRise Main'},
    'upsc': {'id': '@upsc_ssc_cgl_mts_cgl_chsl_gk', 'name': 'UPSC/IAS'},
    'ssc': {'id': '@ssc_cgl_chsl_mts_ntpc_upsc', 'name': 'SSC CGL/MTS'},
    'rssb': {'id': '@ldc_reet_ras_2ndgrade_kalam', 'name': 'RSSB/LDC/REET'},
    'springboard': {'id': '@rssb_gk_rpsc_springboar', 'name': 'Springboard'},
    'kalam': {'id': '@rajasthan_gk_kalam_reet_ldc_ras', 'name': 'Kalam Academy'}
}

DB_STATS = "user_stats.json"
DB_HISTORY = "history.json"
FONT_FILE = "NotoSansDevanagari-Regular.ttf"

quiz_buffer = {}
json_fragments = {}

bot = telebot.TeleBot(BOT_TOKEN)

# ==========================================
# 🌐 FLASK SERVER (Keep Alive)
# ==========================================

app = Flask('')

@app.route('/')
def home():
    return "✅ Bot is Running (Large JSON Support Added)!"

def run_server():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = threading.Thread(target=run_server)
    t.daemon = True
    t.start()

# ==========================================
# 📂 DATA HANDLING
# ==========================================

def load_json(filename):
    if not os.path.exists(filename): return [] if filename == DB_HISTORY else {}
    try:
        with open(filename, 'r', encoding='utf-8') as f: return json.load(f)
    except: return [] if filename == DB_HISTORY else {}

def save_json(filename, data):
    try:
        with open(filename, 'w', encoding='utf-8') as f: json.dump(data, f, indent=4, ensure_ascii=False)
    except: pass

def add_to_history(questions, channel_key):
    history = load_json(DB_HISTORY)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for q in questions:
        history.append({'timestamp': timestamp, 'channel': channel_key, 'data': q})
    cutoff = datetime.now() - timedelta(days=60)
    history = [h for h in history if datetime.strptime(h['timestamp'], "%Y-%m-%d %H:%M:%S") > cutoff]
    save_json(DB_HISTORY, history)

def update_stats(user_id, channel, count, status):
    stats = load_json(DB_STATS)
    uid = str(user_id)
    if uid not in stats: stats[uid] = {'total_sent': 0, 'total_failed': 0, 'channels': [], 'history': []}
    if status == 'success': stats[uid]['total_sent'] += count
    else: stats[uid]['total_failed'] += count
    if channel not in stats[uid]['channels']: stats[uid]['channels'].append(channel)
    save_json(DB_STATS, stats)

# ==========================================
# 📄 PDF ENGINE
# ==========================================

def check_font():
    if not os.path.exists(FONT_FILE):
        url = "https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSansDevanagari/NotoSansDevanagari-Regular.ttf"
        try:
            r = requests.get(url)
            with open(FONT_FILE, 'wb') as f: f.write(r.content)
        except: pass
    return os.path.abspath(FONT_FILE)

def generate_pdf_html(data_list, filename, title_text, date_range_text):
    font_path = check_font()

    html_template = """<html><body>PDF</body></html>"""
    template = Template(html_template)

    rendered_html = template.render(
        title=title_text,
        date_range=date_range_text,
        total=len(data_list),
        items=data_list,
        font_path=font_path
    )

    try:
        HTML(string=rendered_html, base_url=".").write_pdf(filename)
        return filename
    except: 
        return None

# ==========================================
# 🎮 COMMANDS
# ==========================================

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    bot.reply_to(message, "Bot Running ✅")

# ==========================================
# 🧩 JSON HANDLER (shortened)
# ==========================================

@bot.message_handler(content_types=['text'])
def handle_json(m):
    bot.reply_to(m, "Message received.")

# ==========================================
# 📰 BULLETIN FEATURE (NEW)
# ==========================================

BULLETIN_URL = "https://dipr.rajasthan.gov.in/pages/sm/government-order/attachments/14928/85/10/2583"
LAST_PDF_FILE = "last_bulletin.txt"

def get_latest_bulletin():
    try:
        r = requests.get(BULLETIN_URL, timeout=20)
        links = re.findall(r'href="([^"]+\.pdf)"', r.text, re.IGNORECASE)
        if not links:
            return None
        latest = links[0]
        if latest.startswith("/"):
            latest = "https://dipr.rajasthan.gov.in" + latest
        return latest
    except Exception as e:
        print("Bulletin error:", e)
        return None

def load_last_pdf():
    if os.path.exists(LAST_PDF_FILE):
        with open(LAST_PDF_FILE, "r") as f:
            return f.read().strip()
    return ""

def save_last_pdf(link):
    with open(LAST_PDF_FILE, "w") as f:
        f.write(link)

def bulletin_watcher():
    while True:
        try:
            latest = get_latest_bulletin()
            last_saved = load_last_pdf()

            if latest and latest != last_saved:
                file_data = requests.get(latest).content
                bot.send_document(MAIN_CHANNEL_ID, file_data, caption="📰 New e-Bulletin")
                save_last_pdf(latest)

        except Exception as e:
            print("Watcher error:", e)

        time.sleep(600)

@bot.message_handler(commands=['bulletin'])
def ask_bulletin_date(message):
    msg = bot.reply_to(message, "📅 Date भेजो (DD-MM-YYYY):")
    bot.register_next_step_handler(msg, send_bulletin_by_date)

def send_bulletin_by_date(message):
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

# ==========================================
# 🚀 START
# ==========================================

if __name__ == "__main__":
    keep_alive()

    t = threading.Thread(target=bulletin_watcher)
    t.daemon = True
    t.start()

    bot.infinity_polling()
