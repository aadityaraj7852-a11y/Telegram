"""
main.py
Bot ka entry point. Render pe isko "worker" ya "background worker"
service ke roop me run karo (python main.py).
"""

import logging

from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    PollAnswerHandler, ConversationHandler, ChatMemberHandler, filters
)

import config
import database as db
import quiz_engine
from handlers import user_handlers as uh
from handlers import admin_handlers as ah

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


async def track_group_membership(update: Update, context):
    """Jab bot kisi group me add ho ya group ka title change ho"""
    chat = update.effective_chat
    if chat.type in ("group", "supergroup"):
        db.upsert_group(chat.id, chat.title)


async def run_due_boost_jobs(context):
    """JobQueue callback — har minute chalta hai, jitne bhi Visibility
    Booster jobs ka time ho gaya hai unhe repost karta hai (aur agar
    reactions on hain to us group me auto-react bhi karta hai)."""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    from utils.reactions import auto_react

    due = db.get_due_boost_jobs()
    for job in due:
        reply_markup = None
        if job["button_text"] and job["button_url"]:
            reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton(job["button_text"], url=job["button_url"])]])
        try:
            sent = await context.bot.send_message(job["chat_id"], job["content"], reply_markup=reply_markup)
            db.mark_boost_job_run(job["job_id"], job["repost_every_minutes"])
            await auto_react(context, job["chat_id"], sent.message_id)
            if job["max_reposts"] and job["repost_count_done"] + 1 >= job["max_reposts"]:
                db.deactivate_boost_job(job["job_id"])
        except Exception:
            logger.exception(f"Boost job #{job['job_id']} repost karne me error aayi")
            db.deactivate_boost_job(job["job_id"])


async def track_user_activity(update: Update, context):
    """Har message pe user ko 'online'/'last seen' mark karo"""
    if update.effective_user:
        user = update.effective_user
        db.upsert_user(user.id, user.username, user.first_name)
        db.touch_online(user.id)


async def admin_menu_router(update: Update, context):
    """Admin panel ke 'amenu_*' buttons — inline conversation start nahi ho
    sakta callback se, is liye user ko sahi command batate hain (copy-paste
    friendly) taaki wo turant chala sake."""
    query = update.callback_query
    await query.answer()

    hints = {
        "amenu_addq": "➕ Naya question add karne ke liye likho:\n/addquestion",
        "amenu_uploadword": "📎 Word file upload karne ke liye likho:\n/uploadword\n(phir .docx file bhej do)",
        "amenu_export": "📦 Poora question bank export karne ke liye likho:\n/exportquestions",
        "amenu_sample": "📄 Sample format file paane ke liye likho:\n/samplefile",
        "amenu_groupsettings": "⚙️ Group settings dekhne ke liye us group me jaake likho:\n/groupsettings",
        "amenu_listgroups": "📋 Sab registered groups dekhne ke liye likho:\n/listgroups",
        "amenu_broadcast": "📢 Sab users ko message bhejne ke liye likho:\n/broadcast <tumhara message>",
        "amenu_postad": "📣 Ad post karne ke liye likho:\n/postad",
        "amenu_sendnote": "📝 Naya HTML note banane ke liye likho:\n/sendnote",
        "amenu_hashtags": "🏷 Hashtag suggestions ke liye likho:\n/hashtags <apna topic>",
        "amenu_backup": "💾 Database backup paane ke liye likho:\n/backup",
        "amenu_stats": "📊 Bot stats dekhne ke liye likho:\n/stats",
        "amenu_withdrawals": "💰 Pending withdrawals dekhne ke liye likho:\n/withdrawals",
        "amenu_admins": "👮 Sab admins dekhne ke liye likho:\n/listadmins",
        "amenu_reactions": "😀 Reactions Bot dekhne/on-off karne ke liye us group me likho:\n/reactions",
        "amenu_boost": "🚀 Post ko boost (pin + scheduled repost) karne ke liye us group me likho:\n/boost\n\nActive boosts dekhne ke liye:\n/boostlist\n\nBest posting time dekhne ke liye:\n/besttime",
        "amenu_directory": "📋 Apna group/channel directory me add karne ke liye likho:\n/adddirectory\n\nHatane ke liye:\n/removedirectory <id>",
    }
    text = hints.get(query.data, "Command available nahi hai.")
    await query.edit_message_text(text, reply_markup=uh._back_kb())


