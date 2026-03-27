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
PASS_ADMIN = "7852"   # Full Access

# 🎨 BRANDS & LOGOS CONFIGURATION
BRANDS = {
    'mockrise': {
        'website': 'www.mockrise.com',
        'logo': 'https://blogger.googleusercontent.com/img/b/R29vZ2xl/AVvXsEjm8_FXoAwwGHMEMe-XjUwLHyZtqfl-2QCBeve69L-k-DTJ2nbWaMJ56HJYvnIC0He2tHMWVo91xwJUkTcW9B-PmDTbVBUR0WxHLF0IFZebbgQw5RT2foPwzVEVnwKOeospWPq0LokG_Xy3muy6T1I1bQ_gJp-fsP5u1abLM0qhu1kP66yxXqffeclp-90/s640/1000002374.jpg'
    },
    'cpsir': {
        'website': 'https://www.gurudeepaiacademy.com/',
        # Telegram link is not an image file. Replace the URL below with your actual .jpg/.png direct logo link.
        'logo': 'https://blogger.googleusercontent.com/img/a/AVvXsEgUuZDpANHyMD9YoC5ftPljTkNKbJ5rFJJkdV2S5sDWjD-bj19PPDnexZ-0deX07JvtXLp5OtI_dMtBeH9EE6b7PUkJ8eV94I5k8Q_H7TPkNm7WRRiYfQLo4p6mMl-hnqbVQ3IytxmtLx-vxAOgOo6jwbI0wiWnBaY-XeTERgK9id1NCrPDbfj1smHvfm0=s640'
    }
}

# ✅ Channels List (Updated as per your request)
CHANNELS = {
    'mockrise': {'id': '@mockrise', 'name': 'MockRise Main', 'brand': 'mockrise'},
    'cpsir': {'id': '@GuruDeepClasses', 'name': 'GuruDeep Classes', 'brand': 'cpsir'},
    'ssc': {'id': '@ssc_cgl_chsl_mts_ntpc_upsc', 'name': 'SSC CGL/MTS', 'brand': 'mockrise'},
    'kalam': {'id': '@rajasthan_gk_kalam_reet_ldc_ras', 'name': 'Kalam Academy', 'brand': 'mockrise'}
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
# 🌐 FLASK SERVER
# ==========================================

app = Flask('')

@app.route('/')
def home():
    return "✅ Bot is Running (Mockrise & CP Sir Multi-Channel Edition)!"

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

def generate_pdf_html(data_list, filename, title_text, date_range_text, brand_key='mockrise'):
    if not data_list: return None
    font_path = check_font()
    brand_info = BRANDS.get(brand_key, BRANDS['mockrise'])
    
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
        <div class="logo"><img src="{{ brand_logo }}"></div>
        <div class="title"><h1>{{ title }}</h1><p>{{ brand_website }}</p></div><div style="width:70px;"></div>
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
        {% endif %}
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
        font_path=font_path,
        brand_logo=brand_info['logo'],
        brand_website=brand_info['website']
    )
    try:
        HTML(string=rendered_html, base_url=".").write_pdf(filename)
        return filename
    except: return None

def generate_oneliner_pdf_html(data_list, filename, title_text, date_range_text, brand_key='mockrise'):
    if not data_list: return None
    font_path = check_font()
    brand_info = BRANDS.get(brand_key, BRANDS['mockrise'])
    
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
        <div class="logo"><img src="{{ brand_logo }}"></div>
        <div class="title"><h1>{{ title }}</h1><p>{{ brand_website }}</p></div><div style="width:70px;"></div>
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
    rendered_html = template.render(
        title=title_text, 
        date_range=date_range_text, 
        total=len(data_list), 
        items=data_list, 
        font_path=font_path,
        brand_logo=brand_info['logo'],
        brand_website=brand_info['website']
    )
    try:
        HTML(string=rendered_html, base_url=".").write_pdf(filename)
        return filename
    except: return None

# ==========================================
# 🚀 SENDING LOGIC (POLLS & MESSAGES)
# ==========================================

