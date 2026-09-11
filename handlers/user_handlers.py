"""
user_handlers.py
Normal users ke liye commands: start (menu UI), help, group quiz,
solo practice, 1v1 duel challenge, leaderboard, myscore, history,
referral, withdraw, subjects, notes dekhna.

Menu UI: /start ya /menu par ek clean button-based menu aata hai
(sab kuch button se, type kam karna padta hai). Har button ek
category kholta hai.
"""

import time

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

import database as db
import config
import quiz_engine
from utils.exporters import build_leaderboard_text
from utils.permissions import is_admin


# =========================================================================
# MAIN MENU (button UI)
# =========================================================================

def main_menu_keyboard(user_id):
    keyboard = [
        [InlineKeyboardButton("🎯 Group Quiz", callback_data="menu_groupquiz"),
         InlineKeyboardButton("🧠 Solo Practice", callback_data="menu_solo")],
        [InlineKeyboardButton("⚔️ 1v1 Challenge", callback_data="menu_duel"),
         InlineKeyboardButton("📚 Subjects", callback_data="menu_subjects")],
        [InlineKeyboardButton("🏆 Leaderboard", callback_data="menu_leaderboard"),
         InlineKeyboardButton("📊 My Score", callback_data="menu_myscore")],
        [InlineKeyboardButton("🕓 History", callback_data="menu_history"),
         InlineKeyboardButton("🪙 Wallet", callback_data="menu_wallet")],
        [InlineKeyboardButton("👥 Referral", callback_data="menu_referral"),
         InlineKeyboardButton("💸 Withdraw", callback_data="menu_withdraw")],
        [InlineKeyboardButton("💬 Students Lounge", callback_data="menu_lounge"),
         InlineKeyboardButton("📋 Discover", callback_data="menu_discover")],
    ]
    if is_admin(user_id):
        keyboard.append([InlineKeyboardButton("👑 Admin Panel", callback_data="menu_admin")])
    return InlineKeyboardMarkup(keyboard)


def admin_menu_keyboard():
    keyboard = [
        [InlineKeyboardButton("➕ Add Question", callback_data="amenu_addq"),
         InlineKeyboardButton("📎 Upload Word File", callback_data="amenu_uploadword")],
        [InlineKeyboardButton("📦 Export Questions", callback_data="amenu_export"),
         InlineKeyboardButton("📄 Sample File", callback_data="amenu_sample")],
        [InlineKeyboardButton("⚙️ Group Settings", callback_data="amenu_groupsettings"),
         InlineKeyboardButton("📋 List Groups", callback_data="amenu_listgroups")],
        [InlineKeyboardButton("📢 Broadcast", callback_data="amenu_broadcast"),
         InlineKeyboardButton("📣 Post Ad", callback_data="amenu_postad")],
        [InlineKeyboardButton("📝 Send Note", callback_data="amenu_sendnote"),
         InlineKeyboardButton("🏷 Hashtag Ideas", callback_data="amenu_hashtags")],
        [InlineKeyboardButton("💾 Backup", callback_data="amenu_backup"),
         InlineKeyboardButton("📊 Stats", callback_data="amenu_stats")],
        [InlineKeyboardButton("💰 Withdrawals", callback_data="amenu_withdrawals"),
         InlineKeyboardButton("👮 Admins", callback_data="amenu_admins")],
        [InlineKeyboardButton("😀 Reactions Bot", callback_data="amenu_reactions"),
         InlineKeyboardButton("🚀 Visibility Booster", callback_data="amenu_boost")],
        [InlineKeyboardButton("📋 Manage Directory", callback_data="amenu_directory")],
        [InlineKeyboardButton("⬅️ Back", callback_data="menu_back")],
    ]
    return InlineKeyboardMarkup(keyboard)


def _back_kb():
    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Menu", callback_data="menu_back")]])


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
        await update.message.reply_text(
            "👋 Namaste! Quiz shuru karne ke liye /quiz likho.\n"
            "Poora menu dekhne ke liye mujhe private me /start karo 🙂"
        )
        return

    text = (
        f"👋 Namaste {user.first_name}!\n\n"
        "Main tumhara Quiz Bot hoon 🎯 — quiz khelo, coins kamao, "
        "leaderboard me top karo, aur students ke saath jud jao!\n\n"
        "Neeche diye options me se chuno 👇"
    )
    await update.message.reply_text(text, reply_markup=main_menu_keyboard(user.id))


