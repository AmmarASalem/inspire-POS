import functools
import json
import math
import os
import sqlite3
from datetime import datetime, timedelta

from flask import Flask, jsonify, render_template, request

from database import get_db, init_db
from menu_data import CATEGORY_IMAGES, CATEGORY_ORDER
import receipt_printer

app = Flask(__name__)

SETTINGS_FIELDS = (
    "first_hour_rate", "extra_hour_rate", "daily_hourly_cap",
    "weekly_price", "monthly_price", "full_day_price",
    "premium_first_hour_rate", "premium_extra_hour_rate",
)
SUBSCRIPTION_DURATIONS = {
    "weekly": timedelta(days=7),
    "monthly": timedelta(days=30),
    "full_day": timedelta(hours=24),  # 24h from purchase — the shop runs 24/7
}
SUBSCRIPTION_STATUSES = ("weekly", "monthly", "full_day")

# The shop runs 24/7 and a "day" is a calendar day, 12am to 12am: the daily hourly
# cap resets at this time, and reports use the same midnight boundary.
BUSINESS_DAY_RESET_HOUR = 0
BUSINESS_DAY_RESET_MINUTE = 0

# No hour is billed until this many minutes into it, including the first: a 10m stay
# is free, 16m bills 1 hour, 2h08m bills 2, 2h16m bills 3. Mirrored in
# static/js/app.js for the live running total.
HOUR_GRACE_MINUTES = 15

# One-time-setup placeholder — change this before the till goes live.
ADMIN_PIN = os.environ.get("INSPIRE_ADMIN_PIN", "1234")


