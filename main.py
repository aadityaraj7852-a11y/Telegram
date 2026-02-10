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

# ✅ Channels List
CHANNELS = {
    'mockrise': {'id': '@mockrise', 'name': 'MockRise Main'},
    'upsc': {'id': '@upsc_ssc_cgl_mts_cgl_chsl_gk', 'name': 'UPSC/IAS'},
    'ssc': {'id': '@ssc_cgl_chsl_mts_ntpc_upsc', 'name': 'SSC CGL/MTS'},
    'rssb': {'id': '@ldc_reet_ras_2ndgrade_kalam', 'name': 'RSSB/LDC/REET'},
    'springboard': {'id': '@rssb_gk_rpsc_springboar', 'name': 'Mockrise'},
    'kalam': {'id': '@rajasthan_gk_kalam_reet_ldc_ras', 'name': 'Mockrise'}
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
    return "✅ Bot is Running (Edit Mode + Clean PDF)!"

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
# 🎮 COMMANDS & MENU
# ==========================================

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    help_text = """
🤖 <b>MockRise Pro Bot</b>

📝 <b>Editing:</b>
/edit - Edit any question (Change Q, Options, Answer)
/list - View current questions

📂 <b>PDF Tools:</b>
/pdf_daily - Today's Quiz
/pdf_weekly - Last 7 Days
/pdf_custom - Custom Range

📢 <b>Sending:</b>
/rssb, /ssc, /upsc, /springboard, /kalam
/bulk_send - Send to All Channels

🛑 <b>Control:</b>
/stop - Clear JSON
"""
    bot.reply_to(message, help_text, parse_mode='HTML')

@bot.message_handler(commands=['stop'])
def cmd_stop(m):
    uid = m.from_user.id
    if uid in quiz_buffer:
        del quiz_buffer[uid]
        bot.reply_to(m, "🛑 <b>Buffer Cleared.</b>", parse_mode='HTML')
    else:
        bot.reply_to(m, "Buffer already empty.")

@bot.message_handler(commands=['list'])
def cmd_list(m):
    uid = m.from_user.id
    if uid not in quiz_buffer: return bot.reply_to(m, "📭 Buffer Empty.")
    
    text = "📋 <b>Current Questions:</b>\n\n"
    for i, q in enumerate(quiz_buffer[uid]):
        text += f"<b>{i+1}.</b> {q.get('question')[:50]}...\n"
    bot.reply_to(m, text, parse_mode='HTML')

# ==========================================
# ✏️ EDIT FEATURE
# ==========================================

@bot.message_handler(commands=['edit'])
def cmd_edit_start(m):
    uid = m.from_user.id
    if uid not in quiz_buffer or not quiz_buffer[uid]:
        return bot.reply_to(m, "❌ <b>Buffer is Empty!</b> Upload JSON first.", parse_mode='HTML')
    
    msg = bot.reply_to(m, f"✏️ <b>Edit Mode</b>\n\nSend the <b>Question Number</b> (1 - {len(quiz_buffer[uid])}) you want to edit:", parse_mode='HTML')
    bot.register_next_step_handler(msg, step_edit_number)

def step_edit_number(m):
    uid = m.from_user.id
    if m.text.lower() == '/cancel': return bot.reply_to(m, "🚫 Edit Cancelled.")
    
    try:
        idx = int(m.text) - 1
        if 0 <= idx < len(quiz_buffer[uid]):
            q_data = quiz_buffer[uid][idx]
            q_str = json.dumps(q_data, indent=2, ensure_ascii=False)
            
            msg = bot.reply_to(m, 
                f"📝 <b>Editing Question {idx+1}:</b>\n<pre>{q_str}</pre>\n\n👇 <b>Send the NEW JSON</b> code to replace this question:", 
                parse_mode='HTML'
            )
            bot.register_next_step_handler(msg, step_edit_save, idx)
        else:
            bot.reply_to(m, "❌ Invalid Number. Try /edit again.")
    except:
        bot.reply_to(m, "❌ Please send a number.")

def step_edit_save(m, idx):
    uid = m.from_user.id
    try:
        # Cleaner
        clean_text = m.text.replace("‘", "'").replace("’", "'").replace("“", '"').replace("”", '"')
        new_q = json.loads(clean_text)
        
        # Check basic fields
        if 'question' not in new_q: raise ValueError("Missing 'question' field")
        
        quiz_buffer[uid][idx] = new_q
        bot.reply_to(m, f"✅ <b>Question {idx+1} Updated!</b>\nCheck with /list or send now.", parse_mode='HTML')
    except Exception as e:
        bot.reply_to(m, f"❌ <b>Update Failed:</b> Invalid JSON.\nError: {e}\nTry /edit again.", parse_mode='HTML')

# ==========================================
# 🚀 SENDING LOGIC
# ==========================================

def safe_send_poll(target_chat, question, options, correct_index, explanation):
    try:
        if len(question) > 250:
            bot.send_message(target_chat, f"<b>Q.</b> {question}", parse_mode='HTML')
            poll_question = "Q. ऊपर दिए गए प्रश्न का उत्तर दें:"
        else:
            poll_question = question

        if len(explanation) > 190:
            poll_explanation = "Solution 👇 (Check Reply)"
            send_exp_separately = True
        else:
            poll_explanation = explanation
            send_exp_separately = False

        poll_msg = bot.send_poll(
            chat_id=target_chat,
            question=poll_question,
            options=options,
            type='quiz',
            correct_option_id=correct_index,
            explanation=poll_explanation,
            is_anonymous=True
        )

        if send_exp_separately:
            exp_text = f"💡 <b>Detailed Solution:</b>\n\n{explanation}"
            bot.send_message(target_chat, exp_text, reply_to_message_id=poll_msg.message_id, parse_mode='HTML')
            
        return True
    except Exception as e:
        print(f"Error: {e}")
        return False

def process_send(message, key):
    uid = message.from_user.id
    if uid not in quiz_buffer: return bot.reply_to(message, "❌ No JSON data found.")

    target = CHANNELS[key]['id']
    name = CHANNELS[key]['name']
    bot.reply_to(message, f"📤 Sending to <b>{name}</b>...", parse_mode='HTML')
    
    data = quiz_buffer[uid]
    success = 0
    
    for i, item in enumerate(data):
        q = item.get('question', '')
        opts = item.get('options', []) or item.get('option', [])
        ans = item.get('correct_index', 0)
        exp = item.get('explanation', '')
        
        if not q.strip().lower().startswith('q'): q_display = f"Q{i+1}. {q}"
        else: q_display = q

        if safe_send_poll(target, q_display, opts, ans, exp):
            success += 1
            time.sleep(2)

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
# 📅 SMART PDF DISTRIBUTION
# ==========================================

def smart_distribute(m, data, title_prefix, date_label):
    if not data: return bot.reply_to(m, "❌ No data found.")

    bot.reply_to(m, f"⚙️ <b>Processing...</b>\nDate: {date_label}", parse_mode='HTML')

    # 1. Master PDF (Admin)
    master_fname = f"Master_{datetime.now().strftime('%H%M%S')}.pdf"
    res = generate_pdf_html(data, master_fname, f"{title_prefix} (All Data)", date_label)
    
    if res:
        caption = f"🗂 <b>Master PDF</b>\n📅 {date_label}\nBy: @MockRise"
        with open(res, 'rb') as f:
            bot.send_document(m.chat.id, f, caption=caption, parse_mode='HTML')
    
    # 2. Channel Distribution (Clean Names)
    channel_data_map = {}
    for item in data:
        ch_key = item.get('channel')
        if ch_key:
            if ch_key not in channel_data_map: channel_data_map[ch_key] = []
            channel_data_map[ch_key].append(item)
            
    sent_count = 0
    for ch_key, ch_items in channel_data_map.items():
        if ch_key in CHANNELS:
            channel_info = CHANNELS[ch_key]
            ch_fname = f"{ch_key}.pdf"
            
            # ✅ FIX: Removing Channel Name from PDF Title
            # Title inside PDF will be generic, e.g., "Daily Quiz" or "Weekly Compilation"
            clean_title = title_prefix 
            
            ch_pdf = generate_pdf_html(ch_items, ch_fname, clean_title, date_label)
            
            if ch_pdf:
                try:
                    caption_ch = (
                        f"📄 <b>{title_prefix}</b>\n"
                        f"📅 Date: {date_label}\n"
                        f"🔢 Questions: {len(ch_items)}\n"
                        f"By: @MockRise"
                    )
                    with open(ch_pdf, 'rb') as f:
                        bot.send_document(channel_info['id'], f, caption=caption_ch, parse_mode='HTML')
                    sent_count += 1
                    time.sleep(2)
                except Exception as e:
                    bot.send_message(m.chat.id, f"❌ Failed to send to {channel_info['name']}: {e}")

    if sent_count > 0:
        bot.reply_to(m, "🎉 <b>Distribution Complete!</b>", parse_mode='HTML')
    else:
        bot.reply_to(m, "⚠️ No separate channel data found.")

@bot.message_handler(commands=['pdf_daily'])
def cmd_pdf_daily(m):
    today = datetime.now().strftime("%Y-%m-%d")
    today_disp = datetime.now().strftime("%d-%m-%Y")
    hist = load_json(DB_HISTORY)
    data = [h for h in hist if h['timestamp'].startswith(today)]
    smart_distribute(m, data, "Daily Quiz", today_disp)

@bot.message_handler(commands=['pdf_weekly'])
def cmd_pdf_weekly(m):
    end = datetime.now()
    start = end - timedelta(days=7)
    hist = load_json(DB_HISTORY)
    data = [h for h in hist if start <= datetime.strptime(h['timestamp'], "%Y-%m-%d %H:%M:%S") <= end]
    label = f"{start.strftime('%d-%m-%Y')} to {end.strftime('%d-%m-%Y')}"
    smart_distribute(m, data, "Weekly Compilation", label)

@bot.message_handler(commands=['pdf_custom'])
def cmd_pdf_custom(m):
    msg = bot.send_message(m.chat.id, "📅 Send Date Range (DD-MM-YYYY to DD-MM-YYYY):")
    bot.register_next_step_handler(msg, step_pdf_range)

def step_pdf_range(m):
    try:
        txt = m.text.lower().replace('to', ' ').strip()
        parts = txt.split()
        s = datetime.strptime(parts[0], "%d-%m-%Y")
        e = datetime.strptime(parts[1], "%d-%m-%Y") + timedelta(days=1)
        hist = load_json(DB_HISTORY)
        data = [h for h in hist if s <= datetime.strptime(h['timestamp'], "%Y-%m-%d %H:%M:%S") < e]
        label = f"{parts[0]} to {parts[1]}"
        smart_distribute(m, data, "Question Bank", label)
    except: bot.reply_to(m, "❌ Error/Invalid Format.")

@bot.message_handler(content_types=['text'])
def handle_json(m):
    if m.text.strip().startswith('['):
        try:
            clean_text = m.text.replace("‘", "'").replace("’", "'").replace("“", '"').replace("”", '"')
            data = json.loads(clean_text)
            quiz_buffer[m.from_user.id] = data
            msg = (f"✅ <b>JSON Received ({len(data)} Qs)</b>\n\n"
                   f"✏️ <b>Edit:</b> /edit\n"
                   f"👇 <b>Send:</b> /rssb, /ssc, /bulk_send")
            bot.reply_to(m, msg, parse_mode='HTML')
        except Exception as e:
            bot.reply_to(m, f"❌ <b>Invalid JSON</b>\n{e}", parse_mode='HTML')

if __name__ == "__main__":
    keep_alive()
    bot.infinity_polling()