def safe_send_poll(target_chat, question, options, correct_index, explanation):
    try:
        poll_q = question
        sent_q_msg = None
        if len(question) > 250:
            sent_q_msg = bot.send_message(target_chat, f"❓ <b>प्रश्न:</b>\n{question}", parse_mode='HTML')
            poll_q = "👆 ऊपर दिए गए प्रश्न का सही विकल्प चुनें:"

        safe_options = [str(opt)[:97] + "..." if len(str(opt)) > 100 else str(opt) for opt in options]
        poll_e = explanation
        send_separate_exp = False
        
        if len(explanation) > 190:
            poll_e = explanation[:190] + "..."
            send_separate_exp = True

        poll_msg = bot.send_poll(
            chat_id=target_chat, question=poll_q, options=safe_options, type='quiz', 
            correct_option_id=correct_index, explanation=poll_e, is_anonymous=True,
            reply_to_message_id=sent_q_msg.message_id if sent_q_msg else None
        )

        if send_separate_exp:
            bot.send_message(
                target_chat, f"💡 <b>विस्तृत व्याख्या:</b>\n<tg-spoiler>{explanation}</tg-spoiler>", 
                reply_to_message_id=poll_msg.message_id, parse_mode='HTML'
            )
        return True
    except ApiTelegramException as e:
        if e.error_code == 429:
            time.sleep(int(e.result_json['parameters']['retry_after']) + 1)
            return safe_send_poll(target_chat, question, options, correct_index, explanation)
        return False
    except Exception: return False

def safe_send_message(target_chat, text):
    try:
        bot.send_message(chat_id=target_chat, text=text, parse_mode='HTML')
        return True
    except ApiTelegramException as e:
        if e.error_code == 429:
            time.sleep(int(e.result_json['parameters']['retry_after']) + 1)
            return safe_send_message(target_chat, text)
        return False

def process_send(message, keys):
    """Sends JSON buffer to one or multiple channels"""
    if message.chat.type != 'private': return
    
    uid = message.from_user.id
    if uid not in quiz_buffer or len(quiz_buffer[uid]) == 0: 
        return bot.reply_to(message, "❌ आपके पास भेजने के लिए कोई प्रश्न नहीं हैं। पहले JSON भेजें।")
    
    data = quiz_buffer[uid]
    
    for key in keys:
        if key not in CHANNELS: continue
        target = CHANNELS[key]['id']
        bot.reply_to(message, f"🚀 Sending {len(data)} items to {CHANNELS[key]['name']}... कृपया प्रतीक्षा करें।")
        
        success = 0
        one_liners_batch = []
        
        for item in data:
            if 'options' in item:
                # Question Number (Q1., Q2.) is removed for channel send
                if safe_send_poll(target, item['question'], item['options'], item.get('correct_index', 0), item.get('explanation', 'MockRise')):
                    success += 1
                time.sleep(0.3)
            elif 'answer' in item:
                # Question Number is removed for One-Liner channel send too
                one_liners_batch.append(f"🔹 <b>{item['question']}</b>\n👉 <b>उत्तर:</b> {item['answer']}\n")
                success += 1
                
        if one_liners_batch:
            current_msg = "📝 <b>महत्वपूर्ण वन-लाइनर प्रश्न:</b>\n\n"
            for ol in one_liners_batch:
                if len(current_msg) + len(ol) > 4000: 
                    safe_send_message(target, current_msg)
                    time.sleep(2)
                    current_msg = "📝 <b>वन-लाइनर (Cont..):</b>\n\n"
                current_msg += ol + "\n"
            if current_msg.strip():
                safe_send_message(target, current_msg)
            
        if success > 0:
            hist = load_json(DB_HISTORY)
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            for q in data: hist.append({'timestamp': ts, 'channel': key, 'data': q})
            save_json(DB_HISTORY, hist)
            
            bot.reply_to(message, f"✅ सफलता पूर्वक {success} प्रश्न {CHANNELS[key]['name']} पर भेज दिए गए हैं!")
            
    # CLEAR BUFFER AFTER SUCCESSFUL SEND TO ALL REQUESTED CHANNELS
    del quiz_buffer[uid]
    bot.reply_to(message, "✅ प्रक्रिया पूरी हुई। मेमोरी क्लियर कर दी गई है।")

# ==========================================
# 🕒 CHANNEL-SPECIFIC PDF BROADCAST LOGIC
# ==========================================

