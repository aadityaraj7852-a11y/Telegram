"""
quiz_engine.py
Complete Advanced Quiz Engine
Features: 5-Person Ready System, Admin Instant Start, PDF Leaderboards, Custom Timers, Fancy UI, Negative Marking.
"""

import asyncio
import os
import random
import re
import json
import ast
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from fpdf import FPDF

import database as db
import config
from utils.reactions import auto_react
from utils.permissions import is_admin, is_owner

logger = logging.getLogger(__name__)

# Active quizzes aur Ready sessions track karne ke liye
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
# 1. FANCY UI & READY SYSTEM
# ==========================================
async def start_quiz_session(context: ContextTypes.DEFAULT_TYPE, chat_id, chat_title, subject_id, chapter_id, user_id, num_questions, custom_timer=None):
    if is_quiz_active(chat_id):
        await context.bot.send_message(chat_id, "⚠️ यहाँ पहले से एक क्विज़ चल रहा है या शुरू होने वाला है!")
        return

    all_q_rows = db.get_questions()
    filtered_q = []
    for row in all_q_rows:
        # 🛠 FIX: Convert sqlite3.Row to standard dict instantly
        q = dict(row)
        if subject_id and q.get('subject_id') != subject_id: 
            continue
        if chapter_id and q.get('chapter_id') != chapter_id: 
            continue
        filtered_q.append(q)

    if not filtered_q:
        await context.bot.send_message(chat_id, "❌ इस टॉपिक के लिए पर्याप्त सवाल नहीं हैं।")
        return

    random.shuffle(filtered_q)
    questions_to_ask = filtered_q[:num_questions]
    timer = custom_timer if custom_timer else getattr(config, 'QUESTION_TIME', 15)
    subj_name = "Mixed (सभी विषय)" if not subject_id else "Selected Topic"

    # 🔥 FANCY UI + Reward Display (+2, -1)
    text = (
        f"╔══════════════════╗\n"
        f"🏆 *LIVE QUIZ — MockRise* 🏆\n"
        f"╚══════════════════╝\n\n"
        f"📚 *Topic:* {subj_name}\n"
        f"📝 *Unlimited Question Practice*\n\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"❓ *{len(questions_to_ask)} प्रश्न*  ⏱ *{timer}s/Q*\n"
        f"🔀 *Shuffle: ON*\n"
        f"🏅 *Result PDF + Rank*\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"✅ *+2 Coins*  ❌ *-1 Coin*  ⚡ *जल्दी = बेहतर Rank*\n\n"
        f"👇 *Join करें!*"
    )

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("🚀 Join Quiz (0/5)", callback_data=f"ready_{chat_id}")
    ]])

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
        await query.answer("क्विज़ की प्रक्रिया आगे बढ़ चुकी है!", show_alert=True)
        return

    # 🚀 ADMIN OVERRIDE LOGIC
    if is_admin(user.id) or is_owner(user.id):
        session["status"] = "countdown"
        await query.answer("👑 Admin Action: Quiz तुरंत शुरू हो रहा है!", show_alert=True)
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass
        
        await context.bot.send_message(
            chat_id, 
            "🔥 *Admin ने क्विज़ स्टार्ट कर दिया है! पहला सवाल आ रहा है...*", 
            parse_mode="Markdown"
        )
        
        if chat_id in ready_sessions:
            q_data = ready_sessions.pop(chat_id)
            asyncio.create_task(run_quiz(context, chat_id, q_data["chat_title"], q_data["questions"], q_data["timer"]))
        return

    # 👥 NORMAL USER LOGIC
    if user.id in session["ready_users"]:
        await query.answer("आप पहले से Ready हैं! दूसरों का इंतज़ार करें।", show_alert=True)
        return

    session["ready_users"].add(user.id)
    count = len(session["ready_users"])
    await query.answer("✅ आप क्विज़ के लिए तैयार हैं!")

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
        
        await context.bot.send_message(
            chat_id, 
            "🔥 *5 लोग जुड़ चुके हैं! क्विज़ ठीक 1 मिनट में शुरू होगा...*\n\nतैयार रहें!", 
            parse_mode="Markdown"
        )
        
        await asyncio.sleep(60)
        
        if chat_id in ready_sessions:
            q_data = ready_sessions.pop(chat_id)
            asyncio.create_task(run_quiz(context, chat_id, q_data["chat_title"], q_data["questions"], q_data["timer"]))

