"""
database.py
Saara data SQLite me store hota hai (data/quizbot.db).
Render pe deploy karte time agar disk persistent nahi hai to
backup feature (/backup command) use karke DB file export kar
sakte ho aur restore bhi kar sakte ho.
"""

import sqlite3
import time
import json
import os
from contextlib import contextmanager

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "quizbot.db")


def _connect():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


@contextmanager
def get_conn():
    conn = _connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with get_conn() as conn:
        c = conn.cursor()

        c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            joined_at INTEGER,
            last_seen INTEGER,
            last_online INTEGER,
            coins INTEGER DEFAULT 0,
            total_quizzes INTEGER DEFAULT 0,
            total_correct INTEGER DEFAULT 0,
            total_wrong INTEGER DEFAULT 0,
            total_questions INTEGER DEFAULT 0,
            streak INTEGER DEFAULT 0,
            last_streak_date TEXT,
            is_banned INTEGER DEFAULT 0,
            referred_by INTEGER
        )
        """)

        c.execute("""
        CREATE TABLE IF NOT EXISTS admins (
            user_id INTEGER PRIMARY KEY,
            added_by INTEGER,
            added_at INTEGER
        )
        """)

        c.execute("""
        CREATE TABLE IF NOT EXISTS subjects (
            subject_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE
        )
        """)

        c.execute("""
        CREATE TABLE IF NOT EXISTS chapters (
            chapter_id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject_id INTEGER,
            name TEXT,
            FOREIGN KEY(subject_id) REFERENCES subjects(subject_id)
        )
        """)

        c.execute("""
        CREATE TABLE IF NOT EXISTS questions (
            question_id INTEGER PRIMARY KEY AUTOINCREMENT,
            chapter_id INTEGER,
            question_text TEXT,
            options TEXT,          -- JSON list
            correct_index INTEGER,
            explanation TEXT,
            added_by INTEGER,
            added_at INTEGER,
            FOREIGN KEY(chapter_id) REFERENCES chapters(chapter_id)
        )
        """)

        c.execute("""
        CREATE TABLE IF NOT EXISTS quiz_sessions (
            session_id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            chat_title TEXT,
            subject_id INTEGER,
            chapter_id INTEGER,
            started_by INTEGER,
            started_at INTEGER,
            ended_at INTEGER,
            total_questions INTEGER,
            negative_marking INTEGER DEFAULT 0
        )
        """)

        c.execute("""
        CREATE TABLE IF NOT EXISTS quiz_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER,
            user_id INTEGER,
            correct INTEGER DEFAULT 0,
            wrong INTEGER DEFAULT 0,
            skipped INTEGER DEFAULT 0,
            coins_earned INTEGER DEFAULT 0,
            avg_time REAL DEFAULT 0,
            FOREIGN KEY(session_id) REFERENCES quiz_sessions(session_id)
        )
        """)

        c.execute("""
        CREATE TABLE IF NOT EXISTS answer_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER,
            user_id INTEGER,
            question_id INTEGER,
            selected_index INTEGER,
            is_correct INTEGER,
            answer_time_sec REAL,
            answered_at INTEGER
        )
        """)

        c.execute("""
        CREATE TABLE IF NOT EXISTS withdrawals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            coins INTEGER,
            status TEXT DEFAULT 'pending',
            requested_at INTEGER,
            processed_at INTEGER,
            processed_by INTEGER
        )
        """)

        c.execute("""
        CREATE TABLE IF NOT EXISTS ads (
            ad_id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT,
            button_text TEXT,
            button_url TEXT,
            created_by INTEGER,
            created_at INTEGER,
            sent_count INTEGER DEFAULT 0
        )
        """)

        c.execute("""
        CREATE TABLE IF NOT EXISTS groups (
            chat_id INTEGER PRIMARY KEY,
            title TEXT,
            added_at INTEGER,
            is_active INTEGER DEFAULT 1
        )
        """)

        c.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
        """)

        # Per-group/channel custom settings (admin-configurable) -------------
        c.execute("""
        CREATE TABLE IF NOT EXISTS group_settings (
            chat_id INTEGER PRIMARY KEY,
            coin_per_correct INTEGER,
            negative_marking INTEGER DEFAULT 0,
            negative_amount INTEGER,
            entry_fee INTEGER DEFAULT 0,
            added_by INTEGER,
            added_at INTEGER
        )
        """)

        # Solo / 1v1 practice quizzes (private chat) --------------------------
        c.execute("""
        CREATE TABLE IF NOT EXISTS duels (
            duel_id INTEGER PRIMARY KEY AUTOINCREMENT,
            challenger_id INTEGER,
            opponent_id INTEGER,
            subject_id INTEGER,
            chapter_id INTEGER,
            total_questions INTEGER,
            status TEXT DEFAULT 'pending',   -- pending, active, finished, declined
            created_at INTEGER,
            finished_at INTEGER
        )
        """)

        c.execute("""
        CREATE TABLE IF NOT EXISTS duel_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            duel_id INTEGER,
            user_id INTEGER,
            correct INTEGER DEFAULT 0,
            wrong INTEGER DEFAULT 0,
            FOREIGN KEY(duel_id) REFERENCES duels(duel_id)
        )
        """)

        # Notes: HTML notes bot bhej sake, aur PDF watermark/link-clean log ---
        c.execute("""
        CREATE TABLE IF NOT EXISTS notes (
            note_id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            content_html TEXT,
            created_by INTEGER,
            created_at INTEGER
        )
        """)

        c.execute("""
        CREATE TABLE IF NOT EXISTS pdf_jobs (
            job_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            original_name TEXT,
            action TEXT,          -- 'clean' (watermark+link removal)
            created_at INTEGER
        )
        """)

        # Discussion / community chat app -------------------------------------
        c.execute("""
        CREATE TABLE IF NOT EXISTS chat_app_users (
            user_id INTEGER PRIMARY KEY,
            display_name TEXT,
            avatar_emoji TEXT,
            access_token TEXT UNIQUE,
            created_at INTEGER,
            last_seen INTEGER,
            is_banned INTEGER DEFAULT 0
        )
        """)

        c.execute("""
        CREATE TABLE IF NOT EXISTS chat_app_rooms (
            room_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            description TEXT,
            created_by INTEGER,
            created_at INTEGER,
            is_default INTEGER DEFAULT 0
        )
        """)

        c.execute("""
        CREATE TABLE IF NOT EXISTS chat_app_messages (
            message_id INTEGER PRIMARY KEY AUTOINCREMENT,
            room_id INTEGER,
            user_id INTEGER,
            content TEXT,
            sent_at REAL,
            FOREIGN KEY(room_id) REFERENCES chat_app_rooms(room_id)
        )
        """)

        # Reactions Bot: bot apne khud ke posts (quiz results, notes, ads) par
        # auto-react karta hai. Sirf apne messages par — kisi doosre user/
        # channel ke messages par react karna userbot automation hoga, jo
        # nahi kiya jaata (Telegram policy risk).
        c.execute("""
        CREATE TABLE IF NOT EXISTS reaction_settings (
            chat_id INTEGER PRIMARY KEY,
            enabled INTEGER DEFAULT 0,
            emoji_list TEXT DEFAULT '["🔥","👍","🎉"]',
            updated_by INTEGER,
            updated_at INTEGER
        )
        """)

        # View/Visibility Booster: genuine visibility tools — pin, scheduled
        # re-post, best-time-to-post suggestions. Koi fake view/click nahi
        # banata, sirf asli reach improve karne ke tareeke hai.
        c.execute("""
        CREATE TABLE IF NOT EXISTS boost_jobs (
            job_id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            content TEXT,
            button_text TEXT,
            button_url TEXT,
            repost_every_minutes INTEGER,
            repost_count_done INTEGER DEFAULT 0,
            max_reposts INTEGER,
            pin_on_post INTEGER DEFAULT 0,
            created_by INTEGER,
            created_at INTEGER,
            next_run_at INTEGER,
            is_active INTEGER DEFAULT 1
        )
        """)

        c.execute("""
        CREATE TABLE IF NOT EXISTS post_engagement_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            message_id INTEGER,
            posted_at INTEGER,
            member_count_at_post INTEGER
        )
        """)

        # Group/Channel Directory: admin apne (khud ke maalik/manage kiye
        # hue) groups/channels ko category ke saath list karta hai. Users
        # /discover se apni interest ke hisaab se browse karte hain.
        # Ye kisi doosre ke channels ko scrape/spam NAHI karta — sirf
        # wahi entries hoti hain jo admin khud add kare.
        c.execute("""
        CREATE TABLE IF NOT EXISTS directory_entries (
            entry_id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            description TEXT,
            category TEXT,
            invite_link TEXT,
            added_by INTEGER,
            added_at INTEGER,
            click_count INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1
        )
        """)


