import telebot
import json
import time
import os
import threading
import requests
from flask import Flask
from datetime import datetime
from weasyprint import HTML
from jinja2 import Template
from telebot.apihelper import ApiTelegramException

# ==========================================
# ⚙️ CONFIGURATION
# ==========================================

BOT_TOKEN = "7654075050:AAFt3hMFSYcoHPRcrNUfGGVpy859hjKotok"
MAIN_CHANNEL_ID = "@mockrise"

# 🔐 PASSWORDS
PASS_ADMIN = "7852"   # Full Access (Admin Panel)
PASS_LIMIT = "9637"   # Only Holas + PDF (Holas Panel)

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
DB_USERS = "users_db.json"
FONT_FILE = "NotoSansDevanagari-Regular.ttf"

# Memory
quiz_buffer = {}
json_fragments = {}
user_sessions = {}

bot = telebot.TeleBot(BOT_TOKEN)

# ==========================================
# 🌐 FLASK SERVER (Keep-Alive)
# ==========================================

app = Flask('')

@app.route('/')
def home():
    return "✅ Bot is Running (JSON Only + One-Liners Active)!"

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

# ==========================================
# 📄 PDF ENGINE (MCQ & ONE-LINER)
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
    """MCQ PDF Generator"""
    font_path = check_font()
    html_template = """
    <!DOCTYPE html>
    <html lang="hi">
    <head>
    <meta charset="UTF-8">
    <style>
        @font-face { font-family: 'Noto Sans Devanagari'; src: url('file://{{ font_path }}'); }
        @page { size: A4; margin: 20mm 15mm; @bottom-center { content: "Page " counter(page); font-family: 'Noto Sans Devanagari', sans-serif; font-size: 10pt; border-top: 1px solid #444; width: 90%; padding-top: 10px; margin-bottom: 10px; } }
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
        <div class="title"><h1>{{ title }}</h1><p>www.mockrise.com</p></div><div style="width:70px;"></div>
    </div>
    <div class="meta"><div>Date: {{ date_range }}</div><div>Total Questions: {{ total }}</div></div>
    <div class="top-line"></div>
    {% for item in items %}
    <div class="question-block">
        <div class="q-text">Q{{ loop.index }}. {{ item.data.question if item.data else item.question }}</div>
        {% set current_item = item.data if item.data else item %}
        {% if current_item.options %}
        <div class="options">
            {% set labels = ['(A)', '(B)', '(C)', '(D)'] %}
            {% for opt in current_item.options %}
                <div class="option">{{ labels[loop.index0] if loop.index0 < 4 else loop.index }} {{ opt }}</div>
            {% endfor %}
        </div>
        <div class="solution-box">
            {% set ans_idx = current_item.correct_index %}
            <div class="answer">उत्तर: ({{ labels[ans_idx] if ans_idx < 4 else ans_idx+1 }})</div>
            {{ current_item.explanation }}
        </div>
        {% else %}
        <div class="solution-box"><div class="answer">उत्तर: {{ current_item.answer }}</div></div>
        {% endif %}
    </div>
    {% endfor %}
    </body></html>
    """
    template = Template(html_template)
    rendered_html = template.render(title=title_text, date_range=date_range_text, total=len(data_list), items=data_list, font_path=font_path)
    try:
        HTML(string=rendered_html, base_url=".").write_pdf(filename)
        return filename
    except: return None

