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

### Running it on the Windows till machine

The production till machine is Windows, not Linux — the cashier is not expected to touch a terminal. `deploy/windows/` has the launcher scripts; this is a **one-time setup step outside this repo**, redone on any new till machine:

1. Install Python for Windows, then from a Command Prompt in the repo folder: `py -m venv venv` and `venv\Scripts\pip install -r requirements.txt`.
2. Auto-start on boot: press <kbd>Win+R</kbd> → `shell:startup` → Enter, then create a shortcut there pointing at `deploy\windows\start_inspire_silent.vbs` (Browse → set icon to `deploy\windows\inspire.ico`).
3. Desktop fallback icon: create the same shortcut on the Desktop, for the cashier to click if the kiosk window is ever closed. `start_inspire.bat` is idempotent — if the server's already running it just reopens the browser.

`start_inspire.bat` starts the Flask app hidden via `pythonw.exe` (bypassing `app.py`'s `__main__` debug/reloader entirely — it calls `database.init_db()` and `app.run()` directly, since Werkzeug's reloader spawning a second process is a liability for something meant to run unattended), waits for `http://127.0.0.1:5000/` to answer, then opens it full-screen in Chrome/Edge `--kiosk` mode using a dedicated profile under `deploy/windows/kiosk-profile/` (gitignored) so it doesn't collide with the cashier's normal browser profile. `start_inspire_silent.vbs` just runs that `.bat` with a hidden window so nothing flashes on screen. <kbd>Alt+F4</kbd> exits kiosk mode.

If the server never comes up (`start_inspire.bat` times out after 20s waiting on `http://127.0.0.1:5000/`, or `start_inspire_silent.vbs` does nothing visible at all), the cause is invisible by construction: `pythonw.exe` has no console, so a startup exception (bad venv, missing dependency, a locked `inspire.db`, etc.) just vanishes instead of printing anywhere. `deploy/windows/start_inspire_debug.bat` runs the identical startup command with `python.exe` instead, in the foreground with a trailing `pause`, specifically to surface that swallowed traceback — use it once to diagnose, then go back to the normal Startup/`.vbs` setup once fixed. It's a diagnostic script, not part of the deploy path.

**Receipt printing does not yet work on Windows** — `receipt_printer.py` shells out to the Linux/macOS-only CUPS `lp` command (see below); it needs a Windows-specific path (e.g. `python-escpos`'s `Win32Raw` printer, or a raw print via `win32print`) before checkout can print on the till machine. Until that's ported, `print_receipt()` fails closed (returns `printed: False`) rather than raising, so checkout itself still works — see `POST /api/print-receipt` for the frontend's retry path.

## Architecture

**Backend** (`app.py`, single file, all routes) + **SQLite** (`database.py`, stdlib `sqlite3`, no ORM) + **vanilla JS frontend** (`templates/index.html` + `static/js/app.js`, single-page — views are `<section>`s toggled by JS, not separate routes).

### Billing logic (`app.py`)

- Hourly customers (`status == "not_subscribed"`): `compute_time_cost()` charges a flat `FIRST_HOUR_RATE` (30 LE) for the first hour, then `EXTRA_HOUR_RATE` (10 LE) per additional *started* hour (ceil-rounded), from `check_in_time` to now.
- Subscribers (`weekly`/`monthly`/`full_day`, collectively `SUBSCRIPTION_STATUSES`) pay no hourly charge at checkout — anything not `not_subscribed` skips `compute_time_cost()`.
- `full_day` is a flat `FULL_DAY_RATE` (100 LE) day-pass, charged the same way weekly/monthly are (the cashier just confirms payment in the upgrade modal; the app doesn't itself move money). It doesn't expire 24h after purchase — it expires at the *next* `BUSINESS_DAY_RESET_HOUR:BUSINESS_DAY_RESET_MINUTE` (2:30am, a bit past the shop's actual 2am close so a customer running a few minutes late isn't cut off mid-session), computed by `full_day_end()`. `compute_subscription_end()` dispatches between that and the fixed-`timedelta` weekly/monthly math (`SUBSCRIPTION_DURATIONS`, 7d/30d).
- `sync_customer_status()` is called on every customer read (list/get/checkout/etc.) and **lazily reverts** an expired subscription (weekly/monthly/full_day) back to `not_subscribed` by comparing the computed end against now — there is no cron/background job doing this.
- Check-in/checkout: `check_in_time` on the `customers` row marks "on-site". Checkout computes the total, inserts an audit row into `visits` (`check_in`, `check_out`, cost breakdown, `items_json`), and clears `check_in_time`.
- `customers.status` has **no SQL CHECK constraint** — status values are validated in `app.py` only (`upgrade_customer`, `admin_update_customer`). This is deliberate: SQLite can't `ALTER` a `CHECK`, so adding `full_day` after the fact meant `database.py`'s `_migrate_drop_customers_status_check()` rebuilds the table once (copy → drop → rename) to strip the old constraint rather than requiring a fresh DB.

### Menu (`menu_data.py`)

`MENU_ITEMS` is hand-transcribed (category, English name, Arabic name, price in LE) from the physical menu photos. `CATEGORY_IMAGES`/`CATEGORY_ORDER` map each category to the source photo (`static/images/menu-*.webp`) that illustrates it, surfaced by `GET /api/menu` for the checkout UI's category tabs — these images are themselves cropped/converted from the menu photos and show real prices, so they need to be regenerated (not just `menu_data.py` edited) whenever prices change, or the checkout UI's illustration will contradict the actual price list below it.

`database.py`'s `init_db()` only seeds `menu_items` from `MENU_ITEMS` if the table is empty — on an existing DB it instead calls `_migrate_reseed_menu()`, which wipes and reseeds *only if* a category from the current `MENU_ITEMS` (currently checks for `'Pancake'`) isn't present yet. This is a one-time-per-overhaul migration, not a sync-on-every-start: once applied, prices an admin edits via Admin mode survive future restarts instead of being clobbered back to `menu_data.py`'s values. Bumping the menu again later means picking a new "has this migration run" marker category/item the same way.

### Admin mode (`app.py`, `static/js/app.js`)

A single shared PIN (`ADMIN_PIN`, default `"1234"`, overridable via the `INSPIRE_ADMIN_PIN` env var) gates menu price edits and customer edit/delete — there's no per-user auth, this is a physical single-till app. The frontend prompts for the PIN once per browser session (`sessionStorage`), then sends it as an `X-Admin-Pin` header on every admin call (`adminApi()` wrapper around `api()`); the backend's `require_admin` decorator checks that header against `ADMIN_PIN` on each admin route (`GET /api/admin/verify`, `PUT /api/menu/<id>`, `PUT /api/customers/<id>`, `DELETE /api/customers/<id>`) — there's no session/token, so the PIN is effectively re-checked per request. `DELETE` refuses to remove a customer who's currently checked in, and deletes their `visits` rows first (no `ON DELETE CASCADE` in the schema). Change the default PIN before the till goes live.

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
- Payment method dropdown value is `instapay` (labeled "InstaPay") going forward, not `card` — `paymentMethodLabel` in `app.js` still maps the old `card` value so historical session-history entries recorded before the rename keep displaying correctly.
