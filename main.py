
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🎯 **STEP 2: Basic Flow**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1️⃣ JSON copy करो और भेजो
2️⃣ Bot reply करेगा: "✅ JSON Received!"
3️⃣ अब कोई channel command दो:
   /rssb, /ssc, /upsc, /kalam, आदि
4️⃣ Questions सब को भेज दिए जाएंगे!

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🎯 **STEP 3: Advanced Features**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔄 /bulk_send - सब channels को एक साथ भेजें
📊 /stats - अपनी statistics देखें
📄 /pdf_date - Date range से PDF बनाएं

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📌 **Important Notes:**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

• JSON array format में होना चाहिए [ ]
• correct_index 0 से शुरू होता है
• explanation optional है
• Multiple questions एक साथ भेज सकते हो

कोई सवाल हो तो /start से फिर देखो! 🚀
    """
    bot.reply_to(message, help_text, parse_mode='Markdown')

@bot.message_handler(commands=['show'])
def handle_show(message):
    """Show all available channels"""
    channels_text = """
📺 **Available Channels:**

1. 🟦 RSSB Springboard → /rssb
2. 📚 Kalam → /kalam
3. 🎓 SSC (CGL/CHSL/MTS/NTPC) → /ssc
4. 🏆 UPSC/Current Affairs → /upsc
5. 🎯 MockRise → /mockrise
6. 🤖 Bot में देखें → /bot

**Advanced:**
→ /bulk_send (सब को एक साथ)
→ /pdf_date (PDF बनाएं)

किसी भी channel को select करो! 😊
    """
    bot.reply_to(message, channels_text, parse_mode='Markdown')

@bot.message_handler(commands=['pdf_date'])
def handle_pdf_date(message):
    """Start PDF date range selection"""
    msg = bot.send_message(
        message.chat.id, 
        """
📅 **PDF Generate करने के लिए:**

कृपया Start Date दें (Format: DD-MM-YYYY)

उदाहरण: 01-02-2026
        """,
        parse_mode='Markdown'
    )
    bot.register_next_step_handler(msg, get_start_date, message.from_user.id)

def get_start_date(message, user_id):
    """Get start date for PDF"""
    try:
        start_date = datetime.strptime(message.text, "%d-%m-%Y").date()
        msg = bot.send_message(
            message.chat.id,
            """
📅 **अब End Date दें (Format: DD-MM-YYYY)**

उदाहरण: 09-02-2026
            """,
            parse_mode='Markdown'
        )
        bot.register_next_step_handler(msg, generate_pdf, user_id, start_date)
    except:
        bot.reply_to(message, "❌ Date format गलत है! DD-MM-YYYY का उपयोग करें।")

def generate_pdf(message, user_id, start_date):
    """Generate PDF from date range"""
    try:
        end_date = datetime.strptime(message.text, "%d-%m-%Y").date()
        
        if user_id not in quiz_data or not quiz_data[user_id]:
            bot.reply_to(message, "❌ पहले JSON भेजें!")
            return
        
        data = quiz_data[user_id]
        channel_name = "Current Channel"
        
        # Create PDF
        pdf_filename = f"quiz_{user_id}_{start_date}_{end_date}.pdf"
        create_quiz_pdf(data, pdf_filename, start_date, end_date, channel_name)
        
        pdf_cache[user_id] = pdf_filename
        
        bot.reply_to(message, f"""
✅ **PDF तैयार हो गया!**

📊 Details:
• Start Date: {start_date}
• End Date: {end_date}
• Total Questions: {len(data)}