async def menu_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/menu — kabhi bhi menu wapas kholne ke liye"""
    await update.message.reply_text(
        "📋 *Main Menu*\nNeeche se koi option chuno:",
        parse_mode="Markdown",
        reply_markup=main_menu_keyboard(update.effective_user.id)
    )


async def menu_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sab 'menu_*' callback buttons ko route karta hai."""
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "menu_back":
        await query.edit_message_text(
            "📋 *Main Menu*\nNeeche se koi option chuno:",
            parse_mode="Markdown",
            reply_markup=main_menu_keyboard(query.from_user.id)
        )
        return

    if data == "menu_admin":
        if not is_admin(query.from_user.id):
            await query.answer("⛔ Sirf admin ke liye.", show_alert=True)
            return
        await query.edit_message_text(
            "👑 *Admin Panel*\nKya karna hai chuno:",
            parse_mode="Markdown",
            reply_markup=admin_menu_keyboard()
        )
        return

    if data == "menu_groupquiz":
        await query.edit_message_text(
            "🎯 Group quiz sirf group me hi khela ja sakta hai.\n"
            "Apne group me jaake `/quiz` likho — ya bot ko group me add karo.",
            parse_mode="Markdown", reply_markup=_back_kb()
        )
        return

    if data == "menu_solo":
        await _send_mode_subject_picker(query)
        return

    if data == "menu_duel":
        await query.edit_message_text(
            "⚔️ *1v1 Challenge*\n\n"
            "Kisi ko challenge karne ke liye unka username ya user ID ke saath likho:\n"
            "`/challenge @username` ya `/challenge 123456789`\n\n"
            "(Us user ne bhi kabhi bot ko /start kiya hona chahiye)",
            parse_mode="Markdown", reply_markup=_back_kb()
        )
        return

    if data == "menu_subjects":
        await _show_subjects(None, edit=True, query=query)
        return

    if data == "menu_leaderboard":
        rows = db.leaderboard(limit=10)
        text = build_leaderboard_text(rows, "🏆 Global Leaderboard")
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=_back_kb())
        return

    if data == "menu_myscore":
        text = _myscore_text(query.from_user.id)
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=_back_kb())
        return

    if data == "menu_history":
        text = _history_text(query.from_user.id)
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=_back_kb())
        return

    if data == "menu_wallet":
        u = db.get_user(query.from_user.id)
        coins = u["coins"] if u else 0
        await query.edit_message_text(f"🪙 Tumhare paas {coins} coins hain.", reply_markup=_back_kb())
        return

    if data == "menu_referral":
        bot_username = (await context.bot.get_me()).username
        link = f"https://t.me/{bot_username}?start=ref_{query.from_user.id}"
        await query.edit_message_text(
            f"👥 *Referral Program*\n\nApne dost ko is link se invite karo, "
            f"jab wo bot start karega tumhe 20 coins milenge!\n\n{link}",
            parse_mode="Markdown", reply_markup=_back_kb()
        )
        return

    if data == "menu_withdraw":
        await query.edit_message_text(
            "💸 Coins withdraw karne ke liye likho:\n`/withdraw <coins>`\n\nExample: `/withdraw 100`",
            parse_mode="Markdown", reply_markup=_back_kb()
        )
        return

    if data == "menu_lounge":
        await _send_lounge_link_query(query, context)
        return

    if data == "menu_discover":
        categories = db.get_directory_categories()
        if not categories:
            await query.edit_message_text(
                "📋 Abhi directory me koi group/channel list nahi hai.",
                reply_markup=_back_kb()
            )
            return
        keyboard = [[InlineKeyboardButton(f"📁 {c}", callback_data=f"dircat_{c}")] for c in categories]
        keyboard.append([InlineKeyboardButton("⬅️ Menu", callback_data="menu_back")])
        await query.edit_message_text(
            "📋 *Group/Channel Directory*\n\nCategory chuno:",
            parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return


async def _show_subjects(message, edit=False, query=None):
    subjects = db.get_subjects()
    if not subjects:
        text = "Abhi koi subject nahi hai."
    else:
        lines = ["📚 *Available Subjects:*\n"]
        for s in subjects:
            chapters = db.get_chapters(s["subject_id"])
            qcount = len(db.get_questions(subject_id=s["subject_id"]))
            lines.append(f"• {s['name']} — {len(chapters)} chapters, {qcount} questions")
        text = "\n".join(lines)

    if edit and query:
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=_back_kb())
    else:
        await message.reply_text(text, parse_mode="Markdown")


