// Mirrors app.py: a day is 12am to 12am, and the daily hourly cap resets at it.
const BUSINESS_DAY_RESET_HOUR = 0;
const BUSINESS_DAY_RESET_MINUTE = 0;
// Mirrors app.py's HOUR_GRACE_MINUTES: no hour is billed until this many minutes
// into it, the first included (10m is free, 16m bills 1 hour, 2h08m bills 2).
const HOUR_GRACE_MINUTES = 15;

// Used until /api/settings resolves, and as a fallback shape — actual values always
// come from the server (admin-editable, see Admin > Rates & Pricing).
const DEFAULT_SETTINGS = {
  first_hour_rate: 30, extra_hour_rate: 10, daily_hourly_cap: 100,
  weekly_price: 0, monthly_price: 0, full_day_price: 100,
  premium_first_hour_rate: 80, premium_extra_hour_rate: 50,
};

const state = {
  view: "dashboard",
  menu: null,               // [{name, image, items:[{id,name,name_ar,price}]}]
  activeMenuCategory: null,
  checkout: { customerId: null, customer: null, cart: {}, mode: "checkout" }, // cart: {itemId: qty}, mode: "checkout" | "order" | "takeaway"
  lastReceipt: null,
  settings: null,
};

let tickHandle = null;

// ---------- utils ----------

async function api(path, opts = {}) {
  const res = await fetch(path, {
    ...opts,
    headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
  });
  let data = null;
  try { data = await res.json(); } catch (e) { /* no body */ }
  if (!res.ok) {
    const msg = (data && data.error) || `Request failed (${res.status})`;
    throw new Error(msg);
  }
  return data;
}

let adminPin = sessionStorage.getItem("adminPin") || null;

function adminApi(path, opts = {}) {
  return api(path, { ...opts, headers: { ...(opts.headers || {}), "X-Admin-Pin": adminPin } });
}

// Run an admin-only action from anywhere in the app, asking for the PIN first if
// this browser session hasn't unlocked admin mode yet.
let pendingAdminAction = null;

function withAdmin(action) {
  if (adminPin) { action(); return; }
  pendingAdminAction = action;
  document.getElementById("modal-admin-pin").hidden = false;
  document.getElementById("admin-pin-input").focus();
}

// All money allows one decimal place (mirrors app.py's round_money): every sum or
// product of amounts is rounded so float noise never shows up as 112.50000001.
function roundMoney(x) {
  return Math.round((Number(x) || 0) * 10) / 10 + 0;
}

// Amount for display: "112.5 LE", or "125 LE" when there's no fraction.
function le(amount) {
  return roundMoney(amount) + " LE";
}

// Mirrors app.py's discount_amount_for() operation-for-operation (nearest 0.1 LE,
// half up, worked out in tenths) so the cart preview matches the receipt exactly.
function discountAmountFor(subtotal, pct) {
  const subtotalTenths = Math.round(subtotal * 10);
  return roundMoney(Math.floor(subtotalTenths * pct / 100 + 0.5) / 10);
}

// A money input: non-negative, at most one decimal place. null if invalid.
function parseMoneyInput(raw) {
  const n = Number(String(raw).trim());
  if (String(raw).trim() === "" || !Number.isFinite(n) || n < 0) return null;
  return Math.abs(n * 10 - Math.round(n * 10)) > 1e-6 ? null : roundMoney(n);
}

function formatPercent(pct) {
  return `${Number(pct)}%`;
}

function parseServerDt(s) {
  // "YYYY-MM-DD HH:MM:SS" -> Date (local time)
  if (!s) return null;
  const [d, t] = s.split(" ");
  const [y, m, day] = d.split("-").map(Number);
  const [hh, mm, ss] = t.split(":").map(Number);
  return new Date(y, m - 1, day, hh, mm, ss);
}

function settings() {
  return state.settings || DEFAULT_SETTINGS;
}

async function loadSettings() {
  if (state.settings) return state.settings;
  state.settings = await api("/api/settings");
  return state.settings;
}

function nextDayBoundaryClient(start) {
  const cutoff = new Date(start.getFullYear(), start.getMonth(), start.getDate(),
    BUSINESS_DAY_RESET_HOUR, BUSINESS_DAY_RESET_MINUTE, 0, 0);
  return start < cutoff ? cutoff : new Date(cutoff.getTime() + 86400000);
}

function computeTimeCostClient(checkInStr, isPremium, now = new Date()) {
  const s = settings();
  const firstRate = isPremium ? s.premium_first_hour_rate : s.first_hour_rate;
  const extraRate = isPremium ? s.premium_extra_hour_rate : s.extra_hour_rate;
  const cap = isPremium ? null : s.daily_hourly_cap; // private room is uncapped
  let total = 0;
  let segmentStart = parseServerDt(checkInStr);
  while (segmentStart < now) {
    const segmentEnd = new Date(Math.min(nextDayBoundaryClient(segmentStart).getTime(), now.getTime()));
    const elapsedMinutes = (segmentEnd - segmentStart) / 60000;
    const hours = Math.max(0, Math.ceil((elapsedMinutes - HOUR_GRACE_MINUTES) / 60));
    const segCost = hours === 0 ? 0 : roundMoney(firstRate + (hours - 1) * extraRate);
    total = roundMoney(total + (cap == null ? segCost : Math.min(segCost, cap)));
    segmentStart = segmentEnd;
  }
  return total;
}

function formatElapsed(seconds) {
  seconds = Math.max(0, Math.floor(seconds));
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  const pad = (n) => String(n).padStart(2, "0");
  return h > 0 ? `${h}:${pad(m)}:${pad(s)}` : `${m}:${pad(s)}`;
}

function formatDuration(seconds) {
  // Coarser than formatElapsed()'s live timer: totals over a reporting period only
  // need hours and minutes, not a ticking seconds column.
  const total = Math.max(0, Math.floor(seconds || 0));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  if (total > 0 && h === 0 && m === 0) return "<1m";  // don't render a real stay as "0m"
  if (h === 0) return `${m}m`;
  return m === 0 ? `${h}h` : `${h}h ${m}m`;
}

function statusLabel(status) {
  return { not_subscribed: "Not subscribed", weekly: "Weekly", monthly: "Monthly", full_day: "Full Day" }[status] || status;
}

function toast(message, isError = false) {
  const el = document.getElementById("toast");
  el.textContent = message;
  el.classList.toggle("error", isError);
  el.hidden = false;
  clearTimeout(toast._t);
  toast._t = setTimeout(() => { el.hidden = true; }, 3200);
}

