"""
main.py
Bot ka entry point. Render pe isko "worker" ya "background worker"
service ke roop me run karo (python main.py).
"""

import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

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


# =========================================================================
# DUMMY SERVER (Port Clash Fix)
# =========================================================================
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b"Bot is alive and running!")
        
    def log_message(self, format, *args):
        pass 

def keep_alive_server():
    port = int(os.environ.get("PORT", 10000))
    try:
        server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
        server.serve_forever()
    except OSError:
        # Agar Gunicorn pehle se port use kar raha hai to error nahi aayega
        pass
# =========================================================================


async def track_group_membership(update: Update, context):
    chat = update.effective_chat
    # 'channel' add kar diya gaya hai taaki channels bhi auto-save ho jayein
    if chat.type in ("group", "supergroup", "channel"):
        db.upsert_group(chat.id, chat.title)

async def run_due_boost_jobs(context):
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    from utils.reactions import auto_react
    due = db.get_due_boost_jobs()
    for job in due:
        reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton(job["button_text"], url=job["button_url"])]]) if job["button_text"] else None
        try:
            sent = await context.bot.send_message(job["chat_id"], job["content"], reply_markup=reply_markup)
            db.mark_boost_job_run(job["job_id"], job["repost_every_minutes"])
            await auto_react(context, job["chat_id"], sent.message_id)
            if job["max_reposts"] and job["repost_count_done"] + 1 >= job["max_reposts"]:
                db.deactivate_boost_job(job["job_id"])
        except Exception:
            db.deactivate_boost_job(job["job_id"])

async def track_user_activity(update: Update, context):
    if update.effective_user:
        user = update.effective_user
        db.upsert_user(user.id, user.username, user.first_name)
        db.touch_online(user.id)

async def admin_menu_router(update: Update, context):
    query = update.callback_query
    await query.answer()
    hints = {
        "amenu_groupsettings": "⚙️ Group settings dekhne ke liye bot ko apne group me add karein aur wahan likho:\n/groupsettings",
        "amenu_reactions": "😀 Reactions Bot set karne ke liye us group me likho:\n/reactions",
        "amenu_boost": "🚀 Post ko boost (pin + scheduled repost) karne ke liye us group me likho:\n/boost\n\nActive boosts dekhne ke liye:\n/boostlist",
    }
    text = hints.get(query.data, "Command available nahi hai.")
    await query.edit_message_text(text, reply_markup=uh._back_kb())

