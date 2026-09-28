"""
main.py
Bot ka entry point. 
Start Command me sirf: python main.py likhein.
"""

import logging
import os
import threading
import warnings
from http.server import BaseHTTPRequestHandler, HTTPServer

from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    PollAnswerHandler, ConversationHandler, TypeHandler, filters
)
from telegram.warnings import PTBUserWarning

warnings.filterwarnings("ignore", category=PTBUserWarning)

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


# =========================================================
# 🌐 RENDER PORT BINDING FIX (To Prevent Conflict Errors)
# =========================================================
class DummyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b"Bot is alive and running smoothly!")
        
    def log_message(self, format, *args):
        pass 

def run_dummy_server():
    port = int(os.environ.get("PORT", 10000))
    try:
        server = HTTPServer(("0.0.0.0", port), DummyHandler)
        logger.info(f"🌐 Fake Web Server started on port {port} for Render.")
        server.serve_forever()
    except Exception as e:
        logger.error(f"❌ Web server start nahi hua: {e}")
# =========================================================


async def global_tracker(update: Update, context):
    chat = update.effective_chat
    if chat and chat.type in ("group", "supergroup", "channel"):
        db.upsert_group(chat.id, chat.title)

    user = update.effective_user
    if user and not user.is_bot:
        db.upsert_user(user.id, user.username, user.first_name)
        db.touch_online(user.id)


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
        "amenu_reactions": "😀 Reactions Bot set karne ke liye us group me likho:\n/reactions",
    }
    text = hints.get(query.data, "Command available nahi hai.")
    await query.edit_message_text(text, reply_markup=uh._back_kb())

