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

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

import database as db
import config
from utils.permissions import require_admin, require_owner, is_admin
from utils.docx_parser import parse_docx, validate_parsed
from utils.exporters import make_sample_template, export_questions_to_docx

# Conversation states for manual add-question flow
ASK_SUBJECT, ASK_CHAPTER, ASK_QUESTION, ASK_OPTIONS, ASK_ANSWER, ASK_EXPLANATION = range(6)

# Conversation state for ads
ASK_AD_CONTENT, ASK_AD_BUTTON = range(100, 102)


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
            await context.bot.send_message(g["chat_id"], content, reply_markup=reply_markup)
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
    if not await require_owner(update):
        return
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Usage: /setcoinrate <amount>")
        return
    db.set_setting("coin_per_correct", context.args[0])
    await update.message.reply_text(
        f"✅ Coin rate {context.args[0]} set ho gaya (agla restart ke baad fully apply hoga)."
    )