def _myscore_text(user_id):
    u = db.get_user(user_id)
    if not u:
        return "Pehle koi quiz khelo!"
    accuracy = round((u["total_correct"] / u["total_questions"]) * 100, 1) if u["total_questions"] else 0
    return (
        f"📊 *Tumhara Overall Scorecard*\n\n"
        f"👤 {u['first_name']}\n"
        f"🎮 Total Quizzes: {u['total_quizzes']}\n"
        f"✅ Total Correct: {u['total_correct']}\n"
        f"❌ Total Wrong: {u['total_wrong']}\n"
        f"🎯 Accuracy: {accuracy}%\n"
        f"🪙 Coins: {u['coins']}\n"
    )


def _history_text(user_id):
    rows = db.get_user_history(user_id, limit=10)
    if not rows:
        return "Abhi tak koi quiz history nahi hai."
    lines = ["🕓 *Last 10 Quiz History*\n"]
    for r in rows:
        date_str = time.strftime("%d-%b-%Y %H:%M", time.localtime(r["started_at"]))
        lines.append(f"• {date_str} | {r['chat_title']} | ✅{r['correct']} ❌{r['wrong']} | 🪙{r['coins_earned']}")
    return "\n".join(lines)


def _lounge_link_for(user_id, first_name):
    url = config.WEBAPP_PUBLIC_URL
    if not url:
        return None
    u = db.get_user(user_id)
    display_name = (u["first_name"] if u else first_name) or "Student"
    import secrets
    token = secrets.token_urlsafe(24)
    db.upsert_chat_app_user(user_id, display_name, "🎓", token)
    return f"{url.rstrip('/')}/chat?token={token}"


async def _send_lounge_link_query(query, context):
    link = _lounge_link_for(query.from_user.id, query.from_user.first_name)
    if not link:
        await query.edit_message_text(
            "💬 Students Lounge abhi set up nahi hui hai. Owner ko `WEBAPP_PUBLIC_URL` "
            "environment variable set karne ko kaho.",
            reply_markup=_back_kb()
        )
        return
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("💬 Lounge Kholo", url=link)],
        [InlineKeyboardButton("⬅️ Menu", callback_data="menu_back")],
    ])
    await query.edit_message_text(
        "💬 *Students Lounge*\n\nYe ek group chat hai jaha sab students "
        "aapas me baat kar sakte hain. Neeche button dabao (link personal hai, share mat karna):",
        parse_mode="Markdown", reply_markup=keyboard
    )