def build_app():
    db.init_db()
    app = Application.builder().token(config.BOT_TOKEN).build()

    app.add_handler(TypeHandler(Update, global_tracker), group=-1)

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
    
    app.add_handler(CallbackQueryHandler(uh.check_join_callback, pattern=r"^check_join$"))

    # 📩 SUPPORT SYSTEM
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(uh.support_start, pattern=r"^menu_support$"), CommandHandler("support", uh.support_start)],
        states={
            uh.ASK_SUPPORT: [MessageHandler(filters.TEXT & ~filters.COMMAND, uh.support_process)],
        },
        fallbacks=[CommandHandler("cancel", uh.support_cancel)],
        allow_reentry=True
    ))

    # 👨‍💻 ADMIN REPLY
    app.add_handler(MessageHandler(filters.REPLY & filters.TEXT & ~filters.COMMAND, ah.owner_reply_handler))

    # 📄 CLEAN PDF
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(uh.cleanpdf_start, pattern=r"^menu_cleanpdf$"), CommandHandler("cleanpdf", uh.cleanpdf_start)],
        states={
            uh.ASK_PDF: [MessageHandler(filters.ALL & ~filters.COMMAND, uh.cleanpdf_process)],
        },
        fallbacks=[CommandHandler("cancel", uh.cleanpdf_cancel)],
        allow_reentry=True
    ))

    app.add_handler(CallbackQueryHandler(uh.menu_router, pattern=r"^menu_"))
    app.add_handler(CallbackQueryHandler(quiz_engine.handle_ready_callback, pattern=r"^ready_"))
    app.add_handler(PollAnswerHandler(quiz_engine.handle_poll_answer))

    # --------------------------------------------------------
    # ADVANCED ADMIN CONVERSATIONS
    # --------------------------------------------------------
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(ah.admin_add_start, pattern=r"^admin_add_btn$")],
        states={
            ah.ASK_ADMIN_ID_ADD: [MessageHandler(filters.TEXT & ~filters.COMMAND, ah.admin_add_id)],
            ah.ASK_ADMIN_GROUP: [MessageHandler(filters.TEXT & ~filters.COMMAND, ah.admin_add_group)],
            ah.ASK_ADMIN_RIGHTS: [CallbackQueryHandler(ah.admin_add_rights, pattern=r"^arights_")]
        },
        fallbacks=[CommandHandler("cancel", ah.addquestion_cancel)],
        allow_reentry=True
    ))

    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(ah.admin_rem_start, pattern=r"^admin_rem_btn$")],
        states={
            ah.ASK_ADMIN_ID_REMOVE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ah.admin_rem_process)],
        },
        fallbacks=[CommandHandler("cancel", ah.addquestion_cancel)],
        allow_reentry=True
    ))

    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("broadcast", ah.broadcast_start), CallbackQueryHandler(ah.broadcast_start, pattern=r"^amenu_broadcast$")],
        states={
            ah.ASK_BROADCAST_TARGET: [CallbackQueryHandler(ah.broadcast_target, pattern=r"^bcast_")],
            ah.ASK_BROADCAST_MSG: [MessageHandler(filters.ALL & ~filters.COMMAND, ah.broadcast_process)]
        },
        fallbacks=[CommandHandler("cancel", ah.addquestion_cancel)],
        allow_reentry=True
    ))

    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("sendquiz", ah.sendquiz_start), CallbackQueryHandler(ah.sendquiz_start, pattern=r"^amenu_remotequiz$")],
        states={
            ah.ASK_QUIZ_DEST_TYPE: [CallbackQueryHandler(ah.sendquiz_dest_type, pattern=r"^squiz_")],
            ah.ASK_QUIZ_JSON: [
                CommandHandler("done", ah.sendquiz_receive_json_done),
                MessageHandler(filters.TEXT & ~filters.COMMAND, ah.sendquiz_receive_json_text)
            ],
            ah.ASK_QUIZ_GROUP_CHAP: [CallbackQueryHandler(ah.sendquiz_group_chap, pattern=r"^sqsubj_")],
            ah.ASK_QUIZ_GROUP_TIMER: [CallbackQueryHandler(ah.sendquiz_group_timer, pattern=r"^sqchap_")],
            ah.ASK_QUIZ_GROUP_COUNT: [CallbackQueryHandler(ah.sendquiz_group_count, pattern=r"^sqtime_")],
            ah.ASK_QUIZ_GROUP_CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, ah.sendquiz_group_confirm)]
        },
        fallbacks=[CommandHandler("cancel", ah.addquestion_cancel)],
        allow_reentry=True
    ))

    # ✏️ EDIT QUESTION FLOW
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("editquestion", ah.editq_start), CallbackQueryHandler(ah.editq_start, pattern=r"^amenu_editq$")],
        states={
            ah.ASK_EDIT_Q_SEARCH: [MessageHandler(filters.TEXT & ~filters.COMMAND, ah.editq_search)],
            ah.ASK_EDIT_Q_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ah.editq_receive_value)],
        },
        fallbacks=[CommandHandler("cancel", ah.addquestion_cancel)],
        allow_reentry=True
    ))
    
    app.add_handler(CallbackQueryHandler(ah.editq_select_action, pattern=r"^eqsel_"))
    app.add_handler(CallbackQueryHandler(ah.editq_field_action, pattern=r"^eqdo_"))

    # ⚙️ GROUP SETTINGS DM FLOW
    app.add_handler(ConversationHandler(
        entry_points=[
            CommandHandler("groupsettings", ah.groupsettings_start_dm),
            CallbackQueryHandler(ah.groupsettings_start_dm, pattern=r"^amenu_groupsettings$")
        ],
        states={
            ah.ASK_GSET_COINS: [MessageHandler(filters.TEXT & ~filters.COMMAND, ah.groupsettings_coin_receive)],
        },
        fallbacks=[CommandHandler("cancel", ah.addquestion_cancel)],
        allow_reentry=True
    ))
    app.add_handler(CallbackQueryHandler(ah.groupsettings_action, pattern=r"^gset_"))
    app.add_handler(CallbackQueryHandler(ah.groupsettings_coin_prompt, pattern=r"^gsetc_"))

    # 🚀 BOOST SYSTEM DM FLOW
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("boost", ah.boost_start), CallbackQueryHandler(ah.boost_start, pattern=r"^amenu_boost$")],
        states={
            ah.ASK_BOOST_GROUP: [CallbackQueryHandler(ah.boost_group_select, pattern=r"^bgrp_")],
            ah.ASK_BOOST_CONTENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, ah.boost_content)],
            ah.ASK_BOOST_BUTTON: [MessageHandler(filters.TEXT, ah.boost_button)],
            ah.ASK_BOOST_SCHEDULE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ah.boost_schedule)],
        },
        fallbacks=[CommandHandler("cancel", ah.addquestion_cancel)],
        allow_reentry=True
    ))

    app.add_handler(CallbackQueryHandler(ah.pushnote_action, pattern=r"^pushnote_"))
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
        allow_reentry=True
    ))

    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("postad", ah.postad_start), CallbackQueryHandler(ah.postad_start, pattern=r"^amenu_postad$")],
        states={
            ah.ASK_AD_CONTENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, ah.postad_content)],
            ah.ASK_AD_BUTTON: [MessageHandler(filters.TEXT, ah.postad_button)],
        },
        fallbacks=[CommandHandler("cancel", ah.addquestion_cancel)],
        allow_reentry=True
    ))

    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("sendnote", ah.sendnote_start), CallbackQueryHandler(ah.sendnote_start, pattern=r"^amenu_sendnote$")],
        states={
            ah.ASK_NOTE_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ah.sendnote_title)],
            ah.ASK_NOTE_CONTENT: [MessageHandler(filters.TEXT, ah.sendnote_content)],
        },
        fallbacks=[CommandHandler("cancel", ah.addquestion_cancel)],
        allow_reentry=True
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
        allow_reentry=True
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

    app.add_handler(CommandHandler("addadmin", ah.addadmin_cmd))
    app.add_handler(CommandHandler("removeadmin", ah.removeadmin_cmd))
    app.add_handler(CommandHandler("listadmins", ah.listadmins_cmd))
    
    app.add_handler(CommandHandler("boostlist", ah.boostlist_cmd))
    app.add_handler(CommandHandler("stopboost", ah.stopboost_cmd))
    
    app.add_handler(CommandHandler("backup", ah.backup_cmd))
    app.add_handler(CommandHandler("restore", ah.restore_cmd))
    app.add_handler(CommandHandler("stats", ah.stats_cmd))
    app.add_handler(CommandHandler("userinfo", ah.userinfo_cmd))
    app.add_handler(CommandHandler("ban", ah.ban_cmd))
    app.add_handler(CommandHandler("unban", ah.unban_cmd))
    app.add_handler(CommandHandler("withdrawals", ah.withdrawals_cmd))
    app.add_handler(CommandHandler("setcoinrate", ah.setcoinrate_cmd))
    app.add_handler(CommandHandler("setgroupnegative", ah.setgroupnegative_cmd))
    app.add_handler(CommandHandler("setgroupentryfee", ah.setgroupentryfee_cmd))
    
    app.add_handler(CommandHandler("removedirectory", ah.removedirectory_cmd))
    app.add_handler(CallbackQueryHandler(ah.deldir_action, pattern=r"^deldir_"))

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
        
    # Start the dummy web server in the background so Render is happy
    threading.Thread(target=run_dummy_server, daemon=True).start()
    
    app = build_app()
    logger.info("Bot start ho raha hai...")
    
    app.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
        read_timeout=30,
        write_timeout=30,
        connect_timeout=30,
        pool_timeout=30
    )

