"""
database.py — SQLite Database Setup for ZapShare

This file handles:
1. Creating the SQLite database (zapshare.db)
2. Creating the 3 tables: users, messages, files
3. Providing a helper function to get a database connection
"""

import sqlite3
import os

# Base directory = folder where this file lives
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Database file will be created in the backend folder
DATABASE_NAME = os.path.join(BASE_DIR, "zapshare.db")


def get_db():
    """
    Returns a connection to the SQLite database.
    row_factory = sqlite3.Row lets us access columns by name (like a dictionary).
    """
    conn = sqlite3.connect(DATABASE_NAME)
    conn.row_factory = sqlite3.Row  # So we can use row["column_name"]
    conn.execute("PRAGMA foreign_keys = ON")  # Enable foreign key support
    return conn


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
            password TEXT NOT NULL
        )
    """)

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

    conn.commit()
    conn.close()
    print("✅ Database initialized successfully!")


# Create the uploads folder if it doesn't exist
UPLOADS_DIR = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOADS_DIR, exist_ok=True)