# ---------------- USERS ----------------

def upsert_user(user_id, username, first_name, referred_by=None):
    now = int(time.time())
    with get_conn() as conn:
        c = conn.cursor()
        row = c.execute("SELECT user_id FROM users WHERE user_id=?", (user_id,)).fetchone()
        if row:
            c.execute("""UPDATE users SET username=?, first_name=?, last_seen=?
                          WHERE user_id=?""", (username, first_name, now, user_id))
        else:
            c.execute("""INSERT INTO users (user_id, username, first_name, joined_at, last_seen,
                          last_online, referred_by) VALUES (?,?,?,?,?,?,?)""",
                      (user_id, username, first_name, now, now, now, referred_by))
            if referred_by:
                c.execute("UPDATE users SET coins = coins + 20 WHERE user_id=?", (referred_by,))


def touch_online(user_id):
    now = int(time.time())
    with get_conn() as conn:
        conn.execute("UPDATE users SET last_online=?, last_seen=? WHERE user_id=?",
                     (now, now, user_id))


def get_user(user_id):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()


def get_all_users():
    with get_conn() as conn:
        return conn.execute("SELECT * FROM users").fetchall()


def set_ban(user_id, banned: bool):
    with get_conn() as conn:
        conn.execute("UPDATE users SET is_banned=? WHERE user_id=?", (1 if banned else 0, user_id))


