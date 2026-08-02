import sys
sys.stdout.reconfigure(encoding='utf-8')

import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import json
import time
import os
import re
import threading
from flask import Flask
from telebot.apihelper import ApiTelegramException

# ==========================================
# ⚙️ CONFIGURATION
# ==========================================

BOT_TOKEN = "7654075050:AAFlzWihsjRBbpDiiMRj24cTrTk0GbVnFZ4" # अपना सही टोकन यहाँ रखें
MAIN_CHANNEL_ID = "@mockrise"
PASS_ADMIN = "7852"

CHANNELS = {
    'mockrise': {'id': '@mockrise', 'name': 'MockRise Main'},
    'cpsir': {'id': '@GuruDeepClasses', 'name': 'GuruDeep Classes'},
    'ssc': {'id': '@ssc_cgl_chsl_mts_ntpc_upsc', 'name': 'SSC CGL/MTS'},
    'kalam': {'id': '@rajasthan_gk_kalam_reet_ldc_ras', 'name': 'Kalam Academy'}
}

quiz_buffer = {}
json_fragments = {}
user_sessions = {}
temp_broadcast = {}  

bot = telebot.TeleBot(BOT_TOKEN)

# ==========================================
# 🌐 FLASK SERVER
# ==========================================

app = Flask('')
@app.route('/')
def home(): return "✅ Bot is Running without PDF feature!"
def run_server(): app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))
def keep_alive(): threading.Thread(target=run_server, daemon=True).start()

# ==========================================
# ⚙️ BOT MENUS
# ==========================================

def get_menu_text(role, q_count):
    if role == 'admin':
        return f"""👑 <b>Welcome Owner — MockRise!</b>
━━━━━━━━━━━━━━━━━━━━
📝 <b>Quiz Management</b>
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
└─ /cancel — JSON साफ़ करें

🔒 <b>Admin Access:</b> /password
<i>💡 केवल JSON डेटा भेजें। (मेमोरी में प्रश्न: {q_count})</i>"""

@bot.message_handler(commands=['start', 'help'])
def send_welcome(m):
    if m.chat.type != 'private': return
    uid = m.from_user.id
    if uid not in user_sessions: user_sessions[uid] = 'user'
    bot.send_message(m.chat.id, get_menu_text(user_sessions.get(uid, 'user'), len(quiz_buffer.get(uid, []))), parse_mode='HTML')

@bot.message_handler(commands=['password'])
def ask_password(m):
    bot.reply_to(m, "🔑 <b>कृपया अपना पासवर्ड टाइप करके भेजें:</b>", parse_mode='HTML')

@bot.message_handler(commands=['cancel'])
def cancel_json(m):
    uid = m.from_user.id
    if uid in json_fragments: del json_fragments[uid]
    if uid in temp_broadcast: del temp_broadcast[uid]
    if uid in quiz_buffer: del quiz_buffer[uid]
    bot.reply_to(m, "✅ <b>मेमोरी साफ़ कर दी गई है।</b>", parse_mode='HTML')

# ==========================================
# 🚀 MCQ BROADCAST HANDLER (NEW)
# ==========================================

