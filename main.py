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
# âš™ï¸ CONFIGURATION
# ==========================================

BOT_TOKEN = "7654075050:AAECwInoBMxH6Fa8AxIw7WWLqKmQlm5o-AA"
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
# ðŸŒ FLASK SERVER & DATA HANDLING
# ==========================================

app = Flask('')
@app.route('/')
def home(): return "âœ… Bot is Running!"
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
# ðŸ“ NEW PDF GENERATION FUNCTIONS
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
# âš™ï¸ BOT COMMANDS & MENUS
# ==========================================

def get_menu_text(role, q_count):
    if role == 'admin':
        return f"""ðŸ‘‘ <b>Welcome Owner â€” MockRise!</b>
â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”
ðŸ“ <b>Quiz & PDF Management</b>
â”œâ”€ /pdf_daily â€” à¤†à¤œ à¤•à¤¾ PDF 
â”œâ”€ /pdf_weekly â€” à¤¹à¤«à¥à¤¤à¥‡ à¤•à¤¾ PDF
â”œâ”€ /pdf_ca_weekly â€” ðŸ†• Current Affairs Weekly PDF
â”œâ”€ /pdf_quiz_weekly â€” ðŸ†• Weekly Quiz PDF
â”œâ”€ /html_to_pdf â€” ðŸ†• HTML à¤¸à¥‡ PDF à¤¬à¤¨à¤¾à¤à¤
â”œâ”€ /edit â€” à¤ªà¥à¤°à¤¶à¥à¤¨à¥‹à¤‚ à¤®à¥‡à¤‚ à¤¸à¥à¤§à¤¾à¤° à¤•à¤°à¥‡à¤‚
â””â”€ /cancel â€” JSON à¤®à¥‡à¤®à¥‹à¤°à¥€ à¤¸à¤¾à¤«à¤¼ à¤•à¤°à¥‡à¤‚

ðŸš€ <b>Channel Broadcasting</b>
â”œâ”€ /mockrise â€” MockRise Main à¤ªà¤° à¤­à¥‡à¤œà¥‡à¤‚
â”œâ”€ /send_all â€” ðŸš€ à¤¸à¤­à¥€ à¤šà¥ˆà¤¨à¤²à¥à¤¸ à¤ªà¤° à¤à¤• à¤¸à¤¾à¤¥ à¤­à¥‡à¤œà¥‡à¤‚
â””â”€ /send_notes â€” ðŸ“ HTML à¤¨à¥‹à¤Ÿà¥à¤¸/à¤«à¥‹à¤Ÿà¥‹ à¤­à¥‡à¤œà¥‡à¤‚

<i>ðŸ’¡ (à¤®à¥‡à¤®à¥‹à¤°à¥€ à¤®à¥‡à¤‚ à¤ªà¥à¤°à¤¶à¥à¤¨: {q_count})</i>"""
    else:
        return f"""ðŸ‘¤ <b>Welcome User!</b>
â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”
ðŸ“ <b>User Menu</b>
â”œâ”€ /pdf_daily â€” Private PDF à¤¬à¤¨à¤¾à¤à¤
â”œâ”€ /html_to_pdf â€” ðŸ†• HTML à¤¸à¥‡ PDF à¤¬à¤¨à¤¾à¤à¤
â””â”€ /cancel â€” JSON à¤¸à¤¾à¤«à¤¼ à¤•à¤°à¥‡à¤‚

ðŸ”’ <b>Admin Access:</b> /password
<i>ðŸ’¡ à¤•à¥‡à¤µà¤² JSON à¤¡à¥‡à¤Ÿà¤¾ à¤­à¥‡à¤œà¥‡à¤‚à¥¤ (à¤®à¥‡à¤®à¥‹à¤°à¥€ à¤®à¥‡à¤‚ à¤ªà¥à¤°à¤¶à¥à¤¨: {q_count})</i>"""

@bot.message_handler(commands=['start', 'help'])
def send_welcome_and_help(message):
    if message.chat.type != 'private': return
    uid = message.from_user.id
    if uid not in user_sessions: user_sessions[uid] = 'user'
    bot.send_message(message.chat.id, get_menu_text(user_sessions.get(uid, 'user'), len(quiz_buffer.get(uid, []))), parse_mode='HTML')

