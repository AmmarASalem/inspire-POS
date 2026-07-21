const FIRST_HOUR_RATE = 30;
const EXTRA_HOUR_RATE = 10;

const state = {
  view: "dashboard",
  menu: null,               // [{name, image, items:[{id,name,name_ar,price}]}]
  activeMenuCategory: null,
  checkout: { customerId: null, customer: null, cart: {}, mode: "checkout" }, // cart: {itemId: qty}, mode: "checkout" | "order"
  lastReceipt: null,
};

let tickHandle = null;

// ---------- utils ----------

async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  let data = null;
  try { data = await res.json(); } catch (e) { /* no body */ }
  if (!res.ok) {
    const msg = (data && data.error) || `Request failed (${res.status})`;
    throw new Error(msg);
  }
  return data;
}

function parseServerDt(s) {
  // "YYYY-MM-DD HH:MM:SS" -> Date (local time)
  if (!s) return null;
  const [d, t] = s.split(" ");
  const [y, m, day] = d.split("-").map(Number);
  const [hh, mm, ss] = t.split(":").map(Number);
  return new Date(y, m - 1, day, hh, mm, ss);
}

function computeTimeCostClient(checkInStr, now = new Date()) {
  const checkIn = parseServerDt(checkInStr);
  const elapsedMinutes = (now - checkIn) / 60000;
  if (elapsedMinutes <= 60) return FIRST_HOUR_RATE;
  const extraHours = Math.ceil((elapsedMinutes - 60) / 60);
  return FIRST_HOUR_RATE + extraHours * EXTRA_HOUR_RATE;
}

function formatElapsed(seconds) {
  seconds = Math.max(0, Math.floor(seconds));
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  const pad = (n) => String(n).padStart(2, "0");
  return h > 0 ? `${h}:${pad(m)}:${pad(s)}` : `${m}:${pad(s)}`;
}

