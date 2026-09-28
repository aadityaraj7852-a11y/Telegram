"""
admin_handlers.py
Admin/Owner ke liye commands and UI flow.
"""

import os
import time
import re
import json
import asyncio
import random
import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

import database as db
import config
from utils.permissions import require_admin, require_owner, is_admin, is_owner
from utils.docx_parser import parse_docx, validate_parsed
from utils.exporters import make_sample_template, export_questions_to_docx
from utils.html_notes import sanitize_for_telegram, chunk_message

logger = logging.getLogger(__name__)

# Conversation states
ASK_SUBJECT, ASK_CHAPTER, ASK_DOCX_FILE = range(3)
ASK_AD_CONTENT, ASK_AD_BUTTON = range(100, 102)
ASK_NOTE_TITLE, ASK_NOTE_CONTENT = range(200, 202)
ASK_GROUP_ID, ASK_GROUP_COINRATE, ASK_GROUP_NEGATIVE, ASK_GROUP_ENTRYFEE = range(300, 304)
ASK_BOOST_CONTENT, ASK_BOOST_BUTTON, ASK_BOOST_SCHEDULE = range(400, 403)
ASK_DIR_TITLE, ASK_DIR_DESC, ASK_DIR_CATEGORY, ASK_DIR_LINK = range(500, 504)

# New Advanced States
ASK_ADMIN_ID_ADD, ASK_ADMIN_GROUP, ASK_ADMIN_RIGHTS = range(700, 703)
ASK_ADMIN_ID_REMOVE = 704
ASK_BROADCAST_TARGET, ASK_BROADCAST_MSG = range(710, 712)
ASK_QUIZ_DEST_TYPE, ASK_QUIZ_JSON, ASK_QUIZ_GROUP_CHAP, ASK_QUIZ_GROUP_TIMER, ASK_QUIZ_GROUP_COUNT, ASK_QUIZ_GROUP_CONFIRM = range(800, 806)


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


# ---------------- 1. ADVANCED ADMIN MANAGEMENT ----------------
async def manage_admins_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    await update.effective_message.reply_text("➕ Naye Admin ka Telegram ID ya Username bhejo:\n(Cancel ke liye /cancel)")
    return ASK_ADMIN_ID_ADD

async def admin_add_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_admin_id"] = update.message.text.strip()
    await update.effective_message.reply_text("🔗 Is admin ke Group ya Channel ka link/naam batao:\n(Agar koi nahi hai to 'Skip' likho)")
    return ASK_ADMIN_GROUP

async def admin_add_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_admin_group"] = update.message.text.strip()
    kb = [
        [InlineKeyboardButton("👑 Full Rights (Sab kuch)", callback_data="arights_full")],
        [InlineKeyboardButton("📢 Only Broadcast & Quiz", callback_data="arights_limited")]
    ]
    await update.effective_message.reply_text("⚙️ Is admin ko kaunse Rights (Permissions) dene hain?", reply_markup=InlineKeyboardMarkup(kb))
    return ASK_ADMIN_RIGHTS

