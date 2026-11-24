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
                is_premium          INTEGER NOT NULL DEFAULT 0,
                created_at          TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
            );
            INSERT INTO customers_new SELECT
                id, phone, first_name, last_name, status, subscription_start,
                check_in_time, current_order_json, is_premium, created_at
            FROM customers;
            DROP TABLE customers;
            ALTER TABLE customers_new RENAME TO customers;
            CREATE INDEX IF NOT EXISTS idx_customers_phone ON customers(phone);
        """)
        conn.commit()
        conn.execute("PRAGMA foreign_keys = ON")


def _migrate_visits_customer_id_nullable(conn):
    """Takeaway orders are recorded as visits with no customer, so
    visits.customer_id has to be nullable. SQLite can't ALTER a NOT NULL away, so
    rebuild the table once — only runs on DBs created before takeaway existed, and
    every visits row is copied across."""
    info = {row["name"]: row for row in conn.execute("PRAGMA table_info(visits)")}
    if not info.get("customer_id") or not info["customer_id"]["notnull"]:
        return
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.executescript("""
        CREATE TABLE visits_new (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id   INTEGER REFERENCES customers(id),
            check_in      TEXT NOT NULL,
            check_out     TEXT NOT NULL,
            time_cost     INTEGER NOT NULL DEFAULT 0,
            items_cost    INTEGER NOT NULL DEFAULT 0,
            total_cost    INTEGER NOT NULL DEFAULT 0,
            items_json    TEXT NOT NULL DEFAULT '[]',
            payment_method TEXT,
            is_premium    INTEGER NOT NULL DEFAULT 0
        );
        INSERT INTO visits_new SELECT
            id, customer_id, check_in, check_out, time_cost, items_cost,
            total_cost, items_json, payment_method, is_premium
        FROM visits;
        DROP TABLE visits;
        ALTER TABLE visits_new RENAME TO visits;
        CREATE INDEX IF NOT EXISTS idx_visits_customer ON visits(customer_id);
    """)
    conn.commit()
    conn.execute("PRAGMA foreign_keys = ON")


# Bump when menu_data.MENU_ITEMS is overhauled and existing tills should be reseeded
# with it (wiping any admin price edits/added items, so only for a real overhaul).
MENU_VERSION = 1  # 2026-07 overhaul


def _seed_menu(conn):
    from menu_data import MENU_ITEMS
    conn.execute("DELETE FROM menu_items")
    conn.executemany(
        "INSERT INTO menu_items (category, name, name_ar, price) VALUES (?, ?, ?, ?)",
        MENU_ITEMS,
    )
    conn.execute("UPDATE settings SET menu_version=? WHERE id=1", (MENU_VERSION,))


def _migrate_reseed_menu(conn):
    """Reseed from menu_data.py once per MENU_VERSION bump, never on an ordinary
    restart, so prices an admin edits and items they add survive. The version is
    stored in settings.menu_version rather than inferred from which categories exist,
    since admins can now delete items (deleting every item in a 'marker' category
    would otherwise trigger a full wipe on the next restart)."""
    version = conn.execute("SELECT menu_version FROM settings WHERE id=1").fetchone()["menu_version"]
    if version >= MENU_VERSION:
        return
    # DBs from before menu_version existed: the Pancake category means the 2026-07
    # menu (version 1) is already in place, so just record that instead of wiping.
    if MENU_VERSION == 1 and conn.execute(
        "SELECT 1 FROM menu_items WHERE category='Pancake' LIMIT 1"
    ).fetchone():
        conn.execute("UPDATE settings SET menu_version=1 WHERE id=1")
        return
    _seed_menu(conn)


def init_db():
    conn = get_db()
    with open(SCHEMA_PATH) as f:
        conn.executescript(f.read())

    _ensure_column(conn, "customers", "current_order_json", "TEXT NOT NULL DEFAULT '[]'")
    _ensure_column(conn, "visits", "payment_method", "TEXT")
    _ensure_column(conn, "customers", "is_premium", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(conn, "visits", "is_premium", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(conn, "settings", "premium_first_hour_rate", "INTEGER NOT NULL DEFAULT 80")
    _ensure_column(conn, "settings", "premium_extra_hour_rate", "INTEGER NOT NULL DEFAULT 50")
    _ensure_column(conn, "settings", "menu_version", "INTEGER NOT NULL DEFAULT 0")
    _migrate_drop_customers_status_check(conn)
    # after the _ensure_column calls above: this rebuild copies visits column-by-column,
    # so payment_method/is_premium have to exist by the time it runs
    _migrate_visits_customer_id_nullable(conn)
    # ...and these must come AFTER that rebuild, which doesn't know about them and
    # would otherwise silently drop them on a pre-takeaway DB
    _ensure_column(conn, "visits", "discount_percent", "REAL NOT NULL DEFAULT 0")
    _ensure_column(conn, "visits", "discount_amount", "INTEGER NOT NULL DEFAULT 0")
    conn.execute("INSERT OR IGNORE INTO settings (id) VALUES (1)")

    count = conn.execute("SELECT COUNT(*) AS n FROM menu_items").fetchone()["n"]
    if count == 0:
        _seed_menu(conn)
    else:
        _migrate_reseed_menu(conn)
    conn.commit()
    conn.close()