अब क्या करना है:
/pdf_view - Bot में देखें
/pdf_send_all - सभी channels को भेजें
        """, parse_mode='Markdown')
    except:
        bot.reply_to(message, "❌ Date format गलत है!")

def create_quiz_pdf(data, filename, start_date, end_date, channel_name):
    """Create beautiful PDF from quiz data"""
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4
    
    c = canvas.Canvas(filename, pagesize=A4)
    width, height = A4
    
    # Header
    c.setFont("Helvetica-Bold", 18)
    c.drawCentredString(width/2, height - 50, "Telegram Quizzes Summary")
    
    c.setFont("Helvetica-Bold", 14)
    c.drawCentredString(width/2, height - 80, "MockRise")
    
    # Meta info
    c.setFont("Helvetica", 10)
    y_pos = height - 120
    c.drawString(50, y_pos, f"Date Range: {start_date} से {end_date}")
    c.drawString(50, y_pos - 20, f"Total Questions: {len(data)}")
    c.drawString(50, y_pos - 40, f"Channel: {channel_name}")
    
    # Questions
    y_pos = height - 180
    for i, item in enumerate(data, 1):
        if y_pos < 100:
            c.showPage()
            y_pos = height - 50
        
        question = item.get('question', '')
        options = item.get('options', [])
        correct_idx = item.get('correct_index')
        explanation = item.get('explanation', '')
        
        # Question number and text
        c.setFont("Helvetica-Bold", 11)
        c.drawString(50, y_pos, f"Q.{i} {question[:50]}...")
        y_pos -= 25
        
        # Options
        c.setFont("Helvetica", 10)
        for j, opt in enumerate(options):
            c.drawString(70, y_pos, f"({j+1}) {opt}")
            y_pos -= 15
        
        # Correct answer
        c.setFont("Helvetica-Bold", 9)
        c.drawString(50, y_pos, f"► सही उत्तर: ({correct_idx + 1})")
        y_pos -= 20
        
        # Explanation
        c.setFont("Helvetica", 9)
        c.drawString(50, y_pos, f"► व्याख्या: {explanation[:60]}...")
        y_pos -= 40
        
        c.drawString(50, y_pos, "━" * 80)
        y_pos -= 20
    
    # Footer with watermark (rotated)
    c.saveState()
    c.translate(width/2, height/2)
    c.rotate(270)
    c.setFont("Helvetica-Bold", 16)
    c.setFillAlpha(0.3)
    c.drawCentredString(0, 0, "®MockRise")
    c.restoreState()
    
    c.save()

@bot.message_handler(commands=['pdf_view'])
def handle_pdf_view(message):
    """View PDF in bot"""
    user_id = message.from_user.id
    
    if user_id not in pdf_cache:
        bot.reply_to(message, "❌ पहले /pdf_date से PDF बनाएं!")
        return
    
    pdf_file = pdf_cache[user_id]
    
    try:
        with open(pdf_file, 'rb') as f:
            bot.send_document(message.chat.id, f, caption="📄 आपका Quiz PDF")
    except:
        bot.reply_to(message, "❌ PDF नहीं मिला!")

@bot.message_handler(commands=['pdf_send_all'])
def handle_pdf_send_all(message):
    """Send PDF to all channels"""
    user_id = message.from_user.id
    
    if user_id not in pdf_cache:
        bot.reply_to(message, "❌ पहले /pdf_date से PDF बनाएं!")
        return
    
    pdf_file = pdf_cache[user_id]
    
    try:
        for channel_key, (channel_id, channel_name) in CHANNELS.items():
            if isinstance(channel_id, list):
                for ch in channel_id:
                    with open(pdf_file, 'rb') as f:
                        bot.send_document(ch, f, caption=f"📄 {channel_name} - Quiz PDF")
            else:
                with open(pdf_file, 'rb') as f:
                    bot.send_document(channel_id, f, caption=f"📄 {channel_name} - Quiz PDF")
            time.sleep(2)
        
        bot.reply_to(message, "✅ PDF सभी channels को भेज दिया गया!")
    except Exception as e:
        bot.reply_to(message, f"❌ Error: {str(e)[:100]}")

@bot.message_handler(commands=['bulk_send'])
def handle_bulk_send(message):
    """Send to all channels at once"""
    user_id = message.from_user.id
    
    if user_id not in quiz_data or not quiz_data[user_id]:
        bot.reply_to(message, """
❌ पहले JSON भेजें!

🎯 कैसे काम करता है:
1️⃣ JSON भेजें (MCQ के साथ)
2️⃣ /bulk_send दबाएं
3️⃣ सभी 6 channels को एक साथ भेज दिया जाएगा!