def generate_oneliner_pdf_html(data_list, filename, title_text, date_range_text):
    """One-Liner PDF Generator"""
    font_path = check_font()
    html_template = """
    <!DOCTYPE html>
    <html lang="hi">
    <head>
    <meta charset="UTF-8">
    <style>
        @font-face { font-family: 'Noto Sans Devanagari'; src: url('file://{{ font_path }}'); }
        @page { size: A4; margin: 20mm 15mm; @bottom-center { content: "Page " counter(page); font-family: 'Noto Sans Devanagari', sans-serif; font-size: 10pt; border-top: 1px solid #444; width: 90%; padding-top: 10px; margin-bottom: 10px; } }
        body { font-family: "Noto Sans Devanagari", sans-serif; font-size: 11pt; color: #222; margin: 0; }
        .header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 5px; }
        .logo img { width: 70px; height: auto; margin-right: 15px; }
        .title { text-align: center; flex-grow: 1; }
        .title h1 { margin: 0; font-size: 18pt; color: #000; text-transform: uppercase; }
        .title p { margin: 3px 0; font-size: 10pt; color: #555; }
        .meta { display: flex; justify-content: space-between; font-weight: bold; font-size: 10pt; margin-top: 15px; color: #333; }
        .top-line { border-bottom: 2px solid black; margin: 8px 0 20px 0; }
        .question-block { margin-bottom: 15px; padding-bottom: 10px; border-bottom: 1px dashed #ccc; page-break-inside: avoid; }
        .q-text { font-weight: bold; font-size: 11pt; margin-bottom: 5px; color: #000; }
        .answer { font-size: 11pt; color: #333; margin-left: 20px; }
    </style>
    </head>
    <body>
    <div class="header">
        <div class="logo"><img src="https://blogger.googleusercontent.com/img/b/R29vZ2xl/AVvXsEjm8_FXoAwwGHMEMe-XjUwLHyZtqfl-2QCBeve69L-k-DTJ2nbWaMJ56HJYvnIC0He2tHMWVo91xwJUkTcW9B-PmDTbVBUR0WxHLF0IFZebbgQw5RT2foPwzVEVnwKOeospWPq0LokG_Xy3muy6T1I1bQ_gJp-fsP5u1abLM0qhu1kP66yxXqffeclp-90/s640/1000002374.jpg"></div>
        <div class="title"><h1>{{ title }}</h1><p>www.mockrise.com</p></div><div style="width:70px;"></div>
    </div>
    <div class="meta"><div>Date: {{ date_range }}</div><div>Total One-Liners: {{ total }}</div></div>
    <div class="top-line"></div>
    {% for item in items %}
    {% set current_item = item.data if item.data else item %}
    <div class="question-block">
        <div class="q-text">Q{{ loop.index }}. {{ current_item.question }}</div>
        <div class="answer"><b>उत्तर:</b> {{ current_item.answer if current_item.answer else current_item.explanation }}</div>
    </div>
    {% endfor %}
    </body></html>
    """
    template = Template(html_template)
    rendered_html = template.render(title=title_text, date_range=date_range_text, total=len(data_list), items=data_list, font_path=font_path)
    try:
        HTML(string=rendered_html, base_url=".").write_pdf(filename)
        return filename
    except: return None

# ==========================================
# 🚀 SENDING LOGIC (POLLS & MESSAGES)
# ==========================================

def safe_send_poll(target_chat, question, options, correct_index, explanation):
    try:
        poll_q = question[:250]
        poll_e = explanation[:190]
        poll_msg = bot.send_poll(chat_id=target_chat, question=poll_q, options=options, type='quiz', 
                                 correct_option_id=correct_index, explanation=poll_e, is_anonymous=True)
        if len(explanation) > 190:
            bot.send_message(target_chat, f"💡 <b>Detailed Solution:</b>\n\n{explanation}", 
                             reply_to_message_id=poll_msg.message_id, parse_mode='HTML')
        return True
    except ApiTelegramException as e:
        if e.error_code == 429:
            time.sleep(int(e.result_json['parameters']['retry_after']) + 1)
            return safe_send_poll(target_chat, question, options, correct_index, explanation)
        return False

def safe_send_message(target_chat, text):
    try:
        bot.send_message(chat_id=target_chat, text=text, parse_mode='HTML')
        return True
    except ApiTelegramException as e:
        if e.error_code == 429:
            time.sleep(int(e.result_json['parameters']['retry_after']) + 1)
            return safe_send_message(target_chat, text)
        return False

def process_send(message, key):
    uid = message.from_user.id
    if uid not in quiz_buffer or len(quiz_buffer[uid]) == 0: 
        return bot.reply_to(message, "❌ आपके पास भेजने के लिए कोई प्रश्न नहीं हैं। पहले JSON भेजें।")
    
    target = CHANNELS[key]['id']
    data = quiz_buffer[uid]
    bot.reply_to(message, f"🚀 Sending {len(data)} items to {CHANNELS[key]['name']}...")
    success = 0
    
    for i, item in enumerate(data):
        if 'options' in item: # MCQ
            if safe_send_poll(target, f"Q{i+1}. {item['question']}", item['options'], item.get('correct_index', 0), item.get('explanation', 'MockRise')):
                success += 1
        elif 'answer' in item: # One-Liner
            msg_text = f"🔹 <b>Q{i+1}. {item['question']}</b>\n\n👉 <b>उत्तर:</b> {item['answer']}"
            if safe_send_message(target, msg_text):
                success += 1
        time.sleep(0.1)
        
    if success > 0:
        hist = load_json(DB_HISTORY)
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for q in data: hist.append({'timestamp': ts, 'channel': key, 'data': q})
        save_json(DB_HISTORY, hist)
        bot.reply_to(message, f"✅ सफलता पूर्वक {success} प्रश्न भेज दिए गए।")

# ==========================================
# 🎮 COMMANDS & MENU
# ==========================================