async def admin_add_rights(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    rights = query.data.split("_")[1]
    admin_input = context.user_data.get("new_admin_id", "")
    
    uid = 0
    if admin_input.isdigit(): 
        uid = int(admin_input)
    else: 
        uid = random.randint(100000, 999999) 

    db.add_admin(uid, query.from_user.id) 
    
    await query.edit_message_text(
        f"✅ *Admin Successfully Added!*\n\n"
        f"👤 ID/Username: {admin_input}\n"
        f"🔗 Group/Channel: {context.user_data.get('new_admin_group')}\n"
        f"⚙️ Rights: {rights.upper()}\n\n"
        f"Menu me wapas jane ke liye /menu dabayein.", parse_mode="Markdown"
    )
    context.user_data.clear()
    return ConversationHandler.END

async def admin_rem_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query: await update.callback_query.answer()
    if not await check_owner(update): return ConversationHandler.END
    await update.effective_message.reply_text("❌ Jisko admin se hatana hai, uska Telegram ID bhejo:\n(Cancel karne ke liye /cancel likho)")
    return ASK_ADMIN_ID_REMOVE

async def admin_rem_process(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if not text.isdigit():
        await update.message.reply_text("❌ ID sirf numbers me honi chahiye. Dobara bhejo ya /cancel likho:")
        return ASK_ADMIN_ID_REMOVE
    uid = int(text)
    db.remove_admin(uid)
    await update.message.reply_text(f"✅ User {uid} ko admin se hata diya gaya hai.\nMenu ke liye /menu dabayein.")
    return ConversationHandler.END

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


# ---------------- 2. SUPER BROADCAST (TARGETED & HTML + IMAGE SUPPORT) ----------------
async def broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query: await update.callback_query.answer()
    if not await check_admin(update): return ConversationHandler.END
    
    groups = db.get_active_groups()
    if not groups:
         await update.effective_message.reply_text("❌ Koi bhi group ya channel list me nahi hai. Pehle bot ko add karein.")
         return ConversationHandler.END

    kb = [[InlineKeyboardButton(g['title'], callback_data=f"bcast_{g['chat_id']}")] for g in groups]
    kb.append([InlineKeyboardButton("👥 All Users (DM)", callback_data="bcast_users")])
    kb.append([InlineKeyboardButton("🏢 All Groups/Channels", callback_data="bcast_allgroups")])
    kb.append([InlineKeyboardButton("❌ Cancel", callback_data="bcast_cancel")])
    
    await update.effective_message.reply_text("📢 **Broadcast kahan karna hai? Target Choose Karein:**", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
    return ASK_BROADCAST_TARGET

async def broadcast_target(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "bcast_cancel":
        await query.edit_message_text("❌ Broadcast Cancelled.")
        return ConversationHandler.END
        
    context.user_data["bcast_target"] = query.data.split("_")[1]
    
    sample_text = (
        "✍️ *Ab apna Broadcast Message bhejein!*\n\n"
        "💡 *Tip:* Aap yahan simple text, HTML format, Emoji, ya Image ke sath Caption bhi bhej sakte hain. "
        "Aap jaisa message bhejenge (Bold, Italic, Link, Photo), bot exactly waisa hi copy karke bhej dega!\n\n"
        "(Cancel karne ke liye /cancel likhein)"
    )
    await query.edit_message_text(sample_text, parse_mode="Markdown")
    return ASK_BROADCAST_MSG

async def broadcast_process(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target_type = context.user_data.get("bcast_target")
    msg_id = update.message.message_id
    from_chat_id = update.effective_chat.id
    
    targets = []
    if target_type == "users":
        targets = [u["user_id"] for u in db.get_all_users() if not u["is_banned"]]
    elif target_type == "allgroups":
        targets = [g["chat_id"] for g in db.get_active_groups()]
    else:
        try: targets = [int(target_type)]
        except: targets = []

    if not targets:
        await update.message.reply_text("❌ Koi targets nahi mile.")
        return ConversationHandler.END

    status_msg = await update.message.reply_text(f"📢 Broadcast shuru ho raha hai... 0/{len(targets)}")
    sent, failed = 0, 0
    
    for i, t in enumerate(targets):
        try:
            await context.bot.copy_message(chat_id=t, from_chat_id=from_chat_id, message_id=msg_id)
            sent += 1
        except Exception:
            failed += 1
            
        if i % 25 == 0 and i > 0:
            try: await status_msg.edit_text(f"📢 Bhej raha hoon... {i}/{len(targets)}")
            except Exception: pass
            
    await status_msg.edit_text(f"✅ Broadcast Complete!\nTarget: {target_type.upper()}\nSent: {sent} | Failed: {failed}")
    context.user_data.clear()
    return ConversationHandler.END


# ---------------- 3. SEND QUIZ (JSON FOR CHANNELS, ENGINE FOR GROUPS) ----------------
async def sendquiz_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query: await update.callback_query.answer()
    if not await check_admin(update): return ConversationHandler.END
    
    groups = db.get_active_groups()
    if not groups:
         await update.effective_message.reply_text("❌ Koi bhi group ya channel list me nahi hai. Pehle bot ko kisi group me add karein.")
         return ConversationHandler.END

    kb = [[InlineKeyboardButton(f"📢 Channel: {g['title']}", callback_data=f"squiz_channel_{g['chat_id']}")] for g in groups]
    kb.extend([[InlineKeyboardButton(f"👥 Group: {g['title']}", callback_data=f"squiz_group_{g['chat_id']}")] for g in groups])
    kb.append([InlineKeyboardButton("❌ Cancel", callback_data="squiz_cancel")])
    
    await update.effective_message.reply_text("🎯 **Aap Quiz kahan bhejna chahte hain?**", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
    return ASK_QUIZ_DEST_TYPE

async def sendquiz_dest_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "squiz_cancel":
        await query.edit_message_text("❌ Cancelled.")
        return ConversationHandler.END
        
    parts = query.data.split("_")
    dest_type = parts[1] 
    chat_id = int(parts[2])
    
    context.user_data["squiz_dest_type"] = dest_type
    context.user_data["squiz_chat_id"] = chat_id
    
    if dest_type == "channel":
        context.user_data["json_buffer"] = ""
        sample_json = '[\n  {\n    "module": "Rajasthan GK",\n    "question": "प्रश्न?",\n    "option": ["A. x", "B. y", "C. z", "D. w"],\n    "answer": "A",\n    "solution": "व्याख्या"\n  }\n]'
        await query.edit_message_text(
            f"📥 *Channel JSON Upload*\n\nApna JSON code yahan paste karein. Agar code lamba hai to tukdon me paste karte rahein. "
            f"Jab poora code paste ho jaye, tab `/done` type karein.\n\n*Sample Format:*\n`{sample_json}`", parse_mode="Markdown"
        )
        return ASK_QUIZ_JSON
    else:
        subjects = db.get_subjects()
        kb = [[InlineKeyboardButton(s['name'], callback_data=f"sqsubj_{s['subject_id']}")] for s in subjects]
        kb.append([InlineKeyboardButton("🔀 Mix All (Random)", callback_data="sqsubj_all")])
        await query.edit_message_text("📚 **Subejct Choose Karein:**", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
        return ASK_QUIZ_GROUP_CHAP

# --- JSON Logic for Channels ---
async def sendquiz_receive_json_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    
    context.user_data["json_buffer"] = context.user_data.get("json_buffer", "") + text
    await update.message.reply_text("✅ Code added. Agar aur code bacha hai to paste karein, warna `/done` likhein.")
    return ASK_QUIZ_JSON

async def sendquiz_receive_json_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    json_data = context.user_data.get("json_buffer", "").strip()
    if not json_data:
        await update.message.reply_text("❌ Aapne koi JSON data nahi diya. Kripya JSON paste karein.")
        return ASK_QUIZ_JSON

    try:
        if not json_data.startswith('['): json_data = '[' + json_data
        if not json_data.endswith(']'): json_data = json_data + ']'
        json_data = re.sub(r'\]\s*\[', ',', json_data)
        
        parsed_json = json.loads(json_data)
        if not isinstance(parsed_json, list):
            raise ValueError("JSON array list [] format me hona chahiye.")
    except Exception as e:
        await update.message.reply_text(f"❌ JSON Error: {e}\nKripya sahi JSON bhejein ya dobara paste karna shuru karein (Purana code clear kar diya gaya hai).")
        context.user_data["json_buffer"] = ""
        return ASK_QUIZ_JSON
        
    channel_id = context.user_data.get("squiz_chat_id")
    await update.message.reply_text(f"✅ Successfully parsed {len(parsed_json)} questions!\n🚀 Channel me quiz bhejna shuru ho gaya hai. (Har question ke beech 30s ka gap hoga).")
    
    asyncio.create_task(process_channel_json_quiz(context, channel_id, parsed_json, update.effective_user.id))
    context.user_data.clear()
    return ConversationHandler.END


async def process_channel_json_quiz(context, channel_id, parsed_json, admin_id):
    sent = 0
    for item in parsed_json:
        try:
            q = str(item.get("question", "")).replace("<br>", "\n").replace("<br/>", "\n")
            opts_list = item.get("option", [])
            opts = "\n".join([str(o) for o in opts_list]).replace("<br>", "\n")
            ans = str(item.get("answer", ""))
            sol = str(item.get("solution", "")).replace("<br>", "\n").replace("<br/>", "\n")
            module = str(item.get("module", "GK"))
            
            q_text = f"🏷 <b>Topic:</b> {module}\n\n❓ <b>प्रश्न:</b>\n{q}\n\n<b>विकल्प:</b>\n{opts}"
            if len(q_text) > 4000: q_text = q_text[:4000] + "..."
            await context.bot.send_message(chat_id=channel_id, text=q_text, parse_mode="HTML")
            
            if sol:
                sol_text = f"✅ <b>सही उत्तर:</b> {ans}\n\n<tg-spoiler><b>व्याख्या (Explanation):</b>\n{sol}</tg-spoiler>"
            else:
                sol_text = f"✅ <b>सही उत्तर:</b> {ans}"
                
            if len(sol_text) > 4000: sol_text = sol_text[:4000] + "...</tg-spoiler>"
            await context.bot.send_message(chat_id=channel_id, text=sol_text, parse_mode="HTML")
            
            sent += 1
            await asyncio.sleep(30)
        except Exception as e:
            logger.error(f"Error sending to channel: {e}")
            await asyncio.sleep(5)
            
    try:
        await context.bot.send_message(chat_id=admin_id, text=f"✅ Channel me {sent} questions successfully bhej diye gaye hain!")
    except: pass

# --- Group Quiz Logic ---
async def sendquiz_group_chap(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data.split("_")[1]
    
    if data == "all":
        context.user_data['sq_subj'] = None
        context.user_data['sq_chap'] = None
        kb = [[InlineKeyboardButton("15 Sec", callback_data="sqtime_15"), InlineKeyboardButton("20 Sec", callback_data="sqtime_20")],
              [InlineKeyboardButton("30 Sec", callback_data="sqtime_30"), InlineKeyboardButton("45 Sec", callback_data="sqtime_45")]]
        await query.edit_message_text("⏱ **Timer choose karein:**", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
        return ASK_QUIZ_GROUP_TIMER
    else:
        subj_id = int(data)
        context.user_data['sq_subj'] = subj_id
        chaps = db.get_chapters(subj_id)
        kb = [[InlineKeyboardButton(c['name'], callback_data=f"sqchap_{c['chapter_id']}")] for c in chaps]
        kb.append([InlineKeyboardButton("🔀 All Chapters", callback_data="sqchap_all")])
        await query.edit_message_text("📑 **Chapter Choose Karein:**", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
        return ASK_QUIZ_GROUP_TIMER

async def sendquiz_group_timer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data.split("_")[1]
    
    if data != "all": context.user_data['sq_chap'] = int(data)
    else: context.user_data['sq_chap'] = None
    
    kb = [[InlineKeyboardButton("15 Sec", callback_data="sqtime_15"), InlineKeyboardButton("20 Sec", callback_data="sqtime_20")],
          [InlineKeyboardButton("30 Sec", callback_data="sqtime_30"), InlineKeyboardButton("45 Sec", callback_data="sqtime_45")]]
    await query.edit_message_text("⏱ **Har question ke liye Timer choose karein:**", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
    return ASK_QUIZ_GROUP_COUNT

async def sendquiz_group_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data['sq_timer'] = int(query.data.split("_")[1])
    
    kb = [[InlineKeyboardButton("10 Qs", callback_data="sqlen_10"), InlineKeyboardButton("20 Qs", callback_data="sqlen_20")],
          [InlineKeyboardButton("50 Qs", callback_data="sqlen_50"), InlineKeyboardButton("100 Qs", callback_data="sqlen_100")]]
    await query.edit_message_text("🔢 **Kitne questions ka quiz bhejna hai?**", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
    return ASK_QUIZ_GROUP_CONFIRM 

async def sendquiz_group_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    num = int(query.data.split("_")[1])
    chat_id = context.user_data['squiz_chat_id']
    subj = context.user_data.get('sq_subj')
    chap = context.user_data.get('sq_chap')
    timer = context.user_data['sq_timer']

    chat_title = "Remote Group"
    for g in db.get_active_groups():
        if g['chat_id'] == chat_id: chat_title = g['title']

    await query.edit_message_text(f"✅ Awesome! Quiz {num} questions aur {timer}s timer ke sath group '{chat_title}' me launch ho raha hai...")
    
    import quiz_engine
    await quiz_engine.start_quiz_session(context, chat_id, chat_title, subj, chap, query.from_user.id, num, timer)
    
    context.user_data.clear()
    return ConversationHandler.END


# ---------------- ADD QUESTION (SUBJECT -> CHAPTER -> WORD FILE) ----------------
async def addquestion_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query: await update.callback_query.answer()
    if not await check_admin(update): return ConversationHandler.END
    await update.effective_message.reply_text("📚 Subject ka naam likho (jaise: Rajasthan GK):\n(Cancel ke liye /cancel)")
    return ASK_SUBJECT

async def addquestion_subject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_q_subject"] = update.message.text.strip()
    await update.effective_message.reply_text("📑 Chapter ka naam likho (jaise: Geography):")
    return ASK_CHAPTER

async def addquestion_chapter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_q_chapter"] = update.message.text.strip()
    await update.effective_message.reply_text(
        "📎 Ab apne questions ki Word (.docx) file upload karo:\n\n"
        "(Bot automatically sirf Hindi direction wale questions extract karega aur "
        "baaki English wale ya extra text ko ignore kar dega.)"
    )
    return ASK_DOCX_FILE

async def addquestion_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    if not doc or not doc.file_name.lower().endswith(".docx"):
        await update.effective_message.reply_text("❌ Kripya sirf Word (.docx) file bhejein ya /cancel likhein.")
        return ASK_DOCX_FILE

    await update.effective_message.reply_text("⏳ File padh raha hoon... kripya pratiksha karein.")
    file = await context.bot.get_file(doc.file_id)
    local_path = f"/tmp/{doc.file_unique_id}.docx"
    await file.download_to_drive(local_path)

    try:
        parsed = parse_docx(local_path)
        for q in parsed:
            q["subject"] = context.user_data["new_q_subject"]
            q["chapter"] = context.user_data["new_q_chapter"]
            
        valid, errors = validate_parsed(parsed)
    except Exception as e:
        await update.effective_message.reply_text(f"❌ File padhne me error: {e}")
        if os.path.exists(local_path): os.remove(local_path)
        return ConversationHandler.END

    if os.path.exists(local_path): os.remove(local_path)

    if not valid:
        await update.effective_message.reply_text("❌ Koi valid question add nahi hua.")
        context.user_data.clear()
        return ConversationHandler.END

    added = 0
    for q in valid:
        chapter_id = db.find_or_create_chapter(q["subject"], q["chapter"])
        db.add_question(chapter_id, q["question"], q["options"], q["correct_index"], q["explanation"], update.effective_user.id)
        added += 1

    msg = (f"✅ Success! Aapki file se {added} Hindi questions successfully upload ho gaye.\n"
           f"📚 Subject: {context.user_data['new_q_subject']}\n"
           f"📑 Chapter: {context.user_data['new_q_chapter']}")
    if errors: msg += f"\n\n⚠️ {len(errors)} questions skip hue."
        
    await update.effective_message.reply_text(msg)
    context.user_data.clear()
    return ConversationHandler.END

async def addquestion_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.effective_message.reply_text("❌ Cancel ho gaya. Menu ke liye /menu dabayein.")
    return ConversationHandler.END


# ---------------- DIRECT WORD FILE UPLOAD (OPTIONAL / OLD COMMAND) ----------------
async def uploadword_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query: await update.callback_query.answer()
    if not await check_admin(update): return
    await update.effective_message.reply_text("📎 Direct Word (.docx) file bhejo.\n(Naya flow use karne ke liye /addquestion ya 'Add Question' button dabayein.)")

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


# ---------------- OTHER ADMIN FUNCTIONS ----------------
async def listgroups_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query: await update.callback_query.answer()
    if not await check_admin(update): return
    groups = db.get_active_groups()
    lines = ["📋 *Registered Groups / Channels:*"]
    if groups:
        for g in groups: lines.append(f"• {g['title']} (`{g['chat_id']}`)")
    else:
        lines.append("Koi group nahi hai.")
    lines.append("\n💡 _Note: Agar koi group list me nahi hai, to us group me ek bar kuch message karein taaki bot auto-save kar le._")
    await update.effective_message.reply_text("\n".join(lines), parse_mode="Markdown")

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

async def setcoinrate_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_owner(update): return
    if not context.args or not context.args[0].isdigit(): return
    new_rate = int(context.args[0])
    db.set_setting("coin_per_correct", new_rate)
    config.COIN_PER_CORRECT = new_rate
    await update.effective_message.reply_text(f"✅ Global coin rate ab {new_rate} coins/correct answer hai.")

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
        
    groups = db.get_active_groups()
    if not groups:
        await update.effective_message.reply_text("✅ Note ban gaya! (Lekin koi group/channel list me nahi hai.)")
    else:
        kb = [[InlineKeyboardButton(g['title'], callback_data=f"pushnote_{note_id}_{g['chat_id']}")] for g in groups]
        kb.append([InlineKeyboardButton("❌ Cancel", callback_data="pushnote_cancel")])
        await update.effective_message.reply_text("✅ Note ban gaya! **Kahan bhejna hai? Niche button dabayein:**", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
        
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

async def pushnote_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id): return
    
    data = query.data
    if data == "pushnote_cancel":
        await query.edit_message_text("❌ Cancelled.")
        return
        
    _, note_id, chat_id = data.split("_", 2)
    note = db.get_note(int(note_id))
    if not note: 
        await query.edit_message_text("❌ Note nahi mila.")
        return
        
    clean_html = sanitize_for_telegram(note["content_html"])
    try:
        for chunk in chunk_message(f"<b>{note['title']}</b>\n\n{clean_html}"):
            await context.bot.send_message(chat_id, chunk, parse_mode="HTML")
        await query.edit_message_text("✅ Note successfully bhej diya gaya!")
    except Exception as e:
        await query.edit_message_text(f"❌ Error sending note: {e}")

async def notelist_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_admin(update): return
    notes = db.get_notes()
    if not notes:
        await update.effective_message.reply_text("Koi note nahi hai.")
        return
        
    lines = ["📚 *Saved Notes:*\n"]
    for n in notes:
        lines.append(f"• #{n['note_id']} — {n['title']}")
        
    kb = []
    for n in notes:
        kb.append([InlineKeyboardButton(f"Send: {n['title'][:20]}", callback_data=f"notesend_{n['note_id']}")])
        
    await update.effective_message.reply_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

async def notesend_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id): return
    
    note_id = query.data.split('_')[1]
    groups = db.get_active_groups()
    if not groups:
         await query.message.reply_text("❌ Koi group/channel list me nahi hai.")
         return
         
    kb = [[InlineKeyboardButton(g['title'], callback_data=f"pushnote_{note_id}_{g['chat_id']}")] for g in groups]
    kb.append([InlineKeyboardButton("❌ Cancel", callback_data="pushnote_cancel")])
    await query.message.reply_text("🎯 **Is note ko kahan bhejna hai? Target Choose Karein:**", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

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

# 🗑 DIRECTORY ENTRY DELETE LOGIC UPDATED
async def removedirectory_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_admin(update): return
    
    if not context.args or not context.args[0].isdigit():
        categories = db.get_directory_categories()
        if not categories:
            await update.effective_message.reply_text("❌ Directory abhi khali hai.")
            return
            
        text = "📋 *Directory Entries (Delete karne ke liye ID use karein):*\n\n"
        for c in categories:
            text += f"📁 *{c}*\n"
            entries = db.get_directory_entries(c)
            for e in entries:
                text += f"  • ID: `{e['entry_id']}` — {e['title']}\n"
        text += "\n🗑 *Delete Command:* `/removedirectory <ID>`\nExample: `/removedirectory 1`"
        
        await update.effective_message.reply_text(text, parse_mode="Markdown")
        return

    entry_id = int(context.args[0])
    db.deactivate_directory_entry(entry_id)
    await update.effective_message.reply_text(f"✅ Directory entry #{entry_id} hata di gayi hai.")
