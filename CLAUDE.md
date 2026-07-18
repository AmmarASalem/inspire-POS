# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A cashier/point-of-sale web app for **Inspire Workspace & Café**, run entirely on a single till machine with no internet dependency (SQLite file DB, no CDN assets — fonts, CSS, JS, and menu images are all vendored under `static/`). It handles hourly-rate customers, weekly/monthly subscribers, check-in/checkout, a menu ordering flow, and printing physical receipts on a thermal receipt printer.

There is no automated test suite and no frontend build step (plain HTML/CSS/vanilla JS, no bundler/framework).

## Running it

```bash
# using the existing venv/
venv/bin/pip install -r requirements.txt
venv/bin/python app.py
```

Serves on `http://127.0.0.1:5000`. `app.py`'s `__main__` block calls `database.init_db()` on every start, which runs `schema.sql` (idempotent `CREATE TABLE IF NOT EXISTS`) and seeds `menu_items` from `menu_data.MENU_ITEMS` only if that table is empty — safe to restart repeatedly, and deleting `inspire.db` gives a clean slate (empty customers, full menu reseeded).

On Fedora/externally-managed Python installs, `pip install -r requirements.txt --break-system-packages` also works if not using `venv/`.

## Architecture

**Backend** (`app.py`, single file, all routes) + **SQLite** (`database.py`, stdlib `sqlite3`, no ORM) + **vanilla JS frontend** (`templates/index.html` + `static/js/app.js`, single-page — views are `<section>`s toggled by JS, not separate routes).

### Billing logic (`app.py`)

- Hourly customers (`status == "not_subscribed"`): `compute_time_cost()` charges a flat `FIRST_HOUR_RATE` (30 LE) for the first hour, then `EXTRA_HOUR_RATE` (10 LE) per additional *started* hour (ceil-rounded), from `check_in_time` to now.
- Subscribers (`weekly`/`monthly`) pay no hourly charge at checkout.
- `sync_customer_status()` is called on every customer read (list/get/checkout/etc.) and **lazily reverts** an expired subscription back to `not_subscribed` by comparing `subscription_start` + `SUBSCRIPTION_DURATIONS` (7d/30d) against now — there is no cron/background job doing this.
- Check-in/checkout: `check_in_time` on the `customers` row marks "on-site". Checkout computes the total, inserts an audit row into `visits` (`check_in`, `check_out`, cost breakdown, `items_json`), and clears `check_in_time`.

### Menu (`menu_data.py`)

`MENU_ITEMS` is hand-transcribed (category, English name, Arabic name, price in LE) from the physical menu photos in `photos/*.webp`. `CATEGORY_IMAGES`/`CATEGORY_ORDER` map each category to the source photo that illustrates it, surfaced by `GET /api/menu` for the checkout UI's category tabs.

### Receipt printing (`receipt_printer.py`)

Thermal printers here are driven as **rendered images**, not ESC/POS text commands — this was a deliberate choice after discovering the printer's font wraps text at unpredictable column widths, and to reuse the shop's actual brand fonts:

- Composes the receipt as one tall PIL image (576px wide = 80mm @ 203dpi) via the internal `_ReceiptCanvas` builder (`add_row`, `add_separator`, `add_centered_text`, etc.), using exact per-string `textbbox` measurement rather than a generic line-height estimate (a generic estimate previously clipped descenders/serifs on some strings).
- Title font is `static/fonts/PlayfairDisplay-SemiBold.ttf`, body/subtitle font is `static/fonts/Montserrat-*.ttf` — matched to the actual logo's fonts by visual comparison, not guessed.
- The logo icon is cropped from `photos/image.png` using hardcoded pixel bounds (`ICON_BBOX`) because that source PNG bakes the "INSPIRE / WORKSPACE & CAFE" wordmark into the bitmap too; the wordmark is instead re-rendered from the vector fonts above so it prints crisp instead of a re-dithered bitmap.
- The composed image is thresholded to pure black/white *before* handing it to `python-escpos`, since letting its own dithering step handle a not-quite-flat background produced a visible gray stipple.
- Printing goes through a **raw CUPS queue** named `POS80` (`lp -d POS80 -o raw <file>`), not a real driver — this printer (Xprinter XP-Q807K / POS-80 compatible) has no Linux driver, so CUPS is set up to pass ESC/POS bytes straight through. That queue is a **one-time OS-level setup step outside this repo** (`sudo lpadmin -p POS80 -E -v "usb://Printer/POS-80?serial=..." -m raw`) and must be redone on any new till machine.
- `print_receipt()` is deliberately best-effort and never raises — a disconnected/misconfigured printer must never block a checkout. `app.py`'s checkout route calls it inline and returns `printed`/`print_message` in the JSON response; `POST /api/print-receipt` lets the frontend retry/reprint independently using the last receipt payload.

### Frontend (`static/js/app.js`)

Single `state` object, fetch-based calls to the JSON API, no reactive framework. Notable behavior:
- Client-side timers mirror the server's `compute_time_cost()` formula to show a live running total on checked-in customer cards without polling every second (`setInterval` at 1s just re-renders from cached `check_in_time`; the checked-in list itself is re-fetched from the server every 15s).
- The cream/dark-green color theme (`static/css/style.css`) was sampled programmatically from the shop's actual logo (`photos/image.png`), not picked freehand.
