"""
main.py
Bot ka entry point. Render pe isko "worker" ya "background worker"
service ke roop me run karo (python main.py).
"""

import logging
import asyncio
import threading  # <-- Naya import dummy server ke liye
import os         # <-- Naya import port detect karne ke liye
from http.server import BaseHTTPRequestHandler, HTTPServer # <-- Dummy server banane ke liye

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

# ==========================================
# 🌐 DUMMY WEB SERVER (RENDER KO SATISFY KARNE KE LIYE)
# ==========================================
class DummyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b"Telegram Bot is running smoothly!")

def run_dummy_server():
    # Render khud ek PORT environment variable deta hai
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), DummyHandler)
    logger.info(f"Dummy Web Server started on port {port}")
    server.serve_forever()
# ==========================================

async def track_group_membership(update: Update, context):
    """Jab bot kisi group me add ho ya group ka title change ho"""
    chat = update.effective_chat
    if chat.type in ("group", "supergroup"):
        db.upsert_group(chat.id, chat.title)

async def track_user_activity(update: Update, context):
    """Har message pe user ko 'online'/'last seen' mark karo"""
    if update.effective_user:
        user = update.effective_user
        db.upsert_user(user.id, user.username, user.first_name)
        db.touch_online(user.id)

def build_app():
    db.init_db()

    app = Application.builder().token(config.BOT_TOKEN).build()

    # ---- Activity tracking (runs first, non-blocking group) ----
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, track_user_activity), group=-1)
    app.add_handler(ChatMemberHandler(track_group_membership, ChatMemberHandler.MY_CHAT_MEMBER), group=-1)

    # ---- User commands ----
    app.add_handler(CommandHandler("start", uh.start_cmd))
    app.add_handler(CommandHandler("help", uh.help_cmd))
    app.add_handler(CommandHandler("quiz", uh.quiz_cmd))
    app.add_handler(CommandHandler("stopquiz", uh.stopquiz_cmd))
    app.add_handler(CommandHandler("leaderboard", uh.leaderboard_cmd))
    app.add_handler(CommandHandler("globaltop", uh.globaltop_cmd))
    app.add_handler(CommandHandler("myscore", uh.myscore_cmd))
    app.add_handler(CommandHandler("history", uh.history_cmd))
    app.add_handler(CommandHandler("wallet", uh.wallet_cmd))
    app.add_handler(CommandHandler("referral", uh.referral_cmd))
    app.add_handler(CommandHandler("withdraw", uh.withdraw_cmd))
    app.add_handler(CommandHandler("subjects", uh.subjects_cmd))

    # ---- Quiz selection callbacks ----
    app.add_handler(CallbackQueryHandler(uh.subject_selected, pattern=r"^qsubj_"))
    app.add_handler(CallbackQueryHandler(uh.chapter_selected, pattern=r"^qchap_"))
    app.add_handler(CallbackQueryHandler(uh.all_chapters_selected, pattern=r"^qallchap_"))
    app.add_handler(CallbackQueryHandler(uh.length_selected, pattern=r"^qlen_"))
    app.add_handler(CallbackQueryHandler(uh.subject_length_selected, pattern=r"^qslen_"))

    # ---- Poll answers (core quiz scoring) ----
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

    # ---- Admin: word file upload / export / sample ----
    app.add_handler(CommandHandler("uploadword", ah.uploadword_prompt))
    app.add_handler(CommandHandler("samplefile", ah.samplefile_cmd))
    app.add_handler(CommandHandler("exportquestions", ah.exportquestions_cmd))
    app.add_handler(CommandHandler("deletequestion", ah.deletequestion_cmd))

    # Document handler: routes to either question-import or db-restore based on filename/reply
    app.add_handler(MessageHandler(filters.Document.FileExtension("docx"), ah.handle_docx_upload))
    app.add_handler(MessageHandler(filters.Document.FileExtension("db"), ah.handle_db_restore_upload))

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

    # ---- Withdrawal approve/reject callback ----
    app.add_handler(CallbackQueryHandler(ah.withdrawal_action, pattern=r"^w(approve|reject)_"))

    return app

def main():
    if not config.BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN environment variable set nahi hai! .env file check karo.")

    # 1. Background mein dummy server chalu karo
    threading.Thread(target=run_dummy_server, daemon=True).start()

    app = build_app()
    logger.info("Bot start ho raha hai...")
    
    # 2. Python 3.14 Event Loop ka fix
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    # 3. Bot ki polling chalu karo
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
