"""
admin_handlers.py
Admin/Owner ke liye commands:
- Manual question add (conversation flow)
- Word file upload se bulk import
- Sample file / export question bank
- Broadcast, ads post karna
- Backup / restore
- Stats, user info, ban/unban
- Withdrawals approve/reject
- Coin rate set karna
"""

import os
import time
import json
import re

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

import database as db
import config
from utils.permissions import require_admin, require_owner, is_admin
from utils.docx_parser import parse_docx, validate_parsed
from utils.exporters import make_sample_template, export_questions_to_docx
from utils.pdf_cleaner import clean_pdf
from utils.html_notes import sanitize_for_telegram, chunk_message, build_note_html_file

# Conversation states for manual add-question flow
ASK_SUBJECT, ASK_CHAPTER, ASK_QUESTION, ASK_OPTIONS, ASK_ANSWER, ASK_EXPLANATION = range(6)

# Conversation state for ads
ASK_AD_CONTENT, ASK_AD_BUTTON = range(100, 102)

# Conversation states for HTML note composing
ASK_NOTE_TITLE, ASK_NOTE_CONTENT = range(200, 202)

# Conversation states for /addgroup (register a group/channel with custom settings)
ASK_GROUP_ID, ASK_GROUP_COINRATE, ASK_GROUP_NEGATIVE, ASK_GROUP_ENTRYFEE = range(300, 304)


# ---------------- MANUAL ADD QUESTION ----------------

async def addquestion_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update):
        return ConversationHandler.END
    await update.message.reply_text("📚 Subject ka naam likho (jaise: Physics):")
    return ASK_SUBJECT


async def addquestion_subject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_q_subject"] = update.message.text.strip()
    await update.message.reply_text("📑 Chapter ka naam likho (jaise: Motion):")
    return ASK_CHAPTER


async def addquestion_chapter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_q_chapter"] = update.message.text.strip()
    await update.message.reply_text("❓ Ab question likho:")
    return ASK_QUESTION


async def addquestion_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_q_text"] = update.message.text.strip()
    await update.message.reply_text(
        "🔤 Options likho, ek line me ek option "
        "(kam se kam 2, max 4). Jab sab options ho jaye to /done likhna.\n\n"
        "Example:\nKg\nm/s\nNewton\nWatt"
    )
    context.user_data["new_q_options"] = []
    return ASK_OPTIONS


async def addquestion_options(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "/done":
        opts = context.user_data.get("new_q_options", [])
        if len(opts) < 2:
            await update.message.reply_text("Kam se kam 2 options chahiye. Aur options bhejo:")
            return ASK_OPTIONS
        letters = ", ".join(f"{chr(65+i)}) {o}" for i, o in enumerate(opts))
        await update.message.reply_text(f"✅ Options: {letters}\n\nAb sahi answer ka letter likho (A/B/C/D):")
        return ASK_ANSWER

    context.user_data["new_q_options"].append(text)
    await update.message.reply_text(f"✅ Add hua: {text}\nAur option bhejo ya /done likho.")
    return ASK_OPTIONS


async def addquestion_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    letter = update.message.text.strip().upper()
    opts = context.user_data.get("new_q_options", [])
    if letter not in [chr(65+i) for i in range(len(opts))]:
        await update.message.reply_text(f"⚠️ Sirf {', '.join(chr(65+i) for i in range(len(opts)))} me se ek likho:")
        return ASK_ANSWER

    context.user_data["new_q_correct"] = ord(letter) - ord('A')
    await update.message.reply_text("💡 Explanation likho (optional, skip karne ke liye /skip likho):")
    return ASK_EXPLANATION


async def addquestion_explanation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    explanation = "" if text == "/skip" else text

    subject = context.user_data["new_q_subject"]
    chapter = context.user_data["new_q_chapter"]
    q_text = context.user_data["new_q_text"]
    opts = context.user_data["new_q_options"]
    correct = context.user_data["new_q_correct"]

    chapter_id = db.find_or_create_chapter(subject, chapter)
    qid = db.add_question(chapter_id, q_text, opts, correct, explanation, update.effective_user.id)

    await update.message.reply_text(
        f"✅ Question add ho gaya! (ID #{qid})\n📚 {subject} → {chapter}\n\n"
        f"Aur question add karne ke liye /addquestion likho."
    )
    context.user_data.clear()
    return ConversationHandler.END


async def addquestion_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("❌ Cancel ho gaya.")
    return ConversationHandler.END


# ---------------- WORD FILE UPLOAD ----------------

async def uploadword_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update):
        return
    await update.message.reply_text(
        "📎 Word (.docx) file bhejo jisme questions likhe ho.\n"
        "Format nahi pata? /samplefile likho, ek example file milegi."
    )