@bot.message_handler(commands=['start'])
def send_welcome(message):
    uid = message.from_user.id
    users = load_json(DB_USERS); users[str(uid)] = message.from_user.first_name; save_json(DB_USERS, users)
    if message.chat.type != 'private': return
    if uid not in user_sessions: user_sessions[uid] = 'user'
        
    welcome_msg = (
        f"👋 <b>नमस्ते {message.from_user.first_name}! MockRise Bot में आपका स्वागत है।</b>\n\n"
        f"🚨 <b>नोट:</b> अब यह बोट केवल <b>JSON कोड</b> स्वीकार करता है। सादा टेक्स्ट सपोर्ट हटा दिया गया है।\n\n"
        f"<b>MCQ या One-Liner</b> का JSON कोड भेजें और PDF बनाएँ।\n"
        f"🔒 <b>Admin/Holas Access:</b> /password\n"
        f"ℹ️ <b>मदद:</b> /help"
    )
    bot.send_message(message.chat.id, welcome_msg, parse_mode='HTML')

@bot.message_handler(commands=['password'])
def ask_password(message):
    if message.chat.type != 'private': return
    bot.reply_to(message, "🔑 <b>कृपया अपना पासवर्ड टाइप करके भेजें:</b>", parse_mode='HTML')

@bot.message_handler(commands=['help'])
def cmd_help(m):
    uid = m.from_user.id
    role = user_sessions.get(uid, 'user')
    q_count = len(quiz_buffer.get(uid, []))
    txt = f"🤖 <b>MockRise Pro Bot</b>\n👤 <b>Status:</b> {role.upper()}\n📝 <b>बनाए गए प्रश्न (Buffer):</b> {q_count}\n\n"
    if role == 'admin': 
        txt += "👑 <b>Admin Panel:</b>\nचैनल: /mockrise, /rssb, /ssc, /upsc, /holas, /kalam, /springboard\nटूल्स: /edit, /pdf_daily, /pdf_oneliner, /stats, /broadcast"
    elif role == 'limited':
        txt += "🔹 <b>Holas Panel:</b>\nचैनल: /holas\nटूल्स: /edit, /pdf_daily, /pdf_oneliner"
    else:
        txt += "👤 <b>User Panel:</b>\n/pdf_daily - MCQ PDF\n/pdf_oneliner - वन-लाइनर PDF\n/edit - प्रश्नों को एडिट करें"
    bot.reply_to(m, txt, parse_mode='HTML')

@bot.message_handler(commands=['stats', 'broadcast'])
def admin_tools(m):
    if user_sessions.get(m.from_user.id) != 'admin': return bot.reply_to(m, "❌ Access Denied!")
    if m.text.startswith('/stats'):
        bot.reply_to(m, f"📊 <b>Stats:</b>\nTotal Users: {len(load_json(DB_USERS))}", parse_mode='HTML')
    else:
        text = m.text.replace('/broadcast', '').strip()
        if text:
            for u in load_json(DB_USERS):
                try: bot.send_message(u, f"📢 <b>Announcement:</b>\n\n{text}", parse_mode='HTML')
                except: pass
            bot.reply_to(m, "✅ Broadcast Done.")

@bot.message_handler(commands=['mockrise', 'rssb', 'ssc', 'upsc', 'springboard', 'kalam'])
def admin_ch_handle(m):
    if user_sessions.get(m.from_user.id) != 'admin': return bot.reply_to(m, "❌ <b>Access Denied!</b>", parse_mode='HTML')
    process_send(m, m.text.replace('/', ''))

@bot.message_handler(commands=['holas'])
def holas_ch_handle(m):
    if user_sessions.get(m.from_user.id) not in ['admin', 'limited']: return bot.reply_to(m, "❌ <b>Access Denied!</b>", parse_mode='HTML')
    process_send(m, m.text.replace('/', ''))

@bot.message_handler(commands=['pdf_daily', 'pdf_oneliner'])
def cmd_pdf(m):
    uid = m.from_user.id
    is_oneliner = 'oneliner' in m.text
    if uid in quiz_buffer and len(quiz_buffer[uid]) > 0:
        data = quiz_buffer[uid]
        bot.reply_to(m, f"📄 Generating {'One-Liner' if is_oneliner else 'MCQ'} PDF for {len(data)} questions...")
    else:
        today = datetime.now().strftime("%Y-%m-%d")
        hist = load_json(DB_HISTORY)
        data = [h['data'] if 'data' in h else h for h in hist if h.get('timestamp', '').startswith(today)]
        if not data: return bot.reply_to(m, "❌ आपके पास कोई डेटा नहीं है। पहले JSON भेजें।")
        bot.reply_to(m, f"📄 Generating Daily History {'One-Liner' if is_oneliner else 'MCQ'} PDF...")
        
    res = generate_oneliner_pdf_html(data, f"OneLiner_PDF_{uid}.pdf", "MockRise One-Liners", "Latest") if is_oneliner else generate_pdf_html(data, f"MCQ_PDF_{uid}.pdf", "MockRise Quiz PDF", "Latest")
    if res:
        with open(res, 'rb') as f: bot.send_document(m.chat.id, f)
        os.remove(res)

