import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "inspire.db"
SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_db()
    with open(SCHEMA_PATH) as f:
        conn.executescript(f.read())

    count = conn.execute("SELECT COUNT(*) AS n FROM menu_items").fetchone()["n"]
    if count == 0:
        from menu_data import MENU_ITEMS
        conn.executemany(
            "INSERT INTO menu_items (category, name, name_ar, price) VALUES (?, ?, ?, ?)",
            MENU_ITEMS,
        )
    conn.commit()
    conn.close()