async def handle_docx_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return  # silently ignore non-admin file uploads

    doc = update.message.document
    if not doc.file_name.lower().endswith(".docx"):
        return

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
        if os.path.exists(local_path):
            os.remove(local_path)

    if not valid:
        err_text = "\n".join(errors[:10]) if errors else "Koi valid question nahi mila."
        await update.message.reply_text(f"❌ Koi question add nahi hua.\n\n{err_text}")
        return

    added = 0
    for q in valid:
        chapter_id = db.find_or_create_chapter(q["subject"], q["chapter"])
        db.add_question(chapter_id, q["question"], q["options"], q["correct_index"],
                        q["explanation"], update.effective_user.id)
        added += 1

    msg = f"✅ {added} questions successfully add ho gaye!"
    if errors:
        msg += f"\n⚠️ {len(errors)} questions skip hue (format error):\n" + "\n".join(errors[:5])
    await update.message.reply_text(msg)


async def samplefile_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update):
        return
    path = make_sample_template()
    await update.message.reply_document(document=open(path, "rb"),
                                        caption="📄 Ye raha sample format. Isi tarah apni file banao.")


async def exportquestions_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update):
        return
    questions = db.get_questions()
    if not questions:
        await update.message.reply_text("Question bank khali hai.")
        return
    path = export_questions_to_docx(questions)
    await update.message.reply_document(document=open(path, "rb"),
                                        caption=f"📦 Total {len(questions)} questions export kiye.")


async def deletequestion_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update):
        return
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Usage: /deletequestion <id>")
        return
    db.delete_question(int(context.args[0]))
    await update.message.reply_text("✅ Question delete ho gaya.")


# ---------------- ADMIN MANAGEMENT ----------------

async def addadmin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_owner(update):
        return
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Usage: /addadmin <user_id>")
        return
    uid = int(context.args[0])
    db.add_admin(uid, update.effective_user.id)
    await update.message.reply_text(f"✅ User {uid} ab admin hai.")


async def removeadmin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_owner(update):
        return
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Usage: /removeadmin <user_id>")
        return
    uid = int(context.args[0])
    db.remove_admin(uid)
    await update.message.reply_text(f"✅ User {uid} ab admin nahi hai.")


async def listadmins_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update):
        return
    admins = db.list_admins()
    text = "👮 *Admins:*\n" + "\n".join(f"• {a['user_id']}" for a in admins) if admins else "Koi extra admin nahi hai."
    await update.message.reply_text(text, parse_mode="Markdown")


# ---------------- BROADCAST ----------------

async def broadcast_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update):
        return
    text = update.message.text.partition(" ")[2].strip()
    if not text:
        await update.message.reply_text("Usage: /broadcast <message>")
        return

    users = db.get_all_users()
    sent, failed = 0, 0
    status_msg = await update.message.reply_text(f"📢 Bhej raha hoon... 0/{len(users)}")

    for i, u in enumerate(users):
        if u["is_banned"]:
            continue
        try:
            await context.bot.send_message(u["user_id"], f"📢 *Announcement*\n\n{text}", parse_mode="Markdown")
            sent += 1
        except Exception:
            failed += 1
        if i % 25 == 0:
            try:
                await status_msg.edit_text(f"📢 Bhej raha hoon... {i}/{len(users)}")
            except Exception:
                pass

    await status_msg.edit_text(f"✅ Broadcast complete!\nSent: {sent} | Failed: {failed}")


# ---------------- ADS ----------------

async def postad_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update):
        return ConversationHandler.END
    await update.message.reply_text("📝 Ad ka text/content likho:")
    return ASK_AD_CONTENT


async def postad_content(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["ad_content"] = update.message.text
    await update.message.reply_text(
        "🔘 Button chahiye? Agar haan to 'Button Text | https://link.com' format me likho.\n"
        "Nahi chahiye to /skip likho."
    )
    return ASK_AD_BUTTON


async def postad_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    button_text, button_url = None, None
    if text != "/skip" and "|" in text:
        button_text, button_url = [x.strip() for x in text.split("|", 1)]

    content = context.user_data.get("ad_content", "")
    ad_id = db.create_ad(content, button_text, button_url, update.effective_user.id)

    reply_markup = None
    if button_text and button_url:
        reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton(button_text, url=button_url)]])

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
    await update.message.reply_text(f"✅ Ad {sent} groups/channels me bhej diya gaya.")
    context.user_data.clear()
    return ConversationHandler.END


