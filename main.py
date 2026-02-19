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

# 🔐 PASSWORDS
PASS_ADMIN = "7852"   # Full Access
PASS_LIMIT = "9637"   # Only Holas + PDF

# ✅ Channels List
CHANNELS = {
    'mockrise': {'id': '@mockrise', 'name': 'MockRise Main'},
    'upsc': {'id': '@upsc_ssc_cgl_mts_cgl_chsl_gk', 'name': 'UPSC/IAS'},
    'ssc': {'id': '@ssc_cgl_chsl_mts_ntpc_upsc', 'name': 'SSC CGL/MTS'},
    'rssb': {'id': '@ldc_reet_ras_2ndgrade_kalam', 'name': 'RSSB/LDC/REET'},
    'springboard': {'id': '@rssb_gk_rpsc_springboar', 'name': 'Springboard'},
    'kalam': {'id': '@rajasthan_gk_kalam_reet_ldc_ras', 'name': 'Kalam Academy'},
    'holas': {'id': '@upsc_hindi_quizz', 'name': 'Holas (UPSC Hindi)'}
}

# Files
DB_STATS = "user_stats.json"
DB_HISTORY = "history.json"
FONT_FILE = "NotoSansDevanagari-Regular.ttf"

# Memory
quiz_buffer = {}
json_fragments = {}
user_sessions = {} 

bot = telebot.TeleBot(BOT_TOKEN)

# ==========================================
# 🌐 FLASK SERVER
# ==========================================

app = Flask('')

@app.route('/')
def home():
    return "✅ Bot is Running!"

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
    save_json(DB_HISTORY, history)

def update_stats(user_id, channel, count, status):
    stats = load_json(DB_STATS)
    uid = str(user_id)
    if uid not in stats: stats[uid] = {'total_sent': 0, 'total_failed': 0, 'channels': [], 'history': []}
    if status == 'success': stats[uid]['total_sent'] += count
    else: stats[uid]['total_failed'] += count
    save_json(DB_STATS, stats)

# ==========================================
# 🔒 AUTHENTICATION HELPER (Group Friendly)
# ==========================================

def is_auth(m):
    # Agar message group me hai, to auth true maano (Taki group me lock na dikhaye)
    if m.chat.type in ['group', 'supergroup']:
        return True
    return m.from_user.id in user_sessions

def get_role(m):
    if m.chat.type in ['group', 'supergroup']:
        return 'admin' # Group me commands allowed raheinge
    return user_sessions.get(m.from_user.id)

def check_access(m, required_role='limited'):
    if not is_auth(m):
        bot.reply_to(m, "🔒 <b>Locked.</b> Please enter password first in Private Chat.", parse_mode='HTML')
        return False
    role = get_role(m)
    if required_role == 'admin' and role != 'admin':
        bot.reply_to(m, "🚫 Admin Access Required.", parse_mode='HTML')
        return False
    return True

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
    html_template = """
    <!DOCTYPE html>
    <html lang="hi">
    <head>
    <meta charset="UTF-8">
    <style>
        @font-face { font-family: 'Noto Sans Devanagari'; src: url('file://{{ font_path }}'); }
        body { font-family: "Noto Sans Devanagari", sans-serif; font-size: 11pt; }
        .question-block { margin-bottom: 25px; page-break-inside: avoid; }
        .solution-box { border: 2px solid #333; padding: 10px; border-radius: 8px; margin-top: 5px; }
    </style>
    </head>
    <body>
    <h1>{{ title }}</h1>
    <p>Date: {{ date_range }} | Total: {{ total }}</p><hr>
    {% for item in items %}
    <div class="question-block">
        <b>Q{{ loop.index }}. {{ item.data.question }}</b>
        <div style="margin-left: 20px;">
            {% for opt in item.data.options %}<div>{{ loop.index }}. {{ opt }}</div>{% endfor %}
        </div>
        <div class="solution-box">
            <b>Ans: {{ item.data.correct_index + 1 }}</b><br>{{ item.data.explanation }}
        </div>
    </div>
    {% endfor %}
    </body></html>
    """
    try:
        template = Template(html_template)
        rendered_html = template.render(title=title_text, date_range=date_range_text, total=len(data_list), items=data_list, font_path=font_path)
        HTML(string=rendered_html).write_pdf(filename)
        return filename
    except: return None

# ==========================================
# 🚀 SENDING LOGIC (NO GAP / FAST)
# ==========================================

def safe_send_poll(target_chat, question, options, correct_index, explanation):
    try:
        if len(question) > 250:
            bot.send_message(target_chat, f"<b>Q.</b> {question}", parse_mode='HTML')
            q_text = "Q. Solve the above question:"
        else:
            q_text = question

        poll = bot.send_poll(
            chat_id=target_chat,
            question=q_text,
            options=options,
            type='quiz',
            correct_option_id=correct_index,
            explanation=explanation[:190],
            is_anonymous=True
        )
        if len(explanation) > 190:
            bot.send_message(target_chat, f"💡 <b>Full Solution:</b>\n{explanation}", reply_to_message_id=poll.message_id, parse_mode='HTML')
        return True
    except: return False

