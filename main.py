import telebot
import json
import time
import os
import threading
import requests
from flask import Flask
from datetime import datetime, timedelta
from weasyprint import HTML
from jinja2 import Template

# ==========================================
# ⚙️ CONFIGURATION
# ==========================================

BOT_TOKEN = "7654075050:AAFt3hMFSYcoHPRcrNUfGGVpy859hjKotok"
MAIN_CHANNEL_ID = "@mockrise"

# ✅ Channels List
CHANNELS = {
    'mockrise': {'id': '@mockrise', 'name': 'MockRise Main'},
    'upsc': {'id': '@upsc_ssc_cgl_mts_cgl_chsl_gk', 'name': 'UPSC/IAS'},
    'ssc': {'id': '@ssc_cgl_chsl_mts_ntpc_upsc', 'name': 'SSC CGL/MTS'},
    'rssb': {'id': '@ldc_reet_ras_2ndgrade_kalam', 'name': 'RSSB/LDC/REET'},
    'springboard': {'id': '@rssb_gk_rpsc_springboar', 'name': 'Springboard'},
    'kalam': {'id': '@rajasthan_gk_kalam_reet_ldc_ras', 'name': 'Kalam Academy'}
}

# Files
DB_STATS = "user_stats.json"
DB_HISTORY = "history.json"
FONT_FILE = "NotoSansDevanagari-Regular.ttf"

# Memory
quiz_buffer = {}

bot = telebot.TeleBot(BOT_TOKEN)

# ==========================================
# 🌐 FLASK SERVER (Keep Alive)
# ==========================================

app = Flask('')

@app.route('/')
def home():
    return "✅ Bot is Running (Bulk PDF + Website Branding)!"

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
        with open(filename, 'r', encoding='utf-8') as f:
            return json.load(f)
    except: return [] if filename == DB_HISTORY else {}

def save_json(filename, data):
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
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
# 📄 PDF ENGINE (Updated Branding)
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
    
    html_template = """
    <!DOCTYPE html>
    <html lang="hi">
    <head>
    <meta charset="UTF-8">
    <style>
        @font-face { font-family: 'Noto Sans Devanagari'; src: url('file://{{ font_path }}'); }
        @page {
            size: A4; margin: 20mm 15mm;
            @bottom-center {
                content: "Page " counter(page);
                font-family: 'Noto Sans Devanagari', sans-serif;
                font-size: 10pt;
                border-top: 1px solid #444; width: 90%; padding-top: 10px; margin-bottom: 10px;
            }
        }
        body { font-family: "Noto Sans Devanagari", sans-serif; font-size: 11pt; color: #222; margin: 0; }
        .header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 5px; }
        .logo img { width: 70px; height: auto; margin-right: 15px; }
        .title { text-align: center; flex-grow: 1; }
        .title h1 { margin: 0; font-size: 18pt; color: #000; text-transform: uppercase; }
        .title p { margin: 3px 0; font-size: 10pt; color: #555; }
        .meta { display: flex; justify-content: space-between; font-weight: bold; font-size: 10pt; margin-top: 15px; color: #333; }
        .top-line { border-bottom: 2px solid black; margin: 8px 0 20px 0; }
        .question-block { margin-bottom: 25px; page-break-inside: avoid; }
        .q-text { font-weight: bold; font-size: 11pt; margin-bottom: 5px; }
        .options { margin-left: 20px; margin-top: 8px; }
        .option { margin-bottom: 4px; }
        .solution-box { border: 2px solid #333; padding: 10px; border-radius: 8px; margin-top: 10px; background-color: #fff; }
        .answer { font-weight: bold; margin-bottom: 5px; color: #000; }
    </style>
    </head>
    <body>
    <div class="header">
        <div class="logo"><img src="https://blogger.googleusercontent.com/img/b/R29vZ2xl/AVvXsEjm8_FXoAwwGHMEMe-XjUwLHyZtqfl-2QCBeve69L-k-DTJ2nbWaMJ56HJYvnIC0He2tHMWVo91xwJUkTcW9B-PmDTbVBUR0WxHLF0IFZebbgQw5RT2foPwzVEVnwKOeospWPq0LokG_Xy3muy6T1I1bQ_gJp-fsP5u1abLM0qhu1kP66yxXqffeclp-90/s640/1000002374.jpg"></div>
        <div class="title">
            <h1>{{ title }}</h1>
            <p>www.mockrise.com</p> </div>
        <div style="width:70px;"></div>
    </div>
    <div class="meta"><div>Date: {{ date_range }}</div><div>Total Questions: {{ total }}</div></div>
    <div class="top-line"></div>
    {% for item in items %}
    <div class="question-block">
        <div class="q-text">Q{{ loop.index }}. {{ item.data.question }}</div>
        <div class="options">
            {% set labels = ['(A)', '(B)', '(C)', '(D)'] %}
            {% for opt in item.data.options %}
                <div class="option">{{ labels[loop.index0] if loop.index0 < 4 else loop.index }} {{ opt }}</div>
            {% endfor %}
        </div>
        <div class="solution-box">
            {% set ans_idx = item.data.correct_index %}
            <div class="answer">उत्तर: ({{ labels[ans_idx] if ans_idx < 4 else ans_idx+1 }})</div>
            {{ item.data.explanation }}
        </div>
    </div>
    {% endfor %}
    </body></html>
    """
    
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
    except: return None