def get_history_grouped_by_channel(days=1):
    hist = load_json(DB_HISTORY)
    now = datetime.now()
    grouped = {k: {'mcq': [], 'oneliner': []} for k in CHANNELS.keys()}
    
    for h in hist:
        try:
            ts = datetime.strptime(h['timestamp'], "%Y-%m-%d %H:%M:%S")
            if (now - ts).days < days:
                ch = h.get('channel')
                if ch in grouped:
                    item = h.get('data', h)
                    if 'options' in item:
                        grouped[ch]['mcq'].append(item)
                    elif 'answer' in item:
                        grouped[ch]['oneliner'].append(item)
        except: pass
    return grouped

def send_channel_pdfs(days=1, prefix="Daily", user_id=None):
    grouped = get_history_grouped_by_channel(days)
    date_str = datetime.now().strftime("%d-%m-%Y")
    sent_any = False
    
    for ch_key, data in grouped.items():
        mcq_data = data['mcq']
        oneliner_data = data['oneliner']
        target_chat = CHANNELS[ch_key]['id']
        brand_key = CHANNELS[ch_key]['brand']
        brand_name = "CP Sir" if brand_key == "cpsir" else "MockRise"
        
        if mcq_data:
            pdf_name = f"{prefix}_MCQ_{ch_key}_{date_str}.pdf"
            res = generate_pdf_html(mcq_data, pdf_name, f"{brand_name} {prefix} MCQ - {CHANNELS[ch_key]['name']}", date_str, brand_key)
            if res:
                caption = f"📄 {prefix} Quiz\n📅 Date: {date_str}\n🔢 Questions: {len(mcq_data)}\nBy: {brand_name}"
                try:
                    with open(res, 'rb') as f:
                        bot.send_document(target_chat, f, caption=caption)
                    if user_id:
                        with open(res, 'rb') as f:
                            bot.send_document(user_id, f, caption=f"✅ <b>Sent to {target_chat}</b>\n\n{caption}", parse_mode='HTML')
                    sent_any = True
                except: pass
                os.remove(res)
        
        if oneliner_data:
            pdf_name = f"{prefix}_OneLiner_{ch_key}_{date_str}.pdf"
            res = generate_oneliner_pdf_html(oneliner_data, pdf_name, f"{brand_name} {prefix} One-Liners - {CHANNELS[ch_key]['name']}", date_str, brand_key)
            if res:
                caption = f"📄 {prefix} One-Liner\n📅 Date: {date_str}\n🔢 Questions: {len(oneliner_data)}\nBy: {brand_name}"
                try:
                    with open(res, 'rb') as f:
                        bot.send_document(target_chat, f, caption=caption)
                    if user_id:
                        with open(res, 'rb') as f:
                            bot.send_document(user_id, f, caption=f"✅ <b>Sent to {target_chat}</b>\n\n{caption}", parse_mode='HTML')
                    sent_any = True
                except: pass
                os.remove(res)
                
    return sent_any

def auto_scheduler_thread():
    while True:
        try:
            now = datetime.now()
            if now.hour == 21 and now.minute == 0:
                send_channel_pdfs(days=1, prefix="Daily")
                time.sleep(60)
            if now.weekday() == 6 and now.hour == 10 and now.minute == 0:
                send_channel_pdfs(days=7, prefix="Weekly")
                time.sleep(60)
        except: pass
        time.sleep(30)

threading.Thread(target=auto_scheduler_thread, daemon=True).start()

# ==========================================
# 🎮 COMMANDS & MENU (Private Only)
# ==========================================

@bot.message_handler(commands=['start'])
def send_welcome(message):
    if message.chat.type != 'private': return
    uid = message.from_user.id
    users = load_json(DB_USERS); users[str(uid)] = message.from_user.first_name; save_json(DB_USERS, users)
    if uid not in user_sessions: user_sessions[uid] = 'user'
    if uid in json_fragments: del json_fragments[uid]
        
    welcome_msg = (
        f"👋 <b>नमस्ते {message.from_user.first_name}! Bot में आपका स्वागत है।</b>\n\n"
        f"🚨 <b>नोट:</b> केवल <b>JSON कोड</b> स्वीकार्य है।\n"
        f"🔒 <b>Admin Access:</b> /password\n"
        f"ℹ️ <b>मदद:</b> /help\n"
        f"🚫 <b>कैंसिल:</b> /cancel"
    )
    bot.send_message(message.chat.id, welcome_msg, parse_mode='HTML')

