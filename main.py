import sys
# यह लाइन कंसोल/टर्मिनल में हिंदी और Emojis (UTF-8) को सही से दिखाने के लिए है
sys.stdout.reconfigure(encoding='utf-8')

import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import json
import time
import os
import re
import threading
import requests
from flask import Flask
from weasyprint import HTML
from telebot.apihelper import ApiTelegramException

# ==========================================
# ⚙️ CONFIGURATION
# ==========================================

BOT_TOKEN = "7654075050:AAGyj5jKaDOClKmDe7w1j1ZL5yBkimGBtQM"
MAIN_CHANNEL_ID = "@mockrise"
PASS_ADMIN = "7852"

BRANDS = {
    'mockrise': {
        'website': 'www.mockrise.com',
        'logo': 'https://blogger.googleusercontent.com/img/a/AVvXsEhbqzX1vYBTW0G90MZo4vC6D06Sn0hXnN57XtwWxAkijUI5Rddzs5F7CV5PsBD4mJIf06tM97CjnV0Q8KDNlIjM4tJ7o32XmhJNR8vDTltIcmdwlnLTOhicbRuJ3mDq4p-NTCLYTuCwtmffepkOdPE8k7ywaYRqzGdaE12iILrnTNJC15x1Iuzb7Tewkw4=s1146'
    },
    'cpsir': {
        'website': 'https://www.gurudeepaiacademy.com/',
        'logo': 'https://blogger.googleusercontent.com/img/a/AVvXsEgUuZDpANHyMD9YoC5ftPljTkNKbJ5rFJJkdV2S5sDWjD-bj19PPDnexZ-0deX07JvtXLp5OtI_dMtBeH9EE6b7PUkJ8eV94I5k8Q_H7TPkNm7WRRiYfQLo4p6mMl-hnqbVQ3IytxmtLx-vxAOgOo6jwbI0wiWnBaY-XeTERgK9id1NCrPDbfj1smHvfm0=s640'
    }
}

CHANNELS = {
    'mockrise': {'id': '@mockrise', 'name': 'MockRise Main', 'brand': 'mockrise'},
    'cpsir': {'id': '@GuruDeepClasses', 'name': 'GuruDeep Classes', 'brand': 'cpsir'},
    'ssc': {'id': '@ssc_cgl_chsl_mts_ntpc_upsc', 'name': 'SSC CGL/MTS', 'brand': 'mockrise'},
    'kalam': {'id': '@rajasthan_gk_kalam_reet_ldc_ras', 'name': 'Kalam Academy', 'brand': 'mockrise'}
}

DB_STATS = "user_stats.json"
DB_HISTORY = "history.json"
DB_USERS = "users_db.json"
FONT_FILE = "NotoSansDevanagari-Regular.ttf"

quiz_buffer = {}
json_fragments = {}
user_sessions = {}
temp_broadcast = {}  

bot = telebot.TeleBot(BOT_TOKEN)

# ==========================================
# 🌐 FLASK SERVER & DATA HANDLING
# ==========================================

app = Flask('')
@app.route('/')
def home(): return "✅ Bot is Running!"
def run_server(): app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))
def keep_alive(): threading.Thread(target=run_server, daemon=True).start()

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
# 📝 NEW PDF GENERATION FUNCTIONS
# ==========================================

def create_pdf_from_html_string(html_content, filename):
    """Generates PDF from HTML string using WeasyPrint"""
    try:
        # Wrap in basic HTML/CSS if not present to ensure layout
        if "<html" not in html_content.lower():
            html_content = f"""
            <html>
            <head><style>
                @page {{ size: A4; margin: 15mm; background-color: #fdfbf7; }}
                body {{ font-family: sans-serif; color: #333; line-height: 1.6; font-size: 14px; }}
                h1, h2, h3 {{ color: #2c3e50; }}
            </style></head>
            <body>{html_content}</body>
            </html>
            """
        HTML(string=html_content).write_pdf(filename)
        return True
    except Exception as e:
        print(f"PDF Generation Error: {e}")
        return False