def build_app():
    db.init_db()
    app = Application.builder().token(config.BOT_TOKEN).build()

    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, track_user_activity), group=-1)
    app.add_handler(ChatMemberHandler(track_group_membership, ChatMemberHandler.MY_CHAT_MEMBER), group=-1)

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

    app.add_handler(CallbackQueryHandler(uh.menu_router, pattern=r"^menu_"))

    # Ready Button (User System)
    app.add_handler(CallbackQueryHandler(quiz_engine.handle_ready_callback, pattern=r"^ready_"))
    app.add_handler(PollAnswerHandler(quiz_engine.handle_poll_answer))

    # ==============================================================
    # NEW ADVANCED ADMIN CONVERSATIONS
    # ==============================================================
    
    # 1. Advanced Admin Add
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(ah.admin_add_start, pattern=r"^admin_add_btn$")],
        states={
            ah.ASK_ADMIN_ID_ADD: [MessageHandler(filters.TEXT & ~filters.COMMAND, ah.admin_add_id)],
            ah.ASK_ADMIN_GROUP: [MessageHandler(filters.TEXT & ~filters.COMMAND, ah.admin_add_group)],
            ah.ASK_ADMIN_RIGHTS: [CallbackQueryHandler(ah.admin_add_rights, pattern=r"^arights_")]
        },
        fallbacks=[CommandHandler("cancel", ah.addquestion_cancel)],
    ))

    # Admin Remove
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(ah.admin_rem_start, pattern=r"^admin_rem_btn$")],
        states={
            ah.ASK_ADMIN_ID_REMOVE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ah.admin_rem_process)],
        },
        fallbacks=[CommandHandler("cancel", ah.addquestion_cancel)],
    ))

    # 2. Super Broadcast (Text, HTML, Image sab chalega)
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("broadcast", ah.broadcast_start), CallbackQueryHandler(ah.broadcast_start, pattern=r"^amenu_broadcast$")],
        states={
            ah.ASK_BROADCAST_TARGET: [CallbackQueryHandler(ah.broadcast_target, pattern=r"^bcast_")],
            ah.ASK_BROADCAST_MSG: [MessageHandler(filters.ALL & ~filters.COMMAND, ah.broadcast_process)]
        },
        fallbacks=[CommandHandler("cancel", ah.addquestion_cancel)],
    ))

    # 3. Send Quiz (Channel & Group)
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("sendquiz", ah.sendquiz_start), CallbackQueryHandler(ah.sendquiz_start, pattern=r"^amenu_remotequiz$")],
        states={
            ah.ASK_QUIZ_DEST_TYPE: [CallbackQueryHandler(ah.sendquiz_dest_type, pattern=r"^squiz_")],
            ah.ASK_QUIZ_JSON: [MessageHandler(filters.TEXT & ~filters.COMMAND, ah.sendquiz_receive_json)],
            ah.ASK_QUIZ_GROUP_CHAP: [CallbackQueryHandler(ah.sendquiz_group_chap, pattern=r"^sqsubj_")],
            ah.ASK_QUIZ_GROUP_TIMER: [CallbackQueryHandler(ah.sendquiz_group_timer, pattern=r"^sqchap_")],
            ah.ASK_QUIZ_GROUP_COUNT: [CallbackQueryHandler(ah.sendquiz_group_count, pattern=r"^sqtime_")],
            ah.ASK_QUIZ_GROUP_CONFIRM: [CallbackQueryHandler(ah.sendquiz_group_confirm, pattern=r"^sqlen_")]
        },
        fallbacks=[CommandHandler("cancel", ah.addquestion_cancel)],
    ))
    # ==============================================================

    # ---- Direct Button Mapping for Admin Panel ----
    app.add_handler(CallbackQueryHandler(ah.uploadword_prompt, pattern=r"^amenu_uploadword$"))
    app.add_handler(CallbackQueryHandler(ah.samplefile_cmd, pattern=r"^amenu_sample$"))
    app.add_handler(CallbackQueryHandler(ah.exportquestions_cmd, pattern=r"^amenu_export$"))
    app.add_handler(CallbackQueryHandler(ah.backup_cmd, pattern=r"^amenu_backup$"))
    app.add_handler(CallbackQueryHandler(ah.stats_cmd, pattern=r"^amenu_stats$"))
    app.add_handler(CallbackQueryHandler(ah.withdrawals_cmd, pattern=r"^amenu_withdrawals$"))
    app.add_handler(CallbackQueryHandler(ah.manage_admins_menu, pattern=r"^amenu_admins$"))
    app.add_handler(CallbackQueryHandler(ah.listgroups_cmd, pattern=r"^amenu_listgroups$"))

    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("addquestion", ah.addquestion_start), CallbackQueryHandler(ah.addquestion_start, pattern=r"^amenu_addq$")],
        states={
            ah.ASK_SUBJECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, ah.addquestion_subject)],
            ah.ASK_CHAPTER: [MessageHandler(filters.TEXT & ~filters.COMMAND, ah.addquestion_chapter)],
            ah.ASK_DOCX_FILE: [MessageHandler(filters.Document.FileExtension("docx"), ah.addquestion_file)],
        },
        fallbacks=[CommandHandler("cancel", ah.addquestion_cancel)],
    ))

    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("postad", ah.postad_start), CallbackQueryHandler(ah.postad_start, pattern=r"^amenu_postad$")],
        states={
            ah.ASK_AD_CONTENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, ah.postad_content)],
            ah.ASK_AD_BUTTON: [MessageHandler(filters.TEXT, ah.postad_button)],
        },
        fallbacks=[CommandHandler("cancel", ah.addquestion_cancel)],
    ))

    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("sendnote", ah.sendnote_start), CallbackQueryHandler(ah.sendnote_start, pattern=r"^amenu_sendnote$")],
        states={
            ah.ASK_NOTE_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ah.sendnote_title)],
            ah.ASK_NOTE_CONTENT: [MessageHandler(filters.TEXT, ah.sendnote_content)],
        },
        fallbacks=[CommandHandler("cancel", ah.addquestion_cancel)],
    ))

    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("adddirectory", ah.adddirectory_start), CallbackQueryHandler(ah.adddirectory_start, pattern=r"^amenu_directory$")],
        states={
            ah.ASK_DIR_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ah.adddirectory_title)],
            ah.ASK_DIR_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, ah.adddirectory_desc)],
            ah.ASK_DIR_CATEGORY: [MessageHandler(filters.TEXT & ~filters.COMMAND, ah.adddirectory_category)],
            ah.ASK_DIR_LINK: [MessageHandler(filters.TEXT & ~filters.COMMAND, ah.adddirectory_link)],
        },
        fallbacks=[CommandHandler("cancel", ah.addquestion_cancel)],
    ))

    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("boost", ah.boost_start)],
        states={
            ah.ASK_BOOST_CONTENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, ah.boost_content)],
            ah.ASK_BOOST_BUTTON: [MessageHandler(filters.TEXT, ah.boost_button)],
            ah.ASK_BOOST_SCHEDULE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ah.boost_schedule)],
        },
        fallbacks=[CommandHandler("cancel", ah.addquestion_cancel)],
    ))

    app.add_handler(CallbackQueryHandler(admin_menu_router, pattern=r"^amenu_"))

    app.add_handler(CallbackQueryHandler(uh.subject_selected, pattern=r"^qsubj_"))
    app.add_handler(CallbackQueryHandler(uh.chapter_selected, pattern=r"^qchap_"))
    app.add_handler(CallbackQueryHandler(uh.all_chapters_selected, pattern=r"^qallchap_"))
    app.add_handler(CallbackQueryHandler(uh.length_selected, pattern=r"^qlen_"))
    app.add_handler(CallbackQueryHandler(uh.subject_length_selected, pattern=r"^qslen_"))
    app.add_handler(CallbackQueryHandler(uh.solo_subject_selected, pattern=r"^solosubj_"))
    app.add_handler(CallbackQueryHandler(uh.solo_length_selected, pattern=r"^sololen_"))
    app.add_handler(CallbackQueryHandler(uh.duel_subject_selected, pattern=r"^duelsubj_"))
    app.add_handler(CallbackQueryHandler(uh.duel_length_selected, pattern=r"^duellen_"))
    app.add_handler(CallbackQueryHandler(uh.duel_accept_callback, pattern=r"^duelaccept_"))
    app.add_handler(CallbackQueryHandler(uh.duel_decline_callback, pattern=r"^dueldecline_"))

    app.add_handler(CommandHandler("pushnote", ah.pushnote_cmd))
    app.add_handler(CommandHandler("notelist", ah.notelist_cmd))
    app.add_handler(CallbackQueryHandler(ah.notesend_callback, pattern=r"^notesend_"))
    app.add_handler(CommandHandler("uploadword", ah.uploadword_prompt))
    app.add_handler(CommandHandler("samplefile", ah.samplefile_cmd))
    app.add_handler(CommandHandler("exportquestions", ah.exportquestions_cmd))
    app.add_handler(CommandHandler("deletequestion", ah.deletequestion_cmd))
    app.add_handler(MessageHandler(filters.Document.FileExtension("docx"), ah.handle_docx_upload))
    app.add_handler(MessageHandler(filters.Document.FileExtension("db"), ah.handle_db_restore_upload))
    app.add_handler(MessageHandler(filters.Document.PDF, ah.handle_pdf_clean_upload))

    app.add_handler(CommandHandler("addadmin", ah.addadmin_cmd))
    app.add_handler(CommandHandler("removeadmin", ah.removeadmin_cmd))
    app.add_handler(CommandHandler("listadmins", ah.listadmins_cmd))
    app.add_handler(CommandHandler("backup", ah.backup_cmd))
    app.add_handler(CommandHandler("restore", ah.restore_cmd))
    app.add_handler(CommandHandler("stats", ah.stats_cmd))
    app.add_handler(CommandHandler("userinfo", ah.userinfo_cmd))
    app.add_handler(CommandHandler("ban", ah.ban_cmd))
    app.add_handler(CommandHandler("unban", ah.unban_cmd))
    app.add_handler(CommandHandler("withdrawals", ah.withdrawals_cmd))
    app.add_handler(CommandHandler("setcoinrate", ah.setcoinrate_cmd))
    app.add_handler(CommandHandler("groupsettings", ah.groupsettings_cmd))
    app.add_handler(CommandHandler("setgroupcoin", ah.setgroupcoin_cmd))
    app.add_handler(CommandHandler("setgroupnegative", ah.setgroupnegative_cmd))
    app.add_handler(CommandHandler("setgroupentryfee", ah.setgroupentryfee_cmd))
    app.add_handler(CommandHandler("addgroup", ah.addgroup_cmd))
    app.add_handler(CommandHandler("listgroups", ah.listgroups_cmd))
    app.add_handler(CommandHandler("reactions", ah.reactions_cmd))
    app.add_handler(CommandHandler("reactionson", ah.reactionson_cmd))
    app.add_handler(CommandHandler("reactionsoff", ah.reactionsoff_cmd))
    app.add_handler(CommandHandler("setreactionemojis", ah.setreactionemojis_cmd))
    app.add_handler(CommandHandler("boostlist", ah.boostlist_cmd))
    app.add_handler(CommandHandler("stopboost", ah.stopboost_cmd))
    app.add_handler(CommandHandler("besttime", ah.besttime_cmd))
    app.add_handler(CommandHandler("removedirectory", ah.removedirectory_cmd))
    app.add_handler(CommandHandler("discover", uh.discover_cmd))
    app.add_handler(CallbackQueryHandler(uh.directory_category_selected, pattern=r"^dircat_"))
    app.add_handler(CallbackQueryHandler(uh.directory_open_entry, pattern=r"^diropen_"))
    app.add_handler(CallbackQueryHandler(ah.withdrawal_action, pattern=r"^w(approve|reject)_"))

    if app.job_queue:
        app.job_queue.run_repeating(run_due_boost_jobs, interval=60, first=30)

    return app

def main():
    if not config.BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN environment variable set nahi hai! .env file check karo.")
        
    threading.Thread(target=keep_alive_server, daemon=True).start()
    
    app = build_app()
    logger.info("Bot start ho raha hai...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
