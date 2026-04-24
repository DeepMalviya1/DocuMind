"""
db.py

Simple SQLite database for user registration, login, chat history,
and metrics (query logs, latency, token usage, evaluation scores).
Uses user_id (integer) for all operations.
"""

import os
import sqlite3
import hashlib
import secrets
import json

from scripts.log import get_logger

logger = get_logger("Database")

PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
DB_DIR = os.path.join(PROJECT_ROOT, "database")
os.makedirs(DB_DIR, exist_ok=True)
DB_PATH = os.path.join(DB_DIR, "users.db")


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    return conn


def create_tables():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            token TEXT UNIQUE NOT NULL,
            user_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            file_id INTEGER,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            filename TEXT NOT NULL,
            file_type TEXT NOT NULL,
            char_count INTEGER NOT NULL,
            chunk_count INTEGER DEFAULT 0,
            uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, filename)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            username TEXT NOT NULL,
            query TEXT NOT NULL,
            model_used TEXT NOT NULL,
            sources TEXT NOT NULL,
            latency_ms REAL NOT NULL,
            input_tokens INTEGER,
            output_tokens INTEGER,
            total_tokens INTEGER,
            relevance_score REAL,
            source_count INTEGER,
            answer_length INTEGER,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()
    logger.info("Database tables ready")


def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()


def register_user(username, password):
    conn = get_connection()
    cursor = conn.cursor()

    try:
        password_hash = hash_password(password)
        cursor.execute(
            "INSERT INTO users (username, password_hash) VALUES (?, ?)",
            (username, password_hash)
        )
        conn.commit()
        logger.info(f"User registered: {username}")
        return True
    except sqlite3.IntegrityError:
        logger.warning(f"Registration failed: {username} already exists")
        return False
    finally:
        conn.close()


def verify_user(username, password):
    """
    Check username and password.
    Returns user_id if valid, None if not.
    """

    conn = get_connection()
    cursor = conn.cursor()

    password_hash = hash_password(password)
    cursor.execute(
        "SELECT id FROM users WHERE username = ? AND password_hash = ?",
        (username, password_hash)
    )

    user = cursor.fetchone()
    conn.close()

    if user:
        logger.info(f"User verified: {username} (user_id={user[0]})")
        return user[0]
    else:
        logger.warning(f"Verification failed: {username}")
        return None


def create_token(user_id):
    """Create a token for a user_id."""

    token = secrets.token_hex(32)
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "INSERT INTO tokens (token, user_id) VALUES (?, ?)",
        (token, user_id)
    )

    conn.commit()
    conn.close()
    logger.info(f"Token created for user_id={user_id}")
    return token


def verify_token(token):
    """
    Check if token is valid.
    Returns {"user_id": 1, "username": "deep"} if valid, None if not.
    """

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT users.id, users.username
        FROM tokens
        JOIN users ON tokens.user_id = users.id
        WHERE tokens.token = ?
    """, (token,))

    result = cursor.fetchone()
    conn.close()

    if result:
        return {"user_id": result[0], "username": result[1]}
    else:
        logger.warning("Invalid token used")
        return None


def delete_token(token):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM tokens WHERE token = ?", (token,))
    conn.commit()
    conn.close()
    logger.info("Token deleted (logout)")


# ------------------------------------------------------------------
# File registry functions
# ------------------------------------------------------------------

def register_file(user_id, filename, file_type, char_count, chunk_count):
    """
    Register an uploaded file. Returns file_id.
    - If this filename is new for this user: INSERT → get fresh auto-increment id
    - If it already exists: UPDATE in-place → keep the same file_id (no id gaps)
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        # Check if already exists
        cursor.execute(
            "SELECT id FROM files WHERE user_id=? AND filename=?",
            (user_id, filename)
        )
        row = cursor.fetchone()

        if row:
            # Update in-place — preserve the existing file_id
            file_id = row[0]
            cursor.execute(
                """UPDATE files
                   SET file_type=?, char_count=?, chunk_count=?, uploaded_at=CURRENT_TIMESTAMP
                   WHERE id=?""",
                (file_type, char_count, chunk_count, file_id)
            )
        else:
            # New file — let SQLite assign the next sequential id
            cursor.execute(
                """INSERT INTO files (user_id, filename, file_type, char_count, chunk_count)
                   VALUES (?, ?, ?, ?, ?)""",
                (user_id, filename, file_type, char_count, chunk_count)
            )
            file_id = cursor.lastrowid

        conn.commit()
        logger.info(f"File registered: '{filename}' → file_id={file_id} for user_id={user_id}")
        return file_id
    finally:
        conn.close()