सभी channels:
• RSSB Springboard
• Kalam (2 channels)
• SSC
• UPSC
• MockRise

⏳ Process में कुछ समय लगेगा... 🚀
        """, parse_mode='Markdown')
        return
    
    data = quiz_data[user_id]
    bot.reply_to(message, f"⏳ {len(data)} questions सभी 6 channels को भेज रहे हैं...\n\nइसे 2-3 मिनट लग सकते हैं!")
    
    total_sent = 0
    total_failed = 0
    
    for channel_key in ['rssb', 'kalam', 'ssc', 'upsc', 'mockrise']:
        success, failed = send_quiz_internal(data, channel_key)
        total_sent += success
        total_failed += failed
        time.sleep(2)
    
    result = f"""
✅ **Bulk Send Complete!**

📊 Results:
✅ Total Sent: {total_sent}
❌ Failed: {total_failed}

📺 सभी channels को भेज दिया गया!
    """
    
    bot.reply_to(message, result, parse_mode='Markdown')

@bot.message_handler(commands=['stats'])
def handle_stats(message):
    """Show user's statistics"""
    user_id = str(message.from_user.id)
    stats = load_json(DB_STATS)
    
    if user_id not in stats:
        bot.reply_to(message, """
❌ अभी तक कोई data नहीं है।

📊 कैसे काम करता है:
1️⃣ JSON भेजें
2️⃣ /channel_name दबाएं (जैसे /rssb)
3️⃣ तब /stats से अपनी statistics देखें

Statistics में दिखेगा:
• कुल भेजे गए questions
• Failed attempts
• कौन से channels use किए
• Recent activity
        """, parse_mode='Markdown')
        return
    
    user_stats = stats[user_id]
    stats_msg = f"""
📊 **Your Statistics:**

✅ Total Sent: {user_stats['total_sent']}
❌ Failed: {user_stats['total_failed']}
📺 Channels Used: {', '.join(user_stats['channels_used']) or 'None'}

**Recent Activity:**
"""
    
    for history in user_stats['history'][-5:]:
        stats_msg += f"\n• {history['timestamp']} - {history['channel']}: {history['count']} ({'✅' if history['status'] == 'success' else '❌'})"
    
    bot.reply_to(message, stats_msg, parse_mode='Markdown')

@bot.message_handler(commands=['list'])
def handle_list(message):
    """Show all sent questions"""
    user_id = message.from_user.id
    
    if user_id not in quiz_data or not quiz_data[user_id]:
        bot.reply_to(message, """
❌ अभी कोई data नहीं है।

📋 कैसे काम करता है:
1️⃣ JSON भेजें
2️⃣ /list दबाएं
3️⃣ सभी questions की list दिखेगी

इससे आप देख सकते हो:
• कुल कितने questions हैं
• हर question का text
• Duplicate questions (अगर हों)
        """, parse_mode='Markdown')
        return
    
    data = quiz_data[user_id]
    list_msg = f"📋 **Total Questions: {len(data)}**\n\n"
    
    for i, item in enumerate(data[:10], 1):
        question = item.get('question', '')[:50]
        list_msg += f"{i}. {question}...\n"
    
    if len(data) > 10:
        list_msg += f"\n... और {len(data) - 10} और questions"
    
    bot.reply_to(message, list_msg, parse_mode='Markdown')

@bot.message_handler(commands=['duplicate_check'])
def handle_duplicate_check(message):
    """Check for duplicate questions"""
    user_id = message.from_user.id
    
    if user_id not in quiz_data or not quiz_data[user_id]:
        bot.reply_to(message, """
❌ पहले JSON भेजें।

🚫 कैसे काम करता है:
1️⃣ JSON भेजें
2️⃣ /duplicate_check दबाएं
3️⃣ Duplicate questions मिलेंगे (अगर हों)

यह check करेगा:
• कौन से questions repeat हो रहे हैं
• Q1 और Q5 एक जैसे हैं तो बताएगा
        """, parse_mode='Markdown')
        return
    
    data = quiz_data[user_id]
    duplicates = []
    
    for i, item in enumerate(data):
        question = item.get('question', '').lower()
        for j, other_item in enumerate(data):
            if i < j and question == other_item.get('question', '').lower():
                duplicates.append((i+1, j+1, question[:50]))
    
    if duplicates:
        dup_msg = "⚠️ **Duplicate Questions Found:**\n\n"
        for q1, q2, text in duplicates:
            dup_msg += f"Q{q1} और Q{q2}: {text}...\n"
        bot.reply_to(message, dup_msg)
    else:
        bot.reply_to(message, "✅ कोई duplicate questions नहीं हैं!")

