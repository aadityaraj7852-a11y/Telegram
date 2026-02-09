import telebot
import json
import time
import os
import threading
import requests
from flask import Flask
from datetime import datetime, timedelta
from weasyprint import HTML, CSS
from jinja2 import Template

# ==========================================
# ⚙️ CONFIGURATION
# ==========================================

BOT_TOKEN = "7654075050:AAFt3hMFSYcoHPRcrNUfGGVpy859hjKotok"
MAIN_CHANNEL_ID = "@upsc_ssc_cgl_mts_cgl_chsl_gk"

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
    return "✅ Bot is Running with WeasyPrint!"

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
# 📄 PDF ENGINE (HTML -> PDF via WeasyPrint)
# ==========================================

def check_font():
    """Downloads Hindi font for Server."""
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
    
    # 🎨 HTML Template (Design)
    html_template = """
    <!DOCTYPE html>
    <html lang="hi">
    <head>
        <meta charset="UTF-8">
        <style>
            @font-face {
                font-family: 'HindiFont';
                src: url('file://{{ font_path }}');
            }
            body {
                font-family: 'HindiFont', sans-serif;
                margin: 40px;
                font-size: 14px;
            }
            .header {
                text-align: center;
                background-color: #1a237e; /* Dark Blue */
                color: white;
                padding: 15px;
                border-radius: 5px;
                margin-bottom: 20px;
            }
            .header h1 { margin: 0; font-size: 24px; }
            .header p { margin: 5px 0 0; font-size: 12px; opacity: 0.8; }
            
            .meta {
                display: flex;
                justify-content: space-between;
                border-bottom: 2px solid #333;
                padding-bottom: 10px;
                margin-bottom: 20px;
                font-weight: bold;
            }
            
            .question-block {
                margin-bottom: 25px;
                page-break-inside: avoid; /* Keep Q & A together */
            }
            
            .q-text {
                font-weight: bold;
                font-size: 16px;
                margin-bottom: 10px;
                color: #000;
            }
            
            .options {
                margin-left: 20px;
                margin-bottom: 10px;
            }
            .option {
                margin-bottom: 5px;
            }
            
            .solution-box {
                background-color: #f1f8e9; /* Light Greenish/Gray */
                border: 1px solid #c5e1a5;
                padding: 10px;
                border-radius: 5px;
                margin-top: 5px;
            }
            .ans-label {
                color: #2e7d32; /* Green */
                font-weight: bold;
            }
            .exp-label {
                color: #1565c0; /* Blue */
                font-weight: bold;
                margin-left: 10px;
            }
            .exp-text {
                margin-top: 5px;
                color: #333;
                font-size: 13px;
                line-height: 1.4;
            }
            .footer {
                position: fixed;
                bottom: 0;
                width: 100%;
                text-align: center;
                font-size: 10px;
                color: gray;
            }
        </style>
    </head>
    <body>
        <div class="header">
            <h1>{{ title }}</h1>
            <p>@MockRise Telegram Channel | Exam Series</p>
        </div>
        
        <div class="meta">
            <span>Date: {{ date }}</span>
            <span>Total Questions: {{ total }}</span>
        </div>

        {% for item in items %}
        <div class="question-block">
            <div class="q-text">Q{{ loop.index }}. {{ item.data.question }}</div>
            
            <div class="options">
                {% set labels = ['(A)', '(B)', '(C)', '(D)'] %}
                {% for opt in item.data.options %}
                    <div class="option">
                        <strong>{{ labels[loop.index0] if loop.index0 < 4 else loop.index }}</strong> {{ opt }}
                    </div>
                {% endfor %}
            </div>
            
            <div class="solution-box">
                {% set ans_idx = item.data.correct_index %}
                <span class="ans-label">उत्तर: ({{ labels[ans_idx] if ans_idx < 4 else ans_idx+1 }})</span>
                <span class="exp-label">| व्याख्या:</span>
                <div class="exp-text">
                    {{ item.data.explanation }}
                </div>
            </div>
            
            <hr style="border: 0; border-top: 1px solid #eee; margin-top: 20px;">
        </div>
        {% endfor %}
        
        <div class="footer">
            Generated by MockRise Bot
        </div>
    </body>
    </html>
    """
    
    # 🛠 Render HTML
    template = Template(html_template)
    rendered_html = template.render(
        title=title_text,
        date=datetime.now().strftime('%d-%m-%Y'),
        total=len(data_list),
        items=data_list,
        font_path=font_path
    )
    
    # 🖨 Convert to PDF
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
    bot.reply_to(message, "🤖 Bot Started! Send JSON to begin.")

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

# --- PDF COMMAND (UPDATED) ---
@bot.message_handler(commands=['make_pdf'])
def cmd_make_pdf(m):
    bot.reply_to(m, "⏳ Generating PDF (HTML Engine)...")
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
    
    if not pdf_data: return bot.reply_to(m, "❌ Empty Data")
    
    fname = f"Smart_Quiz_{datetime.now().strftime('%d%m')}.pdf"
    
    # Generate using WeasyPrint
    result_file = generate_pdf_html(pdf_data, fname, "MockRise Exam Series")
    
    if result_file:
        with open(result_file, 'rb') as f:
            bot.send_document(m.chat.id, f, caption=f"📄 HQ PDF Generated (Selectable Text)")
        # Auto Broadcast
        with open(result_file, 'rb') as f:
            bot.send_document(MAIN_CHANNEL_ID, f, caption="📚 Latest PDF Update")
    else:
        bot.reply_to(m, "❌ PDF Generation Failed (Server Error).")

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
