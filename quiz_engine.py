"""
quiz_engine.py
Advanced Quiz Engine with 5-Person Ready System, PDF Leaderboards, Custom Timers, and Fancy UI.
"""

import asyncio
import time
import os
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from fpdf import FPDF

import database as db
import config
from utils.reactions import auto_react

active_quizzes = {}
ready_sessions = {}

def is_quiz_active(chat_id):
    return chat_id in active_quizzes or chat_id in ready_sessions

async def stop_quiz(context: ContextTypes.DEFAULT_TYPE, chat_id):
    stopped = False
    if chat_id in active_quizzes:
        active_quizzes[chat_id]['running'] = False
        del active_quizzes[chat_id]
        stopped = True
    if chat_id in ready_sessions:
        del ready_sessions[chat_id]
        stopped = True
    return stopped

# ==========================================
# FANCY UI & READY SYSTEM
# ==========================================
async def start_quiz_session(context: ContextTypes.DEFAULT_TYPE, chat_id, chat_title, subject_id, chapter_id, user_id, num_questions, custom_timer=None):
    if is_quiz_active(chat_id):
        await context.bot.send_message(chat_id, "⚠️ यहाँ पहले से एक क्विज़ चल रहा है या शुरू होने वाला है!")
        return

    all_q = db.get_questions()
    filtered_q = []
    for q in all_q:
        if subject_id and q.get('subject_id') != subject_id: continue
        if chapter_id and q.get('chapter_id') != chapter_id: continue
        filtered_q.append(q)

    if not filtered_q:
        await context.bot.send_message(chat_id, "❌ इस टॉपिक के लिए पर्याप्त सवाल नहीं हैं।")
        return

    random.shuffle(filtered_q)
    questions_to_ask = filtered_q[:num_questions]
    timer = custom_timer if custom_timer else config.QUESTION_TIME
    subj_name = "Mixed (सभी विषय)" if not subject_id else "Selected Topic"

    text = (
        f"❑ *महा-क्विज़ प्रतियोगिता शुरू होने वाली है!*\n"
        f"__________________________________________\n\n"
        f"➭ *विषय (Topic):* {subj_name}\n"
        f"➛ *कुल प्रश्न:* {len(questions_to_ask)} ☞ तैयार हो जाएं!\n\n"
        f"➭ *नियम और समय (Rules & Timer)*\n"
        f"➛ *समय:* {timer} सेकंड प्रति प्रश्न ☞ तेज़ जवाब पर 10 पॉइंट्स!\n"
        f"➛ *शर्त:* क्विज़ शुरू करने के लिए कम से कम 5 लोगों का 'Ready' होना ज़रूरी है।\n"
        f"__________________________________________\n\n"
        f"☞ *नीचे दिए गए बटन पर क्लिक करके अपनी हाज़िरी लगाएँ:*"
    )

    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🚀 I am Ready (0/5)", callback_data=f"ready_{chat_id}")]])
    msg = await context.bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=keyboard)

    ready_sessions[chat_id] = {
        "ready_users": set(),
        "msg_id": msg.message_id,
        "chat_title": chat_title,
        "questions": questions_to_ask,
        "timer": timer,
        "status": "waiting"
    }

async def handle_ready_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = update.effective_chat.id
    user = update.effective_user

    if chat_id not in ready_sessions:
        await query.answer("यह क्विज़ सेशन अब एक्टिव नहीं है।", show_alert=True)
        return

    session = ready_sessions[chat_id]
    if session["status"] != "waiting":
        await query.answer("क्विज़ शुरू हो चुका है!", show_alert=True)
        return

    if user.id in session["ready_users"]:
        await query.answer("आप पहले से Ready हैं! दूसरों का इंतज़ार करें।", show_alert=True)
        return

    session["ready_users"].add(user.id)
    count = len(session["ready_users"])
    await query.answer("✅ आप क्विज़ के लिए तैयार हैं!")

    if count < 5: # 5 LOGIN SYSTEM
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(f"🚀 I am Ready ({count}/5)", callback_data=f"ready_{chat_id}")]])
        try: await query.edit_message_reply_markup(reply_markup=keyboard)
        except Exception: pass
    else:
        session["status"] = "countdown"
        await query.edit_message_reply_markup(reply_markup=None)
        await context.bot.send_message(chat_id, "🔥 *5 लोग जुड़ चुके हैं! क्विज़ ठीक 1 मिनट में शुरू होगा...*", parse_mode="Markdown")
        await asyncio.sleep(60)
        if chat_id in ready_sessions:
            q_data = ready_sessions.pop(chat_id)
            await run_quiz(context, chat_id, q_data["chat_title"], q_data["questions"], q_data["timer"])

