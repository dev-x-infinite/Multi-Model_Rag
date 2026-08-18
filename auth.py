"""
auth.py
Bare-minimum username/password check. Stores the password as plain
text in SQLite -- fine for learning/local use, NOT how you'd actually
deploy this publicly (a real app would hash passwords and use a token
like JWT -- we're deliberately skipping that for now to keep this simple).
"""

import sqlite3
from pathlib import Path

DB_PATH = Path("users.db")


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


init_db()


def get_user(username: str) -> dict | None:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM users WHERE username = ?", (username,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def create_user(username: str, password: str) -> None:
    if get_user(username):
        raise ValueError("Username already exists")

    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO users (username, password) VALUES (?, ?)",
        (username, password),
    )
    conn.commit()
    conn.close()


def authenticate_user(username: str, password: str) -> bool:
    """Returns True if username+password match a stored user."""
    user = get_user(username)
    if not user:
        return False
    return user["password"] == password