def get_files(user_id):
    """Return all files uploaded by a user."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """SELECT id, filename, file_type, char_count, chunk_count, uploaded_at
           FROM files WHERE user_id=? ORDER BY uploaded_at DESC""",
        (user_id,)
    )
    rows = cursor.fetchall()
    conn.close()
    return [
        {
            "file_id":     row[0],
            "filename":    row[1],
            "file_type":   row[2],
            "char_count":  row[3],
            "chunk_count": row[4],
            "uploaded_at": row[5],
        }
        for row in rows
    ]


def get_file(user_id, file_id):
    """Return a single file record, verifying it belongs to user_id."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """SELECT id, filename, file_type, char_count, chunk_count, uploaded_at
           FROM files WHERE id=? AND user_id=?""",
        (file_id, user_id)
    )
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    return {
        "file_id":     row[0],
        "filename":    row[1],
        "file_type":   row[2],
        "char_count":  row[3],
        "chunk_count": row[4],
        "uploaded_at": row[5],
    }


def delete_file(user_id, file_id):
    """Remove a file record (chunks must be cleared separately)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM files WHERE id=? AND user_id=?",
        (file_id, user_id)
    )
    conn.commit()
    conn.close()
    logger.info(f"File record deleted: file_id={file_id} for user_id={user_id}")


# ------------------------------------------------------------------
# Chat history functions  (now per-file when file_id is provided)
# ------------------------------------------------------------------
def save_message(user_id, role, content, file_id=None):
    """Save a chat message. Optionally scoped to a specific file."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO chat_history (user_id, file_id, role, content) VALUES (?, ?, ?, ?)",
        (user_id, file_id, role, content)
    )
    conn.commit()
    conn.close()


def get_chat_history(user_id, limit=20, file_id=None):
    """
    Get recent chat history.
    If file_id given: history for that specific file/bot.
    If file_id is None: global history (no file scope).
    """
    conn = get_connection()
    cursor = conn.cursor()

    if file_id is not None:
        cursor.execute(
            """SELECT role, content FROM chat_history
               WHERE user_id=? AND file_id=?
               ORDER BY id DESC LIMIT ?""",
            (user_id, file_id, limit)
        )
    else:
        cursor.execute(
            """SELECT role, content FROM chat_history
               WHERE user_id=? AND file_id IS NULL
               ORDER BY id DESC LIMIT ?""",
            (user_id, limit)
        )

    rows = cursor.fetchall()
    conn.close()
    return [{"role": role, "content": content} for role, content in reversed(rows)]


def clear_chat_history(user_id, file_id=None):
    """
    Clear chat history.
    If file_id given: only clear that file's history.
    If None: clear all history for the user.
    """
    conn = get_connection()
    cursor = conn.cursor()

    if file_id is not None:
        cursor.execute(
            "DELETE FROM chat_history WHERE user_id=? AND file_id=?",
            (user_id, file_id)
        )
        logger.info(f"Chat history cleared for user_id={user_id}, file_id={file_id}")
    else:
        cursor.execute("DELETE FROM chat_history WHERE user_id=?", (user_id,))
        logger.info(f"All chat history cleared for user_id={user_id}")

    conn.commit()
    conn.close()


# ------------------------------------------------------------------
# Metrics functions
# ------------------------------------------------------------------

def save_metric(user_id, username, query, model_used, sources,
                latency_ms, input_tokens, output_tokens, total_tokens,
                relevance_score, answer_length):
    """Save a single query metric row."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO metrics
           (user_id, username, query, model_used, sources, latency_ms,
            input_tokens, output_tokens, total_tokens, relevance_score,
            source_count, answer_length)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            user_id, username, query, model_used,
            json.dumps(sources),
            round(latency_ms, 2),
            input_tokens, output_tokens, total_tokens,
            round(relevance_score, 4) if relevance_score is not None else None,
            len(sources),
            answer_length
        )
    )
    conn.commit()
    conn.close()
    logger.info(f"Metric saved for user_id={user_id} | latency={latency_ms:.0f}ms | tokens={total_tokens}")