# ==========================================
# 🎮 COMMANDS
# ==========================================

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    help_text = """
🤖 **MockRise Pro Automation Bot**

📂 **PDF Tools:**
/pdf_daily - Today's Quiz (To Bot)
/bulk_pdf_daily - Today's Quiz (To ALL Channels) 🚀
/pdf_weekly - Last 7 Days (To Bot)
/pdf_custom - Custom Range

📢 **Sending:**
/rssb, /ssc, /upsc, /springboard, /kalam
/bulk_send - Send Quizzes to All Channels

🛑 **Control:**
/stop - Clear Current JSON
"""
    # ✅ FIX: Added parse_mode to handle bold text correctly
    bot.reply_to(message, help_text, parse_mode='Markdown')

@bot.message_handler(commands=['stop'])
def cmd_stop(m):
    uid = m.from_user.id
    if uid in quiz_buffer:
        del quiz_buffer[uid]
        bot.reply_to(m, "🛑 **Buffer Cleared.** You can upload new JSON now.", parse_mode='Markdown')
    else:
        bot.reply_to(m, "Nothing to stop.")

# --- SENDING LOGIC ---
def process_send(message, key):
    uid = message.from_user.id
    if uid not in quiz_buffer: return bot.reply_to(message, "❌ No JSON data found.")

    target = CHANNELS[key]['id']
    name = CHANNELS[key]['name']
    bot.reply_to(message, f"📤 Sending to *{name}*...", parse_mode='Markdown')
    
    data = quiz_buffer[uid]
    success = 0
    
    for i, item in enumerate(data):
        try:
            q = item.get('question','')
            opts = item.get('options',[])
            ans = item.get('correct_index',0)
            exp = item.get('explanation','')
            
            if len(exp) > 190:
                s = bot.send_poll(target, f"Q{i+1}. {q}", opts, type='quiz', correct_option_id=ans, explanation="Solution 👇", is_anonymous=True)
                bot.send_message(target, f"📝 Solution:\n{exp}", reply_to_message_id=s.message_id)
            else:
                bot.send_poll(target, f"Q{i+1}. {q}", opts, type='quiz', correct_option_id=ans, explanation=exp, is_anonymous=True)
            
            success += 1
            time.sleep(2)
        except: pass

    if success > 0:
        add_to_history(data, key)
        update_stats(uid, key, success, 'success')
        bot.reply_to(message, f"✅ Sent {success} to {name}.")

@bot.message_handler(commands=['rssb'])
def c_rssb(m): process_send(m, 'rssb')
@bot.message_handler(commands=['ssc'])
def c_ssc(m): process_send(m, 'ssc')
@bot.message_handler(commands=['upsc'])
def c_upsc(m): process_send(m, 'upsc')
@bot.message_handler(commands=['springboard'])
def c_sb(m): process_send(m, 'springboard')
@bot.message_handler(commands=['kalam'])
def c_kl(m): process_send(m, 'kalam')
@bot.message_handler(commands=['bulk_send'])
def c_bulk(m):
    if m.from_user.id not in quiz_buffer: return bot.reply_to(m, "❌ No JSON.")
    for k in CHANNELS: process_send(m, k)
    bot.reply_to(m, "✅ Bulk Send Complete.")

# ==========================================
# 📅 PDF LOGIC (Updated with BULK Mode)
# ==========================================

def get_caption(title, date_label, count):
    # ✅ FIX: Use single asterisk for Bold in standard Markdown
    return (
        f"*Weekly Quizzes Summary*\n"
        f"Date: {date_label}\n"
        f"Total Questions: {count}\n"
        f"BY : @Mockrise"
    )

