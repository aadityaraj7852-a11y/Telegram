"""
admin_handlers.py
Admin/Owner ke liye commands and UI flow.
"""

import os
import time
import re

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

import database as db
import config
from utils.permissions import require_admin, require_owner, is_admin, is_owner
from utils.docx_parser import parse_docx, validate_parsed
from utils.exporters import make_sample_template, export_questions_to_docx
from utils.pdf_cleaner import clean_pdf
from utils.html_notes import sanitize_for_telegram, chunk_message

# Conversation states
ASK_SUBJECT, ASK_CHAPTER, ASK_QUESTION, ASK_OPTIONS, ASK_ANSWER, ASK_EXPLANATION = range(6)
ASK_AD_CONTENT, ASK_AD_BUTTON = range(100, 102)
ASK_NOTE_TITLE, ASK_NOTE_CONTENT = range(200, 202)
ASK_GROUP_ID, ASK_GROUP_COINRATE, ASK_GROUP_NEGATIVE, ASK_GROUP_ENTRYFEE = range(300, 304)
ASK_BOOST_CONTENT, ASK_BOOST_BUTTON, ASK_BOOST_SCHEDULE = range(400, 403)
ASK_DIR_TITLE, ASK_DIR_DESC, ASK_DIR_CATEGORY, ASK_DIR_LINK = range(500, 504)
ASK_ADMIN_ID_ADD, ASK_ADMIN_ID_REMOVE, ASK_BROADCAST_MSG = range(700, 703)


# --- Helper for Buttons & Commands ---
async def check_admin(update: Update):
    if update.callback_query:
        if not is_admin(update.effective_user.id):
            await update.callback_query.answer("⛔ Sirf Admin ke liye.", show_alert=True)
            return False
        return True
    return await require_admin(update)

async def check_owner(update: Update):
    if update.callback_query:
        if not is_owner(update.effective_user.id):
            await update.callback_query.answer("⛔ Sirf Owner ke liye.", show_alert=True)
            return False
        return True
    return await require_owner(update)


# ---------------- MANUAL ADD QUESTION ----------------
async def addquestion_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query: await update.callback_query.answer()
    if not await check_admin(update): return ConversationHandler.END
    await update.effective_message.reply_text("📚 Subject ka naam likho (jaise: Physics):\n(Cancel ke liye /cancel)")
    return ASK_SUBJECT

async def addquestion_subject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_q_subject"] = update.message.text.strip()
    await update.effective_message.reply_text("📑 Chapter ka naam likho (jaise: Motion):")
    return ASK_CHAPTER

async def addquestion_chapter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_q_chapter"] = update.message.text.strip()
    await update.effective_message.reply_text("❓ Ab question likho:")
    return ASK_QUESTION

async def addquestion_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_q_text"] = update.message.text.strip()
    await update.effective_message.reply_text("🔤 Options likho, ek line me ek option.\nJab sab ho jaye to /done likhna.")
    context.user_data["new_q_options"] = []
    return ASK_OPTIONS