def get_metrics(user_id=None, limit=100):
    """
    Fetch metric rows.
    If user_id is given, return only that user's rows.
    If user_id is None, return all rows (admin view).
    """
    conn = get_connection()
    cursor = conn.cursor()

    if user_id is not None:
        cursor.execute(
            """SELECT id, user_id, username, query, model_used, sources,
                      latency_ms, input_tokens, output_tokens, total_tokens,
                      relevance_score, source_count, answer_length, timestamp
               FROM metrics WHERE user_id = ?
               ORDER BY id DESC LIMIT ?""",
            (user_id, limit)
        )
    else:
        cursor.execute(
            """SELECT id, user_id, username, query, model_used, sources,
                      latency_ms, input_tokens, output_tokens, total_tokens,
                      relevance_score, source_count, answer_length, timestamp
               FROM metrics ORDER BY id DESC LIMIT ?""",
            (limit,)
        )

    rows = cursor.fetchall()
    conn.close()

    results = []
    for row in rows:
        results.append({
            "id":              row[0],
            "user_id":         row[1],
            "username":        row[2],
            "query":           row[3],
            "model_used":      row[4],
            "sources":         json.loads(row[5]),
            "latency_ms":      row[6],
            "input_tokens":    row[7],
            "output_tokens":   row[8],
            "total_tokens":    row[9],
            "relevance_score": row[10],
            "source_count":    row[11],
            "answer_length":   row[12],
            "timestamp":       row[13],
        })
    return results


def get_metrics_summary(user_id=None):
    """
    Aggregate summary stats.
    If user_id given: per-user summary. If None: global summary.
    """
    conn = get_connection()
    cursor = conn.cursor()

    base_filter = "WHERE user_id = ?" if user_id else ""
    params = (user_id,) if user_id else ()

    cursor.execute(
        f"""SELECT
               COUNT(*)                    AS total_queries,
               AVG(latency_ms)             AS avg_latency_ms,
               MIN(latency_ms)             AS min_latency_ms,
               MAX(latency_ms)             AS max_latency_ms,
               SUM(input_tokens)           AS total_input_tokens,
               SUM(output_tokens)          AS total_output_tokens,
               SUM(total_tokens)           AS total_tokens,
               AVG(relevance_score)        AS avg_relevance_score,
               AVG(answer_length)          AS avg_answer_length
            FROM metrics {base_filter}""",
        params
    )
    row = cursor.fetchone()

    # Per-model breakdown
    cursor.execute(
        f"""SELECT model_used, COUNT(*) as count, AVG(latency_ms) as avg_lat
            FROM metrics {base_filter}
            GROUP BY model_used""",
        params
    )
    model_rows = cursor.fetchall()
    conn.close()

    return {
        "total_queries":       row[0] or 0,
        "avg_latency_ms":      round(row[1], 2) if row[1] else 0,
        "min_latency_ms":      round(row[2], 2) if row[2] else 0,
        "max_latency_ms":      round(row[3], 2) if row[3] else 0,
        "total_input_tokens":  row[4] or 0,
        "total_output_tokens": row[5] or 0,
        "total_tokens":        row[6] or 0,
        "avg_relevance_score": round(row[7], 4) if row[7] else 0,
        "avg_answer_length":   round(row[8], 1) if row[8] else 0,
        "by_model": [
            {"model": r[0], "query_count": r[1], "avg_latency_ms": round(r[2], 2)}
            for r in model_rows
        ]
    }


create_tables()