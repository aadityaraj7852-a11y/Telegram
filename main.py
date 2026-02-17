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
    'holas': {'id': '@upsc_hindi_quizz', 'name': 'Holas (UPSC Hindi)'} # 🆕 New Channel
}

# Files
DB_STATS = "user_stats.json"
DB_HISTORY = "history.json"
FONT_FILE = "NotoSansDevanagari-Regular.ttf"

# Memory
quiz_buffer = {}
json_fragments = {}
user_sessions = {} # To store login status: {user_id: 'admin' or 'limited'}

bot = telebot.TeleBot(BOT_TOKEN)

# ==========================================
# 🌐 FLASK SERVER
# ==========================================

app = Flask('')

@app.route('/')
def home():
    return "✅ Bot is Running (Password Protected + Holas Channel)!"

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
# 🔒 AUTHENTICATION HELPER
# ==========================================

def is_auth(m):
    """Check if user is logged in."""
    return m.from_user.id in user_sessions

def get_role(m):
    """Get user role: 'admin' or 'limited' or None."""
    return user_sessions.get(m.from_user.id)

def check_access(m, required_role='limited'):
    """
    Checks if user has permission.
    required_role='limited' -> Both Admin and Limited can access.
    required_role='admin' -> Only Admin can access.
    """
    if not is_auth(m):
        bot.reply_to(m, "🔒 <b>Locked!</b> Please enter password to unlock.\nUse /start to login.", parse_mode='HTML')
        return False
    
    role = get_role(m)
    
    if required_role == 'admin' and role != 'admin':
        bot.reply_to(m, "🚫 <b>Access Denied!</b> This command is for Admins (7852) only.", parse_mode='HTML')
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

@bot.message_handler(commands=['start'])
def send_welcome(message):
    uid = message.from_user.id
    
    # Reset Session on Start
    if uid in user_sessions: del user_sessions[uid]
    
    msg = bot.send_message(
        message.chat.id, 
        "🔒 <b>Bot Locked</b>\n\nकृपया अपना पासवर्ड दर्ज करें:", 
        parse_mode='HTML'
    )
    # Don't register next step handler for everything, let the text handler catch the password

@bot.message_handler(commands=['help'])
def send_help(message):
    if not check_access(message): return
    
    role = get_role(message)
    
    help_text = f"""
🤖 <b>MockRise Pro Bot</b>
🔑 Status: <b>{role.upper()}</b>

📝 <b>Editing:</b>
/edit - Edit Questions
/list - View Questions

📂 <b>PDF Tools:</b>
/pdf_daily - Today's Quiz
/pdf_weekly - Last 7 Days
/pdf_custom - Custom Range

📢 <b>Sending:</b>
/holas - Send to Holas (UPSC Hindi) ✅
"""
    if role == 'admin':
        help_text += """
/rssb, /ssc, /upsc, /springboard, /kalam
/bulk_send - Send to ALL Channels 🚀
"""
    
    help_text += "\n🛑 <b>Control:</b>\n/stop - Clear Data\n/logout - Exit"
    bot.reply_to(message, help_text, parse_mode='HTML')

@bot.message_handler(commands=['logout'])
def cmd_logout(m):
    if m.from_user.id in user_sessions:
        del user_sessions[m.from_user.id]
    bot.reply_to(m, "🔒 <b>Logged Out.</b> Use /start to login again.", parse_mode='HTML')

@bot.message_handler(commands=['stop', 'clear_temp'])
def cmd_stop(m):
    if not check_access(m): return
    
    uid = m.from_user.id
    if uid in quiz_buffer: del quiz_buffer[uid]
    if uid in json_fragments: del json_fragments[uid]
    
    bot.reply_to(m, "🛑 <b>All Buffers Cleared.</b> Ready for fresh data.", parse_mode='HTML')