def add_coins(user_id, amount):
    with get_conn() as conn:
        conn.execute("UPDATE users SET coins = coins + ? WHERE user_id=?", (amount, user_id))


def deduct_coins(user_id, amount):
    with get_conn() as conn:
        conn.execute("UPDATE users SET coins = MAX(0, coins - ?) WHERE user_id=?", (amount, user_id))


def leaderboard(limit=10, scope_user_ids=None):
    with get_conn() as conn:
        if scope_user_ids:
            qmarks = ",".join("?" * len(scope_user_ids))
            rows = conn.execute(
                f"SELECT * FROM users WHERE user_id IN ({qmarks}) ORDER BY coins DESC LIMIT ?",
                (*scope_user_ids, limit)).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM users ORDER BY coins DESC LIMIT ?", (limit,)).fetchall()
        return rows


# ---------------- ADMINS ----------------

def add_admin(user_id, added_by):
    with get_conn() as conn:
        conn.execute("INSERT OR IGNORE INTO admins (user_id, added_by, added_at) VALUES (?,?,?)",
                     (user_id, added_by, int(time.time())))


def remove_admin(user_id):
    with get_conn() as conn:
        conn.execute("DELETE FROM admins WHERE user_id=?", (user_id,))


def is_admin(user_id, owner_id):
    if user_id == owner_id:
        return True
    with get_conn() as conn:
        row = conn.execute("SELECT 1 FROM admins WHERE user_id=?", (user_id,)).fetchone()
        return row is not None


def list_admins():
    with get_conn() as conn:
        return conn.execute("SELECT * FROM admins").fetchall()


# ---------------- SUBJECTS / CHAPTERS ----------------

def add_subject(name):
    with get_conn() as conn:
        conn.execute("INSERT OR IGNORE INTO subjects (name) VALUES (?)", (name,))
        return conn.execute("SELECT subject_id FROM subjects WHERE name=?", (name,)).fetchone()[0]


def get_subjects():
    with get_conn() as conn:
        return conn.execute("SELECT * FROM subjects ORDER BY name").fetchall()


def add_chapter(subject_id, name):
    with get_conn() as conn:
        conn.execute("INSERT INTO chapters (subject_id, name) VALUES (?,?)", (subject_id, name))
        return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def get_chapters(subject_id):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM chapters WHERE subject_id=? ORDER BY name",
                            (subject_id,)).fetchall()


def find_or_create_chapter(subject_name, chapter_name):
    sid = add_subject(subject_name)
    with get_conn() as conn:
        row = conn.execute("SELECT chapter_id FROM chapters WHERE subject_id=? AND name=?",
                           (sid, chapter_name)).fetchone()
        if row:
            return row[0]
    return add_chapter(sid, chapter_name)