@bot.message_handler(commands=['password'])
def ask_password(message):
    bot.reply_to(message, "ðŸ”‘ <b>à¤•à¥ƒà¤ªà¤¯à¤¾ à¤…à¤ªà¤¨à¤¾ à¤ªà¤¾à¤¸à¤µà¤°à¥à¤¡ à¤Ÿà¤¾à¤‡à¤ª à¤•à¤°à¤•à¥‡ à¤­à¥‡à¤œà¥‡à¤‚:</b>", parse_mode='HTML')

@bot.message_handler(commands=['cancel'])
def cancel_json(message):
    uid = message.from_user.id
    if uid in json_fragments: del json_fragments[uid]
    if uid in temp_broadcast: del temp_broadcast[uid]
    if uid in quiz_buffer: del quiz_buffer[uid]
    bot.reply_to(message, "âœ… <b>à¤®à¥‡à¤®à¥‹à¤°à¥€ à¤¸à¤¾à¤«à¤¼ à¤•à¤° à¤¦à¥€ à¤—à¤ˆ à¤¹à¥ˆà¥¤</b>", parse_mode='HTML')

# ==========================================
# ðŸ“ NEW: HTML TO PDF & WEEKLY PDF COMMANDS
# ==========================================

@bot.message_handler(commands=['html_to_pdf'])
def cmd_html_to_pdf(m):
    msg = bot.reply_to(m, "ðŸ“ <b>à¤…à¤ªà¤¨à¤¾ HTML à¤•à¥‹à¤¡ à¤­à¥‡à¤œà¥‡à¤‚:</b>\nðŸ‘‰ <i>(à¤‡à¤¸à¥‡ à¤•à¥ˆà¤‚à¤¸à¤¿à¤² à¤•à¤°à¤¨à¥‡ à¤•à¥‡ à¤²à¤¿à¤ /cancel à¤Ÿà¤¾à¤‡à¤ª à¤•à¤°à¥‡à¤‚)</i>", parse_mode='HTML')
    bot.register_next_step_handler(msg, process_custom_html_to_pdf)

def process_custom_html_to_pdf(m):
    if m.text.strip() == '/cancel':
        return bot.reply_to(m, "âœ… à¤•à¥ˆà¤‚à¤¸à¤¿à¤² à¤•à¤° à¤¦à¤¿à¤¯à¤¾ à¤—à¤¯à¤¾ à¤¹à¥ˆà¥¤")
    
    bot.reply_to(m, "â³ PDF à¤¤à¥ˆà¤¯à¤¾à¤° à¤•à¤¿à¤¯à¤¾ à¤œà¤¾ à¤°à¤¹à¤¾ à¤¹à¥ˆ...")
    pdf_path = f"Custom_Notes_{m.from_user.id}.pdf"
    
    if create_pdf_from_html_string(m.text, pdf_path):
        with open(pdf_path, 'rb') as pdf_file:
            bot.send_document(m.chat.id, pdf_file, caption="âœ… à¤†à¤ªà¤•à¤¾ PDF à¤¤à¥ˆà¤¯à¤¾à¤° à¤¹à¥ˆ!")
        os.remove(pdf_path)
    else:
        bot.reply_to(m, "âŒ HTML à¤¸à¥‡ PDF à¤¬à¤¨à¤¾à¤¨à¥‡ à¤®à¥‡à¤‚ à¤¤à¥à¤°à¥à¤Ÿà¤¿ à¤¹à¥à¤ˆà¥¤ à¤•à¥ƒà¤ªà¤¯à¤¾ à¤…à¤ªà¤¨à¤¾ HTML à¤œà¤¾à¤‚à¤šà¥‡à¤‚à¥¤")