@bot.message_handler(commands=['list'])
def cmd_list(m):
    if not check_access(m): return
    
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
    if not check_access(m): return
    
    uid = m.from_user.id
    if uid not in quiz_buffer or not quiz_buffer[uid]:
        return bot.reply_to(m, "❌ <b>Buffer is Empty!</b> Upload JSON first.", parse_mode='HTML')
    
    msg = bot.reply_to(m, f"✏️ <b>Edit Mode</b>\n\nSend the <b>Question Number</b> (1 - {len(quiz_buffer[uid])}):", parse_mode='HTML')
    bot.register_next_step_handler(msg, step_edit_number)

def step_edit_number(m):
    if not check_access(m): return
    uid = m.from_user.id
    if m.text.lower() == '/cancel': return bot.reply_to(m, "🚫 Edit Cancelled.")
    
    try:
        idx = int(m.text) - 1
        if 0 <= idx < len(quiz_buffer[uid]):
            q_data = quiz_buffer[uid][idx]
            q_str = json.dumps(q_data, indent=2, ensure_ascii=False)
            
            msg = bot.reply_to(m, 
                f"📝 <b>Editing Question {idx+1}:</b>\n<pre>{q_str}</pre>\n\n👇 <b>Send NEW JSON</b>:", 
                parse_mode='HTML'
            )
            bot.register_next_step_handler(msg, step_edit_save, idx)
        else:
            bot.reply_to(m, "❌ Invalid Number.")
    except:
        bot.reply_to(m, "❌ Please send a number.")

def step_edit_save(m, idx):
    if not check_access(m): return
    uid = m.from_user.id
    try:
        clean_text = m.text.replace("‘", "'").replace("’", "'").replace("“", '"').replace("”", '"')
        new_q = json.loads(clean_text)
        if 'question' not in new_q: raise ValueError("Missing 'question' field")
        
        quiz_buffer[uid][idx] = new_q
        bot.reply_to(m, f"✅ <b>Updated!</b> Check /list.", parse_mode='HTML')
    except Exception as e:
        bot.reply_to(m, f"❌ <b>Failed:</b> {e}", parse_mode='HTML')

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
    # AUTH CHECK
    role = get_role(message)
    if not role: return bot.reply_to(message, "🔒 Login Required. Send Password.")
    
    # 9637 RESTRICTION: Can only send to 'holas'
    if role == 'limited' and key != 'holas':
        return bot.reply_to(message, "🚫 <b>Access Denied!</b> You can only use /holas", parse_mode='HTML')
        
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

# --- CHANNEL HANDLERS ---
@bot.message_handler(commands=['holas'])
def c_holas(m): process_send(m, 'holas')

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
    # ADMIN ONLY
    if not check_access(m, 'admin'): return
    
    if m.from_user.id not in quiz_buffer: return bot.reply_to(m, "❌ No JSON.")
    
    # Send to all EXCEPT Holas (since it's a special channel) or INCLUDE?
    # Usually bulk implies main channels. I'll include all.
    for k in CHANNELS: 
        process_send(m, k)
        time.sleep(1)
    bot.reply_to(m, "✅ Bulk Send Complete.")

# ==========================================
# 📅 PDF DISTRIBUTION
# ==========================================

def smart_distribute(m, data, title_prefix, date_label):
    if not check_access(m): return # Both users can use PDF
    if not data: return bot.reply_to(m, "❌ No data found.")

    bot.reply_to(m, f"⚙️ <b>Processing...</b>\nDate: {date_label}", parse_mode='HTML')

    # Master PDF
    master_fname = f"Master_{datetime.now().strftime('%H%M%S')}.pdf"
    res = generate_pdf_html(data, master_fname, f"{title_prefix}", date_label)
    
    if res:
        caption = f"🗂 <b>Master PDF</b>\n📅 {date_label}\nBy: @MockRise"
        with open(res, 'rb') as f:
            bot.send_document(m.chat.id, f, caption=caption, parse_mode='HTML')
    
    # Channel Distribution
    # Note: Limited user can generate PDF, but sending to channels depends on rights?
    # Requirement: "pdf in sab" for limited user. Assuming they can Generate PDFs freely.
    # Distributing to channels via bot might be restricted? 
    # Let's allow PDF distribution for now as "pdf tools" are enabled.
    
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
            
            ch_pdf = generate_pdf_html(ch_items, ch_fname, title_prefix, date_label)
            
            if ch_pdf:
                try:
                    caption_ch = (
                        f"📄 <b>{title_prefix}</b>\n"
                        f"📅 Date: {date_label}\n"
                        f"🔢 Questions: {len(ch_items)}\n"
                        f"By: @MockRise"
                    )
                    # Send to channel
                    with open(ch_pdf, 'rb') as f:
                        bot.send_document(channel_info['id'], f, caption=caption_ch, parse_mode='HTML')
                    sent_count += 1
                    time.sleep(2)
                except Exception as e:
                    pass

    if sent_count > 0:
        bot.reply_to(m, "🎉 <b>Distribution Complete!</b>", parse_mode='HTML')

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
    if not check_access(m): return
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

# ==========================================
# 🧩 TEXT HANDLER (PASSWORD & JSON)
# ==========================================

@bot.message_handler(content_types=['text'])
def handle_text(m):
    uid = m.from_user.id
    text = m.text.strip()
    
    # 1️⃣ PASSWORD CHECK
    if text == PASS_ADMIN:
        user_sessions[uid] = 'admin'
        return bot.reply_to(m, "🔓 <b>Welcome ADMIN!</b>\nAccess: Full Control 🚀", parse_mode='HTML')
    
    elif text == PASS_LIMIT:
        user_sessions[uid] = 'limited'
        return bot.reply_to(m, "🔓 <b>Welcome User!</b>\nAccess: /holas & PDF Tools Only.", parse_mode='HTML')
    
    # Check Auth before processing JSON
    if uid not in user_sessions:
        return bot.reply_to(m, "🔒 <b>Locked.</b> Please enter password first.", parse_mode='HTML')

    # 2️⃣ JSON ACCUMULATOR
    if text.startswith('['):
        json_fragments[uid] = text
    
    elif uid in json_fragments:
        json_fragments[uid] += text
        
    else:
        # Ignore random text if logged in
        if not text.startswith('/'): return

    # 3️⃣ PROCESS JSON
    if uid in json_fragments:
        full_text = json_fragments[uid]
        if full_text.endswith(']'):
            try:
                clean_text = full_text.replace("‘", "'").replace("’", "'").replace("“", '"').replace("”", '"')
                clean_text = re.sub(r'^```json\s*|\s*```$', '', clean_text, flags=re.MULTILINE)
                
                data = json.loads(clean_text)
                quiz_buffer[uid] = data
                del json_fragments[uid]
                
                # Show menu based on role
                role = user_sessions[uid]
                if role == 'admin':
                    opts = "/rssb, /ssc, /upsc, /holas\n🚀 /bulk_send"
                else:
                    opts = "/holas (Only)"
                
                msg = (f"✅ <b>JSON Received ({len(data)} Qs)</b>\n\n"
                       f"✏️ /edit\n"
                       f"👇 <b>Send:</b> {opts}\n"
                       f"📄 /pdf_daily")
                bot.reply_to(m, msg, parse_mode='HTML')
                
            except json.JSONDecodeError:
                if len(full_text) > 100000:
                    bot.reply_to(m, "❌ JSON too large/invalid. /stop to clear.")
            except Exception as e:
                bot.reply_to(m, f"❌ Invalid: {e}")
                del json_fragments[uid]
        else:
             bot.reply_to(m, f"📥 <b>Part Received</b> ({len(full_text)} chars)...", parse_mode='HTML')

if __name__ == "__main__":
    keep_alive()
    bot.infinity_polling()
