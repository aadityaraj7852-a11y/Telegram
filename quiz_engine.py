"""
quiz_engine.py
Updated Quiz Engine: Admin/Owner can instantly start the quiz without waiting for user ready clicks.
"""

import asyncio
import os
import random
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from fpdf import FPDF

import database as db
import config
from utils.reactions import auto_react

logger = logging.getLogger(__name__)

# Active quizzes ट्रैक करने के लिए
active_quizzes = {}

def is_quiz_active(chat_id):
    return chat_id in active_quizzes

async def stop_quiz(context: ContextTypes.DEFAULT_TYPE, chat_id):
    if chat_id in active_quizzes:
        active_quizzes[chat_id]['running'] = False
        del active_quizzes[chat_id]
        return True
    return False

# =========================================================================
# INSTANT START QUIZ (Admin/Owner द्वारा तुरंत शुरू करने के लिए)
# =========================================================================
async def start_quiz_session(context: ContextTypes.DEFAULT_TYPE, chat_id, chat_title, subject_id, chapter_id, user_id, num_questions, custom_timer=None):
    if is_quiz_active(chat_id):
        await context.bot.send_message(chat_id, "⚠️ यहाँ पहले से एक क्विज़ चल रहा है!")
        return

    # डेटाबेस से सवाल उठाना
    all_q = db.get_questions()
    filtered_q = []
    for q in all_q:
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

    # बिना इंतज़ार के सीधे ग्रुप में घोषणा करना कि क्विज़ शुरू हो रहा है
    start_text = (
        f"❑ *महा-क्विज़ प्रतियोगिता शुरू हो चुकी है!*\n"
        f"__________________________________________\n\n"
        f"➭ *विषय (Topic):* {subj_name}\n"
        f"➛ *कुल प्रश्न:* {len(questions_to_ask)}\n"
        f"➛ *समय:* {timer} सेकंड प्रति प्रश्न ☞ तेज़ जवाब पर 10 पॉइंट्स!\n"
        f"__________________________________________\n\n"
        f"🚀 *पहला सवाल कुछ ही सेकंड में आ रहा है... तैयार हो जाएं!*"
    )
    
    await context.bot.send_message(chat_id, start_text, parse_mode="Markdown")
    
    # 2 सेकंड का छोटा गैप देकर सीधे क्विज़ शुरू कर देना
    await asyncio.sleep(2)
    await run_quiz(context, chat_id, chat_title, questions_to_ask, timer)


# =========================================================================
# RUN QUIZ & POLL SCORING
# =========================================================================
async def run_quiz(context: ContextTypes.DEFAULT_TYPE, chat_id, chat_title, questions, timer):
    active_quizzes[chat_id] = {
        "running": True, 
        "scores": {}, 
        "current_q": 0, 
        "total_q": len(questions)
    }

    for idx, q in enumerate(questions):
        if chat_id not in active_quizzes or not active_quizzes[chat_id]["running"]: 
            break
        
        try:
            poll_msg = await context.bot.send_poll(
                chat_id, 
                f"प्रश्न {idx+1}/{len(questions)}: {q['question']}", 
                options=q["options"],
                type="quiz", 
                correct_option_id=q["correct_index"], 
                explanation=q.get("explanation", ""),
                open_period=timer, 
                is_anonymous=False
            )
            
            active_quizzes[chat_id]["poll_id"] = poll_msg.poll.id
            active_quizzes[chat_id]["correct_idx"] = q["correct_index"]
            
            # पोल के बंद होने तक का इंतज़ार (timer + 1 second)
            await asyncio.sleep(timer + 1)
            
        except Exception as e:
            logger.error(f"Error sending poll in {chat_id}: {e}")
            await asyncio.sleep(2)

    # जब सारे सवाल खत्म हो जाएं
    if chat_id in active_quizzes:
        scores = active_quizzes[chat_id]["scores"]
        del active_quizzes[chat_id]
        
        # एडमिन/ओनर को प्राइवेट मैसेज में नोटिफिकेशन भेजना कि क्विज़ पूरा हो गया है
        try:
            await context.bot.send_message(
                config.OWNER_ID, 
                f"📊 *Quiz Completed!*\nGroup: {chat_title}\nसारे सवाल सफलताપूर्वक समाप्त हो गए हैं और लीडरबोर्ड भेज दिया गया है।"
            )
        except Exception:
            pass
            
        await generate_and_send_pdf(context, chat_id, chat_title, scores)


# पोल (Poll) में यूज़र का जवाब चेक करना
async def handle_poll_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    answer = update.poll_answer
    poll_id = answer.poll_id
    user_id = answer.user.id
    name = answer.user.first_name
    selected = answer.option_ids[0] if answer.option_ids else -1

    for chat_id, quiz_data in active_quizzes.items():
        if quiz_data.get("poll_id") == poll_id:
            if selected == quiz_data["correct_idx"]:
                if user_id not in quiz_data["scores"]: 
                    quiz_data["scores"][user_id] = {"name": name, "score": 0}
                # सही जवाब पर 10 पॉइंट
                quiz_data["scores"][user_id]["score"] += 10
                
                try:
                    db.add_coins(user_id, 10)
                except Exception as e:
                    logger.error(f"Error adding coins: {e}")
            break


# =========================================================================
# 3. PDF LEADERBOARD GENERATION
# =========================================================================
async def generate_and_send_pdf(context: ContextTypes.DEFAULT_TYPE, chat_id, chat_title, scores_dict):
    if not scores_dict:
        await context.bot.send_message(chat_id, "📝 क्विज़ समाप्त! किसी ने भी सही जवाब नहीं दिया।")
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
        os.remove(file_path)
    except Exception as e:
        logger.error(f"PDF Error: {e}")
        await context.bot.send_message(chat_id, "⚠️ Leaderboard PDF generate karne me error aayi.")
