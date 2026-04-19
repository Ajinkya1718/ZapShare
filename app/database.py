"""
database.py — SQLite Database Setup for ZapShare

This file handles:
1. Creating the SQLite database (zapshare.db)
2. Creating the 3 tables: users, messages, files
3. Providing a helper function to get a database connection
"""

import sqlite3
import os
import time
from contextlib import contextmanager

# Application code directory (where this file lives)
APP_DIR = os.path.dirname(os.path.abspath(__file__))

# DATA_DIR stores mutable runtime state (db/uploads). On Render, point this to
# a mounted persistent disk, e.g. /var/data.
DATA_DIR = os.path.abspath(os.getenv("DATA_DIR", APP_DIR))
os.makedirs(DATA_DIR, exist_ok=True)

# Database file location can be overridden directly if needed.
DATABASE_NAME = os.path.abspath(
    os.getenv("DATABASE_NAME", os.path.join(DATA_DIR, "zapshare.db"))
)

# SQLite concurrency tuning.
# WAL allows concurrent readers during writes (important for polling-based UIs).
SQLITE_TIMEOUT_SECONDS = float(os.getenv("SQLITE_TIMEOUT_SECONDS", "30"))
SQLITE_BUSY_TIMEOUT_MS = int(os.getenv("SQLITE_BUSY_TIMEOUT_MS", "30000"))
SQLITE_ENABLE_WAL = os.getenv("SQLITE_ENABLE_WAL", "1") not in {"0", "false", "False"}


def _configure_connection(conn: sqlite3.Connection) -> sqlite3.Connection:
    conn.row_factory = sqlite3.Row  # So we can use row["column_name"]

    # Keep behavior consistent and safe.
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_MS}")
    conn.execute("PRAGMA temp_store = MEMORY")

    # WAL significantly reduces contention between polling readers and writers.
    if SQLITE_ENABLE_WAL:
        try:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = NORMAL")
        except sqlite3.OperationalError:
            # If WAL can't be enabled (rare; e.g. read-only FS), continue with defaults.
            pass

    return conn


def get_db():
    """
    Returns a connection to the SQLite database.
    row_factory = sqlite3.Row lets us access columns by name (like a dictionary).
    """
    conn = sqlite3.connect(
        DATABASE_NAME,
        timeout=SQLITE_TIMEOUT_SECONDS,
        check_same_thread=False,
    )
    return _configure_connection(conn)


@contextmanager
def db_session(*, commit: bool = False):
    """Context-managed DB session that always closes the connection.

    If commit=True, commits on success and rolls back on error.
    """
    conn = get_db()
    try:
        yield conn
        if commit:
            conn.commit()
    except Exception:
        if commit:
            try:
                conn.rollback()
            except Exception:
                pass
        raise
    finally:
        conn.close()


def is_db_locked_error(exc: BaseException) -> bool:
    return isinstance(exc, sqlite3.OperationalError) and (
        "database is locked" in str(exc).lower() or "database is busy" in str(exc).lower()
    )


def run_write_transaction(fn, *, attempts: int = 5, initial_delay_s: float = 0.05, max_delay_s: float = 0.6):
    """Run a write transaction with retries for transient SQLite lock contention."""
    delay = initial_delay_s
    last_exc: Exception | None = None

    for _ in range(max(1, attempts)):
        try:
            with db_session(commit=True) as conn:
                return fn(conn)
        except Exception as exc:  # noqa: BLE001
            if not is_db_locked_error(exc):
                raise
            last_exc = exc
            time.sleep(delay)
            delay = min(max_delay_s, delay * 2)

    if last_exc is not None:
        raise last_exc
    raise sqlite3.OperationalError("database is locked")


def init_db():
    """
    Creates the database tables if they don't already exist.
    Called once when the app starts.
    """
    conn = get_db()
    cursor = conn.cursor()

    # ---- Table 1: users ----
    # Stores registered users with hashed passwords
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            session_epoch INTEGER NOT NULL DEFAULT 1
        )
    """)

    # Backfill session_epoch for databases created before this column existed.
    user_columns = {
        row["name"]
        for row in cursor.execute("PRAGMA table_info(users)").fetchall()
    }
    if "session_epoch" not in user_columns:
        cursor.execute(
            "ALTER TABLE users ADD COLUMN session_epoch INTEGER NOT NULL DEFAULT 1"
        )

    # ---- Table 2: messages ----
    # Stores text messages between two users
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender_id INTEGER NOT NULL,
            receiver_id INTEGER NOT NULL,
            content TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (sender_id) REFERENCES users(id),
            FOREIGN KEY (receiver_id) REFERENCES users(id)
        )
    """)

    # ---- Table 3: files ----
    # Stores metadata about uploaded files shared between users
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender_id INTEGER NOT NULL,
            receiver_id INTEGER NOT NULL,
            filename TEXT NOT NULL,
            filepath TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (sender_id) REFERENCES users(id),
            FOREIGN KEY (receiver_id) REFERENCES users(id)
        )
    """)

    # Query speed-ups for polling, pagination, and conversation retrieval.
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_messages_sender_receiver_id ON messages(sender_id, receiver_id, id)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_messages_receiver_sender_id ON messages(receiver_id, sender_id, id)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_files_sender_receiver_id ON files(sender_id, receiver_id, id)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_files_receiver_sender_id ON files(receiver_id, sender_id, id)"
    )

    conn.commit()
    conn.close()
    print("✅ Database initialized successfully!")


# Create the uploads folder if it doesn't exist
UPLOADS_DIR = os.path.abspath(os.getenv("UPLOADS_DIR", os.path.join(DATA_DIR, "uploads")))
os.makedirs(UPLOADS_DIR, exist_ok=True)
