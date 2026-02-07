from flask import Flask
import threading
from telethon import TelegramClient, events
import asyncio
import os

# --- Render के लिए Fake Web Server ---
app = Flask('')

@app.route('/')
def home():
    return "Bot is running 24/7!"

def run():
    # Render डिफ़ॉल्ट रूप से पोर्ट 10000 का उपयोग करता है
    app.run(host='0.0.0.0', port=10000)

def keep_alive():
    t = threading.Thread(target=run)
    t.daemon = True
    t.start()

# --- आपके टेलीग्राम क्रेडेंशियल्स ---
api_id = 22921981
api_hash = '9af5a5e1f22e2c5b82f66083e70ec9db'
bot_token = '7654075050:AAFt3hMFSYcoHPRcrNUfGGVpy859hjKotok'

# क्लाइंट सेटअप
client = TelegramClient('forwarder_session', api_id, api_hash)

# सेटिंग्स स्टोर करने के लिए
config = {
    "source": None,
    "target": None,
    "filters": [],
    "active": False
}

async def bot_logic():
    # बॉट लॉगिन
    await client.start(bot_token=bot_token)
    print("बॉट सफलतापूर्वक लॉगिन हो गया है!")

    # --- कमांड्स ---

    @client.on(events.NewMessage(pattern='/start'))
    async def start(event):
        await event.respond(
            "🚀 **Forwarder Control Bot**\n\n"
            "1️⃣ `/source @username` - सोर्स चैनल\n"
            "2️⃣ `/target @username` - टारगेट ग्रुप\n"
            "3️⃣ `/filter शब्द` - शब्द रोकें\n"
            "4️⃣ `/config` - सेटिंग्स देखें\n"
            "5️⃣ `/finish` - शुरू करें\n"
            "6️⃣ `/stop` - रोकें"
        )

    @client.on(events.NewMessage(pattern='/source (.*)'))
    async def set_source(event):
        config["source"] = event.pattern_match.group(1).strip()
        await event.respond(f"✅ Source सेट: {config['source']}")

    @client.on(events.NewMessage(pattern='/target (.*)'))
    async def set_target(event):
        config["target"] = event.pattern_match.group(1).strip()
        await event.respond(f"✅ Target सेट: {config['target']}")

    @client.on(events.NewMessage(pattern='/filter (.*)'))
    async def add_filter(event):
        word = event.pattern_match.group(1).strip().lower()
        config["filters"].append(word)
        await event.respond(f"➕ Filter जोड़ा गया: {word}")

    @client.on(events.NewMessage(pattern='/config'))
    async def show_config(event):
        status = "▶️ Active" if config["active"] else "⏸ Stopped"
        msg = (f"⚙️ **Settings:**\nStatus: {status}\nSource: {config['source']}\nTarget: {config['target']}")
        await event.respond(msg)

    @client.on(events.NewMessage(pattern='/finish'))
    async def finish(event):
        if not config["source"] or not config["target"]:
            await event.respond("❌ पहले source और target सेट करें!")
            return
        config["active"] = True
        await event.respond("🚀 फॉरवर्डिंग शुरू!")

    @client.on(events.NewMessage(pattern='/stop'))
    async def stop(event):
        config["active"] = False
        await event.respond("🛑 फॉरवर्डिंग बंद!")

    # --- फॉरवर्डिंग लॉजिक ---
    @client.on(events.NewMessage)
    async def forwarder_handler(event):
        if not config["active"] or not config["source"]:
            return
        
        try:
            source_entity = await client.get_entity(config["source"])
            if event.chat_id == source_entity.id:
                text = (event.message.message or "").lower()
                for word in config["filters"]:
                    if word in text:
                        return
                await client.forward_messages(config["target"], event.message)
        except Exception as e:
            print(f"Error: {e}")

    await client.run_until_disconnected()

if __name__ == '__main__':
    keep_alive() # Flask सर्वर शुरू करें
    asyncio.run(bot_logic()) # बॉट शुरू करें