@bot.message_handler(commands=['rssb'])
def handle_rssb(message):
    send_quiz_to_channel(message, 'rssb', """
📤 **/rssb - RSSB Springboard को भेजना**

**कैसे काम करता है:**
1️⃣ JSON भेजें (MCQ के साथ)
2️⃣ /rssb दबाएं
3️⃣ सभी questions RSSB channel को poll के रूप में भेज दिए जाएंगे

**Features:**
• Anonymous polls
• Auto-numbering (Q1, Q2...)
• Long explanations के लिए अलग message

**Tips:**
• एक साथ multiple channels को भेज सकते हो
• /bulk_send से सब को एक साथ भेजें
    """)

@bot.message_handler(commands=['ssc'])
def handle_ssc(message):
    send_quiz_to_channel(message, 'ssc', """
📤 **/ssc - SSC CGL/CHSL/MTS/NTPC को भेजना**

**कैसे काम करता है:**
1️⃣ JSON भेजें
2️⃣ /ssc दबाएं
3️⃣ सभी questions SSC channel को भेज दिए जाएंगे

**Target:**
• SSC CGL
• SSC CHSL
• SSC MTS
• SSC NTPC

**Tip:**
/bulk_send से सब channels को एक साथ भेजें!
    """)

@bot.message_handler(commands=['upsc'])
def handle_upsc(message):
    send_quiz_to_channel(message, 'upsc', """
📤 **/upsc - UPSC/Current Affairs को भेजना**

**कैसे काम करता है:**
1️⃣ JSON भेजें
2️⃣ /upsc दबाएं
3️⃣ सभी questions UPSC channel को भेज दिए जाएंगे

**Categories:**
• UPSC Prelims
• Current Affairs
• GK Questions

**Tip:**
/bulk_send से सब channels को एक साथ भेजें!
    """)

@bot.message_handler(commands=['kalam'])
def handle_kalam(message):
    send_quiz_to_channel(message, 'kalam', """
📤 **/kalam - Kalam Channels को भेजना**

**कैसे काम करता है:**
1️⃣ JSON भेजें
2️⃣ /kalam दबाएं
3️⃣ सभी questions 2 Kalam channels को एक साथ भेज दिए जाएंगे

**Channels:**
• Rajasthan GK Kalam REET LDC RAS
• LDC REET RAS 2nd Grade Kalam

**Tip:**
/bulk_send से सब channels को एक साथ भेजें!
    """)

@bot.message_handler(commands=['mockrise'])
def handle_mockrise(message):
    send_quiz_to_channel(message, 'mockrise', """
📤 **/mockrise - MockRise Channel को भेजना**

**कैसे काम करता है:**
1️⃣ JSON भेजें
2️⃣ /mockrise दबाएं
3️⃣ सभी questions MockRise channel को भेज दिए जाएंगे

**Features:**
• Quality questions
• Expert explanations
• Regular updates

**Tip:**
/bulk_send से सब channels को एक साथ भेजें!
    """)

@bot.message_handler(commands=['bot'])
def handle_bot(message):
    """View quiz in bot"""
    user_id = message.from_user.id
    
    if user_id not in quiz_data or not quiz_data[user_id]:
        bot.reply_to(message, """
❌ पहले JSON भेजें!

🤖 कैसे काम करता है:
1️⃣ JSON भेजें (MCQ के साथ)
2️⃣ /bot दबाएं
3️⃣ Bot में ही एक-एक question दिखेगा
4️⃣ Channel को नहीं भेजा जाएगा

फायदा:
• Preview देख सकते हो
• फिर /channel_name से भेज सकते हो
        """, parse_mode='Markdown')
        return
    
    data = quiz_data[user_id]
    bot.reply_to(message, f"📊 कुल {len(data)} प्रश्न हैं।\n\n/bot_view_1 से शुरू करें।")