function statusLabel(status) {
  return { not_subscribed: "Not subscribed", weekly: "Weekly", monthly: "Monthly" }[status] || status;
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
    card.innerHTML = `
      <div class="name">${escapeHtml(c.first_name)} ${escapeHtml(c.last_name)}</div>
      <div class="phone">${escapeHtml(c.phone)}</div>
      <span class="badge badge-${c.status}">${statusLabel(c.status)}</span>
      <div class="session-timer" data-timer>0:00</div>
      <div class="session-cost" data-cost></div>
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
    if (card.dataset.status === "not_subscribed") {
      costEl.textContent = `${computeTimeCostClient(card.dataset.checkin, now)} LE so far`;
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
      <td>${c.check_in_time ? "On-site" : "—"}</td>
      <td class="row-actions">
        ${c.check_in_time
          ? `<button class="btn btn-ghost btn-sm" data-edit-order="${c.id}">Edit Order</button>
             <button class="btn btn-ghost btn-sm" data-checkout="${c.id}">Checkout</button>`
          : `<button class="btn btn-ghost btn-sm" data-checkin="${c.id}">Check in</button>`}
        <button class="btn btn-ghost btn-sm" data-upgrade="${c.id}" data-name="${escapeHtml(c.first_name)} ${escapeHtml(c.last_name)}">Upgrade</button>
        <button class="btn btn-ghost btn-sm" data-history="${c.id}" data-name="${escapeHtml(c.first_name)} ${escapeHtml(c.last_name)}">History</button>
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

  document.body.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-upgrade]");
    if (!btn) return;
    upgradeCustomerId = Number(btn.dataset.upgrade);
    document.getElementById("upgrade-customer-name").textContent = btn.dataset.name || "";
    modal.querySelectorAll('input[name="plan"]').forEach((r) => (r.checked = false));
    document.getElementById("upgrade-payment-confirmed").checked = false;
    errorEl.hidden = true;
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
    document.getElementById("checkout-payment-method").value = "cash";
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
      <div class="mi-price">${item.price} LE</div>
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
  const { customer, cart } = state.checkout;
  const itemsEl = document.getElementById("cart-items");
  const emptyEl = document.getElementById("cart-empty");
  itemsEl.innerHTML = "";

  let itemsCost = 0;
  const entries = Object.entries(cart);
  emptyEl.hidden = entries.length !== 0;
  for (const [id, qty] of entries) {
    const item = findMenuItemById(Number(id));
    if (!item) continue;
    const lineTotal = item.price * qty;
    itemsCost += lineTotal;
    const row = document.createElement("div");
    row.className = "cart-row-item";
    row.innerHTML = `<span>${qty} × ${escapeHtml(item.name)}</span><span>${lineTotal} LE</span>`;
    itemsEl.appendChild(row);
  }

  const timeCost = customer.status === "not_subscribed" ? computeTimeCostClient(customer.check_in_time) : 0;
  document.getElementById("cart-time-line").textContent = customer.status === "not_subscribed"
    ? `Checked in at ${customer.check_in_time.split(" ")[1]} — billed hourly`
    : `${statusLabel(customer.status)} subscriber — no hourly charge`;
  document.getElementById("cart-time-cost").textContent = `${timeCost} LE`;
  document.getElementById("cart-items-cost").textContent = `${itemsCost} LE`;
  document.getElementById("cart-total").textContent = `${timeCost + itemsCost} LE`;
}

document.getElementById("btn-confirm-checkout").addEventListener("click", async () => {
  const { customerId, cart, mode } = state.checkout;
  const items = Object.entries(cart).map(([id, qty]) => ({ id: Number(id), qty }));
  try {
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
      body: JSON.stringify({ items, payment_method: paymentMethod }),
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
    ? r.items.map((i) => `<div class="rline"><span>${i.qty} × ${escapeHtml(i.name)}</span><span>${i.line_total} LE</span></div>`).join("")
    : `<div class="rline"><span>No items</span><span>—</span></div>`;
  body.innerHTML = `
    <div class="rline"><span>${escapeHtml(r.customer.first_name)} ${escapeHtml(r.customer.last_name)}</span><span>${escapeHtml(r.customer.phone)}</span></div>
    <div class="rline"><span>Status</span><span>${statusLabel(r.customer.status)}</span></div>
    <hr>
    <div class="rline"><span>Time charge (${r.billed_hours}h billed)</span><span>${r.time_cost} LE</span></div>
    <hr>
    ${itemsHtml}
    <hr>
    <div class="rline"><span>Items subtotal</span><span>${r.items_cost} LE</span></div>
    <div class="rline receipt-total"><span>Total due</span><span>${r.total_cost} LE</span></div>
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

const paymentMethodLabel = { cash: "Cash", card: "Card", wallet: "Mobile wallet", other: "Other" };

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
      ? v.items.map((i) => `<div class="rline"><span>${i.qty} × ${escapeHtml(i.name)}</span><span>${i.line_total} LE</span></div>`).join("")
      : `<div class="rline"><span>No items ordered</span><span>—</span></div>`;
    const payment = v.payment_method ? (paymentMethodLabel[v.payment_method] || v.payment_method) : "—";
    const div = document.createElement("div");
    div.className = "history-entry";
    div.innerHTML = `
      <div class="h-head"><span>Checked in ${v.check_in}</span><span>Checked out ${v.check_out}</span></div>
      <div class="h-items">${itemsHtml}</div>
      <div class="h-totals"><span>Total (time ${v.time_cost} LE + items ${v.items_cost} LE)</span><span>${v.total_cost} LE</span></div>
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
    const checkinBtn = e.target.closest("[data-checkin]:not(#quick-checkin-input)");
    if (checkinBtn) {
      api(`/api/customers/${checkinBtn.dataset.checkin}/checkin`, { method: "POST" })
        .then(() => { toast("Checked in."); refreshCustomers(); refreshDashboard(); })
        .catch((err) => toast(err.message, true));
    }
  });

  setupQuickCheckin();
  setupNewCustomerModal();
  setupUpgradeModal();

  tickClock();
  setInterval(tickClock, 1000);
  setInterval(() => { if (state.view === "dashboard") tickTimers(); }, 1000);
  setInterval(() => { if (state.view === "dashboard") refreshDashboard(); }, 15000);
  setInterval(() => { if (document.getElementById("modal-checkout").hidden === false) renderCart(); }, 1000);

  refreshDashboard();
}

function debounce(fn, wait) {
  let t;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), wait); };
}

document.addEventListener("DOMContentLoaded", setup);
