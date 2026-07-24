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


def _migrate_drop_customers_status_check(conn):
    """DBs created before the 'full_day' status existed have a CHECK constraint
    that rejects it. SQLite can't ALTER a CHECK, so rebuild the table without one
    (status is validated in app.py instead) — only runs once, customers/visits data preserved."""
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='customers'"
    ).fetchone()
    if row and "CHECK" in row["sql"]:
        # visits.customer_id references this table, so dropping it needs FK checks off
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.executescript("""
            CREATE TABLE customers_new (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                phone               TEXT NOT NULL UNIQUE,
                first_name          TEXT NOT NULL,
                last_name           TEXT NOT NULL,
                status              TEXT NOT NULL DEFAULT 'not_subscribed',
                subscription_start  TEXT,
                check_in_time       TEXT,
                current_order_json  TEXT NOT NULL DEFAULT '[]',
                created_at          TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
            );
            INSERT INTO customers_new SELECT
                id, phone, first_name, last_name, status, subscription_start,
                check_in_time, current_order_json, created_at
            FROM customers;
            DROP TABLE customers;
            ALTER TABLE customers_new RENAME TO customers;
            CREATE INDEX IF NOT EXISTS idx_customers_phone ON customers(phone);
        """)
        conn.commit()
        conn.execute("PRAGMA foreign_keys = ON")


def _migrate_reseed_menu(conn):
    """One-time reseed to the 2026-07 menu overhaul (new prices, new Pancake category).
    Only runs if the new menu hasn't been applied yet, so it never clobbers prices an
    admin has since edited by hand."""
    from menu_data import MENU_ITEMS
    has_new_menu = conn.execute(
        "SELECT 1 FROM menu_items WHERE category='Pancake' LIMIT 1"
    ).fetchone()
    if not has_new_menu:
        conn.execute("DELETE FROM menu_items")
        conn.executemany(
            "INSERT INTO menu_items (category, name, name_ar, price) VALUES (?, ?, ?, ?)",
            MENU_ITEMS,
        )


def init_db():
    conn = get_db()
    with open(SCHEMA_PATH) as f:
        conn.executescript(f.read())

    _ensure_column(conn, "customers", "current_order_json", "TEXT NOT NULL DEFAULT '[]'")
    _ensure_column(conn, "visits", "payment_method", "TEXT")
    _migrate_drop_customers_status_check(conn)

    count = conn.execute("SELECT COUNT(*) AS n FROM menu_items").fetchone()["n"]
    if count == 0:
        from menu_data import MENU_ITEMS
        conn.executemany(
            "INSERT INTO menu_items (category, name, name_ar, price) VALUES (?, ?, ?, ?)",
            MENU_ITEMS,
        )
    else:
        _migrate_reseed_menu(conn)
    conn.commit()
    conn.close()
