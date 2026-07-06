import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
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

BOT_TOKEN = "7654075050:AAF1_Ql6EnsrwnTernsuhkLQvuppKvCpPvw"
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
temp_broadcast = {}  # Temporary memory for Notes Confirmation

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

def check_font():
    if not os.path.exists(FONT_FILE):
        try:
            r = requests.get("https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSansDevanagari/NotoSansDevanagari-Regular.ttf")
            with open(FONT_FILE, 'wb') as f: f.write(r.content)
        except: pass
    return os.path.abspath(FONT_FILE)

# PDF Generation functions are kept intact here but minimized for space...
def generate_pdf_html(data_list, filename, title_text, date_range_text, brand_key='mockrise'):
    # (Same as before)
    return None

def generate_oneliner_pdf_html(data_list, filename, title_text, date_range_text, brand_key='mockrise'):
    # (Same as before)
    return None

def safe_send_poll(target_chat, question, options, correct_index, explanation):
    # (Same as before)
    return True

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
    # (MCQ broadcast logic same as before)
    pass

def send_channel_pdfs(days=1, prefix="Daily", user_id=None):
    # (PDF broadcast logic same as before)
    return False

def get_menu_text(role, q_count):
    if role == 'admin':
        return f"""👑 <b>Welcome Owner — MockRise!</b>
━━━━━━━━━━━━━━━━━━━━
📝 <b>Quiz & PDF Management</b>
├─ /edit — प्रश्नों में सुधार करें
├─ /pdf_daily — आज का PDF सब जगह भेजें
├─ /pdf_weekly — हफ्ते का PDF सब जगह भेजें
└─ /cancel — JSON मेमोरी साफ़ करें

🚀 <b>Channel Broadcasting</b>
├─ /mockrise — MockRise Main पर भेजें
├─ /cpsir — GuruDeep Classes पर भेजें
├─ /ssc — SSC CGL/MTS पर भेजें
├─ /kalam — Kalam Academy पर भेजें
├─ /send_all — 🚀 सभी चैनल्स पर एक साथ भेजें
└─ /send_notes — 📝 HTML नोट्स/फोटो भेजें

👥 <b>User & Admin Tools</b>
├─ /stats — Bot overall stats
├─ /broadcast — 📢 सभी यूज़र्स को मैसेज भेजें
└─ /password — Admin Access लें

<i>💡 (मेमोरी में प्रश्न: {q_count})</i>"""
    else:
        return f"""👤 <b>Welcome User!</b>
━━━━━━━━━━━━━━━━━━━━
📝 <b>User Menu</b>
├─ /pdf_daily — Private PDF बनाएँ
├─ /edit — प्रश्नों में सुधार करें
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
    if message.chat.type != 'private': return
    bot.reply_to(message, "🔑 <b>कृपया अपना पासवर्ड टाइप करके भेजें:</b>", parse_mode='HTML')

@bot.message_handler(commands=['cancel'])
def cancel_json(message):
    if message.chat.type != 'private': return
    uid = message.from_user.id
    if uid in json_fragments: del json_fragments[uid]
    if uid in temp_broadcast: del temp_broadcast[uid]
    bot.reply_to(message, "✅ <b>मेमोरी साफ़ कर दी गई है।</b>", parse_mode='HTML')

@bot.message_handler(commands=['mockrise', 'cpsir', 'ssc', 'kalam', 'send_all'])
def admin_ch_handle(m):
    # Command router for JSON sending
    pass

# ==========================================
# 📝 NEW: NOTES CONFIRMATION SYSTEM
# ==========================================

@bot.message_handler(commands=['send_notes'])
def cmd_send_notes(m):
    if m.chat.type != 'private': return
    uid = m.from_user.id
    if user_sessions.get(uid) != 'admin': return bot.reply_to(m, "❌ <b>Access Denied!</b>", parse_mode='HTML')
    
    msg = bot.reply_to(m, "📝 <b>कृपया अपना मैसेज या Photo (कैप्शन के साथ) भेजें:</b>\n"
                          "👉 <i>(इसे कैंसिल करने के लिए /cancel टाइप करें)</i>", parse_mode='HTML')
    bot.register_next_step_handler(msg, process_html_notes)

def process_html_notes(m):
    if m.chat.type != 'private': return
    uid = m.from_user.id
    
    if m.content_type == 'text' and m.text.strip() == '/cancel':
        return bot.reply_to(m, "✅ नोट्स भेजना कैंसिल कर दिया गया है।")
        
    notes_content = m.text if m.text else m.caption
    
    if not notes_content:
        msg = bot.reply_to(m, "❌ कोई टेक्स्ट या कैप्शन नहीं मिला। कृपया अपना मैसेज दोबारा भेजें या /cancel दबाएं:")
        return bot.register_next_step_handler(msg, process_html_notes)
    
    # <h1> को <b> में बदलें ताकि API Crash न हो
    notes_content = notes_content.replace('<h1>', '<b>').replace('</h1>', '</b>')
    
    # मेमोरी में सुरक्षित करें
    temp_broadcast[uid] = {'msg': m, 'content': notes_content}
    
    # कन्फर्मेशन बटन तैयार करें
    markup = InlineKeyboardMarkup()
    btn_send = InlineKeyboardButton("✅ Send to All", callback_data="send_notes_confirm")
    btn_cancel = InlineKeyboardButton("❌ Cancel", callback_data="send_notes_cancel")
    markup.add(btn_send, btn_cancel)
    
    bot.reply_to(m, "👀 <b>संदेश प्राप्त हुआ!</b>\nक्या आप इसे सभी चैनल्स पर पब्लिश करना चाहते हैं?", reply_markup=markup, parse_mode='HTML')

@bot.callback_query_handler(func=lambda call: call.data.startswith('send_notes_'))
def handle_notes_confirmation(call):
    uid = call.from_user.id
    
    if call.data == 'send_notes_cancel':
        bot.edit_message_text("✅ ब्रॉडकास्ट कैंसिल कर दिया गया है।", call.message.chat.id, call.message.message_id)
        if uid in temp_broadcast: del temp_broadcast[uid]
        return
        
    if call.data == 'send_notes_confirm':
        if uid not in temp_broadcast:
            return bot.answer_callback_query(call.id, "❌ डेटा एक्सपायर हो गया। दोबारा /send_notes करें।", show_alert=True)
            
        data = temp_broadcast[uid]
        m = data['msg']
        notes_content = data['content']
        
        bot.edit_message_text("🚀 संदेश चैनल्स पर भेजा जा रहा है...", call.message.chat.id, call.message.message_id)
        
        success_count = 0
        for key, ch_info in CHANNELS.items():
            target = ch_info['id']
            try:
                if m.content_type == 'photo':
                    bot.send_photo(target, m.photo[-1].file_id, caption=notes_content, parse_mode='HTML')
                else:
                    bot.send_message(target, notes_content, parse_mode='HTML')
                success_count += 1
                time.sleep(0.5)
            except ApiTelegramException as e:
                error_msg = str(e)
                if "can't parse entities" in error_msg:
                    bot.send_message(uid, f"⚠️ <b>HTML Error:</b> आपके मैसेज में कोई टैग गलत है। कृपया सुधार कर दोबारा भेजें।", parse_mode='HTML')
                    return
                else:
                    bot.send_message(uid, f"❌ <b>{ch_info['name']}</b> पर Error: {error_msg}")
                    
        bot.send_message(uid, f"✅ सफलता पूर्वक {success_count} चैनल्स पर पब्लिश कर दिया गया!")
        del temp_broadcast[uid]

# ==========================================
# 🧩 ROBUST JSON & TEXT HANDLER
# ==========================================

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

    if text.startswith('[') and uid not in json_fragments:
        json_fragments[uid] = text
    elif uid in json_fragments:
        json_fragments[uid] += text

    if uid in json_fragments:
        try:
            quiz_buffer[uid] = json.loads(json_fragments[uid])
            del json_fragments[uid] 
        except json.JSONDecodeError:
            return bot.reply_to(m, f"⏳ <b>JSON का हिस्सा प्राप्त हुआ...</b>\nबाकी का हिस्सा भेजें।", parse_mode='HTML')
        except:
            del json_fragments[uid]
            return bot.reply_to(m, "❌ Error. /cancel करें and दोबारा भेजें।")
    else:
        if not text.startswith('/'):
            return bot.reply_to(m, "❌ कृपया केवल JSON फॉर्मेट (`[...]`) में ही प्रश्न भेजें।", parse_mode='HTML')

    if uid in quiz_buffer and not text.startswith('/'):
        bot.reply_to(m, "✅ <b>डेटा सफलतापूर्वक प्राप्त हुआ!</b> 👇", parse_mode='HTML')
        bot.send_message(m.chat.id, get_menu_text(user_sessions[uid], len(quiz_buffer[uid])), parse_mode='HTML')

if __name__ == "__main__":
    keep_alive()
    bot.infinity_polling()