@bot.message_handler(commands=['password'])
def ask_password(message):
    if message.chat.type != 'private': return
    bot.reply_to(message, "🔑 <b>कृपया अपना पासवर्ड टाइप करके भेजें:</b>", parse_mode='HTML')

@bot.message_handler(commands=['cancel'])
def cancel_json(message):
    if message.chat.type != 'private': return
    uid = message.from_user.id
    if uid in json_fragments:
        del json_fragments[uid]
        bot.reply_to(message, "🚫 <b>मेमोरी साफ़ कर दी गई है।</b>\nकृपया अपना JSON दोबारा भेजें।", parse_mode='HTML')
    else:
        bot.reply_to(message, "✅ मेमोरी पहले से साफ़ है।")

@bot.message_handler(commands=['help'])
def cmd_help(m):
    if m.chat.type != 'private': return
    uid = m.from_user.id
    role = user_sessions.get(uid, 'user')
    q_count = len(quiz_buffer.get(uid, []))
    txt = f"🤖 <b>Bot Panel</b>\n👤 <b>Status:</b> {role.upper()}\n📝 <b>बनाए गए प्रश्न:</b> {q_count}\n\n"
    if role == 'admin': 
        txt += "👑 <b>Admin Panel:</b>\n"
        txt += "➡️ एक चैनल पर भेजें: /mockrise, /cpsir, /ssc, /kalam\n"
        txt += "🚀 <b>सब पर एक साथ भेजें:</b> /send_all\n\n"
        txt += "<b>Auto PDFs (Send to Channels & DM):</b>\n/pdf_daily - आज का PDF सब जगह भेजें\n/pdf_weekly - हफ्ते का PDF सब जगह भेजें\n"
        txt += "टूल्स: /edit, /stats, /broadcast, /cancel"
    else:
        txt += "👤 <b>User Panel:</b>\n/pdf_daily - Private PDF\n/edit - एडिट\n/cancel - JSON साफ़ करें"
    bot.reply_to(m, txt, parse_mode='HTML')

@bot.message_handler(commands=['stats', 'broadcast'])
def admin_tools(m):
    if m.chat.type != 'private': return
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

@bot.message_handler(commands=['mockrise', 'cpsir', 'ssc', 'kalam'])
def admin_ch_handle(m):
    if m.chat.type != 'private': return
    if user_sessions.get(m.from_user.id) != 'admin': return bot.reply_to(m, "❌ <b>Access Denied!</b>", parse_mode='HTML')
    key = m.text.replace('/', '')
    process_send(m, [key])

@bot.message_handler(commands=['send_all'])
def admin_send_all_handle(m):
    if m.chat.type != 'private': return
    if user_sessions.get(m.from_user.id) != 'admin': return bot.reply_to(m, "❌ <b>Access Denied!</b>", parse_mode='HTML')
    # Sends to all 4 defined channels at once
    process_send(m, list(CHANNELS.keys()))

@bot.message_handler(commands=['pdf_daily', 'pdf_oneliner', 'pdf_weekly'])
def cmd_pdf_smart(m):
    if m.chat.type != 'private': return
    uid = m.from_user.id
    role = user_sessions.get(uid, 'user')
    cmd = m.text.replace('/', '')
    
    # 1. Private Buffer Check 
    if uid in quiz_buffer and len(quiz_buffer[uid]) > 0:
        data = quiz_buffer[uid]
        is_oneliner = 'answer' in data[0]
        bot.reply_to(m, f"📄 Generating Private {'One-Liner' if is_oneliner else 'MCQ'} PDF for {len(data)} questions...")
        
        date_str = datetime.now().strftime("%d-%m-%Y")
        res = generate_oneliner_pdf_html(data, f"Private_OneLiner_{uid}.pdf", "MockRise One-Liners", date_str) if is_oneliner else generate_pdf_html(data, f"Private_MCQ_{uid}.pdf", "MockRise Quiz PDF", date_str)
        if res:
            with open(res, 'rb') as f: bot.send_document(m.chat.id, f, caption=f"📄 Your Custom PDF\n📅 Date: {date_str}\n🔢 Questions: {len(data)}\nBy: @MockRise")
            os.remove(res)
        return

    # 2. History Check (Channel Dispatch)
    if role != 'admin':
        return bot.reply_to(m, "❌ आपके पास कोई डेटा नहीं है। पहले JSON भेजें।")
    
    days = 7 if 'weekly' in cmd else 1
    prefix = "Weekly" if 'weekly' in cmd else "Daily"
    
    bot.reply_to(m, f"🚀 History चेक की जा रही है... सभी चैनल-वाइज PDF बनाकर डिस्पेच किए जा रहे हैं...")
    
    success = send_channel_pdfs(days, prefix, user_id=uid)
    if not success:
        bot.reply_to(m, "❌ आज के लिए इतिहास (History) में कोई प्रश्न मौजूद नहीं हैं।")