function closeAllModals() {
  document.querySelectorAll(".modal-overlay").forEach((m) => (m.hidden = true));
}

// ---------- navigation ----------

function switchView(view) {
  state.view = view;
  document.querySelectorAll(".nav-btn").forEach((b) => b.classList.toggle("active", b.dataset.view === view));
  document.querySelectorAll(".view").forEach((v) => v.classList.toggle("active", v.id === `view-${view}`));
  if (view === "dashboard") refreshDashboard();
  if (view === "customers") refreshCustomers();
  if (view === "subscriptions") refreshSubscriptions();
  if (view === "admin") refreshAdmin();
}

// ---------- clock ----------

function tickClock() {
  const el = document.getElementById("clock");
  el.textContent = new Date().toLocaleString([], { dateStyle: "medium", timeStyle: "medium" });
}

// ---------- dashboard ----------

let checkedInCache = [];

async function refreshDashboard() {
  try {
    checkedInCache = await api("/api/customers/checked-in");
    renderDashboard();
  } catch (e) { toast(e.message, true); }
}

function renderDashboard() {
  const grid = document.getElementById("checked-in-list");
  const empty = document.getElementById("checked-in-empty");
  grid.innerHTML = "";
  empty.hidden = checkedInCache.length !== 0;

  for (const c of checkedInCache) {
    const card = document.createElement("div");
    card.className = "session-card";
    card.dataset.checkin = c.check_in_time;
    card.dataset.status = c.status;
    card.dataset.premium = c.is_premium ? "1" : "0";
    card.innerHTML = `
      <div class="name">${escapeHtml(c.first_name)} ${escapeHtml(c.last_name)}</div>
      <div class="phone">${escapeHtml(c.phone)}</div>
      <span class="badge badge-${c.status}">${statusLabel(c.status)}</span>
      ${c.is_premium ? `<span class="badge badge-premium">🔒 Private Room</span>` : ""}
      <div class="session-timer" data-timer>0:00</div>
      <div class="session-cost" data-cost></div>
      <button class="btn btn-ghost btn-block" data-toggle-premium="${c.id}">${c.is_premium ? "Move to Normal Seating" : "Move to Private Room"}</button>
      <button class="btn btn-ghost btn-block" data-edit-order="${c.id}">Edit Order</button>
      <button class="btn btn-primary btn-block" data-checkout="${c.id}">Checkout</button>
    `;
    grid.appendChild(card);
  }
  tickTimers();
}

function tickTimers() {
  const now = new Date();
  document.querySelectorAll(".session-card").forEach((card) => {
    const checkIn = parseServerDt(card.dataset.checkin);
    const elapsed = (now - checkIn) / 1000;
    card.querySelector("[data-timer]").textContent = formatElapsed(elapsed);
    const costEl = card.querySelector("[data-cost]");
    const isPremium = card.dataset.premium === "1";
    if (isPremium || card.dataset.status === "not_subscribed") {
      costEl.textContent = `${le(computeTimeCostClient(card.dataset.checkin, isPremium, now))} so far`;
    } else {
      costEl.textContent = "No hourly charge (subscribed)";
    }
  });
}

// ---------- quick check-in ----------

let quickSearchDebounce = null;

function setupQuickCheckin() {
  const input = document.getElementById("quick-checkin-input");
  const results = document.getElementById("quick-checkin-results");

  input.addEventListener("input", () => {
    clearTimeout(quickSearchDebounce);
    const q = input.value.trim();
    if (!q) { results.innerHTML = ""; return; }
    quickSearchDebounce = setTimeout(async () => {
      try {
        const customers = await api(`/api/customers?q=${encodeURIComponent(q)}`);
        renderQuickResults(customers, q);
      } catch (e) { toast(e.message, true); }
    }, 200);
  });

  document.addEventListener("click", (e) => {
    if (!e.target.closest(".quick-checkin")) results.innerHTML = "";
  });

  function renderQuickResults(customers, q) {
    results.innerHTML = "";
    if (customers.length === 0) {
      const div = document.createElement("div");
      div.className = "ac-empty";
      div.textContent = "No matching customer. Use “+ New Customer” to add one.";
      results.appendChild(div);
      return;
    }
    for (const c of customers) {
      const div = document.createElement("div");
      div.className = "ac-item";
      const already = !!c.check_in_time;
      div.innerHTML = `
        <span>${escapeHtml(c.first_name)} ${escapeHtml(c.last_name)} <span class="ac-meta">${escapeHtml(c.phone)} · ${statusLabel(c.status)}</span></span>
        <span class="ac-meta">${already ? "already on-site" : "check in →"}</span>
      `;
      if (!already) {
        div.addEventListener("click", async () => {
          try {
            await api(`/api/customers/${c.id}/checkin`, { method: "POST" });
            toast(`${c.first_name} checked in.`);
            input.value = "";
            results.innerHTML = "";
            refreshDashboard();
            if (state.view === "customers") refreshCustomers();
          } catch (e) { toast(e.message, true); }
        });
      }
      results.appendChild(div);
    }
  }
}

// ---------- customers table ----------

async function refreshCustomers() {
  const q = document.getElementById("customer-search").value.trim();
  try {
    const customers = await api(`/api/customers${q ? `?q=${encodeURIComponent(q)}` : ""}`);
    renderCustomers(customers);
  } catch (e) { toast(e.message, true); }
}

function renderCustomers(customers) {
  const tbody = document.getElementById("customers-tbody");
  tbody.innerHTML = "";
  for (const c of customers) {
    const tr = document.createElement("tr");
    const expires = c.subscription_end ? c.subscription_end : "—";
    tr.innerHTML = `
      <td>${escapeHtml(c.first_name)} ${escapeHtml(c.last_name)}</td>
      <td>${escapeHtml(c.phone)}</td>
      <td><span class="badge badge-${c.status}">${statusLabel(c.status)}</span></td>
      <td>${expires}</td>
      <td>${c.check_in_time ? (c.is_premium ? "On-site 🔒" : "On-site") : "—"}</td>
      <td class="row-actions">
        ${c.check_in_time
          ? `<button class="btn btn-ghost btn-sm" data-edit-order="${c.id}">Edit Order</button>
             <button class="btn btn-ghost btn-sm" data-checkout="${c.id}">Checkout</button>`
          : `<button class="btn btn-ghost btn-sm" data-checkin="${c.id}">Check in</button>`}
        <button class="btn btn-ghost btn-sm" data-upgrade="${c.id}" data-name="${escapeHtml(c.first_name)} ${escapeHtml(c.last_name)}">Upgrade</button>
        <button class="btn btn-ghost btn-sm" data-history="${c.id}" data-name="${escapeHtml(c.first_name)} ${escapeHtml(c.last_name)}">History</button>
        <button class="btn btn-ghost btn-sm" data-edit-customer="${c.id}" title="Admin PIN required">Edit</button>
      </td>
    `;
    tbody.appendChild(tr);
  }
}