def generate_and_distribute(m, data, fname, title, date_label, bulk_mode=False):
    bot.reply_to(m, f"⏳ Generating PDF: *{title}*...", parse_mode='Markdown')
    
    res = generate_pdf_html(data, fname, title, date_label)
    
    if res:
        caption = get_caption(title, date_label, len(data))
        
        # 1. Send to User/Bot
        with open(res, 'rb') as f:
            bot.send_document(m.chat.id, f, caption=caption, parse_mode='Markdown')
            
        # 2. If Bulk Mode -> Send to ALL Channels
        if bulk_mode:
            bot.reply_to(m, "🔄 Forwarding PDF to ALL Channels...")
            for k, v in CHANNELS.items():
                try:
                    with open(res, 'rb') as f:
                        bot.send_document(v['id'], f, caption=caption, parse_mode='Markdown')
                    time.sleep(1)
                except Exception as e:
                    print(f"Failed to send PDF to {k}: {e}")
            bot.reply_to(m, "✅ PDF Sent to all channels.")
    else:
        bot.reply_to(m, "❌ Failed to generate PDF.")

# 1️⃣ DAILY PDF
@bot.message_handler(commands=['pdf_daily'])
def cmd_pdf_daily(m):
    process_daily_pdf(m, bulk=False)

@bot.message_handler(commands=['bulk_pdf_daily'])
def cmd_bulk_pdf_daily(m):
    process_daily_pdf(m, bulk=True)

def process_daily_pdf(m, bulk):
    today = datetime.now().strftime("%Y-%m-%d")
    today_disp = datetime.now().strftime("%d-%m-%Y")
    
    hist = load_json(DB_HISTORY)
    data = [h for h in hist if h['timestamp'].startswith(today)]
    
    if not data: return bot.reply_to(m, "❌ No data found for Today.")
    
    fname = f"Daily_Quiz_{datetime.now().strftime('%d%m')}.pdf"
    generate_and_distribute(m, data, fname, f"Daily Quiz ({today_disp})", today_disp, bulk)

# 2️⃣ WEEKLY PDF
@bot.message_handler(commands=['pdf_weekly'])
def cmd_pdf_weekly(m):
    end_date = datetime.now()
    start_date = end_date - timedelta(days=7)
    
    hist = load_json(DB_HISTORY)
    data = []
    for h in hist:
        h_dt = datetime.strptime(h['timestamp'], "%Y-%m-%d %H:%M:%S")
        if start_date <= h_dt <= end_date: data.append(h)
            
    if not data: return bot.reply_to(m, "❌ No data found for Last 7 Days.")
    
    date_str = f"{start_date.strftime('%d-%m-%Y')} to {end_date.strftime('%d-%m-%Y')}"
    fname = f"Weekly_Quiz.pdf"
    generate_and_distribute(m, data, fname, "Weekly Compilation", date_str, bulk_mode=False)

# 3️⃣ CUSTOM DATE
@bot.message_handler(commands=['pdf_custom'])
def cmd_pdf_custom(m):
    msg = bot.send_message(m.chat.id, "📅 Send Date Range (DD-MM-YYYY to DD-MM-YYYY):")
    bot.register_next_step_handler(msg, step_pdf_range)

def step_pdf_range(m):
    try:
        txt = m.text.lower().replace('to', ' ').strip()
        parts = txt.split()
        if len(parts) < 2: return bot.reply_to(m, "❌ Invalid Format.")
        
        s_date = datetime.strptime(parts[0], "%d-%m-%Y")
        e_date = datetime.strptime(parts[1], "%d-%m-%Y") + timedelta(days=1)
        
        hist = load_json(DB_HISTORY)
        data = [h for h in hist if s_date <= datetime.strptime(h['timestamp'], "%Y-%m-%d %H:%M:%S") < e_date]
                
        if not data: return bot.reply_to(m, "❌ No data.")
        
        fname = f"Custom_Quiz.pdf"
        date_str = f"{s_date.strftime('%d-%m-%Y')} to {parts[1]}"
        generate_and_distribute(m, data, fname, "Custom Question Bank", date_str)
        
    except: bot.reply_to(m, "❌ Error.")

@bot.message_handler(content_types=['text'])
def handle_json(m):
    if m.text.strip().startswith('['):
        try:
            data = json.loads(m.text)
            quiz_buffer[m.from_user.id] = data
            
            # ✅ SHOW ALL OPTIONS AFTER JSON UPLOAD
            msg = (
                f"✅ *JSON Received ({len(data)} Qs)*\n\n"
                f"👇 *Click to Send:*\n"
                f"/rssb - RSSB/REET\n"
                f"/ssc - SSC CGL\n"
                f"/upsc - UPSC/IAS\n"
                f"/springboard - Springboard\n"
                f"/kalam - Kalam Academy\n\n"
                f"🚀 *Bulk Options:*\n"
                f"/bulk_send - Send to ALL\n"
                f"/stop - Clear JSON"
            )
            bot.reply_to(m, msg, parse_mode='Markdown')
        except: bot.reply_to(m, "❌ Invalid JSON")

if __name__ == "__main__":
    keep_alive()
    bot.infinity_polling()