@bot.message_handler(commands=['edit'])
def cmd_edit(m):
    if m.chat.type != 'private': return
    uid = m.from_user.id
    if uid not in quiz_buffer or len(quiz_buffer[uid]) == 0: return bot.reply_to(m, "❌ आपके पास एडिट करने के लिए कोई प्रश्न नहीं है।")
    msg = bot.reply_to(m, f"Q No (1 से {len(quiz_buffer[uid])} के बीच) बताएँ जिसे एडिट करना है:")
    bot.register_next_step_handler(msg, step_edit_num)

def step_edit_num(m):
    if m.chat.type != 'private': return
    try:
        idx = int(m.text) - 1
        q = quiz_buffer[m.from_user.id][idx]
        msg = bot.reply_to(m, f"Q{idx+1} के लिए नया JSON कोड भेजें:")
        bot.register_next_step_handler(msg, step_edit_final, idx)
    except: bot.reply_to(m, "❌ गलत नंबर।")

def step_edit_final(m, idx):
    if m.chat.type != 'private': return
    try:
        quiz_buffer[m.from_user.id][idx] = json.loads(m.text)
        bot.reply_to(m, "✅ प्रश्न सफलतापूर्वक अपडेट कर दिया गया।")
    except: bot.reply_to(m, "❌ JSON फॉर्मेट गलत है, अपडेट फेल।")

# ==========================================
# 🧩 ROBUST FRAGMENTED JSON HANDLER
# ==========================================

@bot.message_handler(content_types=['text'])
def handle_text(m):
    if m.chat.type != 'private': return
    
    uid = m.from_user.id
    text = m.text.strip()
    
    if text == PASS_ADMIN: 
        user_sessions[uid] = 'admin'
        return bot.reply_to(m, "🔓 <b>Admin Panel Unlocked!</b>", parse_mode='HTML')
    
    if uid not in user_sessions: user_sessions[uid] = 'user'
    role = user_sessions[uid]

    if text.startswith('[') and uid not in json_fragments:
        json_fragments[uid] = text
    elif uid in json_fragments:
        json_fragments[uid] += text

    if uid in json_fragments:
        try:
            quiz_buffer[uid] = json.loads(json_fragments[uid])
            del json_fragments[uid] 
        except json.JSONDecodeError:
            return bot.reply_to(m, f"⏳ <b>JSON का हिस्सा प्राप्त हुआ...</b>\n(लंबाई: {len(json_fragments[uid])})\n\nबाकी का हिस्सा भेजें।\n/cancel दबाएं यदि अटक जाए।", parse_mode='HTML')
        except Exception as e:
            del json_fragments[uid]
            return bot.reply_to(m, f"❌ Error: {str(e)}\n\n/cancel करें और दोबारा भेजें।")
    else:
        if not text.startswith('/'):
            return bot.reply_to(m, "❌ <b>कृपया केवल JSON फॉर्मेट (`[...]`) में ही प्रश्न भेजें।</b>", parse_mode='HTML')

    if uid in quiz_buffer and not text.startswith('/'):
        q_count = len(quiz_buffer[uid])
        msg = f"✅ <b>डेटा प्राप्त हुआ ({q_count} प्रश्न तैयार हैं)</b>\n\n"
        msg += f"✏️ /edit - प्रश्नों में सुधार करें\n"
        msg += f"📄 /pdf_daily - (Private) PDF बनाएँ\n\n"
        
        if role == 'admin':
            msg += "👇 <b>चैनल पर भेजें:</b>\n/mockrise, /cpsir, /ssc, /kalam\n"
            msg += "🚀 <b>सब पर एक साथ भेजें:</b> /send_all"
            
        bot.reply_to(m, msg, parse_mode='HTML')

if __name__ == "__main__":
    keep_alive()
    bot.infinity_polling()