// ---------- subscriptions / eligible ----------

async function refreshSubscriptions() {
  try {
    const customers = await api("/api/customers/eligible");
    renderSubscriptions(customers);
  } catch (e) { toast(e.message, true); }
}

function renderSubscriptions(customers) {
  const tbody = document.getElementById("eligible-tbody");
  const empty = document.getElementById("eligible-empty");
  tbody.innerHTML = "";
  empty.hidden = customers.length !== 0;
  const now = new Date();
  for (const c of customers) {
    const end = parseServerDt(c.subscription_end);
    const daysLeft = Math.max(0, Math.ceil((end - now) / 86400000));
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${escapeHtml(c.first_name)} ${escapeHtml(c.last_name)}</td>
      <td>${escapeHtml(c.phone)}</td>
      <td><span class="badge badge-${c.status}">${statusLabel(c.status)}</span></td>
      <td>${c.subscription_start}</td>
      <td>${c.subscription_end}</td>
      <td>${daysLeft}</td>
    `;
    tbody.appendChild(tr);
  }
}

// ---------- admin ----------

async function refreshAdmin() {
  if (!adminPin) {
    pendingAdminAction = null; // unlocking from here just loads the admin page
    document.getElementById("modal-admin-pin").hidden = false;
    document.getElementById("admin-pin-input").focus();
    return;
  }
  try {
    const [menu, customers, rateSettings] = await Promise.all([
      api("/api/menu"), api("/api/customers"), api("/api/settings"),
    ]);
    state.menu = menu; // keep checkout modal in sync with any price edits made here
    state.settings = rateSettings;
    renderAdminMenu(menu);
    renderAdminCustomers(customers);
    renderAdminRates(rateSettings);
    if (activeReportRange.period !== "custom") loadReport();
  } catch (e) { toast(e.message, true); }
}

function renderAdminRates(s) {
  document.getElementById("rate-first-hour").value = s.first_hour_rate;
  document.getElementById("rate-extra-hour").value = s.extra_hour_rate;
  document.getElementById("rate-daily-cap").value = s.daily_hourly_cap;
  document.getElementById("rate-premium-first-hour").value = s.premium_first_hour_rate;
  document.getElementById("rate-premium-extra-hour").value = s.premium_extra_hour_rate;
  document.getElementById("rate-weekly").value = s.weekly_price;
  document.getElementById("rate-monthly").value = s.monthly_price;
  document.getElementById("rate-full-day").value = s.full_day_price;
}

function setupAdminRates() {
  document.getElementById("btn-save-rates").addEventListener("click", async () => {
    const fields = {
      first_hour_rate: document.getElementById("rate-first-hour").value,
      extra_hour_rate: document.getElementById("rate-extra-hour").value,
      daily_hourly_cap: document.getElementById("rate-daily-cap").value,
      premium_first_hour_rate: document.getElementById("rate-premium-first-hour").value,
      premium_extra_hour_rate: document.getElementById("rate-premium-extra-hour").value,
      weekly_price: document.getElementById("rate-weekly").value,
      monthly_price: document.getElementById("rate-monthly").value,
      full_day_price: document.getElementById("rate-full-day").value,
    };
    for (const [key, val] of Object.entries(fields)) {
      const n = parseMoneyInput(val);
      if (n === null) { toast("Rates must be 0 or more, with at most one decimal place (e.g. 12.5).", true); return; }
      fields[key] = n;
    }
    try {
      state.settings = await adminApi("/api/settings", { method: "PUT", body: JSON.stringify(fields) });
      toast("Rates & prices updated.");
    } catch (e) { toast(e.message, true); }
  });
}

function setupAdminPinModal() {
  const modal = document.getElementById("modal-admin-pin");
  const form = document.getElementById("form-admin-pin");
  const errorEl = document.getElementById("admin-pin-error");
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    errorEl.hidden = true;
    const pin = document.getElementById("admin-pin-input").value.trim();
    try {
      await api("/api/admin/verify", { headers: { "X-Admin-Pin": pin } });
      adminPin = pin;
      sessionStorage.setItem("adminPin", pin);
      modal.hidden = true;
      form.reset();
      const action = pendingAdminAction;
      pendingAdminAction = null;
      if (action) action();
      if (state.view === "admin") refreshAdmin();
    } catch (e2) {
      errorEl.hidden = false;
    }
  });
}

// ---------- admin reports ----------

let activeReportRange = { period: "last_week", start: null, end: null };

function setupAdminReports() {
  document.querySelectorAll("[data-report-period]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const period = btn.dataset.reportPeriod;
      document.querySelectorAll("[data-report-period]").forEach((b) => b.classList.toggle("active", b === btn));
      document.getElementById("report-custom-range").hidden = period !== "custom";
      if (period !== "custom") {
        activeReportRange = { period, start: null, end: null };
        loadReport();
      }
    });
  });
  document.getElementById("btn-run-custom-report").addEventListener("click", () => {
    const start = document.getElementById("report-start").value;
    const end = document.getElementById("report-end").value;
    if (!start || !end) { toast("Choose both a start and end date.", true); return; }
    activeReportRange = { period: "custom", start, end };
    loadReport();
  });
}

async function loadReport() {
  const { period, start, end } = activeReportRange;
  let url = `/api/reports?period=${period}`;
  if (period === "custom") url += `&start=${start}&end=${end}`;
  try {
    const report = await adminApi(url);
    renderReport(report);
  } catch (e) { toast(e.message, true); }
}

function renderReport(r) {
  const takeawayCount = r.takeaway_count || 0;
  document.getElementById("report-range-label").textContent =
    `${r.start} → ${r.end} · ${r.visit_count} visit${r.visit_count === 1 ? "" : "s"}`
    + ` · ${takeawayCount} takeaway order${takeawayCount === 1 ? "" : "s"}`;

  document.getElementById("report-summary").innerHTML = `
    <div class="report-stat"><span class="rs-label">Total revenue</span><span class="rs-value">${le(r.total_revenue)}</span></div>
    <div class="report-stat"><span class="rs-label">Time charges</span><span class="rs-value">${le(r.time_revenue)}</span></div>
    <div class="report-stat"><span class="rs-label">Items</span><span class="rs-value">${le(r.items_revenue)}</span></div>
    <div class="report-stat"><span class="rs-label">Private room</span><span class="rs-value">${le(r.premium_revenue)}</span></div>
    <div class="report-stat"><span class="rs-label">Takeaway</span><span class="rs-value">${le(r.takeaway_revenue || 0)}</span></div>
    <div class="report-stat"><span class="rs-label">Discounts given</span><span class="rs-value">${r.discount_total ? "−" : ""}${le(r.discount_total)}</span></div>
  `;

  const paytbody = document.getElementById("report-payments-tbody");
  paytbody.innerHTML = "";
  document.getElementById("report-payments-empty").hidden = r.payment_methods.length !== 0;
  for (const p of r.payment_methods) {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${escapeHtml(paymentLabel(p.method))}</td><td>${p.count}</td><td>${le(p.revenue)}</td>`;
    paytbody.appendChild(tr);
  }

  renderReportReceipts(r.receipts);

  const ptbody = document.getElementById("report-products-tbody");
  const pempty = document.getElementById("report-products-empty");
  ptbody.innerHTML = "";
  pempty.hidden = r.products.length !== 0;
  for (const p of r.products) {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${escapeHtml(p.name || "—")}</td><td>${p.qty}</td><td>${le(p.revenue)}</td>`;
    ptbody.appendChild(tr);
  }

  const ctbody = document.getElementById("report-customers-tbody");
  const cempty = document.getElementById("report-customers-empty");
  ctbody.innerHTML = "";
  cempty.hidden = r.top_customers.length !== 0;
  for (const c of r.top_customers) {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${escapeHtml(c.first_name)} ${escapeHtml(c.last_name)}</td><td>${escapeHtml(c.phone)}</td><td>${formatDuration(c.seconds_on_site)}</td><td>${le(c.total_spent)}</td>`;
    ctbody.appendChild(tr);
  }
}