# ---------------- QUESTIONS ----------------

def add_question(chapter_id, question_text, options, correct_index, explanation, added_by):
    with get_conn() as conn:
        conn.execute("""INSERT INTO questions
            (chapter_id, question_text, options, correct_index, explanation, added_by, added_at)
            VALUES (?,?,?,?,?,?,?)""",
            (chapter_id, question_text, json.dumps(options), correct_index,
             explanation, added_by, int(time.time())))
        return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def get_questions(chapter_id=None, subject_id=None, limit=None):
    with get_conn() as conn:
        if chapter_id:
            q = "SELECT * FROM questions WHERE chapter_id=?"
            params = [chapter_id]
        elif subject_id:
            q = """SELECT questions.* FROM questions
                   JOIN chapters ON questions.chapter_id = chapters.chapter_id
                   WHERE chapters.subject_id=?"""
            params = [subject_id]
        else:
            q = "SELECT * FROM questions"
            params = []
        if limit:
            q += " ORDER BY RANDOM() LIMIT ?"
            params.append(limit)
        return conn.execute(q, params).fetchall()


def delete_question(question_id):
    with get_conn() as conn:
        conn.execute("DELETE FROM questions WHERE question_id=?", (question_id,))


def count_questions():
    with get_conn() as conn:
        return conn.execute("SELECT COUNT(*) FROM questions").fetchone()[0]


# ---------------- QUIZ SESSIONS ----------------

def create_session(chat_id, chat_title, subject_id, chapter_id, started_by, total_questions,
                    negative_marking=0):
    with get_conn() as conn:
        conn.execute("""INSERT INTO quiz_sessions
            (chat_id, chat_title, subject_id, chapter_id, started_by, started_at,
             total_questions, negative_marking)
            VALUES (?,?,?,?,?,?,?,?)""",
            (chat_id, chat_title, subject_id, chapter_id, started_by, int(time.time()),
             total_questions, negative_marking))
        return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def end_session(session_id):
    with get_conn() as conn:
        conn.execute("UPDATE quiz_sessions SET ended_at=? WHERE session_id=?",
                     (int(time.time()), session_id))


def log_answer(session_id, user_id, question_id, selected_index, is_correct, answer_time_sec):
    with get_conn() as conn:
        conn.execute("""INSERT INTO answer_log
            (session_id, user_id, question_id, selected_index, is_correct, answer_time_sec, answered_at)
            VALUES (?,?,?,?,?,?,?)""",
            (session_id, user_id, question_id, selected_index, int(is_correct),
             answer_time_sec, int(time.time())))


def upsert_result(session_id, user_id, correct_delta, wrong_delta, coins_delta, answer_time):
    with get_conn() as conn:
        row = conn.execute("SELECT id, avg_time, correct, wrong FROM quiz_results WHERE session_id=? AND user_id=?",
                           (session_id, user_id)).fetchone()
        if row:
            total_answered = row["correct"] + row["wrong"] + correct_delta + wrong_delta
            new_avg = ((row["avg_time"] * (row["correct"] + row["wrong"])) + answer_time) / max(1, total_answered)
            conn.execute("""UPDATE quiz_results SET correct=correct+?, wrong=wrong+?,
                          coins_earned=coins_earned+?, avg_time=? WHERE id=?""",
                         (correct_delta, wrong_delta, coins_delta, new_avg, row["id"]))
        else:
            conn.execute("""INSERT INTO quiz_results
                (session_id, user_id, correct, wrong, coins_earned, avg_time)
                VALUES (?,?,?,?,?,?)""",
                (session_id, user_id, correct_delta, wrong_delta, coins_delta, answer_time))


def get_session_results(session_id):
    with get_conn() as conn:
        return conn.execute("""SELECT quiz_results.*, users.first_name, users.username
                                FROM quiz_results JOIN users ON quiz_results.user_id = users.user_id
                                WHERE session_id=? ORDER BY correct DESC, avg_time ASC""",
                            (session_id,)).fetchall()


def get_user_history(user_id, limit=20):
    with get_conn() as conn:
        return conn.execute("""SELECT quiz_sessions.session_id, quiz_sessions.chat_title,
                                quiz_sessions.started_at, quiz_results.correct, quiz_results.wrong,
                                quiz_results.coins_earned
                                FROM quiz_results
                                JOIN quiz_sessions ON quiz_results.session_id = quiz_sessions.session_id
                                WHERE quiz_results.user_id=?
                                ORDER BY quiz_sessions.started_at DESC LIMIT ?""",
                            (user_id, limit)).fetchall()