def build_app():
    db.init_db()

    app = Application.builder().token(config.BOT_TOKEN).build()

    # ---- Activity tracking (runs first, non-blocking group) ----
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, track_user_activity), group=-1)
    app.add_handler(ChatMemberHandler(track_group_membership, ChatMemberHandler.MY_CHAT_MEMBER), group=-1)

    # ---- User commands ----
    app.add_handler(CommandHandler("start", uh.start_cmd))
    app.add_handler(CommandHandler("menu", uh.menu_cmd))
    app.add_handler(CommandHandler("help", uh.help_cmd))
    app.add_handler(CommandHandler("quiz", uh.quiz_cmd))
    app.add_handler(CommandHandler("stopquiz", uh.stopquiz_cmd))
    app.add_handler(CommandHandler("solo", uh.solo_cmd))
    app.add_handler(CommandHandler("challenge", uh.challenge_cmd))
    app.add_handler(CommandHandler("leaderboard", uh.leaderboard_cmd))
    app.add_handler(CommandHandler("globaltop", uh.globaltop_cmd))
    app.add_handler(CommandHandler("myscore", uh.myscore_cmd))
    app.add_handler(CommandHandler("history", uh.history_cmd))
    app.add_handler(CommandHandler("wallet", uh.wallet_cmd))
    app.add_handler(CommandHandler("referral", uh.referral_cmd))
    app.add_handler(CommandHandler("withdraw", uh.withdraw_cmd))
    app.add_handler(CommandHandler("subjects", uh.subjects_cmd))
    app.add_handler(CommandHandler("lounge", uh.lounge_cmd))

    # ---- Main menu button router ----
    app.add_handler(CallbackQueryHandler(uh.menu_router, pattern=r"^menu_"))
    app.add_handler(CallbackQueryHandler(admin_menu_router, pattern=r"^amenu_"))

    # ---- Quiz selection callbacks (group quiz) ----
    app.add_handler(CallbackQueryHandler(uh.subject_selected, pattern=r"^qsubj_"))
    app.add_handler(CallbackQueryHandler(uh.chapter_selected, pattern=r"^qchap_"))
    app.add_handler(CallbackQueryHandler(uh.all_chapters_selected, pattern=r"^qallchap_"))
    app.add_handler(CallbackQueryHandler(uh.length_selected, pattern=r"^qlen_"))
    app.add_handler(CallbackQueryHandler(uh.subject_length_selected, pattern=r"^qslen_"))

    # ---- Solo practice callbacks ----
    app.add_handler(CallbackQueryHandler(uh.solo_subject_selected, pattern=r"^solosubj_"))
    app.add_handler(CallbackQueryHandler(uh.solo_length_selected, pattern=r"^sololen_"))

    # ---- 1v1 duel callbacks ----
    app.add_handler(CallbackQueryHandler(uh.duel_subject_selected, pattern=r"^duelsubj_"))
    app.add_handler(CallbackQueryHandler(uh.duel_length_selected, pattern=r"^duellen_"))
    app.add_handler(CallbackQueryHandler(uh.duel_accept_callback, pattern=r"^duelaccept_"))
    app.add_handler(CallbackQueryHandler(uh.duel_decline_callback, pattern=r"^dueldecline_"))

    # ---- Poll answers (core quiz scoring, group + solo + duel) ----
    app.add_handler(PollAnswerHandler(quiz_engine.handle_poll_answer))

    # ---- Admin: manual add question (conversation) ----
    addq_conv = ConversationHandler(
        entry_points=[CommandHandler("addquestion", ah.addquestion_start)],
        states={
            ah.ASK_SUBJECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, ah.addquestion_subject)],
            ah.ASK_CHAPTER: [MessageHandler(filters.TEXT & ~filters.COMMAND, ah.addquestion_chapter)],
            ah.ASK_QUESTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, ah.addquestion_question)],
            ah.ASK_OPTIONS: [MessageHandler(filters.TEXT, ah.addquestion_options)],
            ah.ASK_ANSWER: [MessageHandler(filters.TEXT & ~filters.COMMAND, ah.addquestion_answer)],
            ah.ASK_EXPLANATION: [MessageHandler(filters.TEXT, ah.addquestion_explanation)],
        },
        fallbacks=[CommandHandler("cancel", ah.addquestion_cancel)],
    )
    app.add_handler(addq_conv)

    # ---- Admin: post ad (conversation) ----
    ad_conv = ConversationHandler(
        entry_points=[CommandHandler("postad", ah.postad_start)],
        states={
            ah.ASK_AD_CONTENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, ah.postad_content)],
            ah.ASK_AD_BUTTON: [MessageHandler(filters.TEXT, ah.postad_button)],
        },
        fallbacks=[CommandHandler("cancel", ah.addquestion_cancel)],
    )
    app.add_handler(ad_conv)

    # ---- Admin: HTML note composer (conversation) ----
    note_conv = ConversationHandler(
        entry_points=[CommandHandler("sendnote", ah.sendnote_start)],
        states={
            ah.ASK_NOTE_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ah.sendnote_title)],
            ah.ASK_NOTE_CONTENT: [MessageHandler(filters.TEXT, ah.sendnote_content)],
        },
        fallbacks=[CommandHandler("cancel", ah.addquestion_cancel)],
    )
    app.add_handler(note_conv)
    app.add_handler(CommandHandler("pushnote", ah.pushnote_cmd))
    app.add_handler(CommandHandler("notelist", ah.notelist_cmd))
    app.add_handler(CallbackQueryHandler(ah.notesend_callback, pattern=r"^notesend_"))

    # ---- Admin: word file upload / export / sample ----
    app.add_handler(CommandHandler("uploadword", ah.uploadword_prompt))
    app.add_handler(CommandHandler("samplefile", ah.samplefile_cmd))
    app.add_handler(CommandHandler("exportquestions", ah.exportquestions_cmd))
    app.add_handler(CommandHandler("deletequestion", ah.deletequestion_cmd))

    # ---- Document routing: docx -> question import, db -> restore, pdf -> cleaner ----
    app.add_handler(MessageHandler(filters.Document.FileExtension("docx"), ah.handle_docx_upload))
    app.add_handler(MessageHandler(filters.Document.FileExtension("db"), ah.handle_db_restore_upload))
    app.add_handler(MessageHandler(filters.Document.PDF, ah.handle_pdf_clean_upload))

    # ---- Admin management ----
    app.add_handler(CommandHandler("addadmin", ah.addadmin_cmd))
    app.add_handler(CommandHandler("removeadmin", ah.removeadmin_cmd))
    app.add_handler(CommandHandler("listadmins", ah.listadmins_cmd))

    # ---- Broadcast / backup / stats ----
    app.add_handler(CommandHandler("broadcast", ah.broadcast_cmd))
    app.add_handler(CommandHandler("backup", ah.backup_cmd))
    app.add_handler(CommandHandler("restore", ah.restore_cmd))
    app.add_handler(CommandHandler("stats", ah.stats_cmd))
    app.add_handler(CommandHandler("userinfo", ah.userinfo_cmd))
    app.add_handler(CommandHandler("ban", ah.ban_cmd))
    app.add_handler(CommandHandler("unban", ah.unban_cmd))
    app.add_handler(CommandHandler("withdrawals", ah.withdrawals_cmd))
    app.add_handler(CommandHandler("setcoinrate", ah.setcoinrate_cmd))

    # ---- Per-group/channel settings (coin rate, negative marking, entry fee) ----
    app.add_handler(CommandHandler("groupsettings", ah.groupsettings_cmd))
    app.add_handler(CommandHandler("setgroupcoin", ah.setgroupcoin_cmd))
    app.add_handler(CommandHandler("setgroupnegative", ah.setgroupnegative_cmd))
    app.add_handler(CommandHandler("setgroupentryfee", ah.setgroupentryfee_cmd))
    app.add_handler(CommandHandler("addgroup", ah.addgroup_cmd))
    app.add_handler(CommandHandler("listgroups", ah.listgroups_cmd))

    # ---- Hashtag optimizer (for the bot's own posts) ----
    app.add_handler(CommandHandler("hashtags", ah.hashtags_cmd))

    # ---- Reactions Bot (auto-react on the bot's own posts) ----
    app.add_handler(CommandHandler("reactions", ah.reactions_cmd))
    app.add_handler(CommandHandler("reactionson", ah.reactionson_cmd))
    app.add_handler(CommandHandler("reactionsoff", ah.reactionsoff_cmd))
    app.add_handler(CommandHandler("setreactionemojis", ah.setreactionemojis_cmd))

    # ---- Visibility/Engagement Booster (pin + scheduled repost + best-time) ----
    boost_conv = ConversationHandler(
        entry_points=[CommandHandler("boost", ah.boost_start)],
        states={
            ah.ASK_BOOST_CONTENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, ah.boost_content)],
            ah.ASK_BOOST_BUTTON: [MessageHandler(filters.TEXT, ah.boost_button)],
            ah.ASK_BOOST_SCHEDULE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ah.boost_schedule)],
        },
        fallbacks=[CommandHandler("cancel", ah.addquestion_cancel)],
    )
    app.add_handler(boost_conv)
    app.add_handler(CommandHandler("boostlist", ah.boostlist_cmd))
    app.add_handler(CommandHandler("stopboost", ah.stopboost_cmd))
    app.add_handler(CommandHandler("besttime", ah.besttime_cmd))

    # ---- Group/Channel Directory (self-listed, no scraping) ----
    dir_conv = ConversationHandler(
        entry_points=[CommandHandler("adddirectory", ah.adddirectory_start)],
        states={
            ah.ASK_DIR_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ah.adddirectory_title)],
            ah.ASK_DIR_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, ah.adddirectory_desc)],
            ah.ASK_DIR_CATEGORY: [MessageHandler(filters.TEXT & ~filters.COMMAND, ah.adddirectory_category)],
            ah.ASK_DIR_LINK: [MessageHandler(filters.TEXT & ~filters.COMMAND, ah.adddirectory_link)],
        },
        fallbacks=[CommandHandler("cancel", ah.addquestion_cancel)],
    )
    app.add_handler(dir_conv)
    app.add_handler(CommandHandler("removedirectory", ah.removedirectory_cmd))
    app.add_handler(CommandHandler("discover", uh.discover_cmd))
    app.add_handler(CallbackQueryHandler(uh.directory_category_selected, pattern=r"^dircat_"))
    app.add_handler(CallbackQueryHandler(uh.directory_open_entry, pattern=r"^diropen_"))

    # ---- Withdrawal approve/reject callback ----
    app.add_handler(CallbackQueryHandler(ah.withdrawal_action, pattern=r"^w(approve|reject)_"))

    # ---- Visibility Booster: check every 60 seconds for due reposts ----
    if app.job_queue:
        app.job_queue.run_repeating(run_due_boost_jobs, interval=60, first=30)

    return app


def main():
    if not config.BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN environment variable set nahi hai! .env file check karo.")

    app = build_app()
    logger.info("Bot start ho raha hai...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