function renderReportReceipts(receipts) {
  const tbody = document.getElementById("report-receipts-tbody");
  tbody.innerHTML = "";
  document.getElementById("report-receipts-empty").hidden = receipts.length !== 0;
  for (const rec of receipts) {
    const itemsText = rec.items.length
      ? rec.items.map((i) => `${i.qty} × ${i.name}`).join(", ")
      : "—";
    const who = rec.customer_name === null ? "Takeaway" : rec.customer_name;
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td class="nowrap">${escapeHtml(rec.check_out)}</td>
      <td>${escapeHtml(who)}${rec.time_cost ? `<div class="subtle">time ${le(rec.time_cost)}</div>` : ""}</td>
      <td>${escapeHtml(itemsText)}</td>
      <td>${escapeHtml(paymentLabel(rec.payment_method))}</td>
      <td>${rec.discount_amount ? `${formatPercent(rec.discount_percent)} (−${le(rec.discount_amount)})` : "—"}</td>
      <td class="nowrap">${rec.discount_amount
        ? `<div class="subtle">before: ${le(rec.total_cost + rec.discount_amount)}</div>after: ${le(rec.total_cost)}`
        : `${le(rec.total_cost)}`}</td>
      <td><button class="btn btn-ghost btn-sm btn-danger-ghost" data-delete-receipt="${rec.id}">Delete</button></td>
    `;
    tbody.appendChild(tr);
  }
  tbody.querySelectorAll("[data-delete-receipt]").forEach((btn) =>
    btn.addEventListener("click", () => deleteReceipt(Number(btn.dataset.deleteReceipt)))
  );
}

async function deleteReceipt(id) {
  if (!confirm("Delete this receipt? It will be removed from reports and session history. This cannot be undone.")) return;
  try {
    await adminApi(`/api/visits/${id}`, { method: "DELETE" });
    toast("Receipt deleted.");
    loadReport();
  } catch (e) { toast(e.message, true); }
}

function renderAdminMenu(menu) {
  const container = document.getElementById("admin-menu-list");
  container.innerHTML = "";
  for (const cat of menu) {
    const section = document.createElement("div");
    section.className = "admin-menu-category";
    const h3 = document.createElement("h3");
    h3.textContent = cat.name;
    section.appendChild(h3);
    for (const item of cat.items) {
      const row = document.createElement("div");
      row.className = "admin-menu-row";
      row.innerHTML = `
        <span class="amr-name">${escapeHtml(item.name)} <span class="amr-name-ar">${escapeHtml(item.name_ar || "")}</span></span>
        <input type="number" min="0" step="0.1" class="amr-price" value="${item.price}" data-id="${item.id}">
        <span>LE</span>
        <button class="btn btn-ghost btn-sm" data-save-price="${item.id}">Save</button>
        <button class="btn btn-ghost btn-sm btn-danger-ghost" data-delete-item="${item.id}" data-name="${escapeHtml(item.name)}">Delete</button>
      `;
      section.appendChild(row);
    }
    if (cat.items.length === 0) {
      const empty = document.createElement("div");
      empty.className = "subtle";
      empty.textContent = "No items in this category.";
      section.appendChild(empty);
    }
    container.appendChild(section);
  }

  const datalist = document.getElementById("ami-category-options");
  datalist.innerHTML = "";
  for (const cat of menu) {
    const opt = document.createElement("option");
    opt.value = cat.name;
    datalist.appendChild(opt);
  }

  container.querySelectorAll("[data-delete-item]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      if (!confirm(`Remove "${btn.dataset.name}" from the menu? Past receipts keep it.`)) return;
      try {
        await adminApi(`/api/menu/${btn.dataset.deleteItem}`, { method: "DELETE" });
        toast("Item removed.");
        refreshAdmin();
      } catch (e) { toast(e.message, true); }
    });
  });
  container.querySelectorAll("[data-save-price]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const id = Number(btn.dataset.savePrice);
      const input = container.querySelector(`input[data-id="${id}"]`);
      const price = parseMoneyInput(input.value);
      if (price === null) { toast("Price must be 0 or more, with at most one decimal place (e.g. 12.5).", true); return; }
      try {
        await adminApi(`/api/menu/${id}`, { method: "PUT", body: JSON.stringify({ price }) });
        toast("Price updated.");
        state.menu = null; // force a fresh fetch next time the checkout modal opens
      } catch (e) { toast(e.message, true); }
    });
  });
}

function setupAddMenuItemForm() {
  const form = document.getElementById("form-add-menu-item");
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const body = {
      category: document.getElementById("ami-category").value.trim(),
      name: document.getElementById("ami-name").value.trim(),
      name_ar: document.getElementById("ami-name-ar").value.trim(),
      price: parseMoneyInput(document.getElementById("ami-price").value),
    };
    if (!body.category || !body.name) { toast("Category and name are required.", true); return; }
    if (body.price === null) { toast("Price must be 0 or more, with at most one decimal place (e.g. 12.5).", true); return; }
    try {
      await adminApi("/api/menu", { method: "POST", body: JSON.stringify(body) });
      toast(`Added ${body.name}.`);
      // keep the category filled in, since items are usually added a few at a time
      document.getElementById("ami-name").value = "";
      document.getElementById("ami-name-ar").value = "";
      document.getElementById("ami-price").value = "";
      document.getElementById("ami-name").focus();
      refreshAdmin();
    } catch (e2) { toast(e2.message, true); }
  });
}

let adminEditCustomerId = null;

function renderAdminCustomers(customers) {
  const tbody = document.getElementById("admin-customers-tbody");
  tbody.innerHTML = "";
  for (const c of customers) {
    const expires = c.subscription_end ? c.subscription_end : "—";
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${escapeHtml(c.first_name)} ${escapeHtml(c.last_name)}</td>
      <td>${escapeHtml(c.phone)}</td>
      <td><span class="badge badge-${c.status}">${statusLabel(c.status)}</span></td>
      <td>${expires}</td>
      <td class="row-actions">
        <button class="btn btn-ghost btn-sm" data-admin-edit="${c.id}">Edit</button>
        <button class="btn btn-ghost btn-sm" data-admin-delete="${c.id}">Delete</button>
      </td>
    `;
    tbody.appendChild(tr);
  }
  tbody.querySelectorAll("[data-admin-edit]").forEach((btn) =>
    btn.addEventListener("click", () => openAdminEditCustomer(Number(btn.dataset.adminEdit)))
  );
  tbody.querySelectorAll("[data-admin-delete]").forEach((btn) =>
    btn.addEventListener("click", () => deleteAdminCustomer(Number(btn.dataset.adminDelete)))
  );
}