def record_quiz_completion(user_id, correct, wrong, total_q):
    with get_conn() as conn:
        conn.execute("""UPDATE users SET total_quizzes = total_quizzes + 1,
                        total_correct = total_correct + ?, total_wrong = total_wrong + ?,
                        total_questions = total_questions + ? WHERE user_id=?""",
                     (correct, wrong, total_q, user_id))


# ---------------- WITHDRAWALS ----------------

def request_withdrawal(user_id, coins):
    with get_conn() as conn:
        conn.execute("""INSERT INTO withdrawals (user_id, coins, requested_at)
                        VALUES (?,?,?)""", (user_id, coins, int(time.time())))
        return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def get_pending_withdrawals():
    with get_conn() as conn:
        return conn.execute("""SELECT withdrawals.*, users.first_name, users.username
                                FROM withdrawals JOIN users ON withdrawals.user_id = users.user_id
                                WHERE status='pending' ORDER BY requested_at ASC""").fetchall()


def process_withdrawal(withdrawal_id, status, processed_by):
    with get_conn() as conn:
        conn.execute("""UPDATE withdrawals SET status=?, processed_at=?, processed_by=?
                        WHERE id=?""", (status, int(time.time()), processed_by, withdrawal_id))


# ---------------- ADS ----------------

def create_ad(content, button_text, button_url, created_by):
    with get_conn() as conn:
        conn.execute("""INSERT INTO ads (content, button_text, button_url, created_by, created_at)
                        VALUES (?,?,?,?,?)""",
                     (content, button_text, button_url, created_by, int(time.time())))
        return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def increment_ad_sent(ad_id, count):
    with get_conn() as conn:
        conn.execute("UPDATE ads SET sent_count = sent_count + ? WHERE ad_id=?", (count, ad_id))


# ---------------- GROUPS ----------------

def upsert_group(chat_id, title):
    with get_conn() as conn:
        row = conn.execute("SELECT chat_id FROM groups WHERE chat_id=?", (chat_id,)).fetchone()
        if row:
            conn.execute("UPDATE groups SET title=?, is_active=1 WHERE chat_id=?", (title, chat_id))
        else:
            conn.execute("INSERT INTO groups (chat_id, title, added_at) VALUES (?,?,?)",
                         (chat_id, title, int(time.time())))


def get_active_groups():
    with get_conn() as conn:
        return conn.execute("SELECT * FROM groups WHERE is_active=1").fetchall()


def deactivate_group(chat_id):
    with get_conn() as conn:
        conn.execute("UPDATE groups SET is_active=0 WHERE chat_id=?", (chat_id,))


# ---------------- SETTINGS ----------------

