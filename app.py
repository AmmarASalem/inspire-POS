import math
import sqlite3
from datetime import datetime, timedelta

from flask import Flask, jsonify, render_template, request

from database import get_db, init_db
from menu_data import CATEGORY_IMAGES, CATEGORY_ORDER
import receipt_printer

app = Flask(__name__)

FIRST_HOUR_RATE = 30
EXTRA_HOUR_RATE = 10
SUBSCRIPTION_DURATIONS = {
    "weekly": timedelta(days=7),
    "monthly": timedelta(days=30),
}

DT_FMT = "%Y-%m-%d %H:%M:%S"


def now_str():
    return datetime.now().strftime(DT_FMT)


def parse_dt(s):
    return datetime.strptime(s, DT_FMT)


def compute_time_cost(check_in_str, at=None):
    """First hour flat FIRST_HOUR_RATE, every additional started hour EXTRA_HOUR_RATE."""
    at = at or datetime.now()
    elapsed_minutes = (at - parse_dt(check_in_str)).total_seconds() / 60
    if elapsed_minutes <= 60:
        return FIRST_HOUR_RATE, 1
    extra_hours = math.ceil((elapsed_minutes - 60) / 60)
    return FIRST_HOUR_RATE + extra_hours * EXTRA_HOUR_RATE, 1 + extra_hours


def sync_customer_status(conn, row):
    """Lazily revert an expired weekly/monthly subscription back to not_subscribed.
    Returns a plain dict for the customer, including a computed subscription_end."""
    data = dict(row)
    if data["status"] in SUBSCRIPTION_DURATIONS and data["subscription_start"]:
        start = parse_dt(data["subscription_start"])
        end = start + SUBSCRIPTION_DURATIONS[data["status"]]
        if datetime.now() >= end:
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
    else:
        data["subscription_end"] = None
    return data


def customer_public(data):
    out = {
        "id": data["id"],
        "phone": data["phone"],
        "first_name": data["first_name"],
        "last_name": data["last_name"],
        "status": data["status"],
        "subscription_start": data["subscription_start"],
        "subscription_end": data.get("subscription_end"),
        "check_in_time": data["check_in_time"],
        "created_at": data["created_at"],
    }
    if data["check_in_time"]:
        cost, hours = compute_time_cost(data["check_in_time"])
        out["elapsed_seconds"] = int((datetime.now() - parse_dt(data["check_in_time"])).total_seconds())
        out["running_time_cost"] = cost if data["status"] == "not_subscribed" else 0
        out["billed_hours"] = hours
    return out


@app.route("/")
def index():
    return render_template("index.html")


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
    result = [customer_public(sync_customer_status(conn, r)) for r in rows]
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
    data = customer_public(sync_customer_status(conn, row))
    conn.close()
    return jsonify(data), 201


@app.route("/api/customers/eligible", methods=["GET"])
def eligible_customers():
    """Customers currently on an active weekly/monthly subscription (no hourly charge)."""
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM customers WHERE status IN ('weekly','monthly') ORDER BY subscription_start DESC"
    ).fetchall()
    result = []
    for r in rows:
        data = sync_customer_status(conn, r)
        if data["status"] in ("weekly", "monthly"):
            result.append(customer_public(data))
    conn.close()
    return jsonify(result)


@app.route("/api/customers/checked-in", methods=["GET"])
def checked_in_customers():
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM customers WHERE check_in_time IS NOT NULL ORDER BY check_in_time ASC"
    ).fetchall()
    result = [customer_public(sync_customer_status(conn, r)) for r in rows]
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
    data = customer_public(sync_customer_status(conn, row))
    conn.close()
    return jsonify(data)


@app.route("/api/customers/<int:customer_id>/upgrade", methods=["POST"])
def upgrade_customer(customer_id):
    body = request.get_json(force=True) or {}
    status = body.get("status")
    payment_confirmed = bool(body.get("payment_confirmed"))

    if status not in ("weekly", "monthly"):
        return jsonify({"error": "status must be 'weekly' or 'monthly'"}), 400
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
    data = customer_public(sync_customer_status(conn, row))
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

    conn.execute("UPDATE customers SET check_in_time=? WHERE id=?", (now_str(), customer_id))
    conn.commit()
    row = _get_customer_or_404(conn, customer_id)
    data = customer_public(sync_customer_status(conn, row))
    conn.close()
    return jsonify(data)


@app.route("/api/customers/<int:customer_id>/checkout", methods=["POST"])
def checkout_customer(customer_id):
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

    data = sync_customer_status(conn, row)

    time_cost = 0
    billed_hours = 0
    if data["status"] == "not_subscribed":
        time_cost, billed_hours = compute_time_cost(data["check_in_time"])

    items_cost = 0
    receipt_items = []
    for entry in ordered_items:
        try:
            item_id = int(entry.get("id"))
            qty = int(entry.get("qty", 1))
        except (TypeError, ValueError):
            continue
        if qty <= 0:
            continue
        menu_row = conn.execute("SELECT * FROM menu_items WHERE id=?", (item_id,)).fetchone()
        if not menu_row:
            continue
        line_total = menu_row["price"] * qty
        items_cost += line_total
        receipt_items.append({
            "id": menu_row["id"],
            "name": menu_row["name"],
            "price": menu_row["price"],
            "qty": qty,
            "line_total": line_total,
        })

    total_cost = time_cost + items_cost
    check_out = now_str()

    import json
    conn.execute(
        """INSERT INTO visits (customer_id, check_in, check_out, time_cost, items_cost, total_cost, items_json)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (customer_id, data["check_in_time"], check_out, time_cost, items_cost, total_cost, json.dumps(receipt_items)),
    )
    conn.execute("UPDATE customers SET check_in_time=NULL WHERE id=?", (customer_id,))
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
        "billed_hours": billed_hours,
        "time_cost": time_cost,
        "items": receipt_items,
        "items_cost": items_cost,
        "total_cost": total_cost,
    }
    conn.close()

    printed, print_message = receipt_printer.print_receipt(receipt)
    receipt["printed"] = printed
    receipt["print_message"] = print_message

    return jsonify(receipt)


@app.route("/api/print-receipt", methods=["POST"])
def reprint_receipt():
    """Manual reprint — lets the cashier retry from the on-screen receipt if the
    printer was off/out of paper/etc. during the automatic print at checkout."""
    receipt = request.get_json(force=True) or {}
    if not receipt.get("customer") or "total_cost" not in receipt:
        return jsonify({"error": "Invalid receipt data"}), 400
    printed, message = receipt_printer.print_receipt(receipt)
    return jsonify({"printed": printed, "message": message})


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

    categories = []
    for cat in CATEGORY_ORDER:
        categories.append({
            "name": cat,
            "image": f"/static/images/{CATEGORY_IMAGES.get(cat, '')}",
            "items": grouped.get(cat, []),
        })
    return jsonify(categories)


if __name__ == "__main__":
    init_db()
    app.run(host="127.0.0.1", port=5000, debug=True)