def require_admin(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        if request.headers.get("X-Admin-Pin") != ADMIN_PIN:
            return jsonify({"error": "Invalid admin PIN"}), 403
        return fn(*args, **kwargs)
    return wrapper

DT_FMT = "%Y-%m-%d %H:%M:%S"


def now_str():
    return datetime.now().strftime(DT_FMT)


def parse_dt(s):
    return datetime.strptime(s, DT_FMT)


def round_money(x):
    """All money (prices, rates, totals) allows one decimal place, e.g. 112.5 LE.
    Every sum/product of amounts goes through this so float noise like
    112.50000000000001 never reaches the DB, a receipt, or a report."""
    return round(float(x) + 0.0, 1) + 0.0  # + 0.0 turns -0.0 into 0.0


def parse_money(raw):
    """A non-negative amount with at most one decimal place. Raises ValueError."""
    value = float(raw)
    if not math.isfinite(value) or value < 0 or abs(value * 10 - round(value * 10)) > 1e-6:
        raise ValueError
    return round_money(value)


def get_settings(conn):
    row = conn.execute("SELECT * FROM settings WHERE id=1").fetchone()
    return {field: row[field] for field in SETTINGS_FIELDS}


def compute_time_cost(check_in_str, first_hour_rate, extra_hour_rate, daily_cap=None, at=None):
    """First hour flat, then the extra rate for every additional hour — each hour
    (the first included) billed only once more than HOUR_GRACE_MINUTES of it have
    passed, so a stay of HOUR_GRACE_MINUTES or less is free — capped at daily_cap per business day
    (BUSINESS_DAY_RESET_HOUR:MINUTE to the next occurrence, unless daily_cap is None)
    — a stay spanning multiple business days re-applies the cap each day rather than
    being capped once for the whole stay."""
    at = at or datetime.now()

    total_cost = 0
    total_hours = 0
    segment_start = parse_dt(check_in_str)
    while segment_start < at:
        segment_end = min(next_day_boundary(segment_start), at)
        elapsed_minutes = (segment_end - segment_start).total_seconds() / 60
        seg_hours = max(0, math.ceil((elapsed_minutes - HOUR_GRACE_MINUTES) / 60))
        seg_cost = 0 if seg_hours == 0 else round_money(first_hour_rate + (seg_hours - 1) * extra_hour_rate)
        total_cost = round_money(total_cost + (seg_cost if daily_cap is None else min(seg_cost, daily_cap)))
        total_hours += seg_hours
        segment_start = segment_end
    return total_cost, total_hours


def time_cost_for(check_in_str, is_premium, settings, at=None):
    """Picks premium (private room, uncapped, charged regardless of subscription
    status) vs normal (hourly, capped, waived for subscribers) rates/cap."""
    if is_premium:
        return compute_time_cost(
            check_in_str, settings["premium_first_hour_rate"], settings["premium_extra_hour_rate"],
            daily_cap=None, at=at,
        )
    return compute_time_cost(
        check_in_str, settings["first_hour_rate"], settings["extra_hour_rate"],
        daily_cap=settings["daily_hourly_cap"], at=at,
    )


def next_day_boundary(start):
    """The next BUSINESS_DAY_RESET_HOUR:MINUTE (midnight) after `start` — where the
    daily hourly cap resets."""
    cutoff = start.replace(hour=BUSINESS_DAY_RESET_HOUR, minute=BUSINESS_DAY_RESET_MINUTE,
                            second=0, microsecond=0)
    return cutoff if start < cutoff else cutoff + timedelta(days=1)


def compute_subscription_end(status, subscription_start):
    """Returns the datetime a weekly/monthly/full_day pass expires, or None."""
    if not subscription_start or status not in SUBSCRIPTION_STATUSES:
        return None
    return parse_dt(subscription_start) + SUBSCRIPTION_DURATIONS[status]


def sync_customer_status(conn, row):
    """Lazily revert an expired weekly/monthly/full_day pass back to not_subscribed.
    Returns a plain dict for the customer, including a computed subscription_end."""
    data = dict(row)
    end = compute_subscription_end(data["status"], data["subscription_start"])
    if end is None:
        data["subscription_end"] = None
    elif datetime.now() >= end:
        conn.execute(
            "UPDATE customers SET status='not_subscribed', subscription_start=NULL WHERE id=?",
            (data["id"],),
        )
        conn.commit()
        data["status"] = "not_subscribed"
        data["subscription_start"] = None
        data["subscription_end"] = None
    else:
        data["subscription_end"] = end.strftime(DT_FMT)
    return data


def customer_public(data, settings):
    is_premium = bool(data["is_premium"])
    out = {
        "id": data["id"],
        "phone": data["phone"],
        "first_name": data["first_name"],
        "last_name": data["last_name"],
        "status": data["status"],
        "subscription_start": data["subscription_start"],
        "subscription_end": data.get("subscription_end"),
        "check_in_time": data["check_in_time"],
        "is_premium": is_premium,
        "created_at": data["created_at"],
    }
    if data["check_in_time"]:
        chargeable = is_premium or data["status"] == "not_subscribed"
        cost, hours = time_cost_for(data["check_in_time"], is_premium, settings) if chargeable else (0, 0)
        out["elapsed_seconds"] = int((datetime.now() - parse_dt(data["check_in_time"])).total_seconds())
        out["running_time_cost"] = cost
        out["billed_hours"] = hours
        try:
            out["current_order"] = json.loads(data["current_order_json"])
        except (TypeError, ValueError):
            out["current_order"] = []
    return out


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/admin/verify", methods=["GET"])
@require_admin
def admin_verify():
    return jsonify({"ok": True})


# ---------- Settings ----------

@app.route("/api/settings", methods=["GET"])
def get_settings_route():
    """Public (not admin-gated) — the checkout/upgrade UI needs current rates and
    subscription prices to display, even though only admins can change them."""
    conn = get_db()
    settings = get_settings(conn)
    conn.close()
    return jsonify(settings)


@app.route("/api/settings", methods=["PUT"])
@require_admin
def admin_update_settings():
    """Admin-only: edit the hourly rates/daily cap and subscription prices."""
    body = request.get_json(force=True) or {}
    conn = get_db()
    updated = get_settings(conn)
    for field in SETTINGS_FIELDS:
        if field not in body:
            continue
        try:
            updated[field] = parse_money(body[field])
        except (TypeError, ValueError):
            conn.close()
            return jsonify({"error": f"{field} must be 0 or more, with at most one decimal place"}), 400

    conn.execute(
        """UPDATE settings SET first_hour_rate=?, extra_hour_rate=?, daily_hourly_cap=?,
           weekly_price=?, monthly_price=?, full_day_price=?,
           premium_first_hour_rate=?, premium_extra_hour_rate=? WHERE id=1""",
        tuple(updated[field] for field in SETTINGS_FIELDS),
    )
    conn.commit()
    conn.close()
    return jsonify(updated)


# ---------- Customers ----------

@app.route("/api/customers", methods=["GET"])
def list_customers():
    q = request.args.get("q", "").strip()
    conn = get_db()
    if q:
        like = f"%{q}%"
        rows = conn.execute(
            """SELECT * FROM customers
               WHERE phone LIKE ? OR first_name LIKE ? OR last_name LIKE ?
               ORDER BY created_at DESC""",
            (like, like, like),
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM customers ORDER BY created_at DESC").fetchall()
    settings = get_settings(conn)
    result = [customer_public(sync_customer_status(conn, r), settings) for r in rows]
    conn.close()
    return jsonify(result)


@app.route("/api/customers", methods=["POST"])
def create_customer():
    body = request.get_json(force=True) or {}
    phone = (body.get("phone") or "").strip()
    first_name = (body.get("first_name") or "").strip()
    last_name = (body.get("last_name") or "").strip()

    if not phone or not first_name or not last_name:
        return jsonify({"error": "phone, first_name and last_name are required"}), 400

    conn = get_db()
    try:
        cur = conn.execute(
            "INSERT INTO customers (phone, first_name, last_name) VALUES (?, ?, ?)",
            (phone, first_name, last_name),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({"error": "A customer with this phone number already exists"}), 409

    row = conn.execute("SELECT * FROM customers WHERE id=?", (cur.lastrowid,)).fetchone()
    data = customer_public(sync_customer_status(conn, row), get_settings(conn))
    conn.close()
    return jsonify(data), 201


@app.route("/api/customers/eligible", methods=["GET"])
def eligible_customers():
    """Customers currently on an active weekly/monthly/full_day pass (no hourly charge)."""
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM customers WHERE status IN ('weekly','monthly','full_day') ORDER BY subscription_start DESC"
    ).fetchall()
    settings = get_settings(conn)
    result = []
    for r in rows:
        data = sync_customer_status(conn, r)
        if data["status"] in SUBSCRIPTION_STATUSES:
            result.append(customer_public(data, settings))
    conn.close()
    return jsonify(result)


@app.route("/api/customers/checked-in", methods=["GET"])
def checked_in_customers():
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM customers WHERE check_in_time IS NOT NULL ORDER BY check_in_time ASC"
    ).fetchall()
    settings = get_settings(conn)
    result = [customer_public(sync_customer_status(conn, r), settings) for r in rows]
    conn.close()
    return jsonify(result)


def _get_customer_or_404(conn, customer_id):
    row = conn.execute("SELECT * FROM customers WHERE id=?", (customer_id,)).fetchone()
    return row


@app.route("/api/customers/<int:customer_id>", methods=["GET"])
def get_customer(customer_id):
    conn = get_db()
    row = _get_customer_or_404(conn, customer_id)
    if not row:
        conn.close()
        return jsonify({"error": "Customer not found"}), 404
    data = customer_public(sync_customer_status(conn, row), get_settings(conn))
    conn.close()
    return jsonify(data)


@app.route("/api/customers/<int:customer_id>", methods=["PUT"])
@require_admin
def admin_update_customer(customer_id):
    """Admin-only: edit a customer's profile and/or override their subscription status."""
    body = request.get_json(force=True) or {}
    conn = get_db()
    row = _get_customer_or_404(conn, customer_id)
    if not row:
        conn.close()
        return jsonify({"error": "Customer not found"}), 404

    first_name = (body.get("first_name") or row["first_name"]).strip()
    last_name = (body.get("last_name") or row["last_name"]).strip()
    phone = (body.get("phone") or row["phone"]).strip()
    status = body.get("status", row["status"])
    if status not in ("not_subscribed",) + SUBSCRIPTION_STATUSES:
        conn.close()
        return jsonify({"error": "Invalid status"}), 400

    if status == "not_subscribed":
        subscription_start = None
    elif status != row["status"]:
        subscription_start = now_str()
    else:
        subscription_start = row["subscription_start"]

    try:
        conn.execute(
            """UPDATE customers SET first_name=?, last_name=?, phone=?, status=?, subscription_start=?
               WHERE id=?""",
            (first_name, last_name, phone, status, subscription_start, customer_id),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({"error": "A customer with this phone number already exists"}), 409

    row = _get_customer_or_404(conn, customer_id)
    data = customer_public(sync_customer_status(conn, row), get_settings(conn))
    conn.close()
    return jsonify(data)


@app.route("/api/customers/<int:customer_id>", methods=["DELETE"])
@require_admin
def admin_delete_customer(customer_id):
    conn = get_db()
    row = _get_customer_or_404(conn, customer_id)
    if not row:
        conn.close()
        return jsonify({"error": "Customer not found"}), 404
    if row["check_in_time"]:
        conn.close()
        return jsonify({"error": "Check the customer out before deleting them"}), 400

    conn.execute("DELETE FROM visits WHERE customer_id=?", (customer_id,))
    conn.execute("DELETE FROM customers WHERE id=?", (customer_id,))
    conn.commit()
    conn.close()
    return jsonify({"deleted": True})


@app.route("/api/customers/<int:customer_id>/upgrade", methods=["POST"])
def upgrade_customer(customer_id):
    body = request.get_json(force=True) or {}
    status = body.get("status")
    payment_confirmed = bool(body.get("payment_confirmed"))

    if status not in SUBSCRIPTION_STATUSES:
        return jsonify({"error": "status must be 'weekly', 'monthly' or 'full_day'"}), 400
    if not payment_confirmed:
        return jsonify({"error": "Payment must be confirmed before upgrading"}), 400

    conn = get_db()
    row = _get_customer_or_404(conn, customer_id)
    if not row:
        conn.close()
        return jsonify({"error": "Customer not found"}), 404

    conn.execute(
        "UPDATE customers SET status=?, subscription_start=? WHERE id=?",
        (status, now_str(), customer_id),
    )
    conn.commit()
    row = _get_customer_or_404(conn, customer_id)
    data = customer_public(sync_customer_status(conn, row), get_settings(conn))
    conn.close()
    return jsonify(data)


@app.route("/api/customers/<int:customer_id>/checkin", methods=["POST"])
def checkin_customer(customer_id):
    conn = get_db()
    row = _get_customer_or_404(conn, customer_id)
    if not row:
        conn.close()
        return jsonify({"error": "Customer not found"}), 404
    if row["check_in_time"]:
        conn.close()
        return jsonify({"error": "Customer is already checked in"}), 400

    conn.execute(
        "UPDATE customers SET check_in_time=?, current_order_json='[]', is_premium=0 WHERE id=?",
        (now_str(), customer_id),
    )
    conn.commit()
    row = _get_customer_or_404(conn, customer_id)
    data = customer_public(sync_customer_status(conn, row), get_settings(conn))
    conn.close()
    return jsonify(data)


@app.route("/api/customers/<int:customer_id>/premium", methods=["POST"])
def set_customer_premium(customer_id):
    """Toggle private-room billing for the customer's current on-site session."""
    body = request.get_json(force=True) or {}
    is_premium = bool(body.get("is_premium"))

    conn = get_db()
    row = _get_customer_or_404(conn, customer_id)
    if not row:
        conn.close()
        return jsonify({"error": "Customer not found"}), 404
    if not row["check_in_time"]:
        conn.close()
        return jsonify({"error": "Customer is not checked in"}), 400

    conn.execute("UPDATE customers SET is_premium=? WHERE id=?", (1 if is_premium else 0, customer_id))
    conn.commit()
    row = _get_customer_or_404(conn, customer_id)
    data = customer_public(sync_customer_status(conn, row), get_settings(conn))
    conn.close()
    return jsonify(data)


def _resolve_order_items(conn, ordered_items):
    """Validate [{id, qty}] against menu_items, returning (items_cost, receipt_items)."""
    items_cost = 0
    receipt_items = []
    for entry in ordered_items:
        try:
            item_id = int(entry.get("id"))
            qty = int(entry.get("qty", 1))
        except (TypeError, ValueError, AttributeError):
            continue
        if qty <= 0:
            continue
        menu_row = conn.execute("SELECT * FROM menu_items WHERE id=?", (item_id,)).fetchone()
        if not menu_row:
            continue
        line_total = round_money(menu_row["price"] * qty)
        items_cost = round_money(items_cost + line_total)
        receipt_items.append({
            "id": menu_row["id"],
            "name": menu_row["name"],
            "price": menu_row["price"],
            "qty": qty,
            "line_total": line_total,
        })
    return items_cost, receipt_items


def parse_discount_percent(raw):
    """Optional checkout discount, as a percent of the whole bill. Blank/missing
    means no discount. Raises ValueError for anything outside 0-100."""
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return 0.0
    pct = float(raw)
    if not math.isfinite(pct) or pct < 0 or pct > 100:
        raise ValueError
    return pct


def discount_amount_for(subtotal, pct):
    """To the nearest 0.1 LE, rounded half up — worked out in tenths of a pound.
    Mirrored operation-for-operation in static/js/app.js (discountAmountFor) so the
    cart preview always matches the receipt: change both together."""
    subtotal_tenths = round(subtotal * 10)
    return round_money(math.floor(subtotal_tenths * pct / 100 + 0.5) / 10)


@app.route("/api/customers/<int:customer_id>/order", methods=["POST"])
def save_order(customer_id):
    """Save/update the in-progress order for an on-site customer, without checking out."""
    body = request.get_json(force=True) or {}
    ordered_items = body.get("items", [])  # [{id, qty}]

    conn = get_db()
    row = _get_customer_or_404(conn, customer_id)
    if not row:
        conn.close()
        return jsonify({"error": "Customer not found"}), 404
    if not row["check_in_time"]:
        conn.close()
        return jsonify({"error": "Customer is not checked in"}), 400

    _, receipt_items = _resolve_order_items(conn, ordered_items)
    saved = [{"id": it["id"], "qty": it["qty"]} for it in receipt_items]
    conn.execute(
        "UPDATE customers SET current_order_json=? WHERE id=?",
        (json.dumps(saved), customer_id),
    )
    conn.commit()
    row = _get_customer_or_404(conn, customer_id)
    data = customer_public(sync_customer_status(conn, row), get_settings(conn))
    conn.close()
    return jsonify(data)


@app.route("/api/customers/<int:customer_id>/checkout", methods=["POST"])
def checkout_customer(customer_id):
    body = request.get_json(force=True) or {}
    ordered_items = body.get("items", [])  # [{id, qty}]
    payment_method = (body.get("payment_method") or "").strip() or None
    try:
        discount_percent = parse_discount_percent(body.get("discount_percent"))
    except (TypeError, ValueError):
        return jsonify({"error": "Discount must be a percentage between 0 and 100"}), 400

    conn = get_db()
    row = _get_customer_or_404(conn, customer_id)
    if not row:
        conn.close()
        return jsonify({"error": "Customer not found"}), 404
    if not row["check_in_time"]:
        conn.close()
        return jsonify({"error": "Customer is not checked in"}), 400

    data = sync_customer_status(conn, row)
    is_premium = bool(data["is_premium"])

    time_cost = 0
    billed_hours = 0
    if is_premium or data["status"] == "not_subscribed":
        time_cost, billed_hours = time_cost_for(data["check_in_time"], is_premium, get_settings(conn))

    items_cost, receipt_items = _resolve_order_items(conn, ordered_items)

    subtotal = round_money(time_cost + items_cost)
    discount_amount = discount_amount_for(subtotal, discount_percent)
    total_cost = round_money(subtotal - discount_amount)
    check_out = now_str()

    conn.execute(
        """INSERT INTO visits (customer_id, check_in, check_out, time_cost, items_cost, total_cost, items_json,
                               payment_method, is_premium, discount_percent, discount_amount)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (customer_id, data["check_in_time"], check_out, time_cost, items_cost, total_cost,
         json.dumps(receipt_items), payment_method, int(is_premium), discount_percent, discount_amount),
    )
    conn.execute(
        "UPDATE customers SET check_in_time=NULL, current_order_json='[]', is_premium=0 WHERE id=?",
        (customer_id,),
    )
    conn.commit()

    receipt = {
        "customer": {
            "id": data["id"],
            "first_name": data["first_name"],
            "last_name": data["last_name"],
            "phone": data["phone"],
            "status": data["status"],
        },
        "check_in": data["check_in_time"],
        "check_out": check_out,
        "is_premium": is_premium,
        "billed_hours": billed_hours,
        "time_cost": time_cost,
        "items": receipt_items,
        "items_cost": items_cost,
        "subtotal": subtotal,
        "discount_percent": discount_percent,
        "discount_amount": discount_amount,
        "total_cost": total_cost,
        "payment_method": payment_method,
    }
    conn.close()

    printed, print_message = receipt_printer.print_receipt(receipt)
    receipt["printed"] = printed
    receipt["print_message"] = print_message

    return jsonify(receipt)


@app.route("/api/takeaway", methods=["POST"])
def takeaway_order():
    """Takeaway order for a walk-in buying food/drink to go: items only, no hourly
    charge, no check-in and no customer record needed. Recorded in `visits` (so it
    counts towards revenue reports) as a zero-length visit with a NULL customer_id."""
    body = request.get_json(force=True) or {}
    ordered_items = body.get("items", [])  # [{id, qty}]
    payment_method = (body.get("payment_method") or "").strip() or None
    try:
        discount_percent = parse_discount_percent(body.get("discount_percent"))
    except (TypeError, ValueError):
        return jsonify({"error": "Discount must be a percentage between 0 and 100"}), 400

    conn = get_db()
    items_cost, receipt_items = _resolve_order_items(conn, ordered_items)
    if not receipt_items:
        conn.close()
        return jsonify({"error": "Add at least one item to the order"}), 400

    discount_amount = discount_amount_for(items_cost, discount_percent)
    total_cost = round_money(items_cost - discount_amount)
    sold_at = now_str()
    conn.execute(
        """INSERT INTO visits (customer_id, check_in, check_out, time_cost, items_cost, total_cost, items_json,
                               payment_method, is_premium, discount_percent, discount_amount)
           VALUES (NULL, ?, ?, 0, ?, ?, ?, ?, 0, ?, ?)""",
        (sold_at, sold_at, items_cost, total_cost, json.dumps(receipt_items), payment_method,
         discount_percent, discount_amount),
    )
    conn.commit()
    conn.close()

    receipt = {
        "takeaway": True,
        "customer": None,
        "check_in": sold_at,
        "check_out": sold_at,
        "is_premium": False,
        "billed_hours": 0,
        "time_cost": 0,
        "items": receipt_items,
        "items_cost": items_cost,
        "subtotal": items_cost,
        "discount_percent": discount_percent,
        "discount_amount": discount_amount,
        "total_cost": total_cost,
        "payment_method": payment_method,
    }

    printed, print_message = receipt_printer.print_receipt(receipt)
    receipt["printed"] = printed
    receipt["print_message"] = print_message

    return jsonify(receipt)


@app.route("/api/print-receipt", methods=["POST"])
def reprint_receipt():
    """Manual reprint — lets the cashier retry from the on-screen receipt if the
    printer was off/out of paper/etc. during the automatic print at checkout."""
    receipt = request.get_json(force=True) or {}
    if "total_cost" not in receipt or not (receipt.get("customer") or receipt.get("takeaway")):
        return jsonify({"error": "Invalid receipt data"}), 400
    printed, message = receipt_printer.print_receipt(receipt)
    return jsonify({"printed": printed, "message": message})


@app.route("/api/customers/<int:customer_id>/visits", methods=["GET"])
def customer_visits(customer_id):
    """Session history: every past check-in/checkout for this customer, with its order."""
    conn = get_db()
    row = _get_customer_or_404(conn, customer_id)
    if not row:
        conn.close()
        return jsonify({"error": "Customer not found"}), 404

    rows = conn.execute(
        "SELECT * FROM visits WHERE customer_id=? ORDER BY check_out DESC", (customer_id,)
    ).fetchall()
    conn.close()

    result = []
    for r in rows:
        try:
            items = json.loads(r["items_json"])
        except (TypeError, ValueError):
            items = []
        result.append({
            "id": r["id"],
            "check_in": r["check_in"],
            "check_out": r["check_out"],
            "time_cost": r["time_cost"],
            "items_cost": r["items_cost"],
            "total_cost": r["total_cost"],
            "items": items,
            "payment_method": r["payment_method"],
            "is_premium": bool(r["is_premium"]),
            "discount_percent": r["discount_percent"],
            "discount_amount": r["discount_amount"],
        })
    return jsonify(result)


@app.route("/api/visits/<int:visit_id>", methods=["DELETE"])
@require_admin
def admin_delete_visit(visit_id):
    """Admin-only: delete a receipt (a checkout or takeaway row in `visits`), e.g. one
    rung up by mistake. It drops out of revenue reports and session history."""
    conn = get_db()
    cur = conn.execute("DELETE FROM visits WHERE id=?", (visit_id,))
    conn.commit()
    conn.close()
    if cur.rowcount == 0:
        return jsonify({"error": "Receipt not found"}), 404
    return jsonify({"deleted": True})


# ---------- Reports ----------

REPORT_PERIOD_DAYS = {"last_week": 7, "last_month": 30, "last_3_months": 90}


@app.route("/api/reports", methods=["GET"])
@require_admin
def get_reports():
    """Revenue reporting over a time window: totals, per-product revenue, top
    customers. Days are calendar days (12am to 12am), since the shop runs 24/7.
    `period` is 'today' (since 12am),
    one of REPORT_PERIOD_DAYS' keys (from 12am that many days ago up to now), or
    'custom' with `start`/`end` query params (YYYY-MM-DD, end inclusive)."""
    period = request.args.get("period", "last_week")
    now = datetime.now()
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)

    if period == "today":
        start = midnight
        end = now
    elif period == "custom":
        start_str = request.args.get("start")
        end_str = request.args.get("end")
        if not start_str or not end_str:
            return jsonify({"error": "start and end are required for a custom range"}), 400
        try:
            start = datetime.strptime(start_str, "%Y-%m-%d")
            end = datetime.strptime(end_str, "%Y-%m-%d") + timedelta(days=1)
        except ValueError:
            return jsonify({"error": "start and end must be YYYY-MM-DD"}), 400
    elif period in REPORT_PERIOD_DAYS:
        start = midnight - timedelta(days=REPORT_PERIOD_DAYS[period])
        end = now
    else:
        return jsonify({"error": "Invalid period"}), 400

    if start > end:
        return jsonify({"error": "start must be before end"}), 400

    # The window's upper bound is exclusive, so a rolling window ending exactly at `now`
    # would drop an order rung up in the same second the report was opened.
    query_end = end if period == "custom" else end + timedelta(seconds=1)

    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM visits WHERE check_out >= ? AND check_out < ? ORDER BY check_out",
        (start.strftime(DT_FMT), query_end.strftime(DT_FMT)),
    ).fetchall()

    total_revenue = 0
    time_revenue = 0
    items_revenue = 0
    premium_revenue = 0
    takeaway_revenue = 0
    takeaway_count = 0
    discount_total = 0
    products = {}       # item id -> {id, name, qty, revenue}
    customer_totals = {}  # customer id -> {visit_count, total_spent}
    payment_methods = {}  # method (or "unknown") -> {method, count, revenue}
    receipts = []

    for r in rows:
        total_revenue += r["total_cost"]
        time_revenue += r["time_cost"]
        items_revenue += r["items_cost"]
        discount_total += r["discount_amount"]
        if r["is_premium"]:
            premium_revenue += r["time_cost"]

        method = r["payment_method"] or "unknown"
        pm = payment_methods.setdefault(method, {"method": method, "count": 0, "revenue": 0})
        pm["count"] += 1
        pm["revenue"] += r["total_cost"]

        try:
            items = json.loads(r["items_json"])
        except (TypeError, ValueError):
            items = []
        receipts.append({
            "id": r["id"],
            "customer_id": r["customer_id"],
            "check_in": r["check_in"],
            "check_out": r["check_out"],
            "time_cost": r["time_cost"],
            "items": items,
            "discount_percent": r["discount_percent"],
            "discount_amount": r["discount_amount"],
            "total_cost": r["total_cost"],
            "payment_method": r["payment_method"],
        })
        for it in items:
            entry = products.setdefault(it.get("id"), {
                "id": it.get("id"), "name": it.get("name"), "qty": 0, "revenue": 0,
            })
            entry["qty"] += it.get("qty", 0)
            entry["revenue"] += it.get("line_total", 0)

        if r["customer_id"] is None:  # takeaway order — no customer to credit it to
            takeaway_revenue += r["total_cost"]
            takeaway_count += 1
            continue
        cust = customer_totals.setdefault(
            r["customer_id"], {"visit_count": 0, "total_spent": 0, "seconds_on_site": 0}
        )
        cust["visit_count"] += 1
        cust["total_spent"] += r["total_cost"]
        try:
            cust["seconds_on_site"] += int(
                (parse_dt(r["check_out"]) - parse_dt(r["check_in"])).total_seconds()
            )
        except (TypeError, ValueError):
            pass  # unparseable timestamp — count the money, skip the time

    customer_info = {}
    if customer_totals:
        placeholders = ",".join("?" for _ in customer_totals)
        for c in conn.execute(
            f"SELECT id, first_name, last_name, phone FROM customers WHERE id IN ({placeholders})",
            tuple(customer_totals.keys()),
        ):
            customer_info[c["id"]] = c
    conn.close()

    top_customers = []
    for cid, totals in customer_totals.items():
        info = customer_info.get(cid)
        top_customers.append({
            "id": cid,
            "first_name": info["first_name"] if info else "Deleted",
            "last_name": info["last_name"] if info else "customer",
            "phone": info["phone"] if info else "",
            "visit_count": totals["visit_count"],
            "seconds_on_site": totals["seconds_on_site"],
            "total_spent": round_money(totals["total_spent"]),
        })
    top_customers.sort(key=lambda c: c["total_spent"], reverse=True)
    for group in (payment_methods.values(), products.values()):
        for entry in group:
            entry["revenue"] = round_money(entry["revenue"])

    for rec in receipts:
        info = customer_info.get(rec["customer_id"])
        if rec["customer_id"] is None:
            rec["customer_name"] = None  # takeaway
        elif info:
            rec["customer_name"] = f"{info['first_name']} {info['last_name']}"
        else:
            rec["customer_name"] = "Deleted customer"
    receipts.reverse()  # newest first

    return jsonify({
        "start": start.strftime(DT_FMT),
        "end": min(end, now).strftime(DT_FMT),
        "visit_count": len(rows) - takeaway_count,
        "takeaway_count": takeaway_count,
        "total_revenue": round_money(total_revenue),
        "time_revenue": round_money(time_revenue),
        "items_revenue": round_money(items_revenue),
        "premium_revenue": round_money(premium_revenue),
        "takeaway_revenue": round_money(takeaway_revenue),
        "discount_total": round_money(discount_total),
        "payment_methods": sorted(payment_methods.values(), key=lambda p: p["revenue"], reverse=True),
        "products": sorted(products.values(), key=lambda p: p["revenue"], reverse=True),
        "top_customers": top_customers[:10],
        "receipts": receipts,
    })


# ---------- Menu ----------

@app.route("/api/menu", methods=["GET"])
def get_menu():
    conn = get_db()
    rows = conn.execute("SELECT * FROM menu_items ORDER BY category, id").fetchall()
    conn.close()

    grouped = {cat: [] for cat in CATEGORY_ORDER}
    for r in rows:
        grouped.setdefault(r["category"], []).append({
            "id": r["id"], "name": r["name"], "name_ar": r["name_ar"], "price": r["price"],
        })

    # Categories an admin created that aren't in menu_data.py go last, in name order.
    extra = sorted(cat for cat in grouped if cat not in CATEGORY_IMAGES)
    categories = []
    for cat in CATEGORY_ORDER + extra:
        categories.append({
            "name": cat,
            "image": f"/static/images/{CATEGORY_IMAGES[cat]}" if cat in CATEGORY_IMAGES else None,
            "items": grouped.get(cat, []),
        })
    return jsonify(categories)


@app.route("/api/menu", methods=["POST"])
@require_admin
def admin_add_menu_item():
    """Admin-only: add a new menu item, to an existing category or a new one."""
    body = request.get_json(force=True) or {}
    category = (body.get("category") or "").strip()
    name = (body.get("name") or "").strip()
    name_ar = (body.get("name_ar") or "").strip() or None
    if not category or not name:
        return jsonify({"error": "category and name are required"}), 400
    try:
        price = parse_money(body.get("price"))
    except (TypeError, ValueError):
        return jsonify({"error": "price must be 0 or more, with at most one decimal place"}), 400

    conn = get_db()
    cur = conn.execute(
        "INSERT INTO menu_items (category, name, name_ar, price) VALUES (?, ?, ?, ?)",
        (category, name, name_ar, price),
    )
    conn.commit()
    conn.close()
    return jsonify({"id": cur.lastrowid, "category": category, "name": name,
                    "name_ar": name_ar, "price": price}), 201


@app.route("/api/menu/<int:item_id>", methods=["DELETE"])
@require_admin
def admin_delete_menu_item(item_id):
    """Admin-only: remove a menu item. Past receipts keep its name/price, since
    visits.items_json stores a copy rather than a reference."""
    conn = get_db()
    cur = conn.execute("DELETE FROM menu_items WHERE id=?", (item_id,))
    conn.commit()
    conn.close()
    if cur.rowcount == 0:
        return jsonify({"error": "Menu item not found"}), 404
    return jsonify({"deleted": True})


@app.route("/api/menu/<int:item_id>", methods=["PUT"])
@require_admin
def admin_update_menu_item(item_id):
    """Admin-only: edit a menu item's price (and optionally its name)."""
    body = request.get_json(force=True) or {}
    conn = get_db()
    row = conn.execute("SELECT * FROM menu_items WHERE id=?", (item_id,)).fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "Menu item not found"}), 404

    try:
        price = parse_money(body.get("price", row["price"]))
    except (TypeError, ValueError):
        conn.close()
        return jsonify({"error": "price must be 0 or more, with at most one decimal place"}), 400

    name = (body.get("name") or row["name"]).strip()
    name_ar = body.get("name_ar", row["name_ar"])

    conn.execute(
        "UPDATE menu_items SET price=?, name=?, name_ar=? WHERE id=?",
        (price, name, name_ar, item_id),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM menu_items WHERE id=?", (item_id,)).fetchone()
    conn.close()
    return jsonify({"id": row["id"], "category": row["category"], "name": row["name"],
                     "name_ar": row["name_ar"], "price": row["price"]})


if __name__ == "__main__":
    init_db()
    app.run(host="127.0.0.1", port=5000, debug=True)
