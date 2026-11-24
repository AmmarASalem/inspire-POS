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

`start_inspire.bat` starts the Flask app hidden via `pythonw.exe` (bypassing `app.py`'s `__main__` debug/reloader entirely — `run_server.py` calls `database.init_db()` and `app.run()` directly, since Werkzeug's reloader spawning a second process is a liability for something meant to run unattended), waits for `http://127.0.0.1:5000/` to answer, then opens it full-screen in Chrome/Edge `--kiosk` mode using a dedicated profile under `deploy/windows/kiosk-profile/` (gitignored) so it doesn't collide with the cashier's normal browser profile. `start_inspire_silent.vbs` just runs that `.bat` with a hidden window so nothing flashes on screen. <kbd>Alt+F4</kbd> exits kiosk mode.

If the server never comes up (`start_inspire.bat` times out after 20s waiting on `http://127.0.0.1:5000/`, or `start_inspire_silent.vbs` does nothing visible at all), the cause is invisible by construction: `pythonw.exe` has no console, so a startup exception (bad venv, missing dependency, a locked `inspire.db`, etc.) just vanishes instead of printing anywhere. `deploy/windows/start_inspire_debug.bat` runs the identical startup command with `python.exe` instead, in the foreground with a trailing `pause`, specifically to surface that swallowed traceback — use it once to diagnose, then go back to the normal Startup/`.vbs` setup once fixed. It's a diagnostic script, not part of the deploy path.

