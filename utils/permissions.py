import database as db
import config


def is_owner(user_id):
    return user_id == config.OWNER_ID


def is_admin(user_id):
    return db.is_admin(user_id, config.OWNER_ID)


async def require_admin(update):
    """Returns True if user is admin, else sends a denial message and returns False."""
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.effective_message.reply_text(
            "⛔ Ye command sirf admin/owner use kar sakte hain.")
        return False
    return True


async def require_owner(update):
    user_id = update.effective_user.id
    if not is_owner(user_id):
        await update.effective_message.reply_text(
            "⛔ Ye command sirf bot owner use kar sakta hai.")
        return False
    return True