# ---------------- BACKUP / RESTORE ----------------

async def backup_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update):
        return
    from database import DB_PATH
    if not os.path.exists(DB_PATH):
        await update.message.reply_text("Database file nahi mili.")
        return
    await update.message.reply_document(
        document=open(DB_PATH, "rb"),
        filename=f"quizbot_backup_{int(time.time())}.db",
        caption="💾 Ye raha database backup. Isse restore karne ke liye /restore reply karke ye file bhejo."
    )


async def restore_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_owner(update):
        return
    await update.message.reply_text(
        "⚠️ Restore karne ke liye backup (.db) file is message ko *reply* karke bhejo.",
        parse_mode="Markdown"
    )


async def handle_db_restore_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    if not update.message.reply_to_message:
        return
    if "restore" not in (update.message.reply_to_message.text or "").lower():
        return

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
    if not await require_admin(update):
        return
    users = db.get_all_users()
    total_users = len(users)
    total_coins = sum(u["coins"] for u in users)
    total_q = db.count_questions()
    groups = db.get_active_groups()

    text = (
        f"📊 *Bot Stats*\n\n"
        f"👥 Total Users: {total_users}\n"
        f"🪙 Total Coins in circulation: {total_coins}\n"
        f"❓ Total Questions in bank: {total_q}\n"
        f"👨‍👩‍👧 Active Groups: {len(groups)}\n"
        f"📚 Total Subjects: {len(db.get_subjects())}\n"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def userinfo_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update):
        return
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Usage: /userinfo <user_id>")
        return

    uid = int(context.args[0])
    u = db.get_user(uid)
    if not u:
        await update.message.reply_text("User nahi mila.")
        return

    joined = time.strftime("%d-%b-%Y %H:%M", time.localtime(u["joined_at"]))
    last_online = time.strftime("%d-%b-%Y %H:%M", time.localtime(u["last_online"]))

    text = (
        f"👤 *User Info*\n\n"
        f"ID: {u['user_id']}\n"
        f"Name: {u['first_name']} (@{u['username']})\n"
        f"Joined (bot on kiya): {joined}\n"
        f"Last online: {last_online}\n"
        f"Coins: {u['coins']}\n"
        f"Total Quizzes: {u['total_quizzes']}\n"
        f"Correct/Wrong: {u['total_correct']}/{u['total_wrong']}\n"
        f"Banned: {'Haan' if u['is_banned'] else 'Nahi'}\n"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def ban_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update):
        return
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Usage: /ban <user_id>")
        return
    db.set_ban(int(context.args[0]), True)
    await update.message.reply_text("✅ User ban ho gaya.")


async def unban_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update):
        return
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Usage: /unban <user_id>")
        return
    db.set_ban(int(context.args[0]), False)
    await update.message.reply_text("✅ User unban ho gaya.")


# ---------------- WITHDRAWALS ----------------

async def withdrawals_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update):
        return
    pending = db.get_pending_withdrawals()
    if not pending:
        await update.message.reply_text("Koi pending withdrawal nahi hai.")
        return

    for w in pending:
        text = (
            f"💰 Withdrawal #{w['id']}\n"
            f"User: {w['first_name']} (@{w['username']}) | ID: {w['user_id']}\n"
            f"Coins: {w['coins']}"
        )
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Approve", callback_data=f"wapprove_{w['id']}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"wreject_{w['id']}_{w['user_id']}_{w['coins']}"),
        ]])
        await update.message.reply_text(text, reply_markup=keyboard)


async def withdrawal_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.answer("Sirf admin ye kar sakte hain.", show_alert=True)
        return

    data = query.data
    if data.startswith("wapprove_"):
        wid = int(data.split("_")[1])
        db.process_withdrawal(wid, "approved", query.from_user.id)
        await query.edit_message_text(query.message.text + "\n\n✅ APPROVED")
    elif data.startswith("wreject_"):
        _, wid, user_id, coins = data.split("_")
        db.process_withdrawal(int(wid), "rejected", query.from_user.id)
        db.add_coins(int(user_id), int(coins))  # refund
        await query.edit_message_text(query.message.text + "\n\n❌ REJECTED (coins refund ho gaye)")


# ---------------- SETTINGS ----------------

