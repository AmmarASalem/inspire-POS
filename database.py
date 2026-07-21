import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "inspire.db"
SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _ensure_column(conn, table, column, coldef):
    """ALTER TABLE ... ADD COLUMN for DBs created before this column existed.
    CREATE TABLE IF NOT EXISTS in schema.sql only covers brand-new DBs."""
    existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coldef}")


def init_db():
    conn = get_db()
    with open(SCHEMA_PATH) as f:
        conn.executescript(f.read())

    _ensure_column(conn, "customers", "current_order_json", "TEXT NOT NULL DEFAULT '[]'")
    _ensure_column(conn, "visits", "payment_method", "TEXT")

    count = conn.execute("SELECT COUNT(*) AS n FROM menu_items").fetchone()["n"]
    if count == 0:
        from menu_data import MENU_ITEMS
        conn.executemany(
            "INSERT INTO menu_items (category, name, name_ar, price) VALUES (?, ?, ?, ?)",
            MENU_ITEMS,
        )
    conn.commit()
    conn.close()