async function openAdminEditCustomer(id) {
  let c;
  try { c = await api(`/api/customers/${id}`); } catch (e) { toast(e.message, true); return; }
  adminEditCustomerId = id;
  document.getElementById("aec-first").value = c.first_name;
  document.getElementById("aec-last").value = c.last_name;
  document.getElementById("aec-phone").value = c.phone;
  document.getElementById("aec-status").value = c.status;
  document.getElementById("aec-error").hidden = true;
  document.getElementById("modal-admin-edit-customer").hidden = false;
}

function setupAdminEditCustomerModal() {
  const form = document.getElementById("form-admin-edit-customer");
  const errorEl = document.getElementById("aec-error");
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    errorEl.hidden = true;
    const body = {
      first_name: document.getElementById("aec-first").value.trim(),
      last_name: document.getElementById("aec-last").value.trim(),
      phone: document.getElementById("aec-phone").value.trim(),
      status: document.getElementById("aec-status").value,
    };
    try {
      await adminApi(`/api/customers/${adminEditCustomerId}`, { method: "PUT", body: JSON.stringify(body) });
      document.getElementById("modal-admin-edit-customer").hidden = true;
      toast("Customer updated.");
      if (state.view === "admin") refreshAdmin();
      if (state.view === "dashboard") refreshDashboard();
      if (state.view === "customers") refreshCustomers();
      if (state.view === "subscriptions") refreshSubscriptions();
    } catch (e2) {
      errorEl.textContent = e2.message;
      errorEl.hidden = false;
    }
  });
}

async function deleteAdminCustomer(id) {
  if (!confirm("Delete this customer? This also deletes their session history. This cannot be undone.")) return;
  try {
    await adminApi(`/api/customers/${id}`, { method: "DELETE" });
    toast("Customer deleted.");
    refreshAdmin();
    if (state.view === "customers") refreshCustomers();
  } catch (e) { toast(e.message, true); }
}

// ---------- new customer modal ----------

function setupNewCustomerModal() {
  const modal = document.getElementById("modal-new-customer");
  const form = document.getElementById("form-new-customer");
  const errorEl = document.getElementById("nc-error");

  document.getElementById("btn-new-customer").addEventListener("click", () => {
    form.reset();
    errorEl.hidden = true;
    modal.hidden = false;
    document.getElementById("nc-first").focus();
  });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    errorEl.hidden = true;
    const body = {
      first_name: document.getElementById("nc-first").value.trim(),
      last_name: document.getElementById("nc-last").value.trim(),
      phone: document.getElementById("nc-phone").value.trim(),
    };
    try {
      await api("/api/customers", { method: "POST", body: JSON.stringify(body) });
      modal.hidden = true;
      toast("Customer created.");
      if (state.view === "customers") refreshCustomers();
    } catch (e2) {
      errorEl.textContent = e2.message;
      errorEl.hidden = false;
    }
  });
}

// ---------- upgrade modal ----------

let upgradeCustomerId = null;

function setupUpgradeModal() {
  const modal = document.getElementById("modal-upgrade");
  const errorEl = document.getElementById("upgrade-error");

  document.body.addEventListener("click", async (e) => {
    const btn = e.target.closest("[data-upgrade]");
    if (!btn) return;
    upgradeCustomerId = Number(btn.dataset.upgrade);
    document.getElementById("upgrade-customer-name").textContent = btn.dataset.name || "";
    modal.querySelectorAll('input[name="plan"]').forEach((r) => (r.checked = false));
    document.getElementById("upgrade-payment-confirmed").checked = false;
    errorEl.hidden = true;
    try { await loadSettings(); } catch (e2) { /* fall back to defaults */ }
    const s = settings();
    document.getElementById("plan-sub-weekly").textContent = `Valid for 7 days — ${le(s.weekly_price)}`;
    document.getElementById("plan-sub-monthly").textContent = `Valid for 30 days — ${le(s.monthly_price)}`;
    document.getElementById("plan-sub-full_day").textContent = `${le(s.full_day_price)} — valid for 24 hours`;
    modal.hidden = false;
  });

  document.getElementById("btn-confirm-upgrade").addEventListener("click", async () => {
    const plan = modal.querySelector('input[name="plan"]:checked');
    const confirmed = document.getElementById("upgrade-payment-confirmed").checked;
    errorEl.hidden = true;
    if (!plan) { errorEl.textContent = "Choose a plan."; errorEl.hidden = false; return; }
    if (!confirmed) { errorEl.textContent = "Please confirm payment before upgrading."; errorEl.hidden = false; return; }
    try {
      await api(`/api/customers/${upgradeCustomerId}/upgrade`, {
        method: "POST",
        body: JSON.stringify({ status: plan.value, payment_confirmed: true }),
      });
      modal.hidden = true;
      toast("Subscription upgraded.");
      if (state.view === "customers") refreshCustomers();
      if (state.view === "subscriptions") refreshSubscriptions();
    } catch (e2) {
      errorEl.textContent = e2.message;
      errorEl.hidden = false;
    }
  });
}