async def setcoinrate_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Global default coin rate — owner hi change kar sakta hai."""
    if not await require_owner(update):
        return
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Usage: /setcoinrate <amount>")
        return
    new_rate = int(context.args[0])
    db.set_setting("coin_per_correct", new_rate)
    config.COIN_PER_CORRECT = new_rate  # turant apply, restart ki zaroorat nahi
    await update.message.reply_text(f"✅ Global coin rate ab {new_rate} coins/correct answer hai.")


# ---------------- PER-GROUP SETTINGS ----------------
# Har group/channel apna alag coin rate, negative marking, entry fee rakh
# sakta hai. Owner/admin group me command chalayega, ya /addgroup se
# kisi bhi group_id ko remote se register kar sakta hai.

async def groupsettings_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Is command ko us group/channel me chalao jiske settings badalni hain."""
    if not await require_admin(update):
        return

    chat = update.effective_chat
    if chat.type not in ("group", "supergroup", "channel"):
        await update.message.reply_text(
            "⚠️ Ye command us group/channel me chalao jiske settings set karni hain.\n"
            "Kisi doosre group ko duur se set karne ke liye /addgroup use karo."
        )
        return

    db.upsert_group(chat.id, chat.title)
    gs = db.get_group_settings(chat.id)
    coin_rate = gs["coin_per_correct"] if gs and gs["coin_per_correct"] is not None else config.COIN_PER_CORRECT
    negative = bool(gs["negative_marking"]) if gs else False
    neg_amt = gs["negative_amount"] if gs and gs["negative_amount"] is not None else config.COIN_PER_CORRECT // 2
    entry_fee = gs["entry_fee"] if gs else 0

    text = (
        f"⚙️ *Group Settings — {chat.title}*\n\n"
        f"🪙 Coin per correct: {coin_rate}\n"
        f"⚠️ Negative marking: {'ON (-' + str(neg_amt) + ')' if negative else 'OFF'}\n"
        f"🎟 Entry fee: {entry_fee} coins\n\n"
        f"Badalne ke liye:\n"
        f"`/setgroupcoin <amount>`\n"
        f"`/setgroupnegative on|off <amount>`\n"
        f"`/setgroupentryfee <amount>`"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def setgroupcoin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update):
        return
    chat = update.effective_chat
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Usage: /setgroupcoin <amount>")
        return
    db.upsert_group(chat.id, chat.title)
    db.update_group_setting_field(chat.id, "coin_per_correct", int(context.args[0]))
    await update.message.reply_text(f"✅ Is group ka coin rate ab {context.args[0]} hai.")


async def setgroupnegative_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update):
        return
    chat = update.effective_chat
    if not context.args or context.args[0].lower() not in ("on", "off"):
        await update.message.reply_text("Usage: /setgroupnegative on <amount>  ya  /setgroupnegative off")
        return

    db.upsert_group(chat.id, chat.title)
    is_on = context.args[0].lower() == "on"
    db.update_group_setting_field(chat.id, "negative_marking", int(is_on))

    if is_on:
        amount = int(context.args[1]) if len(context.args) > 1 and context.args[1].isdigit() else config.COIN_PER_CORRECT // 2
        db.update_group_setting_field(chat.id, "negative_amount", amount)
        await update.message.reply_text(f"✅ Negative marking ON — galat jawab pe -{amount} coins.")
    else:
        await update.message.reply_text("✅ Negative marking OFF kar diya.")


async def setgroupentryfee_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update):
        return
    chat = update.effective_chat
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Usage: /setgroupentryfee <amount>  (0 = entry fee band)")
        return
    db.upsert_group(chat.id, chat.title)
    db.update_group_setting_field(chat.id, "entry_fee", int(context.args[0]))
    await update.message.reply_text(f"✅ Entry fee ab {context.args[0]} coins hai.")