@bot.message_handler(commands=['mockrise', 'cpsir', 'ssc', 'kalam', 'send_all'])
def admin_mcq_broadcast(m):
    if m.chat.type != 'private': return
    uid = m.from_user.id
    
    if user_sessions.get(uid) != 'admin': 
        return bot.reply_to(m, "❌ <b>Access Denied!</b>", parse_mode='HTML')
    
    if uid not in quiz_buffer or not quiz_buffer[uid]:
        return bot.reply_to(m, "❌ <b>कोई प्रश्न मेमोरी में नहीं है।</b> पहले JSON डेटा भेजें।", parse_mode='HTML')
        
    cmd = m.text.split('@')[0].replace('/', '')
    
    targets = []
    if cmd == 'send_all':
        targets = [ch['id'] for ch in CHANNELS.values()]
    elif cmd in CHANNELS:
        targets = [CHANNELS[cmd]['id']]
        
    bot.reply_to(m, f"🚀 <b>{len(targets)} चैनल्स पर {len(quiz_buffer[uid])} प्रश्न भेजे जा रहे हैं...</b>", parse_mode='HTML')
    
    for target_chat in targets:
        success_count = 0
        for q in quiz_buffer[uid]:
            q_text = q.get('question', 'No Question')
            opts = [str(opt)[:100] for opt in q.get('option', ['A', 'B', 'C', 'D'])] # Options max limit 100 chars
            
            ans_char = str(q.get('answer', 'A')).upper()
            ans_idx = ord(ans_char) - 65 if len(ans_char) == 1 and 'A' <= ans_char <= 'D' else 0
            if ans_idx < 0 or ans_idx >= len(opts): ans_idx = 0
            
            # ✅ यहाँ @mockrise अपने आप जुड़ जाएगा
            sol_text = f"{q.get('solution', '')}\n\n@mockrise"
            
            try:
                # 1. अगर प्रश्न बहुत बड़ा है (>290 chars)
                if len(q_text) > 290:
                    poll_q = q_text[:285] + "... (👇 नीचे पढ़ें)"
                    msg_poll = bot.send_poll(chat_id=target_chat, question=poll_q, options=opts, type='quiz', correct_option_id=ans_idx)
                    
                    full_msg = f"<b>📝 पूरा प्रश्न:</b>\n{q_text}\n\n<b>💡 व्याख्या:</b>\n<tg-spoiler>{sol_text}</tg-spoiler>"
                    bot.send_message(target_chat, full_msg, reply_to_message_id=msg_poll.message_id, parse_mode='HTML')
                
                # 2. अगर व्याख्या (Solution) बड़ी है (>190 chars)
                elif len(sol_text) > 190:
                    msg_poll = bot.send_poll(chat_id=target_chat, question=q_text, options=opts, type='quiz', correct_option_id=ans_idx)
                    
                    bot.send_message(target_chat, f"<b>💡 व्याख्या:</b>\n<tg-spoiler>{sol_text}</tg-spoiler>", reply_to_message_id=msg_poll.message_id, parse_mode='HTML')
                
                # 3. अगर सब नॉर्मल है
                else:
                    bot.send_poll(chat_id=target_chat, question=q_text, options=opts, type='quiz', correct_option_id=ans_idx, explanation=sol_text)
                
                success_count += 1
                time.sleep(1.5)  # Telegram API flood लिमिट से बचने के लिए डिले
                
            except ApiTelegramException as e:
                if e.error_code == 429:
                    retry = int(e.result_json['parameters']['retry_after'])
                    time.sleep(retry + 1)
                else:
                    bot.send_message(uid, f"❌ Error (Q{success_count+1}): {e}")
                    
        bot.send_message(uid, f"✅ <b>{target_chat}</b> पर {success_count} प्रश्न सफलतापूर्वक भेज दिए गए!", parse_mode='HTML')
        
    bot.send_message(uid, "🎉 <b>ब्रॉडकास्ट प्रोसेस पूरा हो गया!</b>", parse_mode='HTML')

# ==========================================
# 📝 SEND NOTES / HTML HANDLER
# ==========================================

@bot.message_handler(commands=['send_notes'])
def cmd_send_notes(m):
    if m.chat.type != 'private': return
    uid = m.from_user.id
    if user_sessions.get(uid) != 'admin': return bot.reply_to(m, "❌ <b>Access Denied!</b>", parse_mode='HTML')
    
    msg = bot.reply_to(m, "📝 <b>कृपया अपना मैसेज या Photo (कैप्शन के साथ) भेजें:</b>\n👉 <i>(कैंसिल करने के लिए /cancel टाइप करें)</i>", parse_mode='HTML')
    bot.register_next_step_handler(msg, process_html_notes)

def process_html_notes(m):
    if m.chat.type != 'private': return
    uid = m.from_user.id
    
    if m.content_type == 'text' and m.text.strip() == '/cancel':
        return bot.reply_to(m, "✅ नोट्स भेजना कैंसिल कर दिया गया है।")
        
    notes_content = m.text if m.text else m.caption
    
    if not notes_content:
        msg = bot.reply_to(m, "❌ कोई टेक्स्ट नहीं मिला। कृपया अपना मैसेज दोबारा भेजें या /cancel दबाएं:")
        return bot.register_next_step_handler(msg, process_html_notes)
    
    notes_content = notes_content.replace('<h1>', '<b>').replace('</h1>', '</b>')
    temp_broadcast[uid] = {'msg': m, 'content': notes_content}
    
    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("✅ Send to All", callback_data="send_notes_confirm"),
        InlineKeyboardButton("❌ Cancel", callback_data="send_notes_cancel")
    )
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
            return bot.answer_callback_query(call.id, "❌ डेटा एक्सपायर हो गया।", show_alert=True)
            
        data = temp_broadcast[uid]
        m, notes_content = data['msg'], data['content']
        bot.edit_message_text("🚀 संदेश चैनल्स पर भेजा जा रहा है...", call.message.chat.id, call.message.message_id)
        
        for key, ch_info in CHANNELS.items():
            target = ch_info['id']
            try:
                if m.content_type == 'photo':
                    bot.send_photo(target, m.photo[-1].file_id, caption=notes_content, parse_mode='HTML')
                else:
                    bot.send_message(target, notes_content, parse_mode='HTML')
                time.sleep(0.5)
            except Exception as e:
                bot.send_message(uid, f"❌ Error on {ch_info['name']}: {e}")
                    
        bot.send_message(uid, "✅ सफलता पूर्वक सभी चैनल्स पर पब्लिश कर दिया गया!")
        del temp_broadcast[uid]

# ==========================================
# 🧩 ROBUST JSON & TEXT HANDLER
# ==========================================

def clean_json_string(text):
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
            return bot.reply_to(m, "❌ कृपया केवल JSON फॉर्मेट (`[...]`) में ही प्रश्न भेजें।", parse_mode='HTML')

if __name__ == "__main__":
    keep_alive()
    bot.infinity_polling()
