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
    return "✅ Bot is Running (User/Admin/Holas Panels Active)!"

def run_server():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = threading.Thread(target=run_server)
    t.daemon = True
    t.start()

# ==========================================
# 📂 DATA HANDLING & PARSER
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

def text_to_json_parser(text):
    """बिना कोडिंग के सादे टेक्स्ट को JSON में बदलने के लिए"""
    questions = []
    blocks = re.split(r'\n(?=[Qq]?\d+[\.\)])', text)
    for block in blocks:
        try:
            lines = [l.strip() for l in block.split('\n') if l.strip()]
            if len(lines) < 3: continue
            q_text = re.sub(r'^[Qq]?\d+[\.\)]\s*', '', lines[0])
            options = []
            ans_idx = 0
            explanation = "MockRise.com"
            for line in lines[1:]:
                if re.match(r'^[A-Dd1-4\(\)]+[\.\)]', line):
                    options.append(re.sub(r'^[A-Dd1-4\(\)]+[\.\)]\s*', '', line))
                elif "Ans:" in line or "उत्तर:" in line:
                    val = re.search(r'\d+|[A-D]', line).group()
                    ans_idx = int(val)-1 if val.isdigit() else ord(val.upper())-65
                elif "Exp:" in line or "व्याख्या:" in line:
                    explanation = line.split(":", 1)[1].strip()
            if q_text and options:
                questions.append({"question": q_text, "options": options[:4], "correct_index": ans_idx, "explanation": explanation})
        except: continue
    return questions

# ==========================================
# 📄 PDF ENGINE (Original Design)
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
            <p>www.mockrise.com</p>
        </div>
        <div style="width:70px;"></div>
    </div>
    <div class="meta"><div>Date: {{ date_range }}</div><div>Total Questions: {{ total }}</div></div>
    <div class="top-line"></div>
    {% for item in items %}
    <div class="question-block">
        <div class="q-text">Q{{ loop.index }}. {{ item.data.question if item.data else item.question }}</div>
        <div class="options">
            {% set labels = ['(A)', '(B)', '(C)', '(D)'] %}
            {% set current_item = item.data if item.data else item %}
            {% for opt in current_item.options %}
                <div class="option">{{ labels[loop.index0] if loop.index0 < 4 else loop.index }} {{ opt }}</div>
            {% endfor %}
        </div>
        <div class="solution-box">
            {% set current_item = item.data if item.data else item %}
            {% set ans_idx = current_item.correct_index %}
            <div class="answer">उत्तर: ({{ labels[ans_idx] if ans_idx < 4 else ans_idx+1 }})</div>
            {{ current_item.explanation }}
        </div>
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
# 🚀 SENDING LOGIC (FAST + ANTI-FLOOD)
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