# ==========================================
# 2. RUN QUIZ & POLL SCORING
# ==========================================
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
        
        # ⚠️ GIANT TRY-EXCEPT BLOCK: Never let the loop crash!
        try:
            # 🧹 QUESTION SANITIZE
            raw_q = str(q.get("question", "")).replace("<br>", "\n").replace("<br/>", "\n")
            clean_q = re.sub(r'<[^>]+>', '', raw_q).strip()
            if not clean_q: 
                clean_q = "Question"
            if len(clean_q) > 280:
                clean_q = clean_q[:277] + "..."
            question_text = f"Q{idx+1}/{len(questions)}: {clean_q}"

            # 🛠 OPTIONS SAFE PARSING
            raw_opts = q.get("options", [])
            if isinstance(raw_opts, str):
                try:
                    raw_opts = json.loads(raw_opts)
                except Exception:
                    try:
                        raw_opts = ast.literal_eval(raw_opts)
                    except Exception:
                        raw_opts = [o.strip() for o in raw_opts.split("\n") if o.strip()]

            clean_opts = []
            if isinstance(raw_opts, list):
                for opt in raw_opts:
                    opt_str = re.sub(r'<[^>]+>', '', str(opt)).strip()
                    if len(opt_str) > 100:
                        opt_str = opt_str[:97] + "..."
                    if opt_str:
                        clean_opts.append(opt_str)

            while len(clean_opts) < 2:
                clean_opts.append(f"Option {len(clean_opts)+1}")
            clean_opts = clean_opts[:10]

            # 🛠 CORRECT INDEX SAFE BOUNDING
            correct_idx = q.get("correct_index", 0)
            try:
                correct_idx = int(correct_idx)
            except:
                correct_idx = 0
            correct_idx = max(0, min(correct_idx, len(clean_opts) - 1))

            # 🧹 EXPLANATION SANITIZE
            raw_exp = str(q.get("explanation", "")).replace("<br>", "\n").replace("<br/>", "\n")
            clean_exp = re.sub(r'<[^>]+>', '', raw_exp).strip()

            try:
                # 📡 ATTEMPT 1: SEND NATIVE TELEGRAM POLL
                poll_msg = await context.bot.send_poll(
                    chat_id=chat_id, 
                    question=question_text, 
                    options=clean_opts,
                    type="quiz", 
                    correct_option_id=correct_idx, 
                    explanation=clean_exp[:197] + "..." if len(clean_exp) > 200 else (clean_exp if clean_exp else None),
                    open_period=timer, 
                    is_anonymous=False
                )
                
                active_quizzes[chat_id]["poll_id"] = poll_msg.poll.id
                active_quizzes[chat_id]["correct_idx"] = correct_idx
                
                # ⏱ Wait for timer
                await asyncio.sleep(timer + 1)
                
                # 💡 SEND FULL EXPLANATION AFTER TIMER
                if clean_exp:
                    exp_text = f"💡 Q{idx+1} व्याख्या (Explanation):\n{clean_exp[:3900]}"
                    try:
                        await context.bot.send_message(chat_id, exp_text)
                    except Exception:
                        pass
                    await asyncio.sleep(1.5) 
                
            except Exception as e:
                logger.error(f"Poll creation failed for Q{idx+1}: {e}")
                # 🚀 ATTEMPT 2: BULLETPROOF FALLBACK (If Poll Fails)
                try:
                    opts_text = "\n".join([f"{chr(65+i)}. {o}" for i, o in enumerate(clean_opts)])
                    # NO PARSE MODE - To prevent entity parsing crashes!
                    await context.bot.send_message(chat_id, f"❓ {question_text}\n\n{opts_text}")
                    
                    await asyncio.sleep(timer)
                    
                    ans_letter = chr(65+correct_idx)
                    sol_fallback = f"💡 सही उत्तर (Correct Answer): {ans_letter}\n"
                    if clean_exp:
                        sol_fallback += f"\nव्याख्या (Explanation):\n{clean_exp[:3900]}"
                        
                    await context.bot.send_message(chat_id, sol_fallback)
                    await asyncio.sleep(1.5)
                except Exception as inner_e:
                    logger.error(f"Fallback also failed: {inner_e}")
                    await context.bot.send_message(chat_id, f"⚠️ Q{idx+1} लोड नहीं हो सका। अगले प्रश्न पर जा रहे हैं...")
                    await asyncio.sleep(2)

        except Exception as giant_e:
            logger.error(f"Giant Try-Except Block Caught Error: {giant_e}")
            await asyncio.sleep(1)

    # Jab saare sawaal khatam ho jayein
    if chat_id in active_quizzes:
        scores = active_quizzes[chat_id]["scores"]
        del active_quizzes[chat_id]
        await generate_and_send_pdf(context, chat_id, chat_title, scores)


# Poll me user ka jawab check karna (NEGATIVE MARKING INCLUDED)
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
            
            if selected == quiz_data["correct_idx"]:
                # Sahi Jawab: 2 Points + 2 Coins
                quiz_data["scores"][user_id]["score"] += 2
                try:
                    db.add_coins(user_id, 2)
                except Exception as e:
                    logger.error(f"Error adding coins: {e}")
            else:
                # Galat Jawab: -1 Point + 1 Coin cut (Negative Marking)
                quiz_data["scores"][user_id]["score"] -= 1
                try:
                    db.deduct_coins(user_id, 1)
                except Exception as e:
                    logger.error(f"Error deducting coins: {e}")
                    
            break

# ==========================================
# 3. PDF LEADERBOARD GENERATION
# ==========================================
async def generate_and_send_pdf(context: ContextTypes.DEFAULT_TYPE, chat_id, chat_title, scores_dict):
    if not scores_dict:
        await context.bot.send_message(chat_id, "📝 क्विज़ समाप्त! किसी ने भी हिस्सा नहीं लिया।")
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
            if not safe_name: 
                safe_name = "Student"
                
            pdf.cell(30, 10, str(idx + 1), border=1, align='C')
            pdf.cell(100, 10, safe_name[:25], border=1)
            pdf.cell(40, 10, str(user['score']), border=1, align='C')
            pdf.ln()
            
        file_path = f"/tmp/result_{chat_id}.pdf"
        pdf.output(file_path)
        
        await context.bot.send_document(
            chat_id, 
            document=open(file_path, "rb"),
            caption="📄 *विस्तृत लीडरबोर्ड (Detailed Result)* 👆\nडाउनलोड करके अपनी रैंक चेक करें!",
            parse_mode="Markdown"
        )
        if os.path.exists(file_path):
            os.remove(file_path)
    except Exception as e:
        logger.error(f"PDF Error: {e}")
        await context.bot.send_message(chat_id, "⚠️ Leaderboard PDF generate karne me error aayi.")


async def start_duel(*args, **kwargs):
    pass
