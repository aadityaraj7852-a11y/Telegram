"""
quiz_engine.py
Complete Advanced Quiz Engine
Features: 5-Person Ready System, Admin Instant Start, PDF Leaderboards, Custom Timers, Clean UI, Config Coins.
"""

import asyncio
import os
import random
import re
import json
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from fpdf import FPDF

import database as db
import config
from utils.reactions import auto_react
from utils.permissions import is_admin, is_owner

logger = logging.getLogger(__name__)

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

async def start_quiz_session(context: ContextTypes.DEFAULT_TYPE, chat_id, chat_title, subject_id, chapter_id, user_id, num_questions, custom_timer=None):
    if is_quiz_active(chat_id):
        await context.bot.send_message(chat_id, "⚠️ Yahan pehle se ek quiz chal raha hai ya wait kar raha hai!")
        return

    all_q = db.get_questions()
    filtered_q = []
    for q in all_q:
        if subject_id and q.get('subject_id') != subject_id: 
            continue
        if chapter_id and q.get('chapter_id') != chapter_id: 
            continue
        filtered_q.append(q)

    if not filtered_q:
        await context.bot.send_message(chat_id, "❌ Is topic ke liye sufficient questions nahi hain.")
        return

    random.shuffle(filtered_q)
    questions_to_ask = filtered_q[:num_questions]
    timer = custom_timer if custom_timer else getattr(config, 'QUESTION_TIME', 15)
    subj_name = "Mixed (Sabhi Vishay)" if not subject_id else "Selected Topic"

    # 🔥 CLEANED UI (Fixed line length so it doesn't overflow)
    text = (
        "🏆 <b>LIVE QUIZ — MockRise</b> 🏆\n\n"
        f"📚 <b>Topic:</b> {subj_name}\n"
        f"📝 <b>Practice Mode</b>\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        f"❓ <b>{len(questions_to_ask)} Qs</b>  |  ⏱ <b>{timer}s/Q</b>\n"
        "🏅 <b>Result PDF + Rank</b>\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "✅ <b>+2 Coins</b>  ❌ <b>-1 Coin</b>\n\n"
        "👇 <b>Neeche button dabakar join karein!</b>"
    )

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("🚀 Join Quiz (0/5)", callback_data=f"ready_{chat_id}")
    ]])

    msg = await context.bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=keyboard)

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
        await query.answer("Ye quiz session ab active nahi hai.", show_alert=True)
        return

    session = ready_sessions[chat_id]
    if session["status"] != "waiting":
        await query.answer("Quiz shuru ho chuka hai!", show_alert=True)
        return

    if is_admin(user.id) or is_owner(user.id):
        session["status"] = "countdown"
        await query.answer("👑 Admin Action: Quiz turant shuru ho raha hai!", show_alert=True)
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass
        
        await context.bot.send_message(chat_id, "🔥 Admin ne quiz start kar diya hai! Pehla sawal aa raha hai...", parse_mode="Markdown")
        
        if chat_id in ready_sessions:
            q_data = ready_sessions.pop(chat_id)
            await run_quiz(context, chat_id, q_data["chat_title"], q_data["questions"], q_data["timer"])
        return

    if user.id in session["ready_users"]:
        await query.answer("Aap pehle se Ready hain!", show_alert=True)
        return

    session["ready_users"].add(user.id)
    count = len(session["ready_users"])
    await query.answer("✅ Aap ready hain!")

    if count < 5:
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton(f"🚀 Join Quiz ({count}/5)", callback_data=f"ready_{chat_id}")
        ]])
        try:
            await query.edit_message_reply_markup(reply_markup=keyboard)
        except Exception as e:
            logger.error(f"Markup edit error: {e}")
    else:
        session["status"] = "countdown"
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass
        
        await context.bot.send_message(chat_id, "🔥 5 log jud chuke hain! Quiz theek 1 minute me shuru hoga...", parse_mode="Markdown")
        await asyncio.sleep(60)
        
        if chat_id in ready_sessions:
            q_data = ready_sessions.pop(chat_id)
            await run_quiz(context, chat_id, q_data["chat_title"], q_data["questions"], q_data["timer"])

