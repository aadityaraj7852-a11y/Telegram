"""
utils/reactions.py
Reactions Bot ka shared helper — jahan bhi bot khud koi message bhejta
hai (quiz result, note, ad, boost post), is function ko call karke us
par auto-react karaya ja sakta hai. Alag file me rakha hai taaki
quiz_engine.py aur admin_handlers.py dono ise import kar sakein bina
ek-doosre pe circular dependency ke.

Sirf bot ke apne messages par react karta hai — kisi doosre user/
channel ke message par nahi. Ye is liye safe hai kyunki ye Telegram
Bot API ka normal `setMessageReaction` call hai, koi userbot/scraping
nahi.
"""

import random

import database as db


async def auto_react(context, chat_id, message_id):
    """Fail-safe: reaction ek bonus feature hai — kabhi bhi is function
    ka error asli message delivery ko affect nahi karna chahiye."""
    if not db.is_reactions_enabled(chat_id):
        return
    try:
        emojis = db.get_reaction_emojis(chat_id)
        chosen = random.choice(emojis)
        await context.bot.set_message_reaction(
            chat_id=chat_id, message_id=message_id,
            reaction=[{"type": "emoji", "emoji": chosen}]
        )
    except Exception:
        pass