Both launchers run `deploy/windows/run_server.py`, which appends any startup traceback to `deploy/windows/server.log` (gitignored). That file is the first place to look when the till comes up blank. For a till with no internet, `fetch_offline_wheels.bat` (run on a connected machine) downloads the dependency wheels into `deploy/windows/wheels/`, and `setup_till.bat` creates `venv\` and installs from them offline.

On Windows, receipt printing goes through `python-escpos`'s `Win32Raw` backend (pywin32) to the OS default printer; on Linux/macOS it uses the CUPS `lp` path (see below). Either way, `print_receipt()` fails closed (returns `printed: False`) rather than raising, so checkout itself still works — see `POST /api/print-receipt` for the frontend's retry path.

### Database backups

Backups are **manual**: roughly once a week, someone copies `inspire.db` (in the repo folder) onto a flash drive. There is no backup script or scheduled job. The till has no internet, so cloud backup isn't an option, and the flash drive also covers a failure of the till's own disk.

`inspire.db` is the *only* thing that needs backing up — it holds every customer, receipt, menu edit and rate setting. Everything else is in git.

When copying:
- **Do it while nobody is mid-checkout.** The server runs all the time, and a plain file copy taken in the same instant as a write could catch the file half-updated. Writes take milliseconds, so in practice this only means not copying while a checkout or order is being saved. If an `inspire.db-journal` file sits next to `inspire.db` at that moment, a write is in progress: wait a second and copy again.
- **Give each copy a dated name** (e.g. `inspire_2026-11-24.db`) instead of overwriting last week's. If the live DB is ever corrupted without anyone noticing, overwriting would replace the last good copy with the bad one.

To restore: stop the server (reboot the till, or end the `pythonw.exe` process in Task Manager), replace `inspire.db` with the backup copy renamed back to `inspire.db`, then start it again (`start_inspire.bat`, or reboot). On startup, `init_db()` brings an older backup's schema up to date automatically.

The `backups/` folder (gitignored) is left over from an earlier automated backup script and is no longer written to.

## Architecture

**Backend** (`app.py`, single file, all routes) + **SQLite** (`database.py`, stdlib `sqlite3`, no ORM) + **vanilla JS frontend** (`templates/index.html` + `static/js/app.js`, single-page — views are `<section>`s toggled by JS, not separate routes).

### Billing logic (`app.py`)

- Hourly customers (`status == "not_subscribed"`): `compute_time_cost()` charges the first-hour rate (30 LE) for the first hour, then the extra-hour rate (10 LE) per additional hour — but no hour, the first included, is billed until more than `HOUR_GRACE_MINUTES` (15) of it have passed, i.e. `hours = max(0, ceil((minutes - 15) / 60))`: a stay of 15m or less is free, 16m bills 1 hour, 2h08m bills 2, 2h16m bills 3. The grace applies per calendar day, so a stay crossing midnight by 15m or less isn't charged a new first hour. Rates live in the `settings` table (admin-editable); the grace period is a constant mirrored in `static/js/app.js`.
- **Money has one decimal place**: all amounts are LE with up to one decimal (e.g. 112.5) — menu prices, rates, daily cap, subscription prices, line totals, discounts, totals. Input is validated by `parse_money()` (`parseMoneyInput()` in JS). Every sum or product goes through `round_money()` (`roundMoney()` in JS), so float noise never gets stored or shown. Amounts display via `le()` in JS and `_le()` in `receipt_printer.py`, which drop a trailing `.0` (`125 LE`, `112.5 LE`). The existing `INTEGER`-declared columns store the decimals as REAL without a migration.
- **Discount**: checkout and takeaway accept an optional `discount_percent` (0–100, blank = none) applied to the whole bill (time + items). `discount_amount_for()` rounds to the nearest 0.1 LE, half up, working in tenths. It's mirrored step for step in `app.js` (`discountAmountFor`) for the cart preview, so the preview always matches the receipt: change both together. `visits.total_cost` is stored *net* of the discount, alongside `discount_percent`/`discount_amount`; `time_cost`/`items_cost` stay gross, so report totals reconcile as time + items − discounts.
- Subscribers (`weekly`/`monthly`/`full_day`, collectively `SUBSCRIPTION_STATUSES`) pay no hourly charge at checkout — anything not `not_subscribed` skips `compute_time_cost()`.
- `full_day` is a flat `FULL_DAY_RATE` (100 LE) day-pass, charged the same way weekly/monthly are (the cashier just confirms payment in the upgrade modal; the app doesn't itself move money). It lasts 24 hours from purchase, since the shop runs 24/7. (It used to expire at 2:30am, when the shop closed at 2am.) All three passes are fixed durations in `SUBSCRIPTION_DURATIONS` (weekly 7d, monthly 30d, full_day 24h), applied by `compute_subscription_end()`.
- A "day" is a calendar day, 12am to 12am (`BUSINESS_DAY_RESET_HOUR:MINUTE` = 00:00). The daily hourly cap resets at that boundary (`next_day_boundary()`), and reports use it too.
- `sync_customer_status()` is called on every customer read (list/get/checkout/etc.) and **lazily reverts** an expired subscription (weekly/monthly/full_day) back to `not_subscribed` by comparing the computed end against now — there is no cron/background job doing this.
- Check-in/checkout: `check_in_time` on the `customers` row marks "on-site". Checkout computes the total, inserts an audit row into `visits` (`check_in`, `check_out`, cost breakdown, `items_json`), and clears `check_in_time`.
- **Takeaway orders** (`POST /api/takeaway`, "🥤 Takeaway Order" in the sidebar) are for a walk-in buying food/drink to go: items only, no hourly charge, no check-in, and **no customer record at all** — asking a phone number for one coffee is friction the cashier doesn't need. They're still recorded in `visits` so they count towards revenue reports, as a zero-length visit (`check_in == check_out`) with `time_cost = 0` and a **NULL `customer_id`**, which is what marks a row as takeaway. That meant dropping `visits.customer_id`'s `NOT NULL`; as with the status CHECK above, SQLite can't `ALTER` that away, so `database.py`'s `_migrate_visits_customer_id_nullable()` rebuilds the table once. It copies columns explicitly, so it must run *after* the `_ensure_column` calls that add `payment_method`/`is_premium`. Reports keep NULL-customer rows out of Top Customers and break them out as their own `takeaway_revenue`/`takeaway_count`; the receipt (both printed and on-screen) drops the customer and time-charge blocks rather than printing them empty.
- `customers.status` has **no SQL CHECK constraint** — status values are validated in `app.py` only (`upgrade_customer`, `admin_update_customer`). This is deliberate: SQLite can't `ALTER` a `CHECK`, so adding `full_day` after the fact meant `database.py`'s `_migrate_drop_customers_status_check()` rebuilds the table once (copy → drop → rename) to strip the old constraint rather than requiring a fresh DB.

### Menu (`menu_data.py`)

`MENU_ITEMS` is hand-transcribed (category, English name, Arabic name, price in LE) from the physical menu photos. `CATEGORY_IMAGES`/`CATEGORY_ORDER` map each category to the source photo (`static/images/menu-*.webp`) that illustrates it, surfaced by `GET /api/menu` for the checkout UI's category tabs — these images are themselves cropped/converted from the menu photos and show real prices, so they need to be regenerated (not just `menu_data.py` edited) whenever prices change, or the checkout UI's illustration will contradict the actual price list below it.

`database.py`'s `init_db()` only seeds `menu_items` from `MENU_ITEMS` if the table is empty — on an existing DB it instead calls `_migrate_reseed_menu()`, which wipes and reseeds *only if* `settings.menu_version` is below `database.MENU_VERSION`. This is a one-time-per-overhaul migration, not a sync-on-every-start: prices an admin edits and items they add/delete via Admin mode survive restarts. To roll out a new `menu_data.py` overhaul to existing tills, bump `MENU_VERSION` (this wipes admin edits, so only for a real overhaul). The version is stored rather than inferred from "does category X exist" (the old `'Pancake'` check) because admins can delete items — removing every item in a marker category would otherwise wipe the menu on the next restart.

Admins can add items (`POST /api/menu`) to an existing category or a new one, and delete items (`DELETE /api/menu/<id>`). Categories not in `CATEGORY_ORDER` are listed after it, alphabetically, with `image: null`. Deleting an item doesn't affect past receipts: `visits.items_json` stores a copy of name/price, not a reference.

### Admin mode (`app.py`, `static/js/app.js`)

A single shared PIN (`ADMIN_PIN`, default `"1234"`, overridable via the `INSPIRE_ADMIN_PIN` env var) gates rates, reports, menu add/edit/delete, customer edit/delete and receipt deletion — there's no per-user auth, this is a physical single-till app. The frontend prompts for the PIN once per browser session (`sessionStorage`), then sends it as an `X-Admin-Pin` header on every admin call (`adminApi()` wrapper around `api()`); the backend's `require_admin` decorator checks that header against `ADMIN_PIN` on each admin route — there's no session/token, so the PIN is effectively re-checked per request. Admin actions triggered outside the Admin page (e.g. the "Edit" button on the Customers list) go through `withAdmin(action)`, which asks for the PIN first if needed and then runs the action.

Reports (`GET /api/reports`) use calendar days, 12am to 12am, because the shop runs 24/7. "Today" starts at midnight, and Last Week/Month/3 Months start at midnight 7/30/90 days ago. Reports also return a per-payment-method breakdown (`payment_methods`, with NULL shown as "Not recorded"), total `discount_total`, and every receipt in the range (`receipts`, newest first). The Admin page lists those receipts with a Delete button (`DELETE /api/visits/<id>`), which removes the `visits` row from reports and session history entirely, with no soft-delete or audit trail. `DELETE` refuses to remove a customer who's currently checked in, and deletes their `visits` rows first (no `ON DELETE CASCADE` in the schema). Change the default PIN before the till goes live.

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
