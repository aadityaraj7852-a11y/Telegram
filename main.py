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
    return "✅ Bot is Running with Premium PDF Engine!"

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
# 📄 PDF ENGINE (PREMIUM HTML TEMPLATE)
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
    
    # 🎨 PREMIUM HTML TEMPLATE
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
                margin: 20mm 15mm; /* Reduced margins: Top/Bottom 20mm, Left/Right 15mm */
                size: A4;
                @bottom-center {
                    content: "Page " counter(page) " of " counter(pages);
                    font-size: 9pt;
                    color: #666;
                    margin-top: 10px;
                }
            }

            body {
                font-family: 'Noto Sans Devanagari', sans-serif;
                font-size: 11pt;
                line-height: 1.5;
                color: #222;
                margin: 0;
            }

            .header {
                background: linear-gradient(135deg, #1565c0, #0d47a1); /* Premium Blue Gradient */
                color: white;
                padding: 18px;
                border-radius: 6px;
                margin-bottom: 25px;
                text-align: center;
                box-shadow: 0 3px 5px rgba(0,0,0,0.1);
            }
            .header h1 { margin: 0; font-size: 22pt; font-weight: bold; }
            .header p { margin: 8px 0 0; font-size: 10pt; opacity: 0.9; }
            
            .meta {
                display: flex;
                justify-content: space-between;
                border-bottom: 2px solid #e0e0e0;
                padding-bottom: 10px;
                margin-bottom: 25px;
                font-weight: 600;
                color: #444;
                font-size: 10pt;
            }
            
            .question-block {
                margin-bottom: 30px;
                page-break-inside: avoid;
            }
            
            .q-num { color: #1565c0; font-weight: bold; font-size: 12pt; margin-right: 5px; }
            .q-text { font-weight: 600; font-size: 12pt; display: inline; }
            
            .options { margin-left: 25px; margin-top: 12px; margin-bottom: 15px; }
            .option { margin-bottom: 8px; display: flex; align-items: baseline; }
            .opt-label { font-weight: bold; color: #555; margin-right: 10px; min-width: 25px; }
            
            /* --- Premium Solution Box --- */
            .solution-box {
                background-color: #f1f8e9; /* Very Light Green */
                border-left: 4px solid #43a047; /* Strong Green Border */
                padding: 12px 15px;
                border-radius: 4px;
                margin-top: 10px;
                box-shadow: 0 1px 3px rgba(0,0,0,0.05);
            }
            .ans-section {
                font-weight: bold;
                color: #2e7d32;
                margin-bottom: 6px;
                font-size: 11pt;
            }
            .exp-section { color: #333; display: flex; }
            .exp-label { font-weight: bold; color: #1565c0; margin-right: 8px; min-width: 55px;}
            .exp-text { font-size: 10.5pt; }

            hr { border: 0; border-top: 1px solid #eee; margin: 25px 0; }
        </style>
    </head>
    <body>
        <div class="header">
            <h1>{{ title }}</h1>
            <p>@MockRise Telegram Channel | Premium Exam Series</p>
        </div>
        
        <div class="meta">
            <span>📅 Date: {{ date }}</span>
            <span>🔢 Total Questions: {{ total }}</span>
        </div>

        {% for item in items %}
        <div class="question-block">
            <div>
                <span class="q-num">Q{{ loop.index }}.</span>
                <div class="q-text">{{ item.data.question }}</div>
            </div>
            
            <div class="options">
                {% set labels = ['(A)', '(B)', '(C)', '(D)'] %}
                {% for opt in item.data.options %}
                    <div class="option">
                        <span class="opt-label">{{ labels[loop.index0] if loop.index0 < 4 else loop.index }}</span>
                        <span>{{ opt }}</span>
                    </div>
                {% endfor %}
            </div>
            
            <div class="solution-box">
                {% set ans_idx = item.data.correct_index %}
                {% set ans_labels = ['A', 'B', 'C', 'D'] %}
                <div class="ans-section">
                    ✅ सही उत्तर: ({{ ans_labels[ans_idx] if ans_idx < 4 else ans_idx+1 }})
                </div>
                {% if item.data.explanation %}
                <div class="exp-section">
                    <span class="exp-label">💡 व्याख्या:</span>
                    <div class="exp-text">{{ item.data.explanation }}</div>
                </div>
                {% endif %}
            </div>
        </div>
        {% if not loop.last %}<hr>{% endif %}
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
        # Use base_url="." to resolve local file paths for fonts
        HTML(string=rendered_html, base_url=".").write_pdf(filename)
        return filename
    except Exception as e:
        print(f"PDF Error: {e}")
        # Fallback to a simpler call if base_url fails on some setups
        try:
            HTML(string=rendered_html).write_pdf(filename)
            return filename
        except:
            return None

# ==========================================
# 🎮 COMMANDS
# ==========================================

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    bot.reply_to(message, "🤖 Premium PDF Bot Started! Send JSON to begin.")

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
    bot.reply_to(m, "⏳ Generating Premium PDF...")
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
    
    if not pdf_data: return bot.reply_to(m, "❌ Empty Data. Send JSON first.")
    
    fname = f"MockRise_Premium_{datetime.now().strftime('%d%m')}.pdf"
    
    # Generate using Premium HTML Engine
    result_file = generate_pdf_html(pdf_data, fname, "MockRise Exam Series")
    
    if result_file:
        with open(result_file, 'rb') as f:
            bot.send_document(m.chat.id, f, caption=f"✨ Premium PDF Ready! ({len(pdf_data)} Qs)")
        # Auto Broadcast
        with open(result_file, 'rb') as f:
            bot.send_document(MAIN_CHANNEL_ID, f, caption="📚 Latest Premium PDF Update")
    else:
        bot.reply_to(m, "❌ PDF Generation Failed. Check server logs.")

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
        except: bot.reply_to(m, "❌ Invalid JSON. Please check format.")

if __name__ == "__main__":
    keep_alive()
    bot.infinity_polling()