@bot.message_handler(commands=['edit'])
def cmd_edit(m):
    uid = m.from_user.id
    if uid not in quiz_buffer or len(quiz_buffer[uid]) == 0: return bot.reply_to(m, "❌ आपके पास एडिट करने के लिए कोई प्रश्न नहीं है।")
    msg = bot.reply_to(m, f"Q No (1 से {len(quiz_buffer[uid])} के बीच) बताएँ जिसे एडिट करना है:")
    bot.register_next_step_handler(msg, step_edit_num)

def step_edit_num(m):
    try:
        idx = int(m.text) - 1
        q = quiz_buffer[m.from_user.id][idx]
        msg = bot.reply_to(m, f"Q{idx+1} के लिए नया JSON कोड भेजें:")
        bot.register_next_step_handler(msg, step_edit_final, idx)
    except: bot.reply_to(m, "❌ गलत नंबर।")

def step_edit_final(m, idx):
    try:
        quiz_buffer[m.from_user.id][idx] = json.loads(m.text)
        bot.reply_to(m, "✅ प्रश्न सफलतापूर्वक अपडेट कर दिया गया।")
    except: bot.reply_to(m, "❌ JSON फॉर्मेट गलत है, अपडेट फेल।")

# ==========================================
# 🧩 STRICT JSON HANDLER
# ==========================================

@bot.message_handler(content_types=['text'])
def handle_text(m):
    uid = m.from_user.id
    text = m.text.strip()
    
    if text == PASS_ADMIN: 
        user_sessions[uid] = 'admin'
        return bot.reply_to(m, "🔓 <b>Admin Panel Unlocked!</b>", parse_mode='HTML')
    if text == PASS_LIMIT: 
        user_sessions[uid] = 'limited'
        return bot.reply_to(m, "🔓 <b>Holas Panel Unlocked!</b>", parse_mode='HTML')
    
    if uid not in user_sessions: user_sessions[uid] = 'user'
    role = user_sessions[uid]

    # JSON Parsing Logic Only
    if text.startswith('['):
        if text.endswith(']'):
            try:
                quiz_buffer[uid] = json.loads(text)
            except: return bot.reply_to(m, "❌ JSON Parsing Error! कोड सही नहीं है।")
        else:
            json_fragments[uid] = text
            return bot.reply_to(m, "⏳ JSON का पहला हिस्सा मिल गया, बाकी का हिस्सा भेजें...")
    elif uid in json_fragments:
        json_fragments[uid] += text
        if json_fragments[uid].endswith(']'):
            try:
                quiz_buffer[uid] = json.loads(json_fragments[uid])
                del json_fragments[uid]
            except: 
                del json_fragments[uid]
                return bot.reply_to(m, "❌ JSON Parsing Error! कोड सही नहीं है।")
        else:
            return bot.reply_to(m, "⏳ JSON प्राप्त हो रहा है, और भेजें...")
    else:
        if not text.startswith('/'):
            return bot.reply_to(m, "❌ <b>कृपया केवल JSON फॉर्मेट (`[...]`) में ही प्रश्न भेजें।</b>\n\nसादे टेक्स्ट का सपोर्ट हटा दिया गया है।", parse_mode='HTML')

    if uid in quiz_buffer and not text.startswith('/'):
        q_count = len(quiz_buffer[uid])
        msg = f"✅ <b>डेटा प्राप्त हुआ ({q_count} प्रश्न तैयार हैं)</b>\n\n"
        msg += f"✏️ /edit - प्रश्नों में सुधार करें\n"
        msg += f"📄 /pdf_daily - MCQ PDF बनाएँ\n"
        msg += f"📄 /pdf_oneliner - वन-लाइनर PDF बनाएँ\n\n"
        
        if role == 'admin':
            msg += "👇 <b>चैनल पर भेजने के लिए क्लिक करें:</b>\n/mockrise, /rssb, /ssc, /upsc, /holas, /kalam, /springboard"
        elif role == 'limited':
            msg += "👇 <b>चैनल पर भेजने के लिए क्लिक करें:</b>\n/holas"
        else:
            msg += "🔒 <i>नोट: क्विज़ को चैनल पर पब्लिश करने के लिए Admin या Holas एक्सेस होना चाहिए (/password)।</i>"
            
        bot.reply_to(m, msg, parse_mode='HTML')

if __name__ == "__main__":
    keep_alive()
    bot.infinity_polling()