# =========================================================================
# HELP
# =========================================================================

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "*📖 Sab Commands*\n\n"
        "*User Commands:*\n"
        "/start ya /menu — Button menu kholo\n"
        "/quiz — Group me quiz shuru karo\n"
        "/stopquiz — Chal raha quiz rokdo\n"
        "/solo — Private me akela practice karo\n"
        "/challenge <username/id> — Kisi ko 1v1 challenge karo\n"
        "/leaderboard — Group leaderboard\n"
        "/globaltop — Global leaderboard\n"
        "/myscore — Apna scorecard\n"
        "/history — Purani quiz history\n"
        "/wallet — Coins balance\n"
        "/referral — Referral link\n"
        "/withdraw <coins> — Coins withdraw request\n"
        "/subjects — Sab subjects dekho\n"
        "/lounge — Students discussion group ka link\n"
        "/discover — Group/channel directory browse karo\n\n"
        "*PDF/Notes Tools (sabke liye):*\n"
        "Koi bhi PDF bhejo → bot uska watermark/hyperlink hata kar wapas bhej dega\n\n"
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
        "/sendnote — HTML note banao aur bhejo\n"
        "/pushnote <id> <chat_id> — Saved note kisi group me bhejo\n"
        "/notelist — Saare saved notes\n"
        "/hashtags <topic> — Apne post ke liye hashtags\n"
        "/reactions — Reactions Bot status (is group me)\n"
        "/reactionson / /reactionsoff — Auto-react chalu/band\n"
        "/setreactionemojis 🔥 👍 — Reaction emojis set karo\n"
        "/boost — Post ko pin + scheduled repost se boost karo\n"
        "/boostlist / /stopboost <id> — Boost jobs manage karo\n"
        "/besttime — Is group ka best posting time dekho\n"
        "/adddirectory — Apna group/channel directory me add karo\n"
        "/removedirectory <id> — Directory entry hatao\n"
        "/groupsettings — Is group ke settings dekho\n"
        "/setgroupcoin <amt> — Is group ka coin rate\n"
        "/setgroupnegative on <amt> / off — Negative marking\n"
        "/setgroupentryfee <amt> — Entry fee set karo\n"
        "/addgroup <chat_id> [title] — Door se group register karo\n"
        "/listgroups — Sab registered groups\n"
        "/backup — Database backup file paao\n"
        "/restore — Backup file se restore karo\n"
        "/stats — Bot ke stats dekho\n"
        "/userinfo <user_id> — Kisi user ka pura data\n"
        "/ban <user_id> / /unban <user_id>\n"
        "/withdrawals — Pending withdrawal requests\n"
        "/setcoinrate <amount> — Global coin rate\n"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


# =========================================================================
# GROUP QUIZ
# =========================================================================

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


# =========================================================================
# SOLO PRACTICE + 1v1 DUEL (private chat) — minimum N subjects required
# =========================================================================

async def solo_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        await update.message.reply_text("🧠 Solo practice sirf mere private chat me hoti hai. Mujhe DM karo!")
        return
    subjects = db.get_subjects()
    if len(subjects) < config.MIN_SUBJECTS_FOR_SOLO:
        await update.message.reply_text(
            f"❌ Solo practice ke liye kam se kam {config.MIN_SUBJECTS_FOR_SOLO} subjects "
            f"available hone chahiye. Abhi sirf {len(subjects)} hain."
        )
        return
    keyboard = [[InlineKeyboardButton(s["name"], callback_data=f"solosubj_{s['subject_id']}")] for s in subjects]
    await update.message.reply_text("📚 Practice ke liye Subject chuno:", reply_markup=InlineKeyboardMarkup(keyboard))


async def _send_mode_subject_picker(query):
    subjects = db.get_subjects()
    if len(subjects) < config.MIN_SUBJECTS_FOR_SOLO:
        await query.edit_message_text(
            f"❌ Solo practice ke liye kam se kam {config.MIN_SUBJECTS_FOR_SOLO} subjects "
            f"available hone chahiye. Abhi sirf {len(subjects)} hain — admin se aur "
            f"subjects/questions add karne ko kaho.",
            reply_markup=_back_kb()
        )
        return
    keyboard = [[InlineKeyboardButton(s["name"], callback_data=f"solosubj_{s['subject_id']}")] for s in subjects]
    keyboard.append([InlineKeyboardButton("⬅️ Menu", callback_data="menu_back")])
    await query.edit_message_text("📚 Practice ke liye Subject chuno:", reply_markup=InlineKeyboardMarkup(keyboard))


async def solo_subject_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    subject_id = int(query.data.split("_")[1])
    keyboard = [
        [InlineKeyboardButton("5 Questions", callback_data=f"sololen_{subject_id}_5"),
         InlineKeyboardButton("10 Questions", callback_data=f"sololen_{subject_id}_10")],
        [InlineKeyboardButton("20 Questions", callback_data=f"sololen_{subject_id}_20")],
    ]
    await query.edit_message_text("🔢 Kitne questions?", reply_markup=InlineKeyboardMarkup(keyboard))