# ==========================================
# RUN QUIZ & POLL SCORING
# ==========================================
async def run_quiz(context, chat_id, chat_title, questions, timer):
    active_quizzes[chat_id] = {"running": True, "scores": {}, "current_q": 0, "total_q": len(questions)}
    await context.bot.send_message(chat_id, "🚀 *क्विज़ शुरू! पहला सवाल आ रहा है...*", parse_mode="Markdown")
    await asyncio.sleep(2)

    for idx, q in enumerate(questions):
        if chat_id not in active_quizzes or not active_quizzes[chat_id]["running"]: break
        
        poll_msg = await context.bot.send_poll(
            chat_id, f"प्रश्न {idx+1}/{len(questions)}: {q['question']}", options=q["options"],
            type="quiz", correct_option_id=q["correct_index"], explanation=q.get("explanation", ""),
            open_period=timer, is_anonymous=False
        )
        active_quizzes[chat_id]["poll_id"] = poll_msg.poll.id
        active_quizzes[chat_id]["correct_idx"] = q["correct_index"]
        await asyncio.sleep(timer + 1)

    if chat_id in active_quizzes:
        scores = active_quizzes[chat_id]["scores"]
        del active_quizzes[chat_id]
        await generate_and_send_pdf(context, chat_id, chat_title, scores)

async def handle_poll_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    answer = update.poll_answer
    poll_id = answer.poll_id
    user_id = answer.user.id
    name = answer.user.first_name
    selected = answer.option_ids[0] if answer.option_ids else -1

    for chat_id, quiz_data in active_quizzes.items():
        if quiz_data.get("poll_id") == poll_id:
            if selected == quiz_data["correct_idx"]:
                if user_id not in quiz_data["scores"]: quiz_data["scores"][user_id] = {"name": name, "score": 0}
                quiz_data["scores"][user_id]["score"] += 10
                db.add_coins(user_id, 10)
            break

# ==========================================
# PDF LEADERBOARD
# ==========================================
async def generate_and_send_pdf(context, chat_id, chat_title, scores_dict):
    if not scores_dict:
        await context.bot.send_message(chat_id, "📝 क्विज़ समाप्त! किसी ने भी सही जवाब नहीं दिया।")
        return

    sorted_users = sorted(scores_dict.values(), key=lambda x: x["score"], reverse=True)
    text = "🏆 *FINAL LEADERBOARD*\n__________________________\n"
    for i, u in enumerate(sorted_users[:5]):
        medals = ["🥇", "🥈", "🥉", "🏅", "🏅"]
        text += f"{medals[i] if i < 5 else '🔹'} {u['name']} - {u['score']} Points\n"
    await context.bot.send_message(chat_id, text, parse_mode="Markdown")

    try:
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", 'B', 16)
        pdf.cell(200, 10, txt=f"Official Quiz Result", ln=True, align='C')
        pdf.cell(200, 10, txt=f"Group: {chat_title[:30]}", ln=True, align='C')
        pdf.ln(10)
        
        pdf.set_font("Arial", 'B', 12)
        pdf.cell(30, 10, "Rank", border=1, align='C')
        pdf.cell(100, 10, "Student Name", border=1)
        pdf.cell(40, 10, "Score", border=1, align='C')
        pdf.ln()
        
        pdf.set_font("Arial", '', 12)
        for idx, user in enumerate(sorted_users):
            safe_name = user['name'].encode('ascii', 'ignore').decode()
            if not safe_name.strip(): safe_name = "Student"
            pdf.cell(30, 10, str(idx + 1), border=1, align='C')
            pdf.cell(100, 10, safe_name[:25], border=1)
            pdf.cell(40, 10, str(user['score']), border=1, align='C')
            pdf.ln()
            
        file_path = f"/tmp/result_{chat_id}.pdf"
        pdf.output(file_path)
        await context.bot.send_document(
            chat_id, document=open(file_path, "rb"),
            caption="📄 *विस्तृत लीडरबोर्ड (Detailed Result)* 👆\nडाउनलोड करके अपनी रैंक चेक करें!",
            parse_mode="Markdown"
        )
        os.remove(file_path)
    except Exception as e:
        print("PDF Error:", e)

async def start_duel(*args, **kwargs):
    pass