async def addgroup_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Owner/admin apna group/channel ID add kar sakta hai (remote registration),
    taaki wahan ads/quiz bheje ja sakein bina waha jaake command chalaye."""
    if not await require_admin(update):
        return
    if not context.args or len(context.args) < 1:
        await update.message.reply_text(
            "Usage: /addgroup <chat_id> [title]\n\n"
            "Chat ID pata karne ke liye bot ko us group me add karo aur /groupsettings chalao, "
            "ya @userinfobot / @RawDataBot use karo."
        )
        return
    try:
        chat_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Chat ID number hona chahiye (jaise -1001234567890).")
        return

    title = " ".join(context.args[1:]) if len(context.args) > 1 else f"Group {chat_id}"
    db.upsert_group(chat_id, title)
    db.register_group_settings(chat_id, update.effective_user.id)
    await update.message.reply_text(f"✅ '{title}' add ho gaya. Ab /groupsettings us group me ja kar customize karo.")


async def listgroups_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update):
        return
    groups = db.get_active_groups()
    if not groups:
        await update.message.reply_text("Abhi koi group/channel registered nahi hai.")
        return
    lines = ["📋 *Registered Groups/Channels:*\n"]
    for g in groups:
        lines.append(f"• {g['title']} (`{g['chat_id']}`)")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# ---------------- HTML NOTES ----------------

async def sendnote_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update):
        return ConversationHandler.END
    await update.message.reply_text(
        "📝 Note ka title likho:"
    )
    return ASK_NOTE_TITLE


async def sendnote_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["note_title"] = update.message.text.strip()
    await update.message.reply_text(
        "✍️ Ab note ka content likho. HTML tags use kar sakte ho:\n"
        "<b>bold</b>, <i>italic</i>, <u>underline</u>, <a href='...'>link</a>, "
        "<code>code</code>, <pre>preformatted</pre>, <blockquote>quote</blockquote>"
    )
    return ASK_NOTE_CONTENT


async def sendnote_content(update: Update, context: ContextTypes.DEFAULT_TYPE):
    title = context.user_data.get("note_title", "Note")
    content_html = update.message.text

    note_id = db.save_note(title, content_html, update.effective_user.id)
    clean_html = sanitize_for_telegram(content_html)
    full_text = f"<b>{title}</b>\n\n{clean_html}"
    chunks = chunk_message(full_text)

    keyboard = [[InlineKeyboardButton("📤 Group/Channel me bhejo", callback_data=f"notesend_{note_id}")]]

    for chunk in chunks:
        try:
            await update.message.reply_text(chunk, parse_mode="HTML")
        except Exception:
            # agar HTML invalid hua to plain text fallback
            await update.message.reply_text(re.sub(r"<[^>]+>", "", chunk))

    await update.message.reply_text(
        "✅ Note ban gaya aur preview upar bhej diya. Kisi group/channel me bhejne ke liye "
        f"`/pushnote {note_id} <chat_id>` likho.",
        parse_mode="Markdown"
    )
    context.user_data.clear()
    return ConversationHandler.END


async def pushnote_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update):
        return
    if len(context.args) < 2 or not context.args[0].isdigit():
        await update.message.reply_text("Usage: /pushnote <note_id> <chat_id>")
        return

    note = db.get_note(int(context.args[0]))
    if not note:
        await update.message.reply_text("❌ Note nahi mila.")
        return
    try:
        chat_id = int(context.args[1])
    except ValueError:
        await update.message.reply_text("❌ chat_id number hona chahiye.")
        return

    clean_html = sanitize_for_telegram(note["content_html"])
    full_text = f"<b>{note['title']}</b>\n\n{clean_html}"
    chunks = chunk_message(full_text)

    try:
        last_msg = None
        for chunk in chunks:
            last_msg = await context.bot.send_message(chat_id, chunk, parse_mode="HTML")
        if last_msg:
            await auto_react_to_bot_message(context, chat_id, last_msg.message_id)
        await update.message.reply_text("✅ Note bhej diya gaya.")
    except Exception as e:
        await update.message.reply_text(f"❌ Bhejne me error: {e}")


async def notelist_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update):
        return
    notes = db.get_notes()
    if not notes:
        await update.message.reply_text("Koi note nahi bana hai. /sendnote se banao.")
        return
    lines = ["📚 *Saved Notes:*\n"]
    for n in notes:
        lines.append(f"#{n['note_id']} — {n['title']}")
    lines.append("\nBhejne ke liye: /pushnote <id> <chat_id>")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# ---------------- PDF CLEANER (watermark + hyperlink remover) ----------------

async def handle_pdf_clean_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Koi bhi user (admin ya normal) PDF bhej sakta hai clean karne ke liye."""
    doc = update.message.document
    if not doc.file_name.lower().endswith(".pdf"):
        return

    status = await update.message.reply_text("⏳ PDF clean kar raha hoon (watermark/link hata raha hoon)...")

    file = await context.bot.get_file(doc.file_id)
    in_path = f"/tmp/in_{doc.file_unique_id}.pdf"
    out_path = f"/tmp/out_{doc.file_unique_id}.pdf"
    await file.download_to_drive(in_path)

    ok, msg = clean_pdf(in_path, out_path)

    if not ok:
        await status.edit_text(f"❌ Clean nahi ho paya: {msg}")
    else:
        db.log_pdf_job(update.effective_user.id, doc.file_name, "clean")
        clean_name = f"cleaned_{doc.file_name}"
        await update.message.reply_document(
            document=open(out_path, "rb"),
            filename=clean_name,
            caption=f"✅ Clean ho gaya!\n{msg}"
        )
        await status.delete()

    for p in (in_path, out_path):
        if os.path.exists(p):
            os.remove(p)