def set_setting(key, value):
    with get_conn() as conn:
        conn.execute("INSERT INTO settings (key, value) VALUES (?,?) "
                     "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, str(value)))


def get_setting(key, default=None):
    with get_conn() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default


# ---------------- GROUP-SPECIFIC SETTINGS (admin can add own group) --------
# Har group/channel apna alag coin-rate, negative marking, entry fee rakh
# sakta hai. Agar group_settings me row nahi hai to global default (config.py) use hota hai.

def register_group_settings(chat_id, added_by, coin_per_correct=None, negative_marking=0,
                             negative_amount=None, entry_fee=0):
    with get_conn() as conn:
        row = conn.execute("SELECT chat_id FROM group_settings WHERE chat_id=?", (chat_id,)).fetchone()
        if row:
            conn.execute("""UPDATE group_settings SET coin_per_correct=?, negative_marking=?,
                          negative_amount=?, entry_fee=? WHERE chat_id=?""",
                         (coin_per_correct, negative_marking, negative_amount, entry_fee, chat_id))
        else:
            conn.execute("""INSERT INTO group_settings
                (chat_id, coin_per_correct, negative_marking, negative_amount, entry_fee, added_by, added_at)
                VALUES (?,?,?,?,?,?,?)""",
                (chat_id, coin_per_correct, negative_marking, negative_amount, entry_fee,
                 added_by, int(time.time())))


def get_group_settings(chat_id):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM group_settings WHERE chat_id=?", (chat_id,)).fetchone()


def update_group_setting_field(chat_id, field, value):
    """field must be one of the whitelisted column names"""
    allowed = {"coin_per_correct", "negative_marking", "negative_amount", "entry_fee"}
    if field not in allowed:
        raise ValueError("Invalid field")
    with get_conn() as conn:
        row = conn.execute("SELECT chat_id FROM group_settings WHERE chat_id=?", (chat_id,)).fetchone()
        if not row:
            conn.execute("""INSERT INTO group_settings (chat_id, added_at) VALUES (?,?)""",
                        (chat_id, int(time.time())))
        conn.execute(f"UPDATE group_settings SET {field}=? WHERE chat_id=?", (value, chat_id))


def list_registered_groups():
    with get_conn() as conn:
        return conn.execute("""SELECT group_settings.*, groups.title FROM group_settings
                                LEFT JOIN groups ON group_settings.chat_id = groups.chat_id
                                ORDER BY group_settings.added_at DESC""").fetchall()


# ---------------- DUELS (solo practice + 1v1 challenge) --------------------

def create_duel(challenger_id, opponent_id, subject_id, chapter_id, total_questions):
    with get_conn() as conn:
        conn.execute("""INSERT INTO duels
            (challenger_id, opponent_id, subject_id, chapter_id, total_questions, created_at)
            VALUES (?,?,?,?,?,?)""",
            (challenger_id, opponent_id, subject_id, chapter_id, total_questions, int(time.time())))
        return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def get_duel(duel_id):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM duels WHERE duel_id=?", (duel_id,)).fetchone()


def update_duel_status(duel_id, status):
    with get_conn() as conn:
        finished_at = int(time.time()) if status == "finished" else None
        conn.execute("UPDATE duels SET status=?, finished_at=? WHERE duel_id=?",
                     (status, finished_at, duel_id))


def upsert_duel_result(duel_id, user_id, correct_delta, wrong_delta):
    with get_conn() as conn:
        row = conn.execute("SELECT id FROM duel_results WHERE duel_id=? AND user_id=?",
                           (duel_id, user_id)).fetchone()
        if row:
            conn.execute("UPDATE duel_results SET correct=correct+?, wrong=wrong+? WHERE id=?",
                         (correct_delta, wrong_delta, row["id"]))
        else:
            conn.execute("""INSERT INTO duel_results (duel_id, user_id, correct, wrong)
                          VALUES (?,?,?,?)""", (duel_id, user_id, correct_delta, wrong_delta))


def get_duel_results(duel_id):
    with get_conn() as conn:
        return conn.execute("""SELECT duel_results.*, users.first_name, users.username
                                FROM duel_results JOIN users ON duel_results.user_id = users.user_id
                                WHERE duel_id=?""", (duel_id,)).fetchall()


# ---------------- NOTES (HTML notes bot bhej sake) --------------------------

def save_note(title, content_html, created_by):
    with get_conn() as conn:
        conn.execute("""INSERT INTO notes (title, content_html, created_by, created_at)
                        VALUES (?,?,?,?)""", (title, content_html, created_by, int(time.time())))
        return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def get_notes(limit=20):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM notes ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()


def get_note(note_id):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM notes WHERE note_id=?", (note_id,)).fetchone()


def log_pdf_job(user_id, original_name, action):
    with get_conn() as conn:
        conn.execute("""INSERT INTO pdf_jobs (user_id, original_name, action, created_at)
                        VALUES (?,?,?,?)""", (user_id, original_name, action, int(time.time())))


# ---------------- CHAT APP (student discussion / community chat) -----------

def upsert_chat_app_user(user_id, display_name, avatar_emoji, access_token):
    now = int(time.time())
    with get_conn() as conn:
        row = conn.execute("SELECT user_id FROM chat_app_users WHERE user_id=?", (user_id,)).fetchone()
        if row:
            conn.execute("""UPDATE chat_app_users SET display_name=?, last_seen=? WHERE user_id=?""",
                         (display_name, now, user_id))
        else:
            conn.execute("""INSERT INTO chat_app_users
                (user_id, display_name, avatar_emoji, access_token, created_at, last_seen)
                VALUES (?,?,?,?,?,?)""",
                (user_id, display_name, avatar_emoji, access_token, now, now))


def get_chat_app_user_by_token(token):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM chat_app_users WHERE access_token=?", (token,)).fetchone()


def get_chat_app_user(user_id):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM chat_app_users WHERE user_id=?", (user_id,)).fetchone()


def touch_chat_app_user(user_id):
    with get_conn() as conn:
        conn.execute("UPDATE chat_app_users SET last_seen=? WHERE user_id=?",
                     (int(time.time()), user_id))


def ensure_default_room():
    with get_conn() as conn:
        row = conn.execute("SELECT room_id FROM chat_app_rooms WHERE is_default=1").fetchone()
        if row:
            return row["room_id"]
        conn.execute("""INSERT INTO chat_app_rooms (name, description, created_at, is_default)
                        VALUES (?,?,?,1)""",
                     ("Students Lounge", "Sabke liye common discussion room", int(time.time())))
        return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def get_rooms():
    with get_conn() as conn:
        return conn.execute("SELECT * FROM chat_app_rooms ORDER BY is_default DESC, name").fetchall()


def save_chat_message(room_id, user_id, content):
    with get_conn() as conn:
        conn.execute("""INSERT INTO chat_app_messages (room_id, user_id, content, sent_at)
                        VALUES (?,?,?,?)""", (room_id, user_id, content, time.time()))
        return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def get_recent_messages(room_id, limit=50, after_id=None):
    with get_conn() as conn:
        if after_id:
            rows = conn.execute("""SELECT chat_app_messages.*, chat_app_users.display_name,
                                    chat_app_users.avatar_emoji
                                    FROM chat_app_messages
                                    JOIN chat_app_users ON chat_app_messages.user_id = chat_app_users.user_id
                                    WHERE room_id=? AND message_id > ?
                                    ORDER BY message_id ASC LIMIT ?""", (room_id, after_id, limit)).fetchall()
        else:
            rows = conn.execute("""SELECT chat_app_messages.*, chat_app_users.display_name,
                                    chat_app_users.avatar_emoji
                                    FROM chat_app_messages
                                    JOIN chat_app_users ON chat_app_messages.user_id = chat_app_users.user_id
                                    WHERE room_id=?
                                    ORDER BY message_id DESC LIMIT ?""", (room_id, limit)).fetchall()
            rows = list(reversed(rows))
        return rows


# ---------------- REACTIONS BOT (auto-react on the bot's own posts) --------

def get_reaction_settings(chat_id):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM reaction_settings WHERE chat_id=?", (chat_id,)).fetchone()


def set_reaction_enabled(chat_id, enabled, updated_by):
    with get_conn() as conn:
        row = conn.execute("SELECT chat_id FROM reaction_settings WHERE chat_id=?", (chat_id,)).fetchone()
        if row:
            conn.execute("UPDATE reaction_settings SET enabled=?, updated_by=?, updated_at=? WHERE chat_id=?",
                         (int(enabled), updated_by, int(time.time()), chat_id))
        else:
            conn.execute("""INSERT INTO reaction_settings (chat_id, enabled, updated_by, updated_at)
                            VALUES (?,?,?,?)""", (chat_id, int(enabled), updated_by, int(time.time())))


def set_reaction_emojis(chat_id, emoji_list, updated_by):
    with get_conn() as conn:
        row = conn.execute("SELECT chat_id FROM reaction_settings WHERE chat_id=?", (chat_id,)).fetchone()
        payload = json.dumps(emoji_list)
        if row:
            conn.execute("UPDATE reaction_settings SET emoji_list=?, updated_by=?, updated_at=? WHERE chat_id=?",
                         (payload, updated_by, int(time.time()), chat_id))
        else:
            conn.execute("""INSERT INTO reaction_settings (chat_id, emoji_list, updated_by, updated_at)
                            VALUES (?,?,?,?)""", (chat_id, payload, updated_by, int(time.time())))


def is_reactions_enabled(chat_id):
    row = get_reaction_settings(chat_id)
    return bool(row and row["enabled"])


def get_reaction_emojis(chat_id):
    row = get_reaction_settings(chat_id)
    if row and row["emoji_list"]:
        try:
            return json.loads(row["emoji_list"])
        except Exception:
            pass
    return ["🔥", "👍", "🎉"]


# ---------------- VISIBILITY BOOSTER (pin + scheduled repost) --------------

def create_boost_job(chat_id, content, button_text, button_url, repost_every_minutes,
                      max_reposts, pin_on_post, created_by):
    now = int(time.time())
    next_run = now + (repost_every_minutes * 60 if repost_every_minutes else 0)
    with get_conn() as conn:
        conn.execute("""INSERT INTO boost_jobs
            (chat_id, content, button_text, button_url, repost_every_minutes, max_reposts,
             pin_on_post, created_by, created_at, next_run_at)
            VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (chat_id, content, button_text, button_url, repost_every_minutes, max_reposts,
             int(pin_on_post), created_by, now, next_run))
        return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def get_due_boost_jobs():
    now = int(time.time())
    with get_conn() as conn:
        return conn.execute("""SELECT * FROM boost_jobs WHERE is_active=1 AND next_run_at<=?
                                AND (max_reposts IS NULL OR repost_count_done < max_reposts)""",
                            (now,)).fetchall()


def mark_boost_job_run(job_id, repost_every_minutes):
    now = int(time.time())
    next_run = now + (repost_every_minutes * 60 if repost_every_minutes else 999999999)
    with get_conn() as conn:
        conn.execute("""UPDATE boost_jobs SET repost_count_done = repost_count_done + 1,
                        next_run_at=? WHERE job_id=?""", (next_run, job_id))


def deactivate_boost_job(job_id):
    with get_conn() as conn:
        conn.execute("UPDATE boost_jobs SET is_active=0 WHERE job_id=?", (job_id,))


def get_active_boost_jobs(chat_id=None):
    with get_conn() as conn:
        if chat_id:
            return conn.execute("SELECT * FROM boost_jobs WHERE is_active=1 AND chat_id=?",
                                (chat_id,)).fetchall()
        return conn.execute("SELECT * FROM boost_jobs WHERE is_active=1").fetchall()


def log_post_engagement(chat_id, message_id, member_count_at_post):
    with get_conn() as conn:
        conn.execute("""INSERT INTO post_engagement_log (chat_id, message_id, posted_at, member_count_at_post)
                        VALUES (?,?,?,?)""", (chat_id, message_id, int(time.time()), member_count_at_post))


def get_best_posting_hours(chat_id, top_n=3):
    """Group ke apne purane messages ke timestamps se sabse zyada
    activity wale ghante nikaalta hai — asli data se suggestion,
    kisi external scraping ke bina."""
    with get_conn() as conn:
        rows = conn.execute("""SELECT answered_at FROM answer_log
                                JOIN quiz_sessions ON answer_log.session_id = quiz_sessions.session_id
                                WHERE quiz_sessions.chat_id=?""", (chat_id,)).fetchall()
    if not rows:
        return []
    from collections import Counter
    hours = Counter(time.localtime(r["answered_at"]).tm_hour for r in rows)
    return hours.most_common(top_n)


# ---------------- GROUP/CHANNEL DIRECTORY (self-listed, no scraping) -------

def add_directory_entry(title, description, category, invite_link, added_by):
    with get_conn() as conn:
        conn.execute("""INSERT INTO directory_entries
            (title, description, category, invite_link, added_by, added_at)
            VALUES (?,?,?,?,?,?)""",
            (title, description, category, invite_link, added_by, int(time.time())))
        return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def get_directory_categories():
    with get_conn() as conn:
        rows = conn.execute("""SELECT DISTINCT category FROM directory_entries
                                WHERE is_active=1 ORDER BY category""").fetchall()
        return [r["category"] for r in rows]


def get_directory_entries(category=None):
    with get_conn() as conn:
        if category:
            return conn.execute("""SELECT * FROM directory_entries
                                    WHERE is_active=1 AND category=? ORDER BY added_at DESC""",
                                (category,)).fetchall()
        return conn.execute("SELECT * FROM directory_entries WHERE is_active=1 ORDER BY added_at DESC").fetchall()


def increment_directory_click(entry_id):
    with get_conn() as conn:
        conn.execute("UPDATE directory_entries SET click_count = click_count + 1 WHERE entry_id=?", (entry_id,))


def deactivate_directory_entry(entry_id):
    with get_conn() as conn:
        conn.execute("UPDATE directory_entries SET is_active=0 WHERE entry_id=?", (entry_id,))


def get_directory_entry(entry_id):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM directory_entries WHERE entry_id=?", (entry_id,)).fetchone()