// ---------- checkout modal ----------

async function loadMenu() {
  if (state.menu) return state.menu;
  state.menu = await api("/api/menu");
  return state.menu;
}

async function openCheckoutModal(customerId, mode) {
  try {
    const customer = await api(`/api/customers/${customerId}`);
    if (!customer.check_in_time) {
      toast("This customer is not currently checked in.", true);
      return;
    }
    await loadMenu();
    const cart = {};
    for (const it of customer.current_order || []) cart[it.id] = it.qty;
    state.checkout = { customerId, customer, cart, mode };
    state.activeMenuCategory = state.menu[0]?.name || null;

    document.getElementById("checkout-modal-label").textContent = mode === "order" ? "Edit Order" : "Checkout";
    document.getElementById("checkout-customer-name").textContent = `${customer.first_name} ${customer.last_name}`;
    document.getElementById("payment-method-row").hidden = mode !== "checkout";
    document.getElementById("discount-row").hidden = mode !== "checkout";
    document.getElementById("checkout-discount").value = "";
    document.getElementById("checkout-premium-row").hidden = false;
    document.getElementById("cart-time-line").hidden = false;
    document.getElementById("cart-time-row").hidden = false;
    document.getElementById("checkout-payment-method").value = "cash";
    document.getElementById("checkout-premium-toggle").checked = !!customer.is_premium;
    const confirmBtn = document.getElementById("btn-confirm-checkout");
    confirmBtn.textContent = mode === "order" ? "Save Order" : "Confirm & Check Out";
    renderMenuTabs();
    renderMenuItems();
    renderCart();
    document.getElementById("modal-checkout").hidden = false;
  } catch (e) { toast(e.message, true); }
}

function openCheckout(customerId) {
  return openCheckoutModal(customerId, "checkout");
}

function openOrderEditor(customerId) {
  return openCheckoutModal(customerId, "order");
}

async function openTakeawayModal() {
  // Same menu/cart UI, but with no customer at all: nobody is checked in, so the
  // premium toggle and every time-charge line are hidden and only items are billed.
  try {
    await loadMenu();
    state.checkout = { customerId: null, customer: null, cart: {}, mode: "takeaway" };
    state.activeMenuCategory = state.menu[0]?.name || null;

    document.getElementById("checkout-modal-label").textContent = "Takeaway Order";
    document.getElementById("checkout-customer-name").textContent = "walk-in customer";
    document.getElementById("payment-method-row").hidden = false;
    document.getElementById("discount-row").hidden = false;
    document.getElementById("checkout-discount").value = "";
    document.getElementById("checkout-premium-row").hidden = true;
    document.getElementById("cart-time-line").hidden = true;
    document.getElementById("cart-time-row").hidden = true;
    document.getElementById("checkout-payment-method").value = "cash";
    document.getElementById("btn-confirm-checkout").textContent = "Charge & Print";
    renderMenuTabs();
    renderMenuItems();
    renderCart();
    document.getElementById("modal-checkout").hidden = false;
  } catch (e) { toast(e.message, true); }
}

function renderMenuTabs() {
  const tabs = document.getElementById("menu-tabs");
  tabs.innerHTML = "";
  for (const cat of state.menu) {
    const btn = document.createElement("button");
    btn.className = "menu-tab" + (cat.name === state.activeMenuCategory ? " active" : "");
    btn.textContent = cat.name;
    btn.addEventListener("click", () => {
      state.activeMenuCategory = cat.name;
      renderMenuTabs();
      renderMenuItems();
    });
    tabs.appendChild(btn);
  }
}

function renderMenuItems() {
  const container = document.getElementById("menu-items");
  container.innerHTML = "";
  const cat = state.menu.find((c) => c.name === state.activeMenuCategory);
  if (!cat) return;
  for (const item of cat.items) {
    const qty = state.checkout.cart[item.id] || 0;
    const div = document.createElement("div");
    div.className = "menu-item";
    div.innerHTML = `
      <div class="mi-name">${escapeHtml(item.name)}</div>
      <div class="mi-name-ar">${escapeHtml(item.name_ar || "")}</div>
      <div class="mi-price">${le(item.price)}</div>
      <div class="mi-controls">
        <button class="qty-btn" data-dec="${item.id}">−</button>
        <span class="qty-val">${qty}</span>
        <button class="qty-btn" data-inc="${item.id}">+</button>
      </div>
    `;
    container.appendChild(div);
  }
  container.querySelectorAll("[data-inc]").forEach((b) =>
    b.addEventListener("click", () => changeQty(Number(b.dataset.inc), 1))
  );
  container.querySelectorAll("[data-dec]").forEach((b) =>
    b.addEventListener("click", () => changeQty(Number(b.dataset.dec), -1))
  );
}

document.getElementById("checkout-premium-toggle").addEventListener("change", async (e) => {
  const checked = e.target.checked;
  try {
    const updated = await api(`/api/customers/${state.checkout.customerId}/premium`, {
      method: "POST", body: JSON.stringify({ is_premium: checked }),
    });
    state.checkout.customer = updated;
    renderCart();
  } catch (err) {
    e.target.checked = !checked;
    toast(err.message, true);
  }
});

function findMenuItemById(id) {
  for (const cat of state.menu) {
    const found = cat.items.find((i) => i.id === id);
    if (found) return found;
  }
  return null;
}

function changeQty(itemId, delta) {
  const cart = state.checkout.cart;
  const next = (cart[itemId] || 0) + delta;
  if (next <= 0) delete cart[itemId];
  else cart[itemId] = next;
  renderMenuItems();
  renderCart();
}