async def solo_length_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split("_")
    subject_id = int(parts[1])
    num = int(parts[2])
    await query.edit_message_text(f"✅ Solo practice shuru... ({num} questions)")
    await quiz_engine.start_duel(
        context, query.message.chat.id, query.from_user.id, query.from_user.id,
        subject_id, None, num
    )


async def challenge_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/challenge @username ya /challenge <user_id> — 1v1 duel invite."""
    if update.effective_chat.type != "private":
        await update.message.reply_text("⚔️ Challenge sirf private chat se bheja ja sakta hai. Mujhe DM karo!")
        return

    if not context.args:
        await update.message.reply_text(
            "Usage: /challenge <user_id>\n"
            "(Us user ne pehle bot ko /start kiya hona chahiye)"
        )
        return

    target = context.args[0].lstrip("@")
    opponent = None
    if target.isdigit():
        opponent = db.get_user(int(target))
    else:
        for u in db.get_all_users():
            if u["username"] and u["username"].lower() == target.lower():
                opponent = u
                break

    if not opponent:
        await update.message.reply_text("❌ Ye user nahi mila. Unhe pehle bot ko /start karna hoga.")
        return

    if opponent["user_id"] == update.effective_user.id:
        await update.message.reply_text("😅 Khud ko challenge nahi kar sakte! /solo try karo.")
        return

    subjects = db.get_subjects()
    if not subjects:
        await update.message.reply_text("❌ Abhi koi subject nahi hai.")
        return

    keyboard = [[InlineKeyboardButton(s["name"], callback_data=f"duelsubj_{opponent['user_id']}_{s['subject_id']}")]
                for s in subjects]
    await update.message.reply_text(
        f"⚔️ {opponent['first_name']} ko challenge kar rahe ho! Subject chuno:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def duel_subject_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, opponent_id, subject_id = query.data.split("_")
    keyboard = [
        [InlineKeyboardButton("5 Questions", callback_data=f"duellen_{opponent_id}_{subject_id}_5"),
         InlineKeyboardButton("10 Questions", callback_data=f"duellen_{opponent_id}_{subject_id}_10")],
    ]
    await query.edit_message_text("🔢 Kitne questions?", reply_markup=InlineKeyboardMarkup(keyboard))


async def duel_length_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, opponent_id, subject_id, num = query.data.split("_")
    opponent_id, subject_id, num = int(opponent_id), int(subject_id), int(num)

    await query.edit_message_text("✅ Challenge bhej diya! Doosre player ke accept karne ka wait kar rahe hain...")

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Accept", callback_data=f"duelaccept_{query.from_user.id}_{subject_id}_{num}"),
        InlineKeyboardButton("❌ Decline", callback_data=f"dueldecline_{query.from_user.id}"),
    ]])
    try:
        await context.bot.send_message(
            opponent_id,
            f"⚔️ *{query.from_user.first_name}* ne tumhe {num}-question quiz duel ke liye challenge kiya hai!",
            parse_mode="Markdown", reply_markup=keyboard
        )
    except Exception:
        await context.bot.send_message(
            query.message.chat.id,
            "❌ Challenge deliver nahi ho paya (ho sakta hai us user ne bot ko block kar rakha ho)."
        )


async def duel_accept_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, challenger_id, subject_id, num = query.data.split("_")
    challenger_id, subject_id, num = int(challenger_id), int(subject_id), int(num)

    await query.edit_message_text("✅ Accept kar liya! Quiz shuru ho raha hai...")
    try:
        await context.bot.send_message(challenger_id, f"✅ {query.from_user.first_name} ne challenge accept kar liya! Quiz shuru...")
    except Exception:
        pass

    # Dono players ko apne-apne private chat me alag poll milta hai (Telegram me
    # poll ek hi chat me hota hai) — end me duel_id se combined result compare
    # hokar winner announce hota hai.
    await quiz_engine.start_duel(context, challenger_id, challenger_id, query.from_user.id, subject_id, None, num)
    await quiz_engine.start_duel(context, query.from_user.id, challenger_id, query.from_user.id, subject_id, None, num)


async def duel_decline_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    challenger_id = int(query.data.split("_")[1])
    await query.edit_message_text("❌ Challenge decline kar diya.")
    try:
        await context.bot.send_message(challenger_id, f"❌ {query.from_user.first_name} ne tumhara challenge decline kar diya.")
    except Exception:
        pass


# =========================================================================
# LEADERBOARD / SCORE / HISTORY / WALLET / REFERRAL / WITHDRAW / SUBJECTS
# =========================================================================

async def leaderboard_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = db.leaderboard(limit=10)
    text = build_leaderboard_text(rows, "🏆 Global Leaderboard")
    await update.message.reply_text(text, parse_mode="Markdown")


async def globaltop_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = db.leaderboard(limit=20)
    text = build_leaderboard_text(rows, "🌍 Top 20 Global Players")
    await update.message.reply_text(text, parse_mode="Markdown")


async def myscore_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(_myscore_text(update.effective_user.id), parse_mode="Markdown")


async def history_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(_history_text(update.effective_user.id), parse_mode="Markdown")


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

    try:
        await context.bot.send_message(
            config.OWNER_ID,
            f"💰 Nayi withdrawal request!\nUser: {user.first_name} (@{user.username})\n"
            f"ID: {user.id}\nCoins: {amount}\nDekhne ke liye /withdrawals likho."
        )
    except Exception:
        pass


async def subjects_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _show_subjects(update.message)


async def lounge_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Students discussion group ka personal access link deta hai."""
    link = _lounge_link_for(update.effective_user.id, update.effective_user.first_name)
    if not link:
        await update.message.reply_text("💬 Students Lounge abhi set up nahi hui hai.")
        return
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("💬 Lounge Kholo", url=link)]])
    await update.message.reply_text(
        "💬 *Students Lounge*\n\nSab students ke saath baat karo.\n"
        "(Ye link personal hai, kisi ko mat dena)",
        parse_mode="Markdown", reply_markup=keyboard
    )


