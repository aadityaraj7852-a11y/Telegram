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

CHANNELS = {
    'mockrise': {'id': MAIN_CHANNEL_ID, 'name': 'MockRise Main'},
    'rssb': {'id': MAIN_CHANNEL_ID, 'name': 'RSSB Springboard'},
    'kalam': {'id': MAIN_CHANNEL_ID, 'name': 'Kalam Academy'},
    'ssc': {'id': MAIN_CHANNEL_ID, 'name': 'SSC Exams'},
    'upsc': {'id': MAIN_CHANNEL_ID, 'name': 'UPSC/IAS'},
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
    return "✅ Bot is Running with Custom UI!"

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
    cutoff = datetime.now() - timedelta(days=30)
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
# 📄 PDF ENGINE (CUSTOM UI TEMPLATE)
# ==========================================

def check_font():
    """Downloads Hindi font."""
    if not os.path.exists(FONT_FILE):
        print("📥 Downloading Hindi Font...")
        url = "https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSansDevanagari/NotoSansDevanagari-Regular.ttf"
        try:
            r = requests.get(url)
            with open(FONT_FILE, 'wb') as f:
                f.write(r.content)
        except: pass
    return os.path.abspath(FONT_FILE)

def generate_pdf_html(data_list, filename, title_text):
    font_path = check_font()
    
    # 🎨 YOUR CUSTOM HTML TEMPLATE
    html_template = """
    <!DOCTYPE html>
    <html lang="hi">
    <head>
    <meta charset="UTF-8">
    <style>
        @font-face {
            font-family: 'Noto Sans Devanagari';
            src: url('file://{{ font_path }}');
        }

        @page {
            size: A4;
            margin: 20mm 15mm;

            /* Footer page number circle */
            @bottom-center {
                content: counter(page);
                background: #e0e0e0;
                border-radius: 50%;
                padding: 6px 12px;
                font-size: 10pt;
                font-weight: bold;
            }
        }

        body {
            font-family: "Noto Sans Devanagari", sans-serif;
            font-size: 11pt;
            color: #222;
            margin: 0;
        }

        /* Header layout */
        .header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 5px;
        }

        /* Logo spacing */
        .logo img {
            width: 70px;
            height: auto;
            margin-right: 15px;
        }

        /* Title */
        .title {
            text-align: center;
            flex-grow: 1;
        }

        .title h1 {
            margin: 0;
            font-size: 18pt;
            color: #000;
        }

        .title p {
            margin: 3px 0;
            font-size: 10pt;
            color: #555;
        }

        /* Meta row */
        .meta {
            display: flex;
            justify-content: space-between;
            font-weight: bold;
            font-size: 10pt;
            margin-top: 15px;
            color: #333;
        }

        /* Line */
        .top-line {
            border-bottom: 2px solid black;
            margin: 8px 0 20px 0;
        }

        /* Question style */
        .question-block {
            margin-bottom: 25px;
            page-break-inside: avoid;
        }

        .q-text {
            font-weight: bold;
            font-size: 11pt;
            margin-bottom: 5px;
        }

        .options {
            margin-left: 20px;
            margin-top: 8px;
        }

        .option {
            margin-bottom: 4px;
        }

        .solution-box {
            border: 2px solid #333;
            padding: 10px;
            border-radius: 8px;
            margin-top: 10px;
            background-color: #fff;
        }

        .answer {
            font-weight: bold;
            margin-bottom: 5px;
            color: #000;
        }
    </style>
    </head>

    <body>

    <div class="header">
        <div class="logo">
            <img src="https://blogger.googleusercontent.com/img/b/R29vZ2xl/AVvXsEjm8_FXoAwwGHMEMe-XjUwLHyZtqfl-2QCBeve69L-k-DTJ2nbWaMJ56HJYvnIC0He2tHMWVo91xwJUkTcW9B-PmDTbVBUR0WxHLF0IFZebbgQw5RT2foPwzVEVnwKOeospWPq0LokG_Xy3muy6T1I1bQ_gJp-fsP5u1abLM0qhu1kP66yxXqffeclp-90/s640/1000002374.jpg">
        </div>

        <div class="title">
            <h1>{{ title }}</h1>
            <p>@MockRise Telegram Channel</p>
        </div>

        <div style="width:70px;"></div> </div>

    <div class="meta">
        <div>Generated Date: {{ date }}</div>
        <div>Total Questions: {{ total }}</div>
    </div>

    <div class="top-line"></div>

    {% for item in items %}
    <div class="question-block">
        <div class="q-text">Q{{ loop.index }}. {{ item.data.question }}</div>
        
        <div class="options">
            {% set labels = ['(A)', '(B)', '(C)', '(D)'] %}
            {% for opt in item.data.options %}
                <div class="option">
                    {{ labels[loop.index0] if loop.index0 < 4 else loop.index }} {{ opt }}
                </div>
            {% endfor %}
        </div>
        
        <div class="solution-box">
            {% set ans_idx = item.data.correct_index %}
            <div class="answer">उत्तर: ({{ labels[ans_idx] if ans_idx < 4 else ans_idx+1 }})</div>
            {{ item.data.explanation }}
        </div>
    </div>
    {% endfor %}

    </body>
    </html>
    """
    
    # 🛠 Render & Convert
    template = Template(html_template)
    rendered_html = template.render(
        title=title_text,
        date=datetime.now().strftime('%d-%m-%Y'),
        total=len(data_list),
        items=data_list,
        font_path=font_path
    )
    
    try:
        HTML(string=rendered_html, base_url=".").write_pdf(filename)
        return filename
    except Exception as e:
        print(f"PDF Error: {e}")
        return None

# ==========================================
# 🎮 COMMANDS
# ==========================================

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    bot.reply_to(message, "🤖 UI Updated! Send JSON to generate PDF.")

# --- CHANNELS SENDING LOGIC ---
def process_send(message, key):
    uid = message.from_user.id
    if uid not in quiz_buffer: return bot.reply_to(message, "❌ No JSON found.")

    bot.reply_to(message, f"🚀 Sending to {CHANNELS[key]['name']}...")
    data = quiz_buffer[uid]
    target = CHANNELS[key]['id']
    success = 0
    
    for i, item in enumerate(data):
        try:
            q = item.get('question','')
            opts = item.get('options',[])
            ans = item.get('correct_index',0)
            exp = item.get('explanation','')
            
            if len(exp)>190:
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
        bot.reply_to(message, f"✅ Sent {success} questions.")

@bot.message_handler(commands=['rssb'])
def c_rssb(m): process_send(m, 'rssb')
@bot.message_handler(commands=['ssc'])
def c_ssc(m): process_send(m, 'ssc')
@bot.message_handler(commands=['upsc'])
def c_upsc(m): process_send(m, 'upsc')
@bot.message_handler(commands=['kalam'])
def c_kalam(m): process_send(m, 'kalam')
@bot.message_handler(commands=['mockrise'])
def c_mock(m): process_send(m, 'mockrise')

# --- PDF COMMAND ---
@bot.message_handler(commands=['make_pdf'])
def cmd_make_pdf(m):
    bot.reply_to(m, "⏳ Generating PDF (Custom UI)...")
    uid = m.from_user.id
    hist = load_json(DB_HISTORY)
    cutoff = datetime.now() - timedelta(days=7)
    pdf_data = [h for h in hist if datetime.strptime(h['timestamp'], "%Y-%m-%d %H:%M:%S") > cutoff]
    
    if uid in quiz_buffer:
        current_data = quiz_buffer[uid]
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for q in current_data:
            if not any(h['data'].get('question') == q.get('question') for h in pdf_data):
                pdf_data.append({'timestamp': timestamp, 'channel': 'CURRENT', 'data': q})
    
    if not pdf_data: return bot.reply_to(m, "❌ Empty Data.")
    
    fname = f"Smart_Quiz_{datetime.now().strftime('%d%m')}.pdf"
    
    # Generate using Custom HTML Engine
    result_file = generate_pdf_html(pdf_data, fname, "Weekly Compilation")
    
    if result_file:
        with open(result_file, 'rb') as f:
            bot.send_document(m.chat.id, f, caption=f"📄 Custom UI PDF ({len(pdf_data)} Qs)")
        # Auto Broadcast
        with open(result_file, 'rb') as f:
            bot.send_document(MAIN_CHANNEL_ID, f, caption="📚 Latest PDF Update")
    else:
        bot.reply_to(m, "❌ PDF Generation Failed.")

@bot.message_handler(commands=['bulk_send'])
def cmd_bulk(m):
    if m.from_user.id not in quiz_buffer: return bot.reply_to(m, "❌ No JSON.")
    process_send(m, 'mockrise')
    bot.reply_to(m, "✅ Done.")

@bot.message_handler(content_types=['text'])
def handle_json(m):
    if m.text.strip().startswith('['):
        try:
            data = json.loads(m.text)
            quiz_buffer[m.from_user.id] = data
            bot.reply_to(m, f"✅ JSON Received ({len(data)} Qs)\n\n👇 Click:\n/rssb, /make_pdf")
        except: bot.reply_to(m, "❌ Invalid JSON")

if __name__ == "__main__":
    keep_alive()
    bot.infinity_polling()
