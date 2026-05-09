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

        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """)


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

def add_reminder(text: str, schedule_kind: str, schedule_spec: str, tz: str = "Europe/Amsterdam") -> int:
    with _conn() as c:
        cur = c.execute(
            "INSERT INTO reminders (text, schedule_kind, schedule_spec, timezone, created_at) VALUES (?, ?, ?, ?, ?)",
            (text, schedule_kind, schedule_spec, tz, datetime.utcnow().isoformat()),
        )
        return cur.lastrowid


def list_reminders():
    with _conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM reminders WHERE active = 1 ORDER BY id")]


def delete_reminder(rid: int) -> bool:
    with _conn() as c:
        cur = c.execute("UPDATE reminders SET active = 0 WHERE id = ?", (rid,))
        return cur.rowcount > 0


# ---------- emails ----------

def is_email_processed(message_id: str) -> bool:
    with _conn() as c:
        row = c.execute("SELECT 1 FROM processed_emails WHERE message_id = ?", (message_id,)).fetchone()
        return row is not None


def mark_email_processed(message_id: str, event_added: bool = False, calendar_event_id: str | None = None):
    with _conn() as c:
        c.execute(
            "INSERT OR REPLACE INTO processed_emails (message_id, processed_at, event_added, calendar_event_id) VALUES (?, ?, ?, ?)",
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


# ---------- settings (key/value, JSON-encoded) ----------

def get_setting(key: str, default=None):
    with _conn() as c:
        row = c.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        if not row:
            return default
        try:
            return json.loads(row["value"])
        except json.JSONDecodeError:
            return row["value"]


def set_setting(key: str, value):
    with _conn() as c:
        c.execute(
            "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, ?)",
            (key, json.dumps(value), datetime.utcnow().isoformat()),
        )


def get_location() -> dict | None:
    """Returns {postcode, house_number, lat, lon, address} or None if unset."""
    return get_setting("location")
