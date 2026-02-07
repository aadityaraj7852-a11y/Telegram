from telethon import TelegramClient, events
import asyncio

# --- आपके क्रेडेंशियल्स ---
api_id = 22921981
api_hash = '9af5a5e1f22e2c5b82f66083e70ec9db'
bot_token = '7654075050:AAFt3hMFSYcoHPRcrNUfGGVpy859hjKotok'

# क्लाइंट को 'Bot' और 'User' दोनों मोड में सेटअप करना
client = TelegramClient('forwarder_session', api_id, api_hash)

# सेटिंग्स स्टोर करने के लिए
config = {
    "source": None,
    "target": None,
    "filters": [],
    "active": False
}

async def main():
    # बॉट और यूजर सेशन शुरू करना
    await client.start(bot_token=bot_token)
    print("बॉट सफलतापूर्वक शुरू हो गया है! टेलीग्राम पर कमांड्स का उपयोग करें।")

    # --- कमांड्स हैंडलर्स ---

    @client.on(events.NewMessage(pattern='/start'))
    async def start(event):
        await event.respond(
            "🚀 **Forwarder Control Bot**\n\n"
            "1️⃣ `/source @username` - सोर्स चैनल सेट करें\n"
            "2️⃣ `/target @username` - टारगेट ग्रुप सेट करें\n"
            "3️⃣ `/filter शब्द` - जो शब्द नहीं भेजने उन्हें जोड़ें\n"
            "4️⃣ `/config` - वर्तमान सेटिंग्स देखें\n"
            "5️⃣ `/finish` - फॉरवर्डिंग शुरू करें\n"
            "6️⃣ `/stop` - फॉरवर्डिंग रोकें\n"
            "7️⃣ `/logout` - सेशन खत्म करें"
        )

    @client.on(events.NewMessage(pattern='/source (.*)'))
    async def set_source(event):
        source = event.pattern_match.group(1).strip()
        config["source"] = source
        await event.respond(f"✅ **Source सेट:** {source}")

    @client.on(events.NewMessage(pattern='/target (.*)'))
    async def set_target(event):
        target = event.pattern_match.group(1).strip()
        config["target"] = target
        await event.respond(f"✅ **Target सेट:** {target}")

    @client.on(events.NewMessage(pattern='/filter (.*)'))
    async def add_filter(event):
        word = event.pattern_match.group(1).strip().lower()
        config["filters"].append(word)
        await event.respond(f"➕ **Filter जोड़ा गया:** {word}")

    @client.on(events.NewMessage(pattern='/config'))
    async def show_config(event):
        status = "▶️ चलू है" if config["active"] else "⏸ बंद है"
        msg = (f"⚙️ **वर्तमान सेटिंग्स:**\n"
               f"• स्थिति: {status}\n"
               f"• Source: `{config['source']}`\n"
               f"• Target: `{config['target']}`\n"
               f"• Filters: `{', '.join(config['filters']) if config['filters'] else 'None'}`")
        await event.respond(msg)

    @client.on(events.NewMessage(pattern='/finish'))
    async def finish(event):
        if not config["source"] or not config["target"]:
            await event.respond("❌ कृपया पहले `/source` और `/target` सेट करें!")
            return
        config["active"] = True
        await event.respond("🚀 **फॉरवर्डिंग सेवा शुरू कर दी गई है!**")

    @client.on(events.NewMessage(pattern='/stop'))
    async def stop(event):
        config["active"] = False
        await event.respond("🛑 **फॉरवर्डिंग सेवा रोक दी गई है।**")

    @client.on(events.NewMessage(pattern='/logout'))
    async def logout(event):
        await event.respond("👋 लॉगआउट हो रहा है... सेशन फाइल डिलीट हो जाएगी।")
        await client.log_out()

    # --- मुख्य फॉरवर्डिंग लॉजिक (User Account के जरिए) ---
    @client.on(events.NewMessage)
    async def forwarder_logic(event):
        if not config["active"] or not config["source"] or not config["target"]:
            return

        try:
            # चेक करें कि क्या मैसेज सोर्स से आया है
            source_entity = await client.get_entity(config["source"])
            if event.chat_id == source_entity.id:
                text = event.message.message or ""
                
                # फिल्टर चेक
                for word in config["filters"]:
                    if word in text.lower():
                        print(f"Filter hit: {word}")
                        return

                # मैसेज फॉरवर्ड करना
                await client.forward_messages(config["target"], event.message)
        except Exception as e:
            print(f"Forwarding Error: {e}")

    await client.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())
