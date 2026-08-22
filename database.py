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