def process_send(message, key):
    uid = message.from_user.id
    if uid not in quiz_buffer or len(quiz_buffer[uid]) == 0: 
        return bot.reply_to(message, "❌ आपके पास भेजने के लिए कोई प्रश्न नहीं हैं। पहले प्रश्न भेजें।")
    
    target = CHANNELS[key]['id']
    data = quiz_buffer[uid]
    bot.reply_to(message, f"🚀 Sending {len(data)} Qs to {CHANNELS[key]['name']}...")
    success = 0
    for i, item in enumerate(data):
        if safe_send_poll(target, f"Q{i+1}. {item['question']}", item['options'], item['correct_index'], item['explanation']):
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
    users = load_json(DB_USERS)
    users[str(uid)] = message.from_user.first_name
    save_json(DB_USERS, users)
    
    if message.chat.type != 'private': return
    
    # By default, anyone who starts is a normal user
    if uid not in user_sessions:
        user_sessions[uid] = 'user'
        
    welcome_msg = (
        f"👋 <b>नमस्ते {message.from_user.first_name}! MockRise Bot में आपका स्वागत है।</b>\n\n"
        f"👤 <b>Current Mode:</b> User Panel\n"
        f"आप मुझे प्रश्न (Text या JSON) भेज सकते हैं और उनका <b>PDF</b> बना सकते हैं।\n\n"
        f"🔒 <b>Admin/Holas Access:</b> अगर आपके पास एक्सेस है, तो /password टाइप करें।\n"
        f"ℹ️ <b>मदद:</b> क्या-क्या फीचर्स हैं जानने के लिए /help टाइप करें।"
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
    
    txt = f"🤖 <b>MockRise Pro Bot</b>\n"
    txt += f"👤 <b>Status:</b> {role.upper()}\n"
    txt += f"📝 <b>बनाए गए प्रश्न (Buffer):</b> {q_count}\n\n"
    
    if role == 'admin': 
        txt += "👑 <b>Admin Panel:</b>\n"
        txt += "चैनल पर भेजने के लिए:\n/mockrise, /rssb, /ssc, /upsc, /holas, /kalam, /springboard\n\n"
        txt += "अन्य टूल:\n/edit, /pdf_daily, /stats, /broadcast"
    elif role == 'limited':
        txt += "🔹 <b>Holas Panel:</b>\n"
        txt += "चैनल पर भेजने के लिए:\n/holas\n\n"
        txt += "अन्य टूल:\n/edit, /pdf_daily"
    else:
        txt += "👤 <b>User Panel:</b>\n"
        txt += "आप प्रश्न भेजकर केवल उनका PDF बना सकते हैं।\n"
        txt += "/pdf_daily - आज का PDF जनरेट करें\n"
        txt += "/edit - प्रश्नों को एडिट करें"
        
    bot.reply_to(m, txt, parse_mode='HTML')

@bot.message_handler(commands=['stats'])
def cmd_stats(m):
    if user_sessions.get(m.from_user.id) != 'admin': return bot.reply_to(m, "❌ Access Denied!")
    users = load_json(DB_USERS)
    bot.reply_to(m, f"📊 <b>Stats:</b>\nTotal Users: {len(users)}", parse_mode='HTML')

@bot.message_handler(commands=['broadcast'])
def cmd_bc(m):
    if user_sessions.get(m.from_user.id) != 'admin': return bot.reply_to(m, "❌ Access Denied!")
    text = m.text.replace('/broadcast', '').strip()
    if not text: return
    users = load_json(DB_USERS)
    for u in users:
        try: bot.send_message(u, f"📢 <b>Announcement:</b>\n\n{text}", parse_mode='HTML')
        except: pass
    bot.reply_to(m, "✅ Broadcast Done.")

# --- Channel Sending Handlers (Protected) ---
@bot.message_handler(commands=['mockrise', 'rssb', 'ssc', 'upsc', 'springboard', 'kalam'])
def admin_ch_handle(m):
    if user_sessions.get(m.from_user.id) != 'admin':
        return bot.reply_to(m, "❌ <b>Access Denied!</b> यह कमांड केवल Admin के लिए है।", parse_mode='HTML')
    process_send(m, m.text.replace('/', ''))

@bot.message_handler(commands=['holas'])
def holas_ch_handle(m):
    role = user_sessions.get(m.from_user.id)
    if role not in ['admin', 'limited']:
        return bot.reply_to(m, "❌ <b>Access Denied!</b> यह कमांड केवल Holas/Admin के लिए है।", parse_mode='HTML')
    process_send(m, m.text.replace('/', ''))

@bot.message_handler(commands=['pdf_daily'])
def cmd_pdf(m):
    uid = m.from_user.id
    # पहले बफर के प्रश्न चेक करेगा (यूज़र के लिए)
    if uid in quiz_buffer and len(quiz_buffer[uid]) > 0:
        data = quiz_buffer[uid]
        bot.reply_to(m, f"📄 Generating PDF for {len(data)} questions in your buffer...")
    else:
        # अगर एडमिन है तो हिस्ट्री से बनाएगा
        today = datetime.now().strftime("%Y-%m-%d")
        hist = load_json(DB_HISTORY)
        data = [h['data'] if 'data' in h else h for h in hist if h.get('timestamp', '').startswith(today)]
        if not data: return bot.reply_to(m, "❌ आपके पास कोई डेटा नहीं है। पहले प्रश्न भेजें।")
        bot.reply_to(m, "📄 Generating Daily History PDF...")
        
    res = generate_pdf_html(data, f"Quiz_PDF_{uid}.pdf", "MockRise Quiz PDF", "Latest")
    if res:
        with open(res, 'rb') as f: bot.send_document(m.chat.id, f)
        os.remove(res)

@bot.message_handler(commands=['edit'])
def cmd_edit(m):
    uid = m.from_user.id
    if uid not in quiz_buffer or len(quiz_buffer[uid]) == 0: 
        return bot.reply_to(m, "❌ आपके पास एडिट करने के लिए कोई प्रश्न नहीं है।")
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
# 🧩 TEXT HANDLER (Main Logic Engine)
# ==========================================

@bot.message_handler(content_types=['text'])
def handle_text(m):
    uid = m.from_user.id
    text = m.text.strip()
    
    # Password Validation Check
    if text == PASS_ADMIN: 
        user_sessions[uid] = 'admin'
        return bot.reply_to(m, "🔓 <b>Admin Panel Unlocked!</b>\nअब आप सभी चैनलों पर क्विज़ भेज सकते हैं। /help देखें।", parse_mode='HTML')
    if text == PASS_LIMIT: 
        user_sessions[uid] = 'limited'
        return bot.reply_to(m, "🔓 <b>Holas Panel Unlocked!</b>\nअब आप Holas चैनल पर क्विज़ भेज सकते हैं। /help देखें।", parse_mode='HTML')
    
    # Default assign user role if not exist
    if uid not in user_sessions:
        user_sessions[uid] = 'user'
        
    role = user_sessions[uid]

    # JSON or Text Parsing Logic
    if text.startswith('['):
        json_fragments[uid] = text
    elif uid in json_fragments:
        json_fragments[uid] += text
        if json_fragments[uid].endswith(']'):
            try:
                quiz_buffer[uid] = json.loads(json_fragments[uid])
                del json_fragments[uid]
            except: 
                return bot.reply_to(m, "❌ JSON Parsing Error! कृपया सही फॉर्मेट भेजें।")
    else:
        parsed = text_to_json_parser(text)
        if parsed: quiz_buffer[uid] = parsed

    # Response Builder based on Quiz Count and Role
    if uid in quiz_buffer and not text.startswith('/'):
        q_count = len(quiz_buffer[uid])
        msg = f"✅ <b>डेटा प्राप्त हुआ ({q_count} प्रश्न तैयार हैं)</b>\n\n"
        msg += f"✏️ /edit - प्रश्नों में सुधार करें\n"
        msg += f"📄 /pdf_daily - इन प्रश्नों का PDF बनाएँ\n\n"
        
        if role == 'admin':
            msg += "👇 <b>चैनल पर भेजने के लिए क्लिक करें:</b>\n/mockrise, /rssb, /ssc, /upsc, /holas, /kalam, /springboard"
        elif role == 'limited':
            msg += "👇 <b>चैनल पर भेजने के लिए क्लिक करें:</b>\n/holas"
        else:
            msg += "🔒 <i>नोट: क्विज़ को चैनल पर पब्लिश करने के लिए आपके पास Admin या Holas एक्सेस होना चाहिए (/password)।</i>"
            
        bot.reply_to(m, msg, parse_mode='HTML')

if __name__ == "__main__":
    keep_alive()
    bot.infinity_polling()
