"""
quiz_engine.py
Telegram ke native "Quiz Poll" (type=quiz) ka use karta hai jisse
anti-cheat built-in milta hai:
  - Telegram khud ensure karta hai ki har user sirf ek baar answer kar sake
  - is_anonymous=False rakha hai taaki hume pata chale kisne kya answer diya
  - Correct answer poll close hone tak kisi ko dikhta nahi

Naya is version me:
  - Har group/channel apna alag coin-rate, negative-marking, entry-fee rakh
    sakta hai (admin /groupsettings se set karta hai). Agar set nahi hai to
    global default (config.py) use hota hai.
  - Entry fee: jab koi participant apna PEHLA answer deta hai us quiz session
    me, usse entry fee kat ti hai (agar coins kam hain to uska jawab count
    nahi hota aur usse bataya jata hai).
  - Duel engine: private chat me solo practice ya 1v1 challenge quiz.

Flow (group quiz):
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

# active_polls[poll_id] = {
#   "session_id", "question_id", "correct_index", "chat_id",
#   "sent_at", "options", "is_duel", "duel_id"
# }
active_polls = {}

# active_sessions[chat_id] = {
#   "session_id", "questions": [...], "current_index", "task",
#   "negative_marking", "negative_amount", "coin_rate", "entry_fee",
#   "participants", "charged_users"
# }
active_sessions = {}

# active_duels[private_chat_id] tracks a running solo/1v1 quiz in private chat.
active_duels = {}


def _effective_group_config(chat_id):
    """Group-specific settings override the global .env defaults."""
    gs = db.get_group_settings(chat_id)
    coin_rate = config.COIN_PER_CORRECT
    negative = False
    negative_amount = config.COIN_PER_CORRECT // 2
    entry_fee = 0

    if gs:
        if gs["coin_per_correct"] is not None:
            coin_rate = gs["coin_per_correct"]
        negative = bool(gs["negative_marking"])
        if gs["negative_amount"] is not None:
            negative_amount = gs["negative_amount"]
        entry_fee = gs["entry_fee"] or 0

    return {
        "coin_rate": coin_rate,
        "negative_marking": negative,
        "negative_amount": negative_amount,
        "entry_fee": entry_fee,
    }


# =========================================================================
# GROUP QUIZ
# =========================================================================

async def start_quiz_session(context: ContextTypes.DEFAULT_TYPE, chat_id, chat_title,
                              subject_id, chapter_id, started_by, num_questions):
    questions = db.get_questions(chapter_id=chapter_id, limit=num_questions) if chapter_id \
        else db.get_questions(subject_id=subject_id, limit=num_questions)

    if not questions:
        await context.bot.send_message(chat_id, "❌ Is chapter/subject me abhi koi question nahi hai.")
        return

    if chat_id in active_sessions:
        await context.bot.send_message(chat_id, "⚠️ Is group me pehle se ek quiz chal raha hai.")
        return

    cfg = _effective_group_config(chat_id)

    session_id = db.create_session(chat_id, chat_title, subject_id, chapter_id, started_by,
                                    len(questions), int(cfg["negative_marking"]))

    active_sessions[chat_id] = {
        "session_id": session_id,
        "questions": questions,
        "current_index": 0,
        "negative_marking": cfg["negative_marking"],
        "negative_amount": cfg["negative_amount"],
        "coin_rate": cfg["coin_rate"],
        "entry_fee": cfg["entry_fee"],
        "participants": set(),
        "charged_users": set(),
    }

    entry_line = f"🎟 Entry fee: {cfg['entry_fee']} coins (pehla answer dete hi katega)\n" \
        if cfg["entry_fee"] > 0 else ""
    negative_line = f"⚠️ Negative marking ON: galat jawab pe -{cfg['negative_amount']} coins\n" \
        if cfg["negative_marking"] else ""

    await context.bot.send_message(
        chat_id,
        f"🎯 *Quiz Shuru Ho Raha Hai!*\n📚 Total Questions: {len(questions)}\n"
        f"⏱ Har question ke liye {config.QUESTION_TIME} seconds milenge.\n"
        f"🪙 Sahi jawab = {cfg['coin_rate']} coins (+{config.SPEED_BONUS} speed bonus)\n"
        f"{negative_line}{entry_line}\n"
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
        "is_duel": False,
    }

    session["current_index"] += 1

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

    if info.get("is_duel"):
        await _handle_duel_answer(context, poll_answer, info)
        return

    session_id = info["session_id"]
    chat_id = info["chat_id"]
    selected = poll_answer.option_ids[0] if poll_answer.option_ids else None
    is_correct = (selected == info["correct_index"])
    answer_time = round(time.time() - info["sent_at"], 2)

    session = active_sessions.get(chat_id)
    if not session:
        return

    # ---- Entry fee: charged once, on the participant's first answer ----
    entry_fee = session["entry_fee"]
    if entry_fee > 0 and user.id not in session["charged_users"]:
        u = db.get_user(user.id)
        if not u or u["coins"] < entry_fee:
            try:
                await context.bot.send_message(
                    user.id,
                    f"⚠️ Is quiz me participate karne ke liye {entry_fee} coins chahiye "
                    f"(entry fee). Tumhare paas kam coins hain, is liye tumhara jawab count nahi hoga."
                )
            except Exception:
                pass
            return
        db.deduct_coins(user.id, entry_fee)
        session["charged_users"].add(user.id)

    db.log_answer(session_id, user.id, info["question_id"], selected, is_correct, answer_time)

    coin_rate = session["coin_rate"]
    if is_correct:
        coins = coin_rate
        if answer_time <= 5:
            coins += config.SPEED_BONUS
        db.add_coins(user.id, coins)
        db.upsert_result(session_id, user.id, 1, 0, coins, answer_time)
    else:
        penalty = 0
        if session["negative_marking"]:
            penalty = session["negative_amount"]
            db.deduct_coins(user.id, penalty)
        db.upsert_result(session_id, user.id, 0, 1, -penalty, answer_time)

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

    sent = await context.bot.send_message(chat_id, "\n".join(lines), parse_mode="Markdown")
    from utils.reactions import auto_react
    await auto_react(context, chat_id, sent.message_id)


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


# =========================================================================
# SOLO PRACTICE / 1v1 DUEL (private chat)
# =========================================================================

async def start_duel(context: ContextTypes.DEFAULT_TYPE, private_chat_id, challenger_id,
                      opponent_id, subject_id, chapter_id, num_questions):
    """opponent_id = challenger_id for solo practice (no real opponent)."""
    questions = db.get_questions(chapter_id=chapter_id, limit=num_questions) if chapter_id \
        else db.get_questions(subject_id=subject_id, limit=num_questions)

    if not questions:
        await context.bot.send_message(private_chat_id, "❌ Is chapter/subject me abhi koi question nahi hai.")
        return

    if private_chat_id in active_duels:
        await context.bot.send_message(private_chat_id, "⚠️ Pehle se ek quiz chal raha hai yaha.")
        return

    duel_id = db.create_duel(challenger_id, opponent_id, subject_id, chapter_id, len(questions))
    db.update_duel_status(duel_id, "active")

    active_duels[private_chat_id] = {
        "duel_id": duel_id,
        "questions": questions,
        "current_index": 0,
        "task": None,
        "is_solo": (opponent_id == challenger_id),
    }

    mode_text = "Solo Practice 🎯" if opponent_id == challenger_id else "1v1 Duel ⚔️"
    await context.bot.send_message(
        private_chat_id,
        f"🎮 *{mode_text}* shuru!\n📚 Questions: {len(questions)}\n\nReady? 🚀",
        parse_mode="Markdown"
    )
    await asyncio.sleep(2)
    await send_duel_question(context, private_chat_id)


async def send_duel_question(context: ContextTypes.DEFAULT_TYPE, private_chat_id):
    duel = active_duels.get(private_chat_id)
    if not duel:
        return

    idx = duel["current_index"]
    questions = duel["questions"]

    if idx >= len(questions):
        await finish_duel(context, private_chat_id)
        return

    q = questions[idx]
    options = json.loads(q["options"])

    message = await context.bot.send_poll(
        chat_id=private_chat_id,
        question=f"Q{idx+1}/{len(questions)}: {q['question_text']}",
        options=options,
        type=Poll.QUIZ,
        correct_option_id=q["correct_index"],
        is_anonymous=False,
        open_period=min(config.QUESTION_TIME, 30),
        explanation=q["explanation"] or None,
    )

    active_polls[message.poll.id] = {
        "duel_id": duel["duel_id"],
        "question_id": q["question_id"],
        "correct_index": q["correct_index"],
        "chat_id": private_chat_id,
        "sent_at": time.time(),
        "options": options,
        "is_duel": True,
    }

    duel["current_index"] += 1
    duel["task"] = context.application.create_task(
        _schedule_next_duel(context, private_chat_id, min(config.QUESTION_TIME, 30) + 2)
    )


async def _schedule_next_duel(context, private_chat_id, delay):
    await asyncio.sleep(delay)
    if private_chat_id in active_duels:
        await send_duel_question(context, private_chat_id)


async def _handle_duel_answer(context, poll_answer, info):
    user = poll_answer.user
    selected = poll_answer.option_ids[0] if poll_answer.option_ids else None
    is_correct = (selected == info["correct_index"])
    duel_id = info["duel_id"]

    if is_correct:
        coins = config.COIN_PER_CORRECT
        db.add_coins(user.id, coins)
        db.upsert_duel_result(duel_id, user.id, 1, 0)
    else:
        db.upsert_duel_result(duel_id, user.id, 0, 1)


async def finish_duel(context: ContextTypes.DEFAULT_TYPE, private_chat_id):
    duel = active_duels.pop(private_chat_id, None)
    if not duel:
        return

    duel_id = duel["duel_id"]
    db.update_duel_status(duel_id, "finished")
    results = db.get_duel_results(duel_id)
    total_q = len(duel["questions"])

    for r in results:
        db.record_quiz_completion(r["user_id"], r["correct"], r["wrong"], total_q)

    if not results:
        await context.bot.send_message(private_chat_id, "Quiz khatam! Koi jawab nahi mila.")
        return

    lines = ["🏁 *Quiz Khatam!*\n"]
    for r in sorted(results, key=lambda x: -x["correct"]):
        name = r["first_name"] or r["username"] or f"User{r['user_id']}"
        lines.append(f"👤 {name} — ✅{r['correct']} ❌{r['wrong']}")

    if not duel["is_solo"] and len(results) == 2:
        r1, r2 = results[0], results[1]
        if r1["correct"] > r2["correct"]:
            winner = r1["first_name"] or r1["username"]
        elif r2["correct"] > r1["correct"]:
            winner = r2["first_name"] or r2["username"]
        else:
            winner = None
        lines.append(f"\n🏆 Winner: {winner}!" if winner else "\n🤝 Match Draw!")

    await context.bot.send_message(private_chat_id, "\n".join(lines), parse_mode="Markdown")


def is_duel_active(private_chat_id):
    return private_chat_id in active_duels
