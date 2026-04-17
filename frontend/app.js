/* app.js — MF Portfolio Analyzer frontend logic */

// ── API BASE (AUTO SWITCH LOCAL / PROD) ──
const API_BASE =
  window.MF_API_BASE ||
  (window.location.hostname === "localhost"
    ? "http://localhost:5000"
    : "https://mf-tool.onrender.com");

// ── State ──────────────────────────────────────────────────────
let fundUniverse = {};
let selectedFunds = new Set();
let frontier = [];
let frontierIndex = null;

let donutChart = null;
let frontierChart = null;

// ── Init ───────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", async () => {
  console.log("INIT START");
  await loadFunds();
  bindEvents();
});

async function loadFunds() {
  try {
    console.log("Fetching funds...");
    const res = await fetch(`${API_BASE}/api/funds`);
    const data = await res.json();

    if (data.status !== "ok") throw new Error("Bad response");

    fundUniverse = data.funds;
    renderFundList(fundUniverse);

    console.log("Funds loaded");
  } catch (e) {
    showError("Backend not reachable.");
    console.error(e);
  }
}

// ── Render fund list ───────────────────────────────────────────
function renderFundList(universe) {
  const container = document.getElementById("fund-list-container");
  if (!container) return;

  container.innerHTML = "";

  for (const [cat, funds] of Object.entries(universe)) {
    const block = document.createElement("div");
    block.className = "category-block";

    const header = document.createElement("div");
    header.className = "cat-header";
    header.textContent = `${cat} (${funds.length})`;

    const list = document.createElement("div");
    list.className = "fund-list hidden";

    funds.forEach(fund => {
      const item = document.createElement("div");
      item.className = "fund-item";

      const cb = document.createElement("input");
      cb.type = "checkbox";

      const label = document.createElement("span");
      label.textContent = fund.name;

      item.appendChild(cb);
      item.appendChild(label);

      item.addEventListener("click", (e) => {
        if (e.target !== cb) cb.checked = !cb.checked;
        toggleFund(fund.scheme_code, cb.checked);
      });

      list.appendChild(item);
    });

    header.addEventListener("click", () => {
      list.classList.toggle("hidden");
    });

    block.appendChild(header);
    block.appendChild(list);
    container.appendChild(block);
  }
}

function toggleFund(code, checked) {
  if (checked) selectedFunds.add(code);
  else selectedFunds.delete(code);

  renderAmountInputs();
}

// ── Amount inputs ──────────────────────────────────────────────
function renderAmountInputs() {
  const container = document.getElementById("amount-inputs");
  const section = document.getElementById("amount-section");

  if (!container || !section) return;

  if (selectedFunds.size === 0) {
    section.style.display = "none";
    return;
  }

  section.style.display = "block";
  container.innerHTML = "";

  for (const code of selectedFunds) {
    const row = document.createElement("div");

    const inp = document.createElement("input");
    inp.type = "number";
    inp.placeholder = "₹ amount";
    inp.dataset.code = code;

    row.appendChild(inp);
    container.appendChild(row);
  }
}

// ── Events ─────────────────────────────────────────────────────
function bindEvents() {
  const btn = document.getElementById("btn-analyze");
  if (btn) btn.addEventListener("click", runAnalysis);
}

// ── Analysis ───────────────────────────────────────────────────
async function runAnalysis() {
  console.log("RUN ANALYSIS CLICKED");

  if (selectedFunds.size < 3) {
    showError("Select at least 3 funds.");
    return;
  }

  const holdings = [];

  document.querySelectorAll("input[data-code]").forEach(inp => {
    const amt = parseFloat(inp.value);
    if (amt > 0) {
      holdings.push({ scheme_code: inp.dataset.code, amount: amt });
    }
  });

  if (holdings.length < 3) {
    showError("Enter valid amounts for all funds.");
    return;
  }

  try {
    showLoader(true);

    const res = await fetch(`${API_BASE}/api/analyze`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ holdings }),
    });

    const data = await res.json();
    console.log("API RESPONSE:", data);

    if (data.status !== "ok") {
      showError(data.message || "Analysis failed.");
      return;
    }

    renderDashboard(data);

  } catch (e) {
    console.error(e);
    showError("Backend connection failed.");
  } finally {
    showLoader(false);
  }
}

// ── Render dashboard ───────────────────────────────────────────
function renderDashboard(data) {
  console.log("RENDERING DASHBOARD");

  const dash = document.getElementById("dashboard");
  const empty = document.getElementById("empty-state");

  if (empty) empty.style.display = "none";
  if (dash) dash.style.display = "block";

  // Minimal render first (avoid crash)
  if (!dash) {
    alert("Dashboard container missing in HTML");
    return;
  }

  dash.innerHTML = `
    <h3>Optimal Portfolio</h3>
    <pre>${JSON.stringify(data.optimal_portfolio, null, 2)}</pre>

    <h3>Actions</h3>
    <pre>${JSON.stringify(data.actions, null, 2)}</pre>
  `;
}

// ── Helpers ────────────────────────────────────────────────────
function showError(msg) {
  console.error("ERROR:", msg);

  const el = document.getElementById("error-banner");

  if (el) {
    el.textContent = msg;
    el.classList.add("visible");
  } else {
    alert(msg);
  }
}

function showLoader(show) {
  const el = document.getElementById("loader");
  if (el) el.style.display = show ? "block" : "none";
}
