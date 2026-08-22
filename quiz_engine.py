"""
quiz_engine.py
Telegram ke native "Quiz Poll" (type=quiz) ka use karta hai jisse
anti-cheat built-in milta hai:
  - Telegram khud ensure karta hai ki har user sirf ek baar answer kar sake
  - is_anonymous=False rakha hai taaki hume pata chale kisne kya answer diya
  - Correct answer poll close hone tak kisi ko dikhta nahi

Flow:
1. /quiz command -> subject/chapter select -> session create
2. Har question ek poll ke roop me bheja jata hai, open_period ke saath
3. PollAnswer handler har answer ko turant record karta hai (coins/score update)
4. Timer khatam hone par agla question, ya sab questions khatam hone par
   final leaderboard + scorecards bheje jaate hain
"""

import asyncio
import time
import json

from telegram import Poll, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

import database as db
import config
from utils.exporters import build_leaderboard_text

# active_polls[poll_id] = {
#   "session_id", "question_id", "correct_index", "chat_id",
#   "sent_at", "options"
# }
active_polls = {}

# active_sessions[chat_id] = {
#   "session_id", "questions": [...], "current_index", "task", "negative_marking"
# }
active_sessions = {}


async def start_quiz_session(context: ContextTypes.DEFAULT_TYPE, chat_id, chat_title,
                              subject_id, chapter_id, started_by, num_questions,
                              negative_marking=False):
    questions = db.get_questions(chapter_id=chapter_id, limit=num_questions) if chapter_id \
        else db.get_questions(subject_id=subject_id, limit=num_questions)

    if not questions:
        await context.bot.send_message(chat_id, "❌ Is chapter/subject me abhi koi question nahi hai.")
        return

    if chat_id in active_sessions:
        await context.bot.send_message(chat_id, "⚠️ Is group me pehle se ek quiz chal raha hai.")
        return

    session_id = db.create_session(chat_id, chat_title, subject_id, chapter_id, started_by,
                                    len(questions), int(negative_marking))

    active_sessions[chat_id] = {
        "session_id": session_id,
        "questions": questions,
        "current_index": 0,
        "negative_marking": negative_marking,
        "participants": set(),
    }

    await context.bot.send_message(
        chat_id,
        f"🎯 *Quiz Shuru Ho Raha Hai!*\n📚 Total Questions: {len(questions)}\n"
        f"⏱ Har question ke liye {config.QUESTION_TIME} seconds milenge.\n"
        f"🪙 Sahi jawab = {config.COIN_PER_CORRECT} coins (+{config.SPEED_BONUS} speed bonus)\n\n"
        f"Ready ho jao... 3⃣ 2⃣ 1⃣ 🚀",
        parse_mode="Markdown"
    )
    await asyncio.sleep(3)
    await send_next_question(context, chat_id)


async def send_next_question(context: ContextTypes.DEFAULT_TYPE, chat_id):
    session = active_sessions.get(chat_id)
    if not session:
        return

    idx = session["current_index"]
    questions = session["questions"]

    if idx >= len(questions):
        await finish_quiz(context, chat_id)
        return

    q = questions[idx]
    options = json.loads(q["options"])

    try:
        message = await context.bot.send_poll(
            chat_id=chat_id,
            question=f"Q{idx+1}/{len(questions)}: {q['question_text']}",
            options=options,
            type=Poll.QUIZ,
            correct_option_id=q["correct_index"],
            is_anonymous=False,
            open_period=config.QUESTION_TIME,
            explanation=q["explanation"] or None,
        )
    except Exception:
        # fallback: agar open_period fail ho (kuch edge cases me), bina timer ke bhejo
        message = await context.bot.send_poll(
            chat_id=chat_id,
            question=f"Q{idx+1}/{len(questions)}: {q['question_text']}",
            options=options,
            type=Poll.QUIZ,
            correct_option_id=q["correct_index"],
            is_anonymous=False,
        )

    active_polls[message.poll.id] = {
        "session_id": session["session_id"],
        "question_id": q["question_id"],
        "correct_index": q["correct_index"],
        "chat_id": chat_id,
        "sent_at": time.time(),
        "options": options,
    }

    session["current_index"] += 1

    # schedule next question after QUESTION_TIME + small buffer
    session["task"] = context.application.create_task(
        _schedule_next(context, chat_id, config.QUESTION_TIME + 2)
    )


async def _schedule_next(context, chat_id, delay):
    await asyncio.sleep(delay)
    if chat_id in active_sessions:
        await send_next_question(context, chat_id)


async def handle_poll_answer(update, context: ContextTypes.DEFAULT_TYPE):
    """PollAnswerHandler - jab bhi koi user poll me answer deta hai"""
    poll_answer = update.poll_answer
    poll_id = poll_answer.poll_id
    user = poll_answer.user

    info = active_polls.get(poll_id)
    if not info:
        return

    db.upsert_user(user.id, user.username, user.first_name)
    db.touch_online(user.id)

    session_id = info["session_id"]
    chat_id = info["chat_id"]
    selected = poll_answer.option_ids[0] if poll_answer.option_ids else None
    is_correct = (selected == info["correct_index"])
    answer_time = round(time.time() - info["sent_at"], 2)

    db.log_answer(session_id, user.id, info["question_id"], selected, is_correct, answer_time)

    session = active_sessions.get(chat_id)
    negative = session["negative_marking"] if session else False

    if is_correct:
        coins = config.COIN_PER_CORRECT
        if answer_time <= 5:
            coins += config.SPEED_BONUS
        db.add_coins(user.id, coins)
        db.upsert_result(session_id, user.id, 1, 0, coins, answer_time)
    else:
        penalty = 0
        if negative:
            penalty = max(0, config.COIN_PER_CORRECT // 2)
            db.deduct_coins(user.id, penalty)
        db.upsert_result(session_id, user.id, 0, 1, -penalty, answer_time)

    if session:
        session["participants"].add(user.id)


async def finish_quiz(context: ContextTypes.DEFAULT_TYPE, chat_id):
    session = active_sessions.pop(chat_id, None)
    if not session:
        return

    session_id = session["session_id"]
    db.end_session(session_id)

    results = db.get_session_results(session_id)
    total_q = len(session["questions"])

    for r in results:
        db.record_quiz_completion(r["user_id"], r["correct"], r["wrong"], total_q)

    if not results:
        await context.bot.send_message(chat_id, "Quiz khatam! Lekin kisi ne bhi jawab nahi diya. 😅")
        return

    lines = ["🏁 *Quiz Khatam!* Final Results:\n"]
    medals = ["🥇", "🥈", "🥉"]
    for i, r in enumerate(results[:10]):
        prefix = medals[i] if i < 3 else f"{i+1}."
        name = r["first_name"] or r["username"] or f"User{r['user_id']}"
        lines.append(f"{prefix} {name} — ✅{r['correct']} ❌{r['wrong']} | 🪙{r['coins_earned']}")

    lines.append(f"\n📊 Total Questions: {total_q}")
    lines.append("Apna full scorecard dekhne ke liye /myscore likho.")

    await context.bot.send_message(chat_id, "\n".join(lines), parse_mode="Markdown")


def is_quiz_active(chat_id):
    return chat_id in active_sessions


async def stop_quiz(context: ContextTypes.DEFAULT_TYPE, chat_id):
    session = active_sessions.get(chat_id)
    if not session:
        return False
    task = session.get("task")
    if task:
        task.cancel()
    await finish_quiz(context, chat_id)
    return True