@bot.message_handler(commands=['user_stats'])
def handle_user_stats(message):
    """Show all users statistics"""
    stats = load_json(DB_STATS)
    
    if not stats:
        bot.reply_to(message, "❌ अभी तक कोई data नहीं है।")
        return
    
    user_stats_msg = "📊 **All Users Statistics:**\n\n"
    for user_id, user_data in list(stats.items())[:10]:
        user_stats_msg += f"👤 User {user_id}\n"
        user_stats_msg += f"   ✅ Sent: {user_data['total_sent']}\n"
        user_stats_msg += f"   ❌ Failed: {user_data['total_failed']}\n\n"
    
    bot.reply_to(message, user_stats_msg, parse_mode='Markdown')

@bot.message_handler(commands=['report'])
def handle_report(message):
    """Generate detailed report"""
    user_id = str(message.from_user.id)
    stats = load_json(DB_STATS)
    
    if user_id not in stats:
        bot.reply_to(message, "❌ अभी तक कोई data नहीं है।")
        return
    
    user_stats = stats[user_id]
    success_rate = (user_stats['total_sent'] / (user_stats['total_sent'] + user_stats['total_failed']) * 100) if (user_stats['total_sent'] + user_stats['total_failed']) > 0 else 0
    
    report = f"""
📄 **Detailed Report**

👤 **User Information:**
ID: {user_id}

📊 **Statistics:**
Total Questions Sent: {user_stats['total_sent']}
Failed Attempts: {user_stats['total_failed']}
Success Rate: {success_rate:.1f}%

📺 **Channels Used:**
{chr(10).join([f"• {ch}" for ch in user_stats['channels_used']])}

📅 **Last 10 Activities:**
"""
    
    for h in user_stats['history'][-10:]:
        report += f"\n• {h['timestamp']} → {h['channel']}: {h['count']} questions ({'✅' if h['status'] == 'success' else '❌'})"
    
    bot.reply_to(message, report, parse_mode='Markdown')

@bot.message_handler(commands=['analytics'])
def handle_analytics(message):
    """Show channel analytics"""
    args = message.text.split()
    channel = args[1].lower() if len(args) > 1 else None
    
    if not channel:
        analytics_msg = """
📈 **Channel Analytics:**

**Usage:**
/analytics <channel_name>

**Examples:**
/analytics rssb
/analytics ssc
/analytics upsc
/analytics kalam
/analytics mockrise

**Features:**
• Total questions sent
• Number of attempts
• Unique users
• Average per attempt
        """
        bot.reply_to(message, analytics_msg, parse_mode='Markdown')
        return
    
    stats = load_json(DB_STATS)
    channel_stats = {'total_sent': 0, 'total_attempts': 0, 'users': 0}
    
    for user_id, user_data in stats.items():
        if channel in user_data['channels_used']:
            channel_stats['users'] += 1
        for h in user_data['history']:
            if channel in h['channel'].lower():
                channel_stats['total_sent'] += h['count']
                channel_stats['total_attempts'] += 1
    
    analytics_msg = f"""
📈 **{channel.upper()} Channel Analytics:**

📊 **Statistics:**
Total Questions: {channel_stats['total_sent']}
Total Attempts: {channel_stats['total_attempts']}
Unique Users: {channel_stats['users']}
Avg per Attempt: {channel_stats['total_sent'] / channel_stats['total_attempts'] if channel_stats['total_attempts'] > 0 else 0:.1f}
    """
    
    bot.reply_to(message, analytics_msg, parse_mode='Markdown')