function renderCart() {
  const { customer, cart, mode } = state.checkout;
  const itemsEl = document.getElementById("cart-items");
  const emptyEl = document.getElementById("cart-empty");
  itemsEl.innerHTML = "";

  let itemsCost = 0;
  const entries = Object.entries(cart);
  emptyEl.hidden = entries.length !== 0;
  for (const [id, qty] of entries) {
    const item = findMenuItemById(Number(id));
    if (!item) continue;
    const lineTotal = roundMoney(item.price * qty);
    itemsCost = roundMoney(itemsCost + lineTotal);
    const row = document.createElement("div");
    row.className = "cart-row-item";
    row.innerHTML = `<span>${qty} × ${escapeHtml(item.name)}</span><span>${le(lineTotal)}</span>`;
    itemsEl.appendChild(row);
  }

  let timeCost = 0;
  if (mode !== "takeaway") {
    const isPremium = !!customer.is_premium;
    const chargeable = isPremium || customer.status === "not_subscribed";
    timeCost = chargeable ? computeTimeCostClient(customer.check_in_time, isPremium) : 0;
    document.getElementById("cart-time-line").textContent = isPremium
      ? `Private room since ${customer.check_in_time.split(" ")[1]} — billed hourly (premium rate)`
      : chargeable
        ? `Checked in at ${customer.check_in_time.split(" ")[1]} — billed hourly`
        : `${statusLabel(customer.status)} subscriber — no hourly charge`;
    document.getElementById("cart-time-cost").textContent = `${le(timeCost)}`;
  }
  document.getElementById("cart-items-cost").textContent = `${le(itemsCost)}`;

  const subtotal = roundMoney(timeCost + itemsCost);
  const pct = mode === "order" ? 0 : readDiscountPercent();
  const discountRow = document.getElementById("cart-discount-row");
  const validPct = pct !== null && pct > 0;
  const discount = validPct ? discountAmountFor(subtotal, pct) : 0;
  discountRow.hidden = !validPct;
  document.getElementById("cart-subtotal-row").hidden = !validPct;
  if (validPct) {
    document.getElementById("cart-subtotal").textContent = `${le(subtotal)}`;
    document.getElementById("cart-discount-label").textContent = `Discount (${formatPercent(pct)})`;
    document.getElementById("cart-discount-amount").textContent = `−${le(discount)}`;
  }
  document.getElementById("checkout-discount").classList.toggle("invalid", pct === null);
  document.getElementById("cart-total-label").textContent = validPct ? "Total after discount" : "Total";
  document.getElementById("cart-total").textContent = `${le(subtotal - discount)}`;
}

// The optional discount box: 0 when blank, null when it holds something invalid.
function readDiscountPercent() {
  const raw = document.getElementById("checkout-discount").value.trim();
  if (raw === "") return 0;
  const pct = Number(raw);
  return Number.isFinite(pct) && pct >= 0 && pct <= 100 ? pct : null;
}

document.getElementById("btn-confirm-checkout").addEventListener("click", async () => {
  const { customerId, cart, mode } = state.checkout;
  const items = Object.entries(cart).map(([id, qty]) => ({ id: Number(id), qty }));
  const discountPercent = mode === "order" ? 0 : readDiscountPercent();
  if (discountPercent === null) { toast("Discount must be a percentage between 0 and 100.", true); return; }
  try {
    if (mode === "takeaway") {
      if (items.length === 0) { toast("Add at least one item to the order.", true); return; }
      const receipt = await api("/api/takeaway", {
        method: "POST",
        body: JSON.stringify({
          items,
          payment_method: document.getElementById("checkout-payment-method").value,
          discount_percent: discountPercent,
        }),
      });
      document.getElementById("modal-checkout").hidden = true;
      showReceipt(receipt);
      return;
    }
    if (mode === "order") {
      await api(`/api/customers/${customerId}/order`, {
        method: "POST",
        body: JSON.stringify({ items }),
      });
      document.getElementById("modal-checkout").hidden = true;
      toast("Order saved.");
      refreshDashboard();
      if (state.view === "customers") refreshCustomers();
      return;
    }
    const paymentMethod = document.getElementById("checkout-payment-method").value;
    const receipt = await api(`/api/customers/${customerId}/checkout`, {
      method: "POST",
      body: JSON.stringify({ items, payment_method: paymentMethod, discount_percent: discountPercent }),
    });
    document.getElementById("modal-checkout").hidden = true;
    showReceipt(receipt);
    refreshDashboard();
    if (state.view === "customers") refreshCustomers();
  } catch (e) { toast(e.message, true); }
});

function showReceipt(r) {
  state.lastReceipt = r;
  const body = document.getElementById("receipt-body");
  const itemsHtml = r.items.length
    ? r.items.map((i) => `<div class="rline"><span>${i.qty} × ${escapeHtml(i.name)}</span><span>${le(i.line_total)}</span></div>`).join("")
    : `<div class="rline"><span>No items</span><span>—</span></div>`;
  const headerHtml = r.takeaway
    ? `<div class="rline"><span>Takeaway order</span><span>${escapeHtml(r.check_out)}</span></div>`
    : `<div class="rline"><span>${escapeHtml(r.customer.first_name)} ${escapeHtml(r.customer.last_name)}</span><span>${escapeHtml(r.customer.phone)}</span></div>
       <div class="rline"><span>Status</span><span>${statusLabel(r.customer.status)}</span></div>
       <hr>
       <div class="rline"><span>${escapeHtml(r.is_premium
          ? `Private room time charge (${r.billed_hours}h billed)`
          : r.customer.status === "not_subscribed"
            ? `Time charge (${r.billed_hours}h billed)`
            : `Time charge (${statusLabel(r.customer.status)})`)}</span><span>${le(r.time_cost)}</span></div>`;
  const discountHtml = r.discount_amount
    ? `<div class="rline receipt-subtotal"><span>Total before discount</span><span>${le(r.total_cost + r.discount_amount)}</span></div>
       <div class="rline"><span>Discount (${formatPercent(r.discount_percent)})</span><span>−${le(r.discount_amount)}</span></div>`
    : "";
  const paymentHtml = r.payment_method
    ? `<div class="rline subtle"><span>Paid by</span><span>${escapeHtml(paymentLabel(r.payment_method))}</span></div>`
    : "";
  body.innerHTML = `
    ${headerHtml}
    <hr>
    ${itemsHtml}
    <hr>
    <div class="rline"><span>Items subtotal</span><span>${le(r.items_cost)}</span></div>
    ${discountHtml}
    <div class="rline receipt-total"><span>${r.discount_amount ? "Total after discount" : "Total due"}</span><span>${le(r.total_cost)}</span></div>
    ${paymentHtml}
  `;
  renderPrintStatus("printed" in r ? r.printed : null, r.print_message);
  document.getElementById("modal-receipt").hidden = false;
}

function renderPrintStatus(printed, message) {
  const el = document.getElementById("print-status");
  if (printed === true) {
    el.textContent = "Printed to receipt printer.";
    el.className = "print-status ok";
  } else if (printed === false) {
    el.textContent = `Couldn't print: ${message || "unknown error"}`;
    el.className = "print-status fail";
  } else {
    el.textContent = "";
    el.className = "print-status";
  }
}