async def run_quiz(context: ContextTypes.DEFAULT_TYPE, chat_id, chat_title, questions, timer):
    active_quizzes[chat_id] = {
        "running": True, 
        "scores": {}, 
        "current_q": 0, 
        "total_q": len(questions)
    }
    
    await asyncio.sleep(2)

    for idx, q in enumerate(questions):
        if chat_id not in active_quizzes or not active_quizzes[chat_id]["running"]: 
            break
        
        try:
            raw_q = str(q.get("question", "")).replace("<br>", "\n").replace("<br/>", "\n")
            clean_q = re.sub(r'<[^>]+>', '', raw_q).strip()
            if len(clean_q) > 280:
                clean_q = clean_q[:277] + "..."
            question_text = f"Q{idx+1}/{len(questions)}: {clean_q}"

            raw_opts = q.get("options", [])
            if isinstance(raw_opts, str):
                try:
                    raw_opts = json.loads(raw_opts)
                except Exception:
                    raw_opts = [o.strip() for o in raw_opts.split("\n") if o.strip()]

            clean_opts = []
            for opt in raw_opts:
                opt_str = re.sub(r'<[^>]+>', '', str(opt)).strip()
                if len(opt_str) > 100:
                    opt_str = opt_str[:97] + "..."
                if opt_str:
                    clean_opts.append(opt_str)

            while len(clean_opts) < 2:
                clean_opts.append(f"Option {len(clean_opts)+1}")
            clean_opts = clean_opts[:10]

            correct_idx = q.get("correct_index", 0)
            if not isinstance(correct_idx, int) or correct_idx < 0 or correct_idx >= len(clean_opts):
                correct_idx = 0

            raw_exp = str(q.get("explanation", "")).replace("<br>", "\n").replace("<br/>", "\n")
            clean_exp = re.sub(r'<[^>]+>', '', raw_exp).strip()
            if len(clean_exp) > 200:
                clean_exp = clean_exp[:197] + "..."

            poll_msg = await context.bot.send_poll(
                chat_id=chat_id, 
                question=question_text, 
                options=clean_opts,
                type="quiz", 
                correct_option_id=correct_idx, 
                explanation=clean_exp if clean_exp else None,
                open_period=timer, 
                is_anonymous=False
            )
            
            active_quizzes[chat_id]["poll_id"] = poll_msg.poll.id
            active_quizzes[chat_id]["correct_idx"] = correct_idx
            
            await asyncio.sleep(timer + 1)
            
        except Exception as e:
            logger.error(f"Error sending poll in {chat_id}: {e}")
            await asyncio.sleep(2)

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
            if user_id not in quiz_data["scores"]: 
                quiz_data["scores"][user_id] = {"name": name, "score": 0}
            
            # Get group specific coin settings or fall back to global config
            gs = db.get_group_settings(chat_id)
            correct_reward = gs.get('coin_per_correct') if gs and gs.get('coin_per_correct') else getattr(config, 'COIN_PER_CORRECT', 2)
            
            if selected == quiz_data["correct_idx"]:
                quiz_data["scores"][user_id]["score"] += 2
                try:
                    db.add_coins(user_id, correct_reward)
                except Exception as e:
                    logger.error(f"Error adding coins: {e}")
            else:
                quiz_data["scores"][user_id]["score"] -= 1
                try:
                    db.deduct_coins(user_id, 1)
                except Exception as e:
                    logger.error(f"Error deducting coins: {e}")
            break

async def generate_and_send_pdf(context: ContextTypes.DEFAULT_TYPE, chat_id, chat_title, scores_dict):
    if not scores_dict:
        await context.bot.send_message(chat_id, "📝 Quiz samapt! Kisi ne bhi hissa nahi liya.")
        return

    sorted_users = sorted(scores_dict.values(), key=lambda x: x["score"], reverse=True)
    
    text = "🏆 *FINAL LEADERBOARD*\n__________________________\n"
    for i, u in enumerate(sorted_users[:5]):
        medals = ["🥇", "🥈", "🥉", "🏅", "🏅"]
        medal = medals[i] if i < 5 else '🔹'
        text += f"{medal} {u['name']} - {u['score']} Points\n"
    
    await context.bot.send_message(chat_id, text, parse_mode="Markdown")

    try:
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", 'B', 16)
        pdf.cell(200, 10, txt="Official Quiz Result", ln=True, align='C')
        
        safe_chat_title = chat_title[:30].encode('ascii', 'ignore').decode() if chat_title else "Group Quiz"
        pdf.cell(200, 10, txt=f"Group: {safe_chat_title}", ln=True, align='C')
        pdf.ln(10)
        
        pdf.set_font("Arial", 'B', 12)
        pdf.cell(30, 10, "Rank", border=1, align='C')
        pdf.cell(100, 10, "Student Name", border=1)
        pdf.cell(40, 10, "Score", border=1, align='C')
        pdf.ln()
        
        pdf.set_font("Arial", '', 12)
        for idx, user in enumerate(sorted_users):
            safe_name = user['name'].encode('ascii', 'ignore').decode().strip()
            if not safe_name: safe_name = "Student"
                
            pdf.cell(30, 10, str(idx + 1), border=1, align='C')
            pdf.cell(100, 10, safe_name[:25], border=1)
            pdf.cell(40, 10, str(user['score']), border=1, align='C')
            pdf.ln()
            
        file_path = f"/tmp/result_{chat_id}.pdf"
        pdf.output(file_path)
        
        await context.bot.send_document(
            chat_id, 
            document=open(file_path, "rb"),
            caption="📄 *Vistrit Leaderboard (Detailed Result)* 👆\nDownload karke apni rank check karein!",
            parse_mode="Markdown"
        )
        if os.path.exists(file_path): os.remove(file_path) 
    except Exception as e:
        logger.error(f"PDF Error: {e}")
        await context.bot.send_message(chat_id, "⚠️ Leaderboard PDF generate karne me error aayi.")

async def start_duel(*args, **kwargs):
    pass