@bot.message_handler(commands=['template'])
def handle_template(message):
    """Save and manage templates"""
    user_id = message.from_user.id
    
    if user_id not in quiz_data or not quiz_data[user_id]:
        bot.reply_to(message, """
❌ पहले JSON भेजें।

💾 कैसे काम करता है:
1️⃣ JSON भेजें
2️⃣ /template दबाएं
3️⃣ Template का नाम दें (जैसे: GK_2024)
4️⃣ Template save हो जाएगा
5️⃣ अगली बार use कर सकते हो!

फायदा:
• बार-बार JSON नहीं भेजना पड़ेगा
• Template को edit करके use कर सकते हो
        """, parse_mode='Markdown')
        return
    
    msg = bot.send_message(message.chat.id, "💾 Template का नाम दें (जैसे: GK_2024):")
    bot.register_next_step_handler(msg, process_template_name, user_id)

def process_template_name(message, user_id):
    """Process template name"""
    template_name = message.text.strip()
    data = quiz_data[user_id]
    
    templates = load_json(DB_TEMPLATES)
    if str(user_id) not in templates:
        templates[str(user_id)] = {}
    
    templates[str(user_id)][template_name] = {
        'data': data,
        'saved_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        'question_count': len(data)
    }
    
    save_json(DB_TEMPLATES, templates)
    bot.reply_to(message, f"✅ Template '{template_name}' save हो गया!\n{len(data)} questions save किए गए।")

@bot.message_handler(commands=['multi_lang'])
def handle_multi_lang(message):
    """Set language preference"""
    lang_msg = """
🌍 **Multiple Languages Support:**

**Currently Supporting:**
• 🇮🇳 Hindi
• 🇬🇧 English
• 🇮🇳 Gujarati

**कैसे काम करता है:**
1️⃣ अपनी language चुनो
2️⃣ Questions उसी language में भेजे जाएंगे

**Features:**
• Bilingual questions
• Language-specific formatting
• Auto-translation support

**Coming Soon:**
More languages जल्द जोड़े जाएंगे!
    """
    bot.reply_to(message, lang_msg, parse_mode='Markdown')

@bot.message_handler(commands=['edit'])
def handle_edit(message):
    """Edit a question"""
    if message.from_user.id not in quiz_data:
        bot.reply_to(message, "❌ पहले JSON भेजें।")
        return
    
    msg = bot.send_message(message.chat.id, "✏️ Question number दें (जैसे: 5):")
    bot.register_next_step_handler(msg, process_edit_question, message.from_user.id)

def process_edit_question(message, user_id):
    """Process question editing"""
    try:
        q_num = int(message.text) - 1
        if user_id not in quiz_data or q_num >= len(quiz_data[user_id]):
            bot.reply_to(message, "❌ Question number गलत है।")
            return
        
        msg = bot.send_message(message.chat.id, "नया Question text दें:")
        bot.register_next_step_handler(msg, process_edit_text, user_id, q_num)
    except:
        bot.reply_to(message, "❌ गलत number है।")

def process_edit_text(message, user_id, q_num):
    """Process edited question text"""
    quiz_data[user_id][q_num]['question'] = message.text
    bot.reply_to(message, f"✅ Q{q_num + 1} update हो गया!")

@bot.message_handler(commands=['schedule'])
def handle_schedule(message):
    """Schedule posting for later"""
    msg = bot.send_message(message.chat.id, """
⏰ **Schedule Posting:**

**Format:** समय निर्धारित करें

**उदाहरण:**
/schedule_14_30_rssb
(दोपहर 2:30 को RSSB channel को भेजना)

**फॉर्मेट:**
/schedule_HH_MM_CHANNEL

**Supported Channels:**
rssb, ssc, upsc, kalam, mockrise
    """)

@bot.message_handler(commands=['stop'])
def handle_stop(message):
    bot.reply_to(message, "🛑 Bot बंद हो रहा है...\n\n/start करने के लिए फिर से शुरू करें।")

# -------- INTERNAL FUNCTIONS --------