@bot.message_handler(commands=['pdf_ca_weekly', 'pdf_quiz_weekly'])
def cmd_weekly_pdfs(m):
    uid = m.from_user.id
    if uid not in quiz_buffer or not quiz_buffer[uid]:
        return bot.reply_to(m, "âŒ à¤ªà¤¹à¤²à¥‡ à¤®à¥‡à¤®à¥‹à¤°à¥€ à¤®à¥‡à¤‚ JSON à¤¡à¥‡à¤Ÿà¤¾ à¤­à¥‡à¤œà¥‡à¤‚à¥¤ (Questions: 0)")
        
    cmd = m.text.split('@')[0]
    title = "Weekly Current Affairs" if cmd == '/pdf_ca_weekly' else "Weekly Quiz"
    
    bot.reply_to(m, f"â³ {title} PDF à¤œà¤¨à¤°à¥‡à¤Ÿ à¤•à¤¿à¤¯à¤¾ à¤œà¤¾ à¤°à¤¹à¤¾ à¤¹à¥ˆ...")
    
    # ðŸ†• Basic PDF Generation logic from JSON Buffer for Weekly
    html_content = f"<h1 style='text-align:center;'>{title}</h1>"
    for i, q in enumerate(quiz_buffer[uid]):
        html_content += f"<h3>Q{{i+1}}. {{q.get('question', '')}}</h3>"
        for opt in q.get('option', []):
            html_content += f"<div>- {{opt}}</div>"
        html_content += f"<br><b>Answer:</b> {{q.get('answer', '')}}<br>"
        html_content += f"<b>Solution:</b> {{q.get('solution', '')}}<hr>"

    pdf_path = f"{{title.replace(' ', '_')}}.pdf"
    if create_pdf_from_html_string(html_content, pdf_path):
        with open(pdf_path, 'rb') as pdf_file:
            bot.send_document(m.chat.id, pdf_file, caption=f"âœ… {{title}} PDF à¤¤à¥ˆà¤¯à¤¾à¤° à¤¹à¥ˆ!")
        os.remove(pdf_path)
    else:
        bot.reply_to(m, "âŒ PDF à¤œà¤¨à¤°à¥‡à¤Ÿ à¤•à¤°à¤¨à¥‡ à¤®à¥‡à¤‚ à¤¤à¥à¤°à¥à¤Ÿà¤¿à¥¤")

# ==========================================
# ðŸ§© ROBUST JSON & TEXT HANDLER
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
        bot.reply_to(m, "ðŸ”“ <b>Admin Panel Unlocked!</b>", parse_mode='HTML')
        return bot.send_message(m.chat.id, get_menu_text('admin', len(quiz_buffer.get(uid, []))), parse_mode='HTML')
    
    if uid not in user_sessions: user_sessions[uid] = 'user'

    cleaned_text = clean_json_string(text)

    # ðŸ†• Robust JSON Builder
    if cleaned_text.startswith('[') or uid in json_fragments:
        if uid not in json_fragments:
            json_fragments[uid] = cleaned_text
        else:
            json_fragments[uid] += cleaned_text

        try:
            quiz_buffer[uid] = json.loads(json_fragments[uid])
            del json_fragments[uid] 
            bot.reply_to(m, "âœ… <b>à¤¡à¥‡à¤Ÿà¤¾ à¤¸à¤«à¤²à¤¤à¤¾à¤ªà¥‚à¤°à¥à¤µà¤• à¤ªà¥à¤°à¤¾à¤ªà¥à¤¤ à¤¹à¥à¤†!</b> ðŸ‘‡", parse_mode='HTML')
            bot.send_message(m.chat.id, get_menu_text(user_sessions[uid], len(quiz_buffer[uid])), parse_mode='HTML')
        except json.JSONDecodeError:
            return bot.reply_to(m, f"â³ <b>JSON à¤•à¤¾ à¤¹à¤¿à¤¸à¥à¤¸à¤¾ à¤ªà¥à¤°à¤¾à¤ªà¥à¤¤ à¤¹à¥à¤†...</b>\nà¤¬à¤¾à¤•à¥€ à¤•à¤¾ à¤¹à¤¿à¤¸à¥à¤¸à¤¾ à¤­à¥‡à¤œà¥‡à¤‚à¥¤ (Total: {len(json_fragments[uid])} chars)", parse_mode='HTML')
        except Exception as e:
            del json_fragments[uid]
            return bot.reply_to(m, f"âŒ Error: {e}. /cancel à¤•à¤°à¥‡à¤‚ à¤”à¤° à¤¦à¥‹à¤¬à¤¾à¤°à¤¾ à¤­à¥‡à¤œà¥‡à¤‚à¥¤")
    else:
        if not text.startswith('/'):
            return bot.reply_to(m, "âŒ à¤•à¥ƒà¤ªà¤¯à¤¾ à¤•à¥‡à¤µà¤² JSON à¤«à¥‰à¤°à¥à¤®à¥‡à¤Ÿ (`[...]`) à¤®à¥‡à¤‚ à¤¹à¥€ à¤ªà¥à¤°à¤¶à¥à¤¨ à¤­à¥‡à¤œà¥‡à¤‚ à¤¯à¤¾ à¤•à¤®à¤¾à¤‚à¤¡ à¤•à¤¾ à¤‰à¤ªà¤¯à¥‹à¤— à¤•à¤°à¥‡à¤‚à¥¤", parse_mode='HTML')

if __name__ == "__main__":
    keep_alive()
    bot.infinity_polling()