# =========================================================================
# GROUP/CHANNEL DIRECTORY (browse — admin-listed entries only)
# =========================================================================

async def discover_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Categories dikhata hai — jitne bhi admin ne apne groups/channels
    directory me add kiye hain unhe browse karne ka option."""
    categories = db.get_directory_categories()
    if not categories:
        await update.message.reply_text(
            "📋 Abhi directory me koi group/channel list nahi hai.\n"
            "Admin `/adddirectory` se apne groups/channels add kar sakta hai."
        )
        return
    keyboard = [[InlineKeyboardButton(f"📁 {c}", callback_data=f"dircat_{c}")] for c in categories]
    await update.message.reply_text(
        "📋 *Group/Channel Directory*\n\nCategory chuno:",
        parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def directory_category_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    category = query.data.split("_", 1)[1]
    entries = db.get_directory_entries(category)

    if not entries:
        await query.edit_message_text(f"'{category}' me abhi koi entry nahi hai.", reply_markup=_back_kb())
        return

    lines = [f"📁 *{category}*\n"]
    keyboard = []
    for e in entries:
        lines.append(f"• *{e['title']}*\n  {e['description']}")
        keyboard.append([InlineKeyboardButton(f"🔗 {e['title']}", callback_data=f"diropen_{e['entry_id']}")])
    keyboard.append([InlineKeyboardButton("⬅️ Menu", callback_data="menu_back")])

    await query.edit_message_text("\n\n".join(lines), parse_mode="Markdown",
                                  reply_markup=InlineKeyboardMarkup(keyboard))


async def directory_open_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    entry_id = int(query.data.split("_")[1])
    entry = db.get_directory_entry(entry_id)
    if not entry:
        await query.answer("Ye entry ab available nahi hai.", show_alert=True)
        return
    db.increment_directory_click(entry_id)
    await query.answer()
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🚀 Join Karo", url=entry["invite_link"])]])
    await query.message.reply_text(
        f"📌 *{entry['title']}*\n{entry['description']}",
        parse_mode="Markdown", reply_markup=keyboard
    )