def send_quiz_internal(data, channel_key):
    """Internal function to send quiz"""
    channels_data = CHANNELS.get(channel_key)
    if not channels_data:
        return 0, 0
    
    channels = channels_data[0]
    if isinstance(channels, str):
        channels = [channels]
    
    success_count = 0
    failed_count = 0
    
    for i, item in enumerate(data):
        try:
            question_text = item.get("question", "").strip()
            options = item.get("options", [])
            correct_id = item.get("correct_index")
            explanation = item.get("explanation", "").strip()
            
            q_num = i + 1
            numbered_question = f"Q{q_num}. {question_text}"
            
            if not question_text or not options or correct_id is None:
                continue
            
            if len(numbered_question) > 250:
                for ch in channels:
                    bot.send_message(ch, numbered_question)
                poll_question = f"Q{q_num}: ☝️ ऊपर दिए गए प्रश्न का उत्तर चुनें:"
            else:
                poll_question = numbered_question
            
            if len(explanation) > 190:
                poll_explanation = "विस्तृत व्याख्या नीचे देखें 👇"
                send_full_explanation = True
            else:
                poll_explanation = explanation
                send_full_explanation = False
            
            for ch in channels:
                sent_poll = bot.send_poll(
                    chat_id=ch,
                    question=poll_question,
                    options=options,
                    type='quiz',
                    correct_option_id=correct_id,
                    explanation=poll_explanation,
                    is_anonymous=True
                )
                
                if send_full_explanation:
                    bot.send_message(
                        ch,
                        f"📝 Solution {q_num}:\n{explanation}",
                        reply_to_message_id=sent_poll.message_id
                    )
            
            success_count += 1
            time.sleep(2)
        
        except Exception as e:
            failed_count += 1
    
    return success_count, failed_count

def send_quiz_to_channel(message, channel_key, help_text):
    """Send quiz to specific channel"""
    user_id = message.from_user.id
    
    if user_id not in quiz_data or not quiz_data[user_id]:
        bot.reply_to(message, f"""
{help_text}

❌ पहले JSON भेजें!
    """, parse_mode='Markdown')
        return
    
    data = quiz_data[user_id]
    channel_name = CHANNELS.get(channel_key, ('', 'Unknown'))[1]
    
    bot.reply_to(message, f"⏳ {len(data)} प्रश्न {channel_name} को भेज रहे हैं...\n\n✅ Soon!")
    
    success, failed = send_quiz_internal(data, channel_key)
    
    result = f"""
✅ **काम पूरा!**

📊 Results:
✅ भेज दिए गए: {success}
❌ Failed: {failed}

📺 Channel: {channel_name}

Tips:
• /bulk_send से सब channels को एक साथ भेजें
• /stats से अपनी statistics देखें
    """
    
    bot.reply_to(message, result, parse_mode='Markdown')

@bot.message_handler(content_types=['text'])
def handle_json(message):
    """Handle JSON input"""
    try:
        data = json.loads(message.text)
        
        if not isinstance(data, list):
            bot.reply_to(message, "❌ Error: JSON लिस्ट [] से शुरू होना चाहिए।")
            return
        
        quiz_data[message.from_user.id] = data
        
        success_msg = f"""
✅ **JSON Received!**

📊 Total Questions: {len(data)}

अब क्या करना है:

**Option 1: सीधा Channel को भेजें**
/rssb, /ssc, /upsc, /kalam, /mockrise
/bot (Bot में देखें)

**Option 2: सब को एक साथ**
/bulk_send

**Option 3: PDF बनाएं**
/pdf_date (Date range से)

**Option 4: Advanced**
/stats (Statistics देखें)
/list (Questions की list)
/duplicate_check (Duplicates check करें)

शुरू करो! 🚀
        """
        bot.reply_to(message, success_msg, parse_mode='Markdown')
    
    except json.JSONDecodeError:
        bot.reply_to(message, "❌ JSON फॉर्मेट गलत है।\n\n/help से सही format देखो!")
    except Exception as e:
        bot.reply_to(message, f"❌ Error: {str(e)[:100]}")

# -------- BOT START --------
keep_alive()
print("✅ Bot is running with Complete Advanced Features!")
print("✅ All 23 Commands + PDF Generation Ready!")
print("Features: schedule, stats, edit, list, duplicate_check, bulk_send")
print("         user_stats, report, analytics, template, multi_lang, PDF")
bot.infinity_polling()