# ---------------- HASHTAG OPTIMIZER (for the bot's own posts/ads) ----------------

_HASHTAG_BANK = {
    "quiz": ["#Quiz", "#QuizTime", "#OnlineQuiz", "#TestYourself", "#QuizChallenge"],
    "study": ["#StudyMaterial", "#Students", "#Learning", "#ExamPrep", "#StudyGroup"],
    "coins": ["#Rewards", "#EarnWhileYouLearn", "#WinCoins"],
    "general": ["#Education", "#KnowledgeIsPower", "#DailyQuiz", "#Competition"],
}


def _suggest_hashtags(topic_text, max_tags=8):
    topic_text = topic_text.lower()
    tags = []
    if any(k in topic_text for k in ["quiz", "test", "exam"]):
        tags += _HASHTAG_BANK["quiz"]
    if any(k in topic_text for k in ["study", "notes", "chapter", "subject", "student"]):
        tags += _HASHTAG_BANK["study"]
    if any(k in topic_text for k in ["coin", "reward", "win", "earn"]):
        tags += _HASHTAG_BANK["coins"]
    tags += _HASHTAG_BANK["general"]

    # word-based tags from the topic itself
    words = re.findall(r"[a-zA-Z]{4,}", topic_text)
    for w in words[:5]:
        tag = f"#{w.capitalize()}"
        if tag not in tags:
            tags.append(tag)

    # de-dup, preserve order, cap
    seen = set()
    result = []
    for t in tags:
        if t.lower() not in seen:
            seen.add(t.lower())
            result.append(t)
    return result[:max_tags]


async def hashtags_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/hashtags <apna post ka text ya topic> — bot ke apne posts/ads ke liye
    relevant hashtags suggest karta hai (koi external scraping nahi karta)."""
    if not await require_admin(update):
        return
    topic = update.message.text.partition(" ")[2].strip()
    if not topic:
        await update.message.reply_text("Usage: /hashtags <apne post ka topic ya text>\nExample: /hashtags Physics chapter quiz coins jeetiye")
        return

    tags = _suggest_hashtags(topic)
    await update.message.reply_text(
        "🏷 *Suggested Hashtags:*\n\n" + " ".join(tags) +
        "\n\nApne ad/post ke end me copy-paste kar sakte ho.",
        parse_mode="Markdown"
    )


# ---------------- NOTE: send-to-group callback ----------------

async def notesend_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.answer("Sirf admin ye kar sakte hain.", show_alert=True)
        return
    note_id = query.data.split("_")[1]
    await query.message.reply_text(
        f"Kis group/channel me bhejna hai? Uska chat_id ke saath likho:\n`/pushnote {note_id} <chat_id>`",
        parse_mode="Markdown"
    )


# =========================================================================
# REACTIONS BOT
# Bot apne khud ke messages (quiz results, ads, notes, boost posts) par
# auto-react karta hai — is group me jitne bhi bot-posts jaate hain unpar
# emoji reaction laga deta hai. Ye Telegram Bot API ke andar hi hota hai
# (set_message_reaction), koi userbot/scraping nahi. Doosre users ke ya
# doosre channels ke messages par react nahi karta.
# =========================================================================

async def reactions_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Is group/channel me reactions on/off dikhata hai."""
    if not await require_admin(update):
        return
    chat = update.effective_chat
    gs = db.get_reaction_settings(chat.id)
    enabled = bool(gs["enabled"]) if gs else False
    emojis = db.get_reaction_emojis(chat.id)
    text = (
        f"😀 *Reactions Bot — {chat.title or 'Yaha'}*\n\n"
        f"Status: {'✅ ON' if enabled else '❌ OFF'}\n"
        f"Emojis: {' '.join(emojis)}\n\n"
        f"Jab bhi bot khud koi post (quiz result, ad, note, boost) bhejta hai, "
        f"wo khud usi par in emojis se react karega — isse post active/lively dikhti hai.\n\n"
        f"`/reactionson` — chalu karo\n"
        f"`/reactionsoff` — band karo\n"
        f"`/setreactionemojis 🔥 👍 🎉` — emojis badlo (space se separate, max 5)"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def reactionson_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update):
        return
    chat = update.effective_chat
    db.set_reaction_enabled(chat.id, True, update.effective_user.id)
    await update.message.reply_text("✅ Reactions Bot chalu ho gaya — ab bot apne posts par auto-react karega.")