async def addquestion_options(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "/done":
        opts = context.user_data.get("new_q_options", [])
        if len(opts) < 2:
            await update.effective_message.reply_text("Kam se kam 2 options chahiye. Aur options bhejo:")
            return ASK_OPTIONS
        letters = ", ".join(f"{chr(65+i)}) {o}" for i, o in enumerate(opts))
        await update.effective_message.reply_text(f"✅ Options: {letters}\n\nAb sahi answer ka letter likho (A/B/C/D):")
        return ASK_ANSWER
    context.user_data["new_q_options"].append(text)
    await update.effective_message.reply_text(f"✅ Add hua: {text}\nAur option bhejo ya /done likho.")
    return ASK_OPTIONS

async def addquestion_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    letter = update.message.text.strip().upper()
    opts = context.user_data.get("new_q_options", [])
    if letter not in [chr(65+i) for i in range(len(opts))]:
        await update.effective_message.reply_text("⚠️ Sahi letter likho:")
        return ASK_ANSWER
    context.user_data["new_q_correct"] = ord(letter) - ord('A')
    await update.effective_message.reply_text("💡 Explanation likho (optional, skip ke liye /skip likho):")
    return ASK_EXPLANATION

async def addquestion_explanation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    explanation = "" if text == "/skip" else text
    chapter_id = db.find_or_create_chapter(context.user_data["new_q_subject"], context.user_data["new_q_chapter"])
    qid = db.add_question(chapter_id, context.user_data["new_q_text"], context.user_data["new_q_options"], 
                          context.user_data["new_q_correct"], explanation, update.effective_user.id)
    await update.effective_message.reply_text(f"✅ Question add ho gaya! (ID #{qid})\nMenu ke liye /menu dabayein.")
    context.user_data.clear()
    return ConversationHandler.END

async def addquestion_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.effective_message.reply_text("❌ Cancel ho gaya. Menu ke liye /menu dabayein.")
    return ConversationHandler.END


# ---------------- WORD FILE UPLOAD ----------------
async def uploadword_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query: await update.callback_query.answer()
    if not await check_admin(update): return
    await update.effective_message.reply_text("📎 Word (.docx) file bhejo jisme questions likhe ho.\nFormat nahi pata? /samplefile se template check karo.")

async def handle_docx_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    doc = update.message.document
    if not doc.file_name.lower().endswith(".docx"): return
    await update.message.reply_text("⏳ File padh raha hoon...")
    file = await context.bot.get_file(doc.file_id)
    local_path = f"/tmp/{doc.file_unique_id}.docx"
    await file.download_to_drive(local_path)
    try:
        parsed = parse_docx(local_path)
        valid, errors = validate_parsed(parsed)
    except Exception as e:
        await update.message.reply_text(f"❌ File padhne me error: {e}")
        return
    finally:
        if os.path.exists(local_path): os.remove(local_path)
    if not valid:
        await update.message.reply_text("❌ Koi question add nahi hua.")
        return
    added = 0
    for q in valid:
        chapter_id = db.find_or_create_chapter(q["subject"], q["chapter"])
        db.add_question(chapter_id, q["question"], q["options"], q["correct_index"], q["explanation"], update.effective_user.id)
        added += 1
    await update.message.reply_text(f"✅ {added} questions successfully add ho gaye!")

async def samplefile_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query: await update.callback_query.answer()
    if not await check_admin(update): return
    path = make_sample_template()
    await update.effective_message.reply_document(document=open(path, "rb"), caption="📄 Ye raha sample format. Isi tarah apni file banao.")

async def exportquestions_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query: await update.callback_query.answer()
    if not await check_admin(update): return
    questions = db.get_questions()
    if not questions:
        await update.effective_message.reply_text("Question bank khali hai.")
        return
    path = export_questions_to_docx(questions)
    await update.effective_message.reply_document(document=open(path, "rb"), caption=f"📦 Total {len(questions)} questions export kiye.")

async def deletequestion_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_admin(update): return
    if not context.args or not context.args[0].isdigit():
        await update.effective_message.reply_text("Usage: /deletequestion <id>")
        return
    db.delete_question(int(context.args[0]))
    await update.effective_message.reply_text("✅ Question delete ho gaya.")


# ---------------- NEW ADMIN MANAGEMENT (UI BASED) ----------------
async def manage_admins_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Button click se sab admins ki list dikhata hai aur add/remove ke buttons deta hai"""
    if update.callback_query: await update.callback_query.answer()
    if not await check_admin(update): return

    admins = db.list_admins()
    text = "👮 *Admins List:*\n\n" + ("\n".join(f"• ID: `{a['user_id']}`" for a in admins) if admins else "Koi extra admin nahi hai.")
    
    keyboard = []
    if is_owner(update.effective_user.id):
        keyboard.append([InlineKeyboardButton("➕ Add Admin", callback_data="admin_add_btn"),
                         InlineKeyboardButton("❌ Remove Admin", callback_data="admin_rem_btn")])
    keyboard.append([InlineKeyboardButton("⬅️ Back", callback_data="menu_admin")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode="Markdown")
    else:
        await update.effective_message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")

async def admin_add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query: await update.callback_query.answer()
    if not await check_owner(update): return ConversationHandler.END
    await update.effective_message.reply_text(
        "➕ Jis user ko admin banana hai, uska Telegram ID bhejo:\n\n"
        "(ID pata karne ke liye us user se kaho bot me /start dabaye ya @userinfobot check kare)\n\n"
        "(Cancel karne ke liye /cancel likho)"
    )
    return ASK_ADMIN_ID_ADD

async def admin_add_process(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if not text.isdigit():
        await update.message.reply_text("❌ ID sirf numbers me honi chahiye. Dobara bhejo ya /cancel likho:")
        return ASK_ADMIN_ID_ADD
    uid = int(text)
    db.add_admin(uid, update.effective_user.id)
    await update.message.reply_text(f"✅ User {uid} ab admin ban gaya hai!\n\nMenu me wapas jane ke liye /menu dabayein.")
    return ConversationHandler.END

async def admin_rem_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query: await update.callback_query.answer()
    if not await check_owner(update): return ConversationHandler.END
    await update.effective_message.reply_text("❌ Jisko admin se hatana hai, uska Telegram ID bhejo:\n\n(Cancel karne ke liye /cancel likho)")
    return ASK_ADMIN_ID_REMOVE

async def admin_rem_process(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if not text.isdigit():
        await update.message.reply_text("❌ ID sirf numbers me honi chahiye. Dobara bhejo ya /cancel likho:")
        return ASK_ADMIN_ID_REMOVE
    uid = int(text)
    db.remove_admin(uid)
    await update.message.reply_text(f"✅ User {uid} ko admin se hata diya gaya hai.\n\nMenu me wapas jane ke liye /menu dabayein.")
    return ConversationHandler.END

# Old text commands for backup compatibility
async def addadmin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_owner(update): return
    if not context.args or not context.args[0].isdigit():
        await update.effective_message.reply_text("Usage: /addadmin <user_id>")
        return
    db.add_admin(int(context.args[0]), update.effective_user.id)
    await update.effective_message.reply_text(f"✅ User {context.args[0]} ab admin hai.")

async def removeadmin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_owner(update): return
    if not context.args or not context.args[0].isdigit():
        await update.effective_message.reply_text("Usage: /removeadmin <user_id>")
        return
    db.remove_admin(int(context.args[0]))
    await update.effective_message.reply_text(f"✅ User {context.args[0]} ab admin nahi hai.")

async def listadmins_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await manage_admins_menu(update, context)


# ---------------- BROADCAST (UI BASED) ----------------
async def broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query: await update.callback_query.answer()
    if not await check_admin(update): return ConversationHandler.END
    await update.effective_message.reply_text("📢 Sab users ko jo message bhejna hai, wo yahan type karo:\n\n(Cancel karne ke liye /cancel likho)")
    return ASK_BROADCAST_MSG

async def broadcast_process(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    users = db.get_all_users()
    sent, failed = 0, 0
    status_msg = await update.message.reply_text(f"📢 Bhej raha hoon... 0/{len(users)}")
    for i, u in enumerate(users):
        if u["is_banned"]: continue
        try:
            await context.bot.send_message(u["user_id"], f"📢 *Announcement*\n\n{text}", parse_mode="Markdown")
            sent += 1
        except Exception:
            failed += 1
        if i % 25 == 0:
            try: await status_msg.edit_text(f"📢 Bhej raha hoon... {i}/{len(users)}")
            except Exception: pass
    await status_msg.edit_text(f"✅ Broadcast complete!\nSent: {sent} | Failed: {failed}")
    return ConversationHandler.END


# ---------------- ADS ----------------
async def postad_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query: await update.callback_query.answer()
    if not await check_admin(update): return ConversationHandler.END
    await update.effective_message.reply_text("📝 Ad ka text/content likho:\n(Cancel ke liye /cancel)")
    return ASK_AD_CONTENT

async def postad_content(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["ad_content"] = update.message.text
    await update.effective_message.reply_text("🔘 Button chahiye? 'Button Text | https://link.com' format me likho.\nNahi chahiye to /skip likho.")
    return ASK_AD_BUTTON

async def postad_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    button_text, button_url = None, None
    if text != "/skip" and "|" in text:
        button_text, button_url = [x.strip() for x in text.split("|", 1)]
    content = context.user_data.get("ad_content", "")
    ad_id = db.create_ad(content, button_text, button_url, update.effective_user.id)
    reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton(button_text, url=button_url)]]) if button_text else None
    groups = db.get_active_groups()
    sent = 0
    for g in groups:
        try:
            msg = await context.bot.send_message(g["chat_id"], content, reply_markup=reply_markup)
            await auto_react_to_bot_message(context, g["chat_id"], msg.message_id)
            sent += 1
        except Exception:
            db.deactivate_group(g["chat_id"])
    db.increment_ad_sent(ad_id, sent)
    await update.effective_message.reply_text(f"✅ Ad {sent} groups/channels me bhej diya gaya.")
    context.user_data.clear()
    return ConversationHandler.END


# ---------------- BACKUP / RESTORE ----------------
async def backup_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query: await update.callback_query.answer()
    if not await check_admin(update): return
    from database import DB_PATH
    if not os.path.exists(DB_PATH):
        await update.effective_message.reply_text("Database file nahi mili.")
        return
    await update.effective_message.reply_document(document=open(DB_PATH, "rb"), filename=f"quizbot_backup_{int(time.time())}.db", caption="💾 Ye raha database backup.")

async def restore_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_owner(update): return
    await update.effective_message.reply_text("⚠️ Restore karne ke liye backup (.db) file is message ko *reply* karke bhejo.", parse_mode="Markdown")

async def handle_db_restore_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    if not update.message.reply_to_message: return
    if "restore" not in (update.message.reply_to_message.text or "").lower(): return
    doc = update.message.document
    if not doc.file_name.endswith(".db"):
        await update.message.reply_text("❌ Sirf .db backup file valid hai.")
        return
    from database import DB_PATH
    file = await context.bot.get_file(doc.file_id)
    await file.download_to_drive(DB_PATH)
    await update.message.reply_text("✅ Database restore ho gaya! Bot ko restart karna better rahega.")


# ---------------- STATS / USER INFO ----------------
async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query: await update.callback_query.answer()
    if not await check_admin(update): return
    users = db.get_all_users()
    text = (f"📊 *Bot Stats*\n\n👥 Total Users: {len(users)}\n"
            f"🪙 Coins: {sum(u['coins'] for u in users)}\n"
            f"❓ Questions: {db.count_questions()}\n"
            f"👨‍👩‍👧 Active Groups: {len(db.get_active_groups())}\n")
    await update.effective_message.reply_text(text, parse_mode="Markdown")

async def userinfo_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_admin(update): return
    if not context.args or not context.args[0].isdigit():
        await update.effective_message.reply_text("Usage: /userinfo <user_id>")
        return
    u = db.get_user(int(context.args[0]))
    if not u:
        await update.effective_message.reply_text("User nahi mila.")
        return
    text = f"👤 *User Info*\n\nID: {u['user_id']}\nName: {u['first_name']}\nCoins: {u['coins']}\nQuizzes: {u['total_quizzes']}"
    await update.effective_message.reply_text(text, parse_mode="Markdown")

async def ban_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_admin(update): return
    if not context.args or not context.args[0].isdigit(): return
    db.set_ban(int(context.args[0]), True)
    await update.effective_message.reply_text("✅ User ban ho gaya.")

async def unban_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_admin(update): return
    if not context.args or not context.args[0].isdigit(): return
    db.set_ban(int(context.args[0]), False)
    await update.effective_message.reply_text("✅ User unban ho gaya.")


# ---------------- WITHDRAWALS ----------------
async def withdrawals_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query: await update.callback_query.answer()
    if not await check_admin(update): return
    pending = db.get_pending_withdrawals()
    if not pending:
        await update.effective_message.reply_text("Koi pending withdrawal nahi hai.")
        return
    for w in pending:
        text = f"💰 Withdrawal #{w['id']}\nUser: {w['first_name']} | ID: {w['user_id']}\nCoins: {w['coins']}"
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("✅ Approve", callback_data=f"wapprove_{w['id']}"), InlineKeyboardButton("❌ Reject", callback_data=f"wreject_{w['id']}_{w['user_id']}_{w['coins']}") ]])
        await update.effective_message.reply_text(text, reply_markup=keyboard)

async def withdrawal_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id): return
    data = query.data
    if data.startswith("wapprove_"):
        db.process_withdrawal(int(data.split("_")[1]), "approved", query.from_user.id)
        await query.edit_message_text(query.message.text + "\n\n✅ APPROVED")
    elif data.startswith("wreject_"):
        _, wid, user_id, coins = data.split("_")
        db.process_withdrawal(int(wid), "rejected", query.from_user.id)
        db.add_coins(int(user_id), int(coins))
        await query.edit_message_text(query.message.text + "\n\n❌ REJECTED (coins refund)")


# ---------------- SETTINGS ----------------
async def setcoinrate_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_owner(update): return
    if not context.args or not context.args[0].isdigit(): return
    new_rate = int(context.args[0])
    db.set_setting("coin_per_correct", new_rate)
    config.COIN_PER_CORRECT = new_rate
    await update.effective_message.reply_text(f"✅ Global coin rate ab {new_rate} coins/correct answer hai.")


# ---------------- PER-GROUP SETTINGS ----------------
async def groupsettings_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_admin(update): return
    chat = update.effective_chat
    if chat.type not in ("group", "supergroup", "channel"):
        await update.effective_message.reply_text("⚠️ Ye command us group me chalao jiske settings set karni hain.")
        return
    db.upsert_group(chat.id, chat.title)
    gs = db.get_group_settings(chat.id)
    text = (f"⚙️ *Group Settings — {chat.title}*\n\n"
            f"🪙 Coin per correct: {gs['coin_per_correct'] if gs and gs['coin_per_correct'] else config.COIN_PER_CORRECT}\n"
            f"Badalne ke liye:\n`/setgroupcoin <amount>`\n`/setgroupnegative on <amount>`")
    await update.effective_message.reply_text(text, parse_mode="Markdown")

async def setgroupcoin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_admin(update): return
    if not context.args or not context.args[0].isdigit(): return
    db.update_group_setting_field(update.effective_chat.id, "coin_per_correct", int(context.args[0]))
    await update.effective_message.reply_text(f"✅ Is group ka coin rate ab {context.args[0]} hai.")

async def setgroupnegative_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_admin(update): return
    if not context.args or context.args[0].lower() not in ("on", "off"): return
    db.update_group_setting_field(update.effective_chat.id, "negative_marking", int(context.args[0].lower() == "on"))
    await update.effective_message.reply_text("✅ Negative marking updated.")

async def setgroupentryfee_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_admin(update): return
    if not context.args or not context.args[0].isdigit(): return
    db.update_group_setting_field(update.effective_chat.id, "entry_fee", int(context.args[0]))
    await update.effective_message.reply_text("✅ Entry fee updated.")

async def addgroup_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_admin(update): return
    if not context.args or len(context.args) < 1: return
    try: chat_id = int(context.args[0])
    except ValueError: return
    db.upsert_group(chat_id, f"Group {chat_id}")
    db.register_group_settings(chat_id, update.effective_user.id)
    await update.effective_message.reply_text("✅ Group add ho gaya.")

async def listgroups_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query: await update.callback_query.answer()
    if not await check_admin(update): return
    groups = db.get_active_groups()
    lines = ["📋 *Registered Groups:*\n"] + [f"• {g['title']} (`{g['chat_id']}`)" for g in groups]
    await update.effective_message.reply_text("\n".join(lines) if groups else "Koi group nahi hai.", parse_mode="Markdown")


# ---------------- HTML NOTES ----------------
async def sendnote_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query: await update.callback_query.answer()
    if not await check_admin(update): return ConversationHandler.END
    await update.effective_message.reply_text("📝 Note ka title likho:\n(Cancel ke liye /cancel)")
    return ASK_NOTE_TITLE

async def sendnote_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["note_title"] = update.message.text.strip()
    await update.effective_message.reply_text("✍️ Ab HTML note ka content likho:")
    return ASK_NOTE_CONTENT

async def sendnote_content(update: Update, context: ContextTypes.DEFAULT_TYPE):
    title = context.user_data.get("note_title", "Note")
    note_id = db.save_note(title, update.message.text, update.effective_user.id)
    clean_html = sanitize_for_telegram(update.message.text)
    for chunk in chunk_message(f"<b>{title}</b>\n\n{clean_html}"):
        try: await update.effective_message.reply_text(chunk, parse_mode="HTML")
        except: await update.effective_message.reply_text(re.sub(r"<[^>]+>", "", chunk))
    await update.effective_message.reply_text(f"✅ Note ban gaya! Group me bhejne ke liye:\n`/pushnote {note_id} <chat_id>`", parse_mode="Markdown")
    context.user_data.clear()
    return ConversationHandler.END

async def pushnote_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_admin(update): return
    if len(context.args) < 2 or not context.args[0].isdigit(): return
    note = db.get_note(int(context.args[0]))
    if not note: return
    try: chat_id = int(context.args[1])
    except ValueError: return
    clean_html = sanitize_for_telegram(note["content_html"])
    try:
        for chunk in chunk_message(f"<b>{note['title']}</b>\n\n{clean_html}"):
            await context.bot.send_message(chat_id, chunk, parse_mode="HTML")
        await update.effective_message.reply_text("✅ Note bhej diya gaya.")
    except Exception as e:
        await update.effective_message.reply_text(f"❌ Error: {e}")

async def notelist_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_admin(update): return
    notes = db.get_notes()
    lines = ["📚 *Saved Notes:*\n"] + [f"#{n['note_id']} — {n['title']}" for n in notes]
    await update.effective_message.reply_text("\n".join(lines) if notes else "Koi note nahi hai.", parse_mode="Markdown")

async def notesend_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id): return
    await query.message.reply_text(f"Group me bhejne ke liye likho:\n`/pushnote {query.data.split('_')[1]} <chat_id>`", parse_mode="Markdown")


# ---------------- PDF CLEANER ----------------
async def handle_pdf_clean_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    if not doc.file_name.lower().endswith(".pdf"): return
    status = await update.message.reply_text("⏳ PDF clean kar raha hoon...")
    file = await context.bot.get_file(doc.file_id)
    in_path, out_path = f"/tmp/in_{doc.file_unique_id}.pdf", f"/tmp/out_{doc.file_unique_id}.pdf"
    await file.download_to_drive(in_path)
    ok, msg = clean_pdf(in_path, out_path)
    if not ok:
        await status.edit_text(f"❌ Clean nahi ho paya: {msg}")
    else:
        db.log_pdf_job(update.effective_user.id, doc.file_name, "clean")
        await update.message.reply_document(document=open(out_path, "rb"), filename=f"cleaned_{doc.file_name}", caption="✅ Clean ho gaya!")
        await status.delete()
    for p in (in_path, out_path):
        if os.path.exists(p): os.remove(p)


# ---------------- REACTIONS BOT ----------------
async def reactions_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_admin(update): return
    chat = update.effective_chat
    gs = db.get_reaction_settings(chat.id)
    enabled = bool(gs["enabled"]) if gs else False
    text = (f"😀 *Reactions Bot*\nStatus: {'✅ ON' if enabled else '❌ OFF'}\n"
            f"`/reactionson` — chalu karo\n`/reactionsoff` — band karo\n"
            f"`/setreactionemojis 🔥 👍` — emojis badlo")
    await update.effective_message.reply_text(text, parse_mode="Markdown")

async def reactionson_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_admin(update): return
    db.set_reaction_enabled(update.effective_chat.id, True, update.effective_user.id)
    await update.effective_message.reply_text("✅ Reactions Bot chalu ho gaya.")

async def reactionsoff_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_admin(update): return
    db.set_reaction_enabled(update.effective_chat.id, False, update.effective_user.id)
    await update.effective_message.reply_text("✅ Reactions Bot band kar diya.")

async def setreactionemojis_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_admin(update): return
    if not context.args: return
    db.set_reaction_emojis(update.effective_chat.id, context.args[:5], update.effective_user.id)
    await update.effective_message.reply_text(f"✅ Reaction emojis set: {' '.join(context.args[:5])}")

async def auto_react_to_bot_message(context, chat_id, message_id):
    from utils.reactions import auto_react
    await auto_react(context, chat_id, message_id)


# ---------------- VISIBILITY BOOSTER ----------------
async def boost_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query: await update.callback_query.answer()
    if not await check_admin(update): return ConversationHandler.END
    await update.effective_message.reply_text("📝 Boost karne wala message likho:\n(Cancel ke liye /cancel)")
    return ASK_BOOST_CONTENT

async def boost_content(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["boost_content"] = update.message.text
    await update.effective_message.reply_text("🔘 Button chahiye? 'Text | https://link.com' format me likho, ya /skip likho.")
    return ASK_BOOST_BUTTON

async def boost_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text != "/skip" and "|" in text:
        context.user_data["btext"], context.user_data["burl"] = [x.strip() for x in text.split("|", 1)]
    await update.effective_message.reply_text("⏱ Schedule batao format me: `<minutes> <times>`\n(jaise `120 3` har 2 ghante me 3 baar)", parse_mode="Markdown")
    return ASK_BOOST_SCHEDULE

async def boost_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    parts = update.message.text.strip().split()
    if len(parts) != 2 or not all(p.isdigit() for p in parts):
        await update.effective_message.reply_text("⚠️ Format sahi nahi hai. Example: `120 3`")
        return ASK_BOOST_SCHEDULE
    every_min, times = int(parts[0]), int(parts[1])
    chat = update.effective_chat
    btext = context.user_data.get("btext")
    burl = context.user_data.get("burl")
    rm = InlineKeyboardMarkup([[InlineKeyboardButton(btext, url=burl)]]) if btext else None
    try:
        sent = await context.bot.send_message(chat.id, context.user_data.get("boost_content"), reply_markup=rm)
        await auto_react_to_bot_message(context, chat.id, sent.message_id)
        job_id = db.create_boost_job(chat.id, context.user_data.get("boost_content"), btext, burl, every_min, times, True, update.effective_user.id)
        db.mark_boost_job_run(job_id, every_min)
        await update.effective_message.reply_text("✅ Post bhej diya gaya!")
    except Exception as e:
        await update.effective_message.reply_text(f"❌ Error: {e}")
    context.user_data.clear()
    return ConversationHandler.END

async def boostlist_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_admin(update): return
    jobs = db.get_active_boost_jobs(update.effective_chat.id)
    lines = ["🚀 *Active Boosts:*\n"] + [f"#{j['job_id']} — har {j['repost_every_minutes']} min me"]
    await update.effective_message.reply_text("\n".join(lines) if jobs else "Koi active boost nahi hai.", parse_mode="Markdown")

async def stopboost_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_admin(update): return
    if not context.args or not context.args[0].isdigit(): return
    db.deactivate_boost_job(int(context.args[0]))
    await update.effective_message.reply_text("✅ Boost job rok diya gaya.")

async def besttime_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_admin(update): return
    hours = db.get_best_posting_hours(update.effective_chat.id)
    lines = ["⏰ *Best Posting Times*\n"] + [f"• {h%12 or 12}:00 {'AM' if h<12 else 'PM'} — {c} activities" for h, c in hours]
    await update.effective_message.reply_text("\n".join(lines) if hours else "Data nahi hai.", parse_mode="Markdown")


# ---------------- DIRECTORY ----------------
async def adddirectory_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query: await update.callback_query.answer()
    if not await check_admin(update): return ConversationHandler.END
    await update.effective_message.reply_text("📋 Title likho (jaise: Physics Study Group):\n(Cancel ke liye /cancel)")
    return ASK_DIR_TITLE

async def adddirectory_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["dir_title"] = update.message.text.strip()
    await update.effective_message.reply_text("📝 Chhoti si description likho:")
    return ASK_DIR_DESC

async def adddirectory_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["dir_desc"] = update.message.text.strip()
    await update.effective_message.reply_text("🏷 Category likho (jaise: Education, Motivation):")
    return ASK_DIR_CATEGORY

async def adddirectory_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["dir_category"] = update.message.text.strip()
    await update.effective_message.reply_text("🔗 Invite link bhejo (https://...):")
    return ASK_DIR_LINK

async def adddirectory_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    entry_id = db.add_directory_entry(context.user_data["dir_title"], context.user_data["dir_desc"], 
                                      context.user_data["dir_category"], update.message.text.strip(), update.effective_user.id)
    await update.effective_message.reply_text(f"✅ Directory me add ho gaya! (#{entry_id})\nMenu ke liye /menu dabayein.")
    context.user_data.clear()
    return ConversationHandler.END

async def removedirectory_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_admin(update): return
    if not context.args or not context.args[0].isdigit(): return
    db.deactivate_directory_entry(int(context.args[0]))
    await update.effective_message.reply_text("✅ Directory entry hata di gayi.")