def process_send(message, key):
    role = get_role(message)
    if not role: return bot.reply_to(message, "🔒 Please Login.")
    
    if role == 'limited' and key != 'holas':
        return bot.reply_to(message, "🚫 Access Restricted.")
        
    uid = message.from_user.id
    if uid not in quiz_buffer: return bot.reply_to(message, "❌ No JSON.")

    target = CHANNELS[key]['id']
    name = CHANNELS[key]['name']
    
    data = quiz_buffer[uid]
    success = 0
    
    bot.reply_to(message, f"🚀 Sending {len(data)} questions to {name}...")

    for i, item in enumerate(data):
        q = item.get('question', '')
        opts = item.get('options', []) or item.get('option', [])
        ans = item.get('correct_index', 0)
        exp = item.get('explanation', '')
        
        q_display = f"Q{i+1}. {q}" if not q.lower().startswith('q') else q

        if safe_send_poll(target, q_display, opts, ans, exp):
            success += 1
            # 3s gap removed. Small sleep (0.1s) is kept only to prevent Telegram flood limits.
            time.sleep(0.05) 

    if success > 0:
        add_to_history(data, key)
        update_stats(uid, key, success, 'success')
        bot.reply_to(message, f"✅ Done! {success} Qs sent to {name}.")

# ==========================================
# 🎮 COMMANDS
# ==========================================

@bot.message_handler(commands=['start'])
def send_welcome(message):
    uid = message.from_user.id
    if message.chat.type != 'private':
        return bot.reply_to(message, "Bot is active in this group. ✅")
    
    if uid in user_sessions: del user_sessions[uid]
    bot.send_message(message.chat.id, "🔒 <b>Bot Locked</b>\n\nPassword dalein:", parse_mode='HTML')

@bot.message_handler(commands=['mockrise'])
def c_mr(m): process_send(m, 'mockrise')

@bot.message_handler(commands=['holas'])
def c_ho(m): process_send(m, 'holas')

@bot.message_handler(commands=['rssb'])
def c_rs(m): process_send(m, 'rssb')

@bot.message_handler(commands=['ssc'])
def c_ss(m): process_send(m, 'ssc')

@bot.message_handler(commands=['upsc'])
def c_up(m): process_send(m, 'upsc')

@bot.message_handler(commands=['bulk_send'])
def c_bulk(m):
    if not check_access(m, 'admin'): return
    for k in CHANNELS: 
        process_send(m, k)
    bot.reply_to(m, "🚀 Bulk Send Finished.")

@bot.message_handler(commands=['pdf_daily'])
def cmd_pdf_daily(m):
    today = datetime.now().strftime("%Y-%m-%d")
    hist = load_json(DB_HISTORY)
    data = [h for h in hist if h['timestamp'].startswith(today)]
    if not data: return bot.reply_to(m, "❌ Today no questions found.")
    
    fname = f"Daily_{today}.pdf"
    res = generate_pdf_html(data, fname, "Daily Quiz", today)
    if res:
        with open(res, 'rb') as f: bot.send_document(m.chat.id, f)
        os.remove(res)

@bot.message_handler(commands=['edit'])
def cmd_edit(m):
    uid = m.from_user.id
    if uid not in quiz_buffer: return bot.reply_to(m, "Empty buffer.")
    msg = bot.reply_to(m, f"Send Q No (1-{len(quiz_buffer[uid])}):")
    bot.register_next_step_handler(msg, step_edit_num)

def step_edit_num(m):
    try:
        idx = int(m.text) - 1
        q = quiz_buffer[m.from_user.id][idx]
        msg = bot.reply_to(m, f"Current:\n<pre>{json.dumps(q, ensure_ascii=False)}</pre>\n\nSend New JSON:", parse_mode='HTML')
        bot.register_next_step_handler(msg, step_edit_final, idx)
    except: bot.reply_to(m, "Invalid.")

def step_edit_final(m, idx):
    try:
        quiz_buffer[m.from_user.id][idx] = json.loads(m.text)
        bot.reply_to(m, "✅ Updated.")
    except: bot.reply_to(m, "Failed.")

# ==========================================
# 🧩 TEXT HANDLER
# ==========================================

@bot.message_handler(content_types=['text'])
def handle_text(m):
    uid = m.from_user.id
    text = m.text.strip()
    
    if text == PASS_ADMIN:
        user_sessions[uid] = 'admin'
        return bot.reply_to(m, "🔓 Admin Access Granted.")
    elif text == PASS_LIMIT:
        user_sessions[uid] = 'limited'
        return bot.reply_to(m, "🔓 Limited Access Granted.")

    if not is_auth(m):
        return # Silent in groups, lock in PM

    if text.startswith('[') or uid in json_fragments:
        if text.startswith('['): json_fragments[uid] = text
        else: json_fragments[uid] += text
        
        if json_fragments[uid].endswith(']'):
            try:
                data = json.loads(json_fragments[uid])
                quiz_buffer[uid] = data
                del json_fragments[uid]
                
                role = get_role(m)
                opts = "/mockrise, /rssb, /ssc, /upsc, /holas\n🚀 /bulk_send" if role == 'admin' else "/holas"
                
                msg = (f"✅ <b>JSON Received ({len(data)} Qs)</b>\n\n"
                       f"✏️ /edit\n"
                       f"👇 <b>Send:</b> {opts}\n"
                       f"📄 /pdf_daily")
                bot.reply_to(m, msg, parse_mode='HTML')
            except: pass
        else:
            bot.reply_to(m, "📥 Receiving part...")

if __name__ == "__main__":
    keep_alive()
    bot.infinity_polling()