document.getElementById("btn-reprint").addEventListener("click", async () => {
  if (!state.lastReceipt) return;
  const btn = document.getElementById("btn-reprint");
  btn.disabled = true;
  btn.textContent = "Printing…";
  try {
    const res = await api("/api/print-receipt", {
      method: "POST",
      body: JSON.stringify(state.lastReceipt),
    });
    renderPrintStatus(res.printed, res.message);
    if (!res.printed) toast(res.message, true);
  } catch (e) {
    renderPrintStatus(false, e.message);
    toast(e.message, true);
  } finally {
    btn.disabled = false;
    btn.textContent = "Print / Reprint";
  }
});

// ---------- session history modal ----------

const paymentMethodLabel = { cash: "Cash", instapay: "InstaPay", card: "Card", wallet: "Mobile wallet", other: "Other" };

function paymentLabel(method) {
  if (!method || method === "unknown") return "Not recorded";
  return paymentMethodLabel[method] || method;
}

async function openHistory(customerId, name) {
  document.getElementById("history-customer-name").textContent = name || "";
  document.getElementById("modal-history").hidden = false;
  const list = document.getElementById("history-list");
  list.innerHTML = "";
  try {
    const visits = await api(`/api/customers/${customerId}/visits`);
    renderHistory(visits);
  } catch (e) { toast(e.message, true); }
}

function renderHistory(visits) {
  const list = document.getElementById("history-list");
  const empty = document.getElementById("history-empty");
  list.innerHTML = "";
  empty.hidden = visits.length !== 0;
  for (const v of visits) {
    const itemsHtml = v.items.length
      ? v.items.map((i) => `<div class="rline"><span>${i.qty} × ${escapeHtml(i.name)}</span><span>${le(i.line_total)}</span></div>`).join("")
      : `<div class="rline"><span>No items ordered</span><span>—</span></div>`;
    const payment = v.payment_method ? (paymentMethodLabel[v.payment_method] || v.payment_method) : "—";
    const div = document.createElement("div");
    div.className = "history-entry";
    div.innerHTML = `
      <div class="h-head"><span>Checked in ${v.check_in}</span><span>Checked out ${v.check_out}</span></div>
      <div class="h-items">${itemsHtml}</div>
      ${v.discount_amount ? `
      <div class="h-discount"><span>Total before discount (time ${le(v.time_cost)}${v.is_premium ? " · private room" : ""} + items ${le(v.items_cost)})</span><span>${le(v.total_cost + v.discount_amount)}</span></div>
      <div class="h-discount"><span>Discount (${formatPercent(v.discount_percent)})</span><span>−${le(v.discount_amount)}</span></div>
      <div class="h-totals"><span>Total after discount</span><span>${le(v.total_cost)}</span></div>` : `
      <div class="h-totals"><span>Total (time ${le(v.time_cost)}${v.is_premium ? " · private room" : ""} + items ${le(v.items_cost)})</span><span>${le(v.total_cost)}</span></div>`}
      <div class="h-payment">Payment method: ${escapeHtml(payment)}</div>
    `;
    list.appendChild(div);
  }
}

// ---------- misc ----------

function escapeHtml(str) {
  return String(str).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

function setup() {
  document.querySelectorAll(".nav-btn").forEach((b) =>
    b.addEventListener("click", () => switchView(b.dataset.view))
  );
  document.querySelectorAll("[data-close-modal]").forEach((b) =>
    b.addEventListener("click", closeAllModals)
  );
  document.querySelectorAll(".modal-overlay").forEach((overlay) =>
    overlay.addEventListener("click", (e) => { if (e.target === overlay) overlay.hidden = true; })
  );

  document.getElementById("customer-search").addEventListener("input", debounce(refreshCustomers, 200));

  document.body.addEventListener("click", (e) => {
    const checkoutBtn = e.target.closest("[data-checkout]");
    if (checkoutBtn) { openCheckout(Number(checkoutBtn.dataset.checkout)); return; }
    const editOrderBtn = e.target.closest("[data-edit-order]");
    if (editOrderBtn) { openOrderEditor(Number(editOrderBtn.dataset.editOrder)); return; }
    const historyBtn = e.target.closest("[data-history]");
    if (historyBtn) { openHistory(Number(historyBtn.dataset.history), historyBtn.dataset.name); return; }
    const editCustomerBtn = e.target.closest("[data-edit-customer]");
    if (editCustomerBtn) {
      const id = Number(editCustomerBtn.dataset.editCustomer);
      withAdmin(() => openAdminEditCustomer(id));
      return;
    }
    const premiumBtn = e.target.closest("[data-toggle-premium]");
    if (premiumBtn) {
      const id = Number(premiumBtn.dataset.togglePremium);
      const current = checkedInCache.find((c) => c.id === id);
      const next = !(current && current.is_premium);
      api(`/api/customers/${id}/premium`, { method: "POST", body: JSON.stringify({ is_premium: next }) })
        .then(() => { toast(next ? "Moved to private room." : "Moved to normal seating."); refreshDashboard(); })
        .catch((err) => toast(err.message, true));
      return;
    }
    const checkinBtn = e.target.closest("[data-checkin]:not(#quick-checkin-input)");
    if (checkinBtn) {
      api(`/api/customers/${checkinBtn.dataset.checkin}/checkin`, { method: "POST" })
        .then(() => { toast("Checked in."); refreshCustomers(); refreshDashboard(); })
        .catch((err) => toast(err.message, true));
    }
  });

  document.getElementById("btn-takeaway").addEventListener("click", openTakeawayModal);
  document.getElementById("checkout-discount").addEventListener("input", renderCart);

  setupQuickCheckin();
  setupNewCustomerModal();
  setupUpgradeModal();
  setupAdminPinModal();
  setupAdminEditCustomerModal();
  setupAdminRates();
  setupAdminReports();
  setupAddMenuItemForm();

  tickClock();
  setInterval(tickClock, 1000);
  setInterval(() => { if (state.view === "dashboard") tickTimers(); }, 1000);
  setInterval(() => { if (state.view === "dashboard") refreshDashboard(); }, 15000);
  setInterval(() => { if (document.getElementById("modal-checkout").hidden === false) renderCart(); }, 1000);

  loadSettings().catch(() => {});
  refreshDashboard();
}

function debounce(fn, wait) {
  let t;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), wait); };
}

document.addEventListener("DOMContentLoaded", setup);
