"""
utils/permissions.py
Handles owner and admin checks.
"""
import config

def is_owner(user_id):
    # Check karta hai ki user pehla owner hai ya dusra owner
    main_owner = user_id == config.OWNER_ID
    # getattr use kar rahe hain taaki agar config me SECOND_OWNER_ID na ho to bot crash na ho
    second_owner = user_id == getattr(config, "SECOND_OWNER_ID", 0)
    
    return main_owner or second_owner

def is_admin(user_id):
    # Agar wo owner hai, ya phir extra admins ki list me hai, to wo admin hai
    return is_owner(user_id) or user_id in config.EXTRA_ADMIN_IDS

async def require_owner(update):
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("⛔ Sirf Owner hi ye command use kar sakta hai.")
        return False
    return True

async def require_admin(update):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Sirf Admin hi ye command use kar sakta hai.")
        return False
    return True
