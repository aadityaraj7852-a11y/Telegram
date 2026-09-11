"""
webapp/app.py
Students Lounge — ek WhatsApp-jaisa group discussion chat, Telegram
bot se link hota hai. User bot me /lounge command se ek personal
access-token wala link paata hai, jo ye Flask app khol deta hai.

Simple design (Render free tier ke liye reliable):
- Login: sirf bot-generated token se hota hai (koi password nahi)
- Messages: polling-based (har 2 sec me naye messages fetch)
  websocket ki jagah — Render ke free HTTP worker pe zyada reliable
- Same SQLite database jo bot use karta hai (data/quizbot.db)
- Ek hi default room "Students Lounge" — sab is me chat karte hain

Is app ko alag se run kiya jaata hai (Render pe alag "Web Service"):
gunicorn webapp.app:app  (ya python webapp/app.py for local test)
"""

import os
import sys
import html

# Parent folder ko path me daalo taaki 'database' module mile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, request, jsonify, render_template, abort

import database as db

app = Flask(__name__, template_folder="templates", static_folder="static")


def _get_user_from_token(token):
    if not token:
        return None
    return db.get_chat_app_user_by_token(token)


@app.route("/")
def index():
    return (
        "<h2>Quiz Bot — Students Lounge backend chal raha hai ✅</h2>"
        "<p>Telegram bot me <code>/lounge</code> command se apna personal link lo.</p>"
    )


@app.route("/chat")
def chat_page():
    token = request.args.get("token", "")
    user = _get_user_from_token(token)
    if not user:
        return (
            "<h3>⚠️ Invalid ya expired link</h3>"
            "<p>Telegram bot me <code>/lounge</code> command dobara chalao naya link paane ke liye.</p>"
        ), 403

    if user["is_banned"]:
        return "<h3>⛔ Aapko is lounge se ban kar diya gaya hai.</h3>", 403

    db.touch_chat_app_user(user["user_id"])
    return render_template("chat.html", token=token, display_name=user["display_name"])


@app.route("/api/me")
def api_me():
    token = request.args.get("token", "")
    user = _get_user_from_token(token)
    if not user:
        abort(403)
    return jsonify({
        "user_id": user["user_id"],
        "display_name": user["display_name"],
        "avatar_emoji": user["avatar_emoji"] or "🎓",
    })


@app.route("/api/messages")
def api_messages():
    """Poll-based fetch: ?token=...&after_id=123 (0/absent = last 50)"""
    token = request.args.get("token", "")
    user = _get_user_from_token(token)
    if not user:
        abort(403)

    db.touch_chat_app_user(user["user_id"])
    room_id = db.ensure_default_room()

    after_id = request.args.get("after_id", type=int)
    rows = db.get_recent_messages(room_id, limit=100, after_id=after_id if after_id else None)

    messages = [{
        "id": r["message_id"],
        "user_id": r["user_id"],
        "name": r["display_name"] or "Student",
        "avatar": r["avatar_emoji"] or "🎓",
        "text": r["content"],
        "sent_at": r["sent_at"],
        "is_me": r["user_id"] == user["user_id"],
    } for r in rows]

    return jsonify({"messages": messages, "room": "Students Lounge"})


@app.route("/api/send", methods=["POST"])
def api_send():
    token = request.args.get("token", "") or (request.json or {}).get("token", "")
    user = _get_user_from_token(token)
    if not user:
        abort(403)
    if user["is_banned"]:
        return jsonify({"error": "banned"}), 403

    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"error": "empty"}), 400
    if len(text) > 2000:
        text = text[:2000]

    # Basic sanitization — plain text only, no HTML injection into other
    # users' browsers (frontend also escapes on render, defense in depth)
    text = html.escape(text)

    room_id = db.ensure_default_room()
    msg_id = db.save_chat_message(room_id, user["user_id"], text)
    db.touch_chat_app_user(user["user_id"])

    return jsonify({"ok": True, "message_id": msg_id})


if __name__ == "__main__":
    db.init_db()
    port = int(os.getenv("PORT", os.getenv("WEBAPP_PORT", "8080")))
    app.run(host="0.0.0.0", port=port, debug=False)
