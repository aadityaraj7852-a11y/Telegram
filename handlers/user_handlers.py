"""
user_handlers.py
Normal users ke liye commands: start, help, quiz start, leaderboard,
myscore, history, referral, withdraw request, profile
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

import database as db
import config
import quiz_engine
from utils.exporters import build_leaderboard_text, build_scorecard_text


async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    referred_by = None
    if context.args and context.args[0].startswith("ref_"):
        try:
            referred_by = int(context.args[0].replace("ref_", ""))
            if referred_by == user.id:
                referred_by = None
        except ValueError:
            referred_by = None

    existing = db.get_user(user.id)
    db.upsert_user(user.id, user.username, user.first_name, referred_by=referred_by if not existing else None)
    db.touch_online(user.id)

    if update.effective_chat.type in ("group", "supergroup"):
        db.upsert_group(update.effective_chat.id, update.effective_chat.title)

    text = (
        f"👋 Namaste {user.first_name}!\n\n"
        "Main ek Quiz Bot hoon — group me quiz khelo, coins kamao aur "
        "leaderboard me top karo! 🏆\n\n"
        "*Kuch useful commands:*\n"
        "/quiz — Group me quiz shuru karo\n"
        "/leaderboard — Top players dekho\n"
        "/myscore — Apna score card dekho\n"
        "/history — Apni quiz history dekho\n"
        "/referral — Apna referral link paao\n"
        "/wallet — Coins balance dekho\n"
        "/help — Sab commands ki list\n"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "*📖 Sab Commands*\n\n"
        "*User Commands:*\n"
        "/quiz — Naya quiz shuru karo (group me)\n"
        "/stopquiz — Chal raha quiz rokdo\n"
        "/leaderboard — Group leaderboard\n"
        "/globaltop — Global leaderboard\n"
        "/myscore — Apna scorecard\n"
        "/history — Purani quiz history\n"
        "/wallet — Coins balance\n"
        "/referral — Referral link\n"
        "/withdraw <coins> — Coins withdraw request\n"
        "/subjects — Sab subjects dekho\n\n"
        "*Admin Commands (owner/admin):*\n"
        "/addquestion — Manually question add karo\n"
        "/uploadword — Word file se bulk questions add karo\n"
        "/samplefile — Sample format file paao\n"
        "/exportquestions — Poora question bank docx me export karo\n"
        "/deletequestion <id> — Question delete karo\n"
        "/addadmin <user_id> — Naya admin banao (owner only)\n"
        "/removeadmin <user_id> — Admin hatao (owner only)\n"
        "/broadcast <text> — Sab users ko message\n"
        "/postad — Group/channel me ad post karo\n"
        "/backup — Database backup file paao\n"
        "/restore — Backup file se restore karo\n"
        "/stats — Bot ke stats dekho\n"
        "/userinfo <user_id> — Kisi user ka pura data\n"
        "/ban <user_id> / /unban <user_id>\n"
        "/withdrawals — Pending withdrawal requests\n"
        "/setcoinrate <amount> — Correct answer ka coin rate set karo\n"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def quiz_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type not in ("group", "supergroup"):
        await update.message.reply_text("⚠️ Quiz sirf group me hi khela ja sakta hai. Bot ko group me add karo!")
        return

    if quiz_engine.is_quiz_active(chat.id):
        await update.message.reply_text("⚠️ Yaha pehle se quiz chal raha hai.")
        return

    subjects = db.get_subjects()
    if not subjects:
        await update.message.reply_text("❌ Abhi tak koi subject/question add nahi hua hai. Admin se kehna /uploadword use kare.")
        return

    keyboard = [[InlineKeyboardButton(s["name"], callback_data=f"qsubj_{s['subject_id']}")] for s in subjects]
    await update.message.reply_text("📚 Subject chuno:", reply_markup=InlineKeyboardMarkup(keyboard))


async def subject_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    subject_id = int(query.data.split("_")[1])
    chapters = db.get_chapters(subject_id)

    keyboard = [[InlineKeyboardButton(c["name"], callback_data=f"qchap_{subject_id}_{c['chapter_id']}")]
                for c in chapters]
    keyboard.append([InlineKeyboardButton("📖 Poora Subject (sab chapters)", callback_data=f"qallchap_{subject_id}")])
    await query.edit_message_text("📑 Chapter chuno:", reply_markup=InlineKeyboardMarkup(keyboard))


async def chapter_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split("_")
    subject_id = int(parts[1])
    chapter_id = int(parts[2])

    keyboard = [
        [InlineKeyboardButton("10 Questions", callback_data=f"qlen_{subject_id}_{chapter_id}_10"),
         InlineKeyboardButton("20 Questions", callback_data=f"qlen_{subject_id}_{chapter_id}_20")],
        [InlineKeyboardButton("30 Questions", callback_data=f"qlen_{subject_id}_{chapter_id}_30")],
    ]
    await query.edit_message_text("🔢 Kitne questions chahiye?", reply_markup=InlineKeyboardMarkup(keyboard))


async def all_chapters_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    subject_id = int(query.data.split("_")[1])

    keyboard = [
        [InlineKeyboardButton("10 Questions", callback_data=f"qslen_{subject_id}_10"),
         InlineKeyboardButton("20 Questions", callback_data=f"qslen_{subject_id}_20")],
        [InlineKeyboardButton("30 Questions", callback_data=f"qslen_{subject_id}_30")],
    ]
    await query.edit_message_text("🔢 Kitne questions chahiye?", reply_markup=InlineKeyboardMarkup(keyboard))


async def length_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split("_")
    subject_id = int(parts[1])
    chapter_id = int(parts[2])
    num = int(parts[3])

    await query.edit_message_text(f"✅ Quiz shuru ho raha hai... ({num} questions)")

    chat = query.message.chat
    await quiz_engine.start_quiz_session(
        context, chat.id, chat.title, subject_id, chapter_id,
        query.from_user.id, num
    )


async def subject_length_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split("_")
    subject_id = int(parts[1])
    num = int(parts[2])

    await query.edit_message_text(f"✅ Quiz shuru ho raha hai... ({num} questions)")

    chat = query.message.chat
    await quiz_engine.start_quiz_session(
        context, chat.id, chat.title, subject_id, None,
        query.from_user.id, num
    )


async def stopquiz_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    stopped = await quiz_engine.stop_quiz(context, chat.id)
    if not stopped:
        await update.message.reply_text("Koi active quiz nahi hai.")


async def leaderboard_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = db.leaderboard(limit=10)
    text = build_leaderboard_text(rows, "🏆 Global Leaderboard")
    await update.message.reply_text(text, parse_mode="Markdown")


async def globaltop_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = db.leaderboard(limit=20)
    text = build_leaderboard_text(rows, "🌍 Top 20 Global Players")
    await update.message.reply_text(text, parse_mode="Markdown")


async def myscore_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    u = db.get_user(user.id)
    if not u:
        await update.message.reply_text("Pehle koi quiz khelo /quiz se!")
        return

    accuracy = round((u["total_correct"] / u["total_questions"]) * 100, 1) if u["total_questions"] else 0
    text = (
        f"📊 *Tumhara Overall Scorecard*\n\n"
        f"👤 {u['first_name']}\n"
        f"🎮 Total Quizzes: {u['total_quizzes']}\n"
        f"✅ Total Correct: {u['total_correct']}\n"
        f"❌ Total Wrong: {u['total_wrong']}\n"
        f"🎯 Accuracy: {accuracy}%\n"
        f"🪙 Coins: {u['coins']}\n"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def history_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    rows = db.get_user_history(user.id, limit=10)
    if not rows:
        await update.message.reply_text("Abhi tak koi quiz history nahi hai.")
        return

    import time as _time
    lines = ["🕓 *Last 10 Quiz History*\n"]
    for r in rows:
        date_str = _time.strftime("%d-%b-%Y %H:%M", _time.localtime(r["started_at"]))
        lines.append(f"• {date_str} | {r['chat_title']} | ✅{r['correct']} ❌{r['wrong']} | 🪙{r['coins_earned']}")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def wallet_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    u = db.get_user(user.id)
    coins = u["coins"] if u else 0
    await update.message.reply_text(f"🪙 Tumhare paas {coins} coins hain.")


async def referral_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bot_username = (await context.bot.get_me()).username
    link = f"https://t.me/{bot_username}?start=ref_{update.effective_user.id}"
    await update.message.reply_text(
        f"👥 *Referral Program*\n\nApne dost ko is link se invite karo, "
        f"jab wo bot start karega tumhe 20 coins milenge!\n\n{link}",
        parse_mode="Markdown"
    )


async def withdraw_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Usage: /withdraw <coins>\nExample: /withdraw 100")
        return

    amount = int(context.args[0])
    u = db.get_user(user.id)
    if not u or u["coins"] < amount:
        await update.message.reply_text("❌ Itne coins tumhare paas nahi hain.")
        return

    db.deduct_coins(user.id, amount)
    wid = db.request_withdrawal(user.id, amount)
    await update.message.reply_text(
        f"✅ Withdrawal request bhej di gayi (ID #{wid})। Admin approve karega to process ho jayega."
    )

    # notify owner
    try:
        await context.bot.send_message(
            config.OWNER_ID,
            f"💰 Nayi withdrawal request!\nUser: {user.first_name} (@{user.username})\n"
            f"ID: {user.id}\nCoins: {amount}\nDekhne ke liye /withdrawals likho."
        )
    except Exception:
        pass


async def subjects_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    subjects = db.get_subjects()
    if not subjects:
        await update.message.reply_text("Abhi koi subject nahi hai.")
        return
    lines = ["📚 *Available Subjects:*\n"]
    for s in subjects:
        chapters = db.get_chapters(s["subject_id"])
        lines.append(f"• {s['name']} ({len(chapters)} chapters)")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