if __name__ == "__main__":
    main()
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
        try:
            await context.bot.send_message(chat_id, "⚠️ यहाँ पहले से एक क्विज़ चल रहा है या शुरू होने वाला है!")
        except Exception:
            await context.bot.send_message(user_id, "❌ ग्रुप में मैसेज नहीं भेज सका। क्या बॉट को ग्रुप में परमिशन है?")
        return

    try:
        all_q_rows = db.get_questions()
    except Exception as e:
        await context.bot.send_message(user_id, f"❌ Database se questions nikalne me error: {e}")
        return

    filtered_q = []
    for row in all_q_rows:
        # 🛠 HYPER-SAFE DICT CONVERTER (Fix for Python 3.12 sqlite3.Row)
        q = {}
        if isinstance(row, dict):
            q = row
        else:
            try:
                q = {k: row[k] for k in row.keys()}
            except Exception:
                try:
                    q = dict(row)
                except Exception:
                    continue # Skip if totally unreadable
            
        q_subj = str(q.get('subject_id', ''))
        q_chap = str(q.get('chapter_id', ''))
        
        if subject_id and q_subj != str(subject_id): 
            continue
        if chapter_id and q_chap != str(chapter_id): 
            continue
        filtered_q.append(q)

    if not filtered_q:
        try:
            await context.bot.send_message(chat_id, "❌ इस टॉपिक के लिए पर्याप्त सवाल नहीं हैं। (कही Database खाली तो नहीं है?)")
        except Exception:
            await context.bot.send_message(user_id, "❌ इस टॉपिक के लिए Database में कोई सवाल नहीं मिला! कृपया Word File दोबारा अपलोड करें।")
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

    try:
        msg = await context.bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=keyboard)
    except Exception as e:
        await context.bot.send_message(user_id, f"❌ Quiz UI ग्रुप में नहीं जा सका! Error: {e}")
        return

    ready_sessions[chat_id] = {
        "ready_users": set(),
        "msg_id": msg.message_id,
        "chat_title": chat_title,
        "questions": questions_to_ask,
        "timer": timer,
        "status": "waiting",
        "admin_id": user_id
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
        
        try:
            await context.bot.send_message(chat_id, "🔥 *Admin ने क्विज़ स्टार्ट कर दिया है! पहला सवाल आ रहा है...*", parse_mode="Markdown")
        except Exception:
            pass
        
        if chat_id in ready_sessions:
            q_data = ready_sessions.pop(chat_id)
            asyncio.create_task(run_quiz(context, chat_id, q_data["chat_title"], q_data["questions"], q_data["timer"], q_data["admin_id"]))
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
        
        try:
            await context.bot.send_message(chat_id, "🔥 *5 लोग जुड़ चुके हैं! क्विज़ ठीक 1 मिनट में शुरू होगा...*\n\nतैयार रहें!", parse_mode="Markdown")
        except Exception:
            pass
            
        await asyncio.sleep(60)
        
        if chat_id in ready_sessions:
            q_data = ready_sessions.pop(chat_id)
            asyncio.create_task(run_quiz(context, chat_id, q_data["chat_title"], q_data["questions"], q_data["timer"], q_data["admin_id"]))

# ==========================================
# 2. RUN QUIZ & POLL SCORING
# ==========================================
async def run_quiz(context: ContextTypes.DEFAULT_TYPE, chat_id, chat_title, questions, timer, admin_id):
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
                    # 🔥 FIX: Remove ###A, ###B formatting from options
                    opt_str = re.sub(r'^###[A-D]\s*', '', opt_str).strip()
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
                    try:
                        await context.bot.send_message(chat_id, f"⚠️ Q{idx+1} लोड नहीं हो सका। अगले प्रश्न पर जा रहे हैं...")
                    except:
                        pass
                    await asyncio.sleep(2)

        except Exception as giant_e:
            logger.error(f"Giant Try-Except Block Caught Error: {giant_e}")
            await asyncio.sleep(1)

    # Jab saare sawaal khatam ho jayein
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
            if selected == quiz_data["correct_idx"]:
                quiz_data["scores"][user_id]["score"] += 2
                try: db.add_coins(user_id, 2)
                except Exception: pass
            else:
                quiz_data["scores"][user_id]["score"] -= 1
                try: db.deduct_coins(user_id, 1)
                except Exception: pass
            break

async def generate_and_send_pdf(context: ContextTypes.DEFAULT_TYPE, chat_id, chat_title, scores_dict):
    if not scores_dict:
        try: await context.bot.send_message(chat_id, "📝 क्विज़ समाप्त! किसी ने भी हिस्सा नहीं लिया।")
        except Exception: pass
        return

    sorted_users = sorted(scores_dict.values(), key=lambda x: x["score"], reverse=True)
    text = "🏆 *FINAL LEADERBOARD*\n__________________________\n"
    for i, u in enumerate(sorted_users[:5]):
        medals = ["🥇", "🥈", "🥉", "🏅", "🏅"]
        medal = medals[i] if i < 5 else '🔹'
        text += f"{medal} {u['name']} - {u['score']} Points\n"
    try: await context.bot.send_message(chat_id, text, parse_mode="Markdown")
    except Exception: pass

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
        await context.bot.send_document(chat_id, document=open(file_path, "rb"), caption="📄 *विस्तृत लीडरबोर्ड (Detailed Result)* 👆\nडाउनलोड करके अपनी रैंक चेक करें!", parse_mode="Markdown")
        if os.path.exists(file_path): os.remove(file_path)
    except Exception as e:
        try: await context.bot.send_message(chat_id, "⚠️ Leaderboard PDF generate karne me error aayi.")
        except Exception: pass

async def start_duel(*args, **kwargs):
    pass