async def reactionsoff_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update):
        return
    chat = update.effective_chat
    db.set_reaction_enabled(chat.id, False, update.effective_user.id)
    await update.message.reply_text("✅ Reactions Bot band kar diya.")


async def setreactionemojis_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update):
        return
    if not context.args:
        await update.message.reply_text("Usage: /setreactionemojis 🔥 👍 🎉  (max 5 emoji, space se separate)")
        return
    emojis = context.args[:5]
    db.set_reaction_emojis(update.effective_chat.id, emojis, update.effective_user.id)
    await update.message.reply_text(f"✅ Reaction emojis set: {' '.join(emojis)}")


async def auto_react_to_bot_message(context, chat_id, message_id):
    """Helper — kahin bhi bot ka apna message bhejne ke baad ye call karo.
    Actual logic utils/reactions.py me hai (shared with quiz_engine.py)."""
    from utils.reactions import auto_react
    await auto_react(context, chat_id, message_id)  # reactions optional hain, silently skip agar Telegram support na kare


# =========================================================================
# VISIBILITY / ENGAGEMENT BOOSTER
# Genuine reach-improving tools: pin on post, scheduled re-posting, aur
# apne hi purane data se "best time to post" suggestion. Ye kisi bhi fake
# view/click/member count generate nahi karta — sirf asli tareeke se
# content ko zyada logo tak pahuchne me madad karta hai.
# =========================================================================

ASK_BOOST_CONTENT, ASK_BOOST_BUTTON, ASK_BOOST_SCHEDULE = range(400, 403)


async def boost_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update):
        return ConversationHandler.END
    chat = update.effective_chat
    if chat.type not in ("group", "supergroup", "channel"):
        await update.message.reply_text("⚠️ Ye command us group/channel me chalao jaha post boost karni hai.")
        return ConversationHandler.END
    await update.message.reply_text("📝 Boost karne wala message/content likho:")
    return ASK_BOOST_CONTENT


async def boost_content(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["boost_content"] = update.message.text
    await update.message.reply_text(
        "🔘 Button chahiye? 'Button Text | https://link.com' format me likho, ya /skip likho."
    )
    return ASK_BOOST_BUTTON


async def boost_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    button_text, button_url = None, None
    if text != "/skip" and "|" in text:
        button_text, button_url = [x.strip() for x in text.split("|", 1)]
    context.user_data["boost_button_text"] = button_text
    context.user_data["boost_button_url"] = button_url

    await update.message.reply_text(
        "⏱ Kitni der me repost karna hai (minutes me)? Aur kitni baar total?\n"
        "Format: `<minutes> <times>`  (jaise: `120 3` = har 2 ghante me, total 3 baar)\n"
        "Sirf ek baar post karna ho to `0 1` likho.",
        parse_mode="Markdown"
    )
    return ASK_BOOST_SCHEDULE


async def boost_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    parts = update.message.text.strip().split()
    if len(parts) != 2 or not all(p.isdigit() for p in parts):
        await update.message.reply_text("⚠️ Format sahi nahi hai. Example: `120 3`", parse_mode="Markdown")
        return ASK_BOOST_SCHEDULE

    every_min, times = int(parts[0]), int(parts[1])
    chat = update.effective_chat
    content = context.user_data.get("boost_content", "")
    button_text = context.user_data.get("boost_button_text")
    button_url = context.user_data.get("boost_button_url")

    reply_markup = None
    if button_text and button_url:
        reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton(button_text, url=button_url)]])

    try:
        sent = await context.bot.send_message(chat.id, content, reply_markup=reply_markup)
        member_count = None
        try:
            member_count = await context.bot.get_chat_member_count(chat.id)
        except Exception:
            pass
        db.log_post_engagement(chat.id, sent.message_id, member_count)
        await auto_react_to_bot_message(context, chat.id, sent.message_id)

        pin_it = True  # first post of a boost job gets pinned for visibility
        if pin_it:
            try:
                await context.bot.pin_chat_message(chat.id, sent.message_id, disable_notification=True)
            except Exception:
                pass

        job_id = db.create_boost_job(chat.id, content, button_text, button_url, every_min,
                                     times, pin_it, update.effective_user.id)
        db.mark_boost_job_run(job_id, every_min)

        msg = f"✅ Post bhej diya gaya aur pin kar diya!"
        if every_min and times > 1:
            msg += f"\nAgle {times - 1} repost har {every_min} minute me automatically honge."
        await update.message.reply_text(msg)
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

    context.user_data.clear()
    return ConversationHandler.END


