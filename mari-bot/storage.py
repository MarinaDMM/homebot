"""SQLite-backed persistence for reminders, processed-email tracking, and user settings."""

import sqlite3
import json
from datetime import datetime
from pathlib import Path
from contextlib import contextmanager

DB_PATH = Path(__file__).parent / "state.db"


def init_db():
    with _conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            chat_id INTEGER,
            text TEXT NOT NULL,
            schedule_kind TEXT NOT NULL,    -- 'once' | 'cron'
            schedule_spec TEXT NOT NULL,    -- ISO datetime for once, cron expr for cron
            timezone TEXT DEFAULT 'Europe/Amsterdam',
            created_at TEXT NOT NULL,
            active INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS processed_emails (
            message_id TEXT PRIMARY KEY,
            processed_at TEXT NOT NULL,
            event_added INTEGER DEFAULT 0,
            calendar_event_id TEXT
        );

        CREATE TABLE IF NOT EXISTS pending_confirmations (
            token TEXT PRIMARY KEY,
            kind TEXT NOT NULL,             -- 'event' | 'lock' | 'unlock'
            payload TEXT NOT NULL,          -- JSON
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS user_settings (
            user_id INTEGER NOT NULL,
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (user_id, key)
        );
        """)
    # Migrate: add columns to reminders if upgrading from single-tenant schema
    with _conn() as c:
        for col, typ in [("user_id", "INTEGER"), ("chat_id", "INTEGER")]:
            try:
                c.execute(f"ALTER TABLE reminders ADD COLUMN {col} {typ}")
            except Exception:
                pass  # column already exists


@contextmanager
def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


# ---------- reminders ----------

def add_reminder(user_id: int, chat_id: int, text: str, schedule_kind: str, schedule_spec: str,
                 tz: str = "Europe/Amsterdam") -> int:
    with _conn() as c:
        cur = c.execute(
            "INSERT INTO reminders (user_id, chat_id, text, schedule_kind, schedule_spec, timezone, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_id, chat_id, text, schedule_kind, schedule_spec, tz, datetime.utcnow().isoformat()),
        )
        return cur.lastrowid


def list_reminders(user_id: int):
    with _conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT * FROM reminders WHERE active = 1 AND user_id = ? ORDER BY id", (user_id,)
        )]


def list_all_active_reminders():
    """All active reminders across all users — used for scheduler hydration on startup."""
    with _conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT * FROM reminders WHERE active = 1 ORDER BY id"
        )]


def delete_reminder(user_id: int, rid: int) -> bool:
    with _conn() as c:
        cur = c.execute(
            "UPDATE reminders SET active = 0 WHERE id = ? AND user_id = ?", (rid, user_id)
        )
        return cur.rowcount > 0


# ---------- emails ----------

def is_email_processed(message_id: str) -> bool:
    with _conn() as c:
        row = c.execute("SELECT 1 FROM processed_emails WHERE message_id = ?", (message_id,)).fetchone()
        return row is not None


def mark_email_processed(message_id: str, event_added: bool = False, calendar_event_id: str | None = None):
    with _conn() as c:
        c.execute(
            "INSERT OR REPLACE INTO processed_emails (message_id, processed_at, event_added, calendar_event_id)"
            " VALUES (?, ?, ?, ?)",
            (message_id, datetime.utcnow().isoformat(), 1 if event_added else 0, calendar_event_id),
        )


# ---------- pending confirmations (inline button callbacks) ----------

def stash_confirmation(token: str, kind: str, payload: dict):
    with _conn() as c:
        c.execute(
            "INSERT OR REPLACE INTO pending_confirmations (token, kind, payload, created_at) VALUES (?, ?, ?, ?)",
            (token, kind, json.dumps(payload), datetime.utcnow().isoformat()),
        )


def pop_confirmation(token: str):
    with _conn() as c:
        row = c.execute("SELECT kind, payload FROM pending_confirmations WHERE token = ?", (token,)).fetchone()
        if not row:
            return None
        c.execute("DELETE FROM pending_confirmations WHERE token = ?", (token,))
        return row["kind"], json.loads(row["payload"])


# ---------- per-user settings ----------

def get_user_setting(user_id: int, key: str, default=None):
    with _conn() as c:
        row = c.execute(
            "SELECT value FROM user_settings WHERE user_id = ? AND key = ?", (user_id, key)
        ).fetchone()
        if not row:
            return default
        try:
            return json.loads(row["value"])
        except json.JSONDecodeError:
            return row["value"]


def set_user_setting(user_id: int, key: str, value):
    with _conn() as c:
        c.execute(
            "INSERT OR REPLACE INTO user_settings (user_id, key, value, updated_at) VALUES (?, ?, ?, ?)",
            (user_id, key, json.dumps(value), datetime.utcnow().isoformat()),
        )


def get_location(user_id: int) -> dict | None:
    """Returns {postcode, house_number, lat, lon, address, chat_id} or None."""
    return get_user_setting(user_id, "location")


def set_location(user_id: int, chat_id: int, data: dict):
    """Store location; chat_id is included so the morning briefing knows where to send."""
    set_user_setting(user_id, "location", {**data, "chat_id": chat_id})


def list_users_with_location() -> list[tuple[int, dict]]:
    """Returns [(user_id, location_dict)] for every user who has set a location."""
    with _conn() as c:
        rows = c.execute(
            "SELECT user_id, value FROM user_settings WHERE key = 'location'"
        ).fetchall()
    result = []
    for row in rows:
        try:
            loc = json.loads(row["value"])
            result.append((row["user_id"], loc))
        except Exception:
            pass
    return result