# ==========================================
# ⚙️ BOT COMMANDS & MENUS
# ==========================================

def get_menu_text(role, q_count):
    if role == 'admin':
        return f"""👑 <b>Welcome Owner — MockRise!</b>
━━━━━━━━━━━━━━━━━━━━
📝 <b>Quiz & PDF Management</b>
├─ /pdf_daily — आज का PDF 
├─ /pdf_weekly — हफ्ते का PDF
├─ /pdf_ca_weekly — 🆕 Current Affairs Weekly PDF
├─ /pdf_quiz_weekly — 🆕 Weekly Quiz PDF
├─ /html_to_pdf — 🆕 HTML से PDF बनाएँ
├─ /edit — प्रश्नों में सुधार करें
└─ /cancel — JSON मेमोरी साफ़ करें

🚀 <b>Channel Broadcasting</b>
├─ /mockrise — MockRise Main पर भेजें
├─ /send_all — 🚀 सभी चैनल्स पर एक साथ भेजें
└─ /send_notes — 📝 HTML नोट्स/फोटो भेजें

<i>💡 (मेमोरी में प्रश्न: {q_count})</i>"""
    else:
        return f"""👤 <b>Welcome User!</b>
━━━━━━━━━━━━━━━━━━━━
📝 <b>User Menu</b>
├─ /pdf_daily — Private PDF बनाएँ
├─ /html_to_pdf — 🆕 HTML से PDF बनाएँ
└─ /cancel — JSON साफ़ करें

🔒 <b>Admin Access:</b> /password
<i>💡 केवल JSON डेटा भेजें। (मेमोरी में प्रश्न: {q_count})</i>"""

@bot.message_handler(commands=['start', 'help'])
def send_welcome_and_help(message):
    if message.chat.type != 'private': return
    uid = message.from_user.id
    if uid not in user_sessions: user_sessions[uid] = 'user'
    bot.send_message(message.chat.id, get_menu_text(user_sessions.get(uid, 'user'), len(quiz_buffer.get(uid, []))), parse_mode='HTML')

@bot.message_handler(commands=['password'])
def ask_password(message):
    bot.reply_to(message, "🔑 <b>कृपया अपना पासवर्ड टाइप करके भेजें:</b>", parse_mode='HTML')

@bot.message_handler(commands=['cancel'])
def cancel_json(message):
    uid = message.from_user.id
    if uid in json_fragments: del json_fragments[uid]
    if uid in temp_broadcast: del temp_broadcast[uid]
    if uid in quiz_buffer: del quiz_buffer[uid]
    bot.reply_to(message, "✅ <b>मेमोरी साफ़ कर दी गई है।</b>", parse_mode='HTML')

# ==========================================
# 📝 NEW: HTML TO PDF & WEEKLY PDF COMMANDS
# ==========================================

@bot.message_handler(commands=['html_to_pdf'])
def cmd_html_to_pdf(m):
    msg = bot.reply_to(m, "📝 <b>अपना HTML कोड भेजें:</b>\n👉 <i>(इसे कैंसिल करने के लिए /cancel टाइप करें)</i>", parse_mode='HTML')
    bot.register_next_step_handler(msg, process_custom_html_to_pdf)

def process_custom_html_to_pdf(m):
    if m.text.strip() == '/cancel':
        return bot.reply_to(m, "✅ कैंसिल कर दिया गया है।")
    
    bot.reply_to(m, "⏳ PDF तैयार किया जा रहा है...")
    pdf_path = f"Custom_Notes_{m.from_user.id}.pdf"
    
    if create_pdf_from_html_string(m.text, pdf_path):
        with open(pdf_path, 'rb') as pdf_file:
            bot.send_document(m.chat.id, pdf_file, caption="✅ आपका PDF तैयार है!")
        os.remove(pdf_path)
    else:
        bot.reply_to(m, "❌ HTML से PDF बनाने में त्रुटि हुई। कृपया अपना HTML जांचें।")

@bot.message_handler(commands=['pdf_ca_weekly', 'pdf_quiz_weekly'])
def cmd_weekly_pdfs(m):
    uid = m.from_user.id
    if uid not in quiz_buffer or not quiz_buffer[uid]:
        return bot.reply_to(m, "❌ पहले मेमोरी में JSON डेटा भेजें। (Questions: 0)")
        
    cmd = m.text.split('@')[0]
    title = "Weekly Current Affairs" if cmd == '/pdf_ca_weekly' else "Weekly Quiz"
    
    bot.reply_to(m, f"⏳ {title} PDF जनरेट किया जा रहा है...")
    
    # 🆕 Basic PDF Generation logic from JSON Buffer for Weekly
    html_content = f"<h1 style='text-align:center;'>{title}</h1>"
    for i, q in enumerate(quiz_buffer[uid]):
        html_content += f"<h3>Q{i+1}. {q.get('question', '')}</h3>"
        for opt in q.get('option', []):
            html_content += f"<div>- {opt}</div>"
        html_content += f"<br><b>Answer:</b> {q.get('answer', '')}<br>"
        html_content += f"<b>Solution:</b> {q.get('solution', '')}<hr>"

    pdf_path = f"{title.replace(' ', '_')}.pdf"
    if create_pdf_from_html_string(html_content, pdf_path):
        with open(pdf_path, 'rb') as pdf_file:
            bot.send_document(m.chat.id, pdf_file, caption=f"✅ {title} PDF तैयार है!")
        os.remove(pdf_path)
    else:
        bot.reply_to(m, "❌ PDF जनरेट करने में त्रुटि।")

# ==========================================
# 🧩 ROBUST JSON & TEXT HANDLER
# ==========================================

def clean_json_string(text):
    # Removes markdown like ```json ... ``` often produced by LLMs
    text = re.sub(r'^```(?:json)?', '', text, flags=re.MULTILINE)
    text = re.sub(r'```$', '', text, flags=re.MULTILINE)
    return text.strip()

@bot.message_handler(content_types=['text'])
def handle_text(m):
    if m.chat.type != 'private': return
    uid = m.from_user.id
    text = m.text.strip()
    
    if text == PASS_ADMIN: 
        user_sessions[uid] = 'admin'
        bot.reply_to(m, "🔓 <b>Admin Panel Unlocked!</b>", parse_mode='HTML')
        return bot.send_message(m.chat.id, get_menu_text('admin', len(quiz_buffer.get(uid, []))), parse_mode='HTML')
    
    if uid not in user_sessions: user_sessions[uid] = 'user'

    cleaned_text = clean_json_string(text)

    # 🆕 Robust JSON Builder
    if cleaned_text.startswith('[') or uid in json_fragments:
        if uid not in json_fragments:
            json_fragments[uid] = cleaned_text
        else:
            json_fragments[uid] += cleaned_text

        try:
            quiz_buffer[uid] = json.loads(json_fragments[uid])
            del json_fragments[uid] 
            bot.reply_to(m, "✅ <b>डेटा सफलतापूर्वक प्राप्त हुआ!</b> 👇", parse_mode='HTML')
            bot.send_message(m.chat.id, get_menu_text(user_sessions[uid], len(quiz_buffer[uid])), parse_mode='HTML')
        except json.JSONDecodeError:
            return bot.reply_to(m, f"⏳ <b>JSON का हिस्सा प्राप्त हुआ...</b>\nबाकी का हिस्सा भेजें। (Total: {len(json_fragments[uid])} chars)", parse_mode='HTML')
        except Exception as e:
            del json_fragments[uid]
            return bot.reply_to(m, f"❌ Error: {e}. /cancel करें और दोबारा भेजें।")
    else:
        if not text.startswith('/'):
            return bot.reply_to(m, "❌ कृपया केवल JSON फॉर्मेट (`[...]`) में ही प्रश्न भेजें या कमांड का उपयोग करें।", parse_mode='HTML')

if __name__ == "__main__":
    keep_alive()
    bot.infinity_polling()
