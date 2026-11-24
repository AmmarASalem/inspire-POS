-- Inspire Workspace & Cafe -- cashier system schema (SQLite)
--
-- Money columns (prices, rates, costs, totals) hold LE with up to one decimal place,
-- e.g. 112.5. Some are declared INTEGER for historical reasons; SQLite stores a
-- fractional value in them as REAL regardless, so no migration was needed when
-- decimals were allowed. app.py rounds every amount with round_money().

CREATE TABLE IF NOT EXISTS customers (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    phone               TEXT NOT NULL UNIQUE,
    first_name          TEXT NOT NULL,
    last_name           TEXT NOT NULL,
    status              TEXT NOT NULL DEFAULT 'not_subscribed',
                        -- 'not_subscribed' | 'weekly' | 'monthly' | 'full_day' (validated in app.py,
                        -- not a CHECK, so new statuses don't need a table rebuild)
    subscription_start  TEXT,               -- ISO datetime, set when status becomes weekly/monthly
    check_in_time       TEXT,               -- ISO datetime, set while the customer is on-site
    current_order_json  TEXT NOT NULL DEFAULT '[]',  -- in-progress order for the active on-site session
    is_premium          INTEGER NOT NULL DEFAULT 0,  -- private-room seating for the current on-site session
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
    customer_id   INTEGER REFERENCES customers(id),
                  -- NULL for a takeaway order: a walk-in buying food/drink to go,
                  -- with no customer record, no workspace stay and no hourly charge
    check_in      TEXT NOT NULL,
    check_out     TEXT NOT NULL,   -- equal to check_in for a takeaway order
    time_cost     INTEGER NOT NULL DEFAULT 0,
    items_cost    INTEGER NOT NULL DEFAULT 0,
    total_cost    INTEGER NOT NULL DEFAULT 0,
    items_json    TEXT NOT NULL DEFAULT '[]',
    payment_method TEXT,
    is_premium    INTEGER NOT NULL DEFAULT 0,  -- whether this session billed at the private-room rate
    discount_percent REAL NOT NULL DEFAULT 0,  -- optional checkout discount, % of time + items
    discount_amount  INTEGER NOT NULL DEFAULT 0 -- in LE; total_cost is already net of this
);

CREATE INDEX IF NOT EXISTS idx_customers_phone ON customers(phone);
CREATE INDEX IF NOT EXISTS idx_visits_customer ON visits(customer_id);

-- Single row (id=1) holding admin-editable hourly/subscription pricing, so the
-- rates baked into app.py as defaults can be changed from the Admin page without
-- a code change/redeploy.
CREATE TABLE IF NOT EXISTS settings (
    id                  INTEGER PRIMARY KEY CHECK (id = 1),
    first_hour_rate     INTEGER NOT NULL DEFAULT 30,
    extra_hour_rate     INTEGER NOT NULL DEFAULT 10,
    daily_hourly_cap    INTEGER NOT NULL DEFAULT 100,
    weekly_price        INTEGER NOT NULL DEFAULT 0,
    monthly_price       INTEGER NOT NULL DEFAULT 0,
    full_day_price      INTEGER NOT NULL DEFAULT 100,
    premium_first_hour_rate INTEGER NOT NULL DEFAULT 80,  -- private-room rate: everyone pays this,
    premium_extra_hour_rate INTEGER NOT NULL DEFAULT 50,  -- including subscribers, uncapped
    menu_version        INTEGER NOT NULL DEFAULT 0  -- which menu_data.py overhaul is seeded (database.MENU_VERSION)
);
