-- Inspire Workspace & Cafe -- cashier system schema (SQLite)

CREATE TABLE IF NOT EXISTS customers (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    phone               TEXT NOT NULL UNIQUE,
    first_name          TEXT NOT NULL,
    last_name           TEXT NOT NULL,
    status              TEXT NOT NULL DEFAULT 'not_subscribed'
                        CHECK (status IN ('not_subscribed', 'weekly', 'monthly')),
    subscription_start  TEXT,               -- ISO datetime, set when status becomes weekly/monthly
    check_in_time       TEXT,               -- ISO datetime, set while the customer is on-site
    current_order_json  TEXT NOT NULL DEFAULT '[]',  -- in-progress order for the active on-site session
    created_at          TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS menu_items (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    category    TEXT NOT NULL,
    name        TEXT NOT NULL,
    name_ar     TEXT,
    price       INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS visits (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id   INTEGER NOT NULL REFERENCES customers(id),
    check_in      TEXT NOT NULL,
    check_out     TEXT NOT NULL,
    time_cost     INTEGER NOT NULL DEFAULT 0,
    items_cost    INTEGER NOT NULL DEFAULT 0,
    total_cost    INTEGER NOT NULL DEFAULT 0,
    items_json    TEXT NOT NULL DEFAULT '[]',
    payment_method TEXT
);

CREATE INDEX IF NOT EXISTS idx_customers_phone ON customers(phone);
CREATE INDEX IF NOT EXISTS idx_visits_customer ON visits(customer_id);