async def boostlist_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update):
        return
    jobs = db.get_active_boost_jobs(update.effective_chat.id)
    if not jobs:
        await update.message.reply_text("Is group/channel me koi active boost job nahi hai.")
        return
    lines = ["🚀 *Active Boost Jobs:*\n"]
    for j in jobs:
        lines.append(f"#{j['job_id']} — {j['repost_count_done']}/{j['max_reposts'] or '∞'} posts done, "
                     f"har {j['repost_every_minutes']} min me")
    lines.append("\nRokne ke liye: `/stopboost <id>`")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def stopboost_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update):
        return
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Usage: /stopboost <job_id>")
        return
    db.deactivate_boost_job(int(context.args[0]))
    await update.message.reply_text("✅ Boost job rok diya gaya.")


async def besttime_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Is group ke apne purane quiz-activity data se best posting hours
    nikaalta hai — koi external/fake data nahi, sirf real usage pattern."""
    if not await require_admin(update):
        return
    chat = update.effective_chat
    best_hours = db.get_best_posting_hours(chat.id)
    if not best_hours:
        await update.message.reply_text(
            "📊 Abhi is group ka itna activity-data nahi hai suggestion dene ke liye. "
            "Kuch quizzes karwao, phir dobara try karo."
        )
        return
    lines = ["⏰ *Best Posting Time Suggestions*\n(Is group ke apne quiz-activity data ke aadhar par)\n"]
    for hour, count in best_hours:
        period = "AM" if hour < 12 else "PM"
        display_hour = hour % 12 or 12
        lines.append(f"• {display_hour}:00 {period} — {count} activities is ghante me")
    lines.append("\nInhi ghanto me post/quiz karwana zyada log active milenge.")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# =========================================================================
# GROUP/CHANNEL DIRECTORY
# Admin apne khud ke (jinke wo owner/admin hain) groups/channels ko category
# ke saath list karta hai. Users /discover se apni interest ke hisaab se
# browse karte hain. Ye kisi doosre ke channels ko scan/scrape NAHI karta —
# sirf wahi entries hoti hain jo admin ne khud add ki hon.
# =========================================================================

ASK_DIR_TITLE, ASK_DIR_DESC, ASK_DIR_CATEGORY, ASK_DIR_LINK = range(500, 504)


async def adddirectory_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update):
        return ConversationHandler.END
    await update.message.reply_text(
        "📋 *Naya Group/Channel Directory Entry*\n\n"
        "⚠️ Sirf apne khud ke (jinke tum owner/admin ho) groups/channels add karo.\n\n"
        "Title likho (jaise: Physics Study Group):",
        parse_mode="Markdown"
    )
    return ASK_DIR_TITLE


async def adddirectory_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["dir_title"] = update.message.text.strip()
    await update.message.reply_text("📝 Chhoti si description likho:")
    return ASK_DIR_DESC


async def adddirectory_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["dir_desc"] = update.message.text.strip()
    await update.message.reply_text(
        "🏷 Category likho (jaise: Education, Coding, Motivation, General):"
    )
    return ASK_DIR_CATEGORY


async def adddirectory_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["dir_category"] = update.message.text.strip()
    await update.message.reply_text("🔗 Invite link bhejo (https://t.me/... ya @username):")
    return ASK_DIR_LINK


async def adddirectory_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    link = update.message.text.strip()
    title = context.user_data.get("dir_title", "")
    desc = context.user_data.get("dir_desc", "")
    category = context.user_data.get("dir_category", "General")

    entry_id = db.add_directory_entry(title, desc, category, link, update.effective_user.id)
    await update.message.reply_text(
        f"✅ Directory me add ho gaya! (#{entry_id})\n📋 {title} — {category}\n\n"
        f"Users ab `/discover` se ise dekh sakte hain."
    )
    context.user_data.clear()
    return ConversationHandler.END


async def removedirectory_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update):
        return
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Usage: /removedirectory <entry_id>")
        return
    db.deactivate_directory_entry(int(context.args[0]))
    await update.message.reply_text("✅ Directory entry hata di gayi.")
