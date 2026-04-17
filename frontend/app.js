/* app.js — MF Portfolio Analyzer frontend logic */

// Backend URL
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
  await loadFunds();
  bindEvents();
});

// ── Load Funds ─────────────────────────────────────────────────
async function loadFunds() {
  try {
    const res = await fetch(`${API_BASE}/api/funds`);
    const data = await res.json();
    fundUniverse = data.funds;
    renderFundList(fundUniverse);
  } catch (e) {
    showError("Backend not reachable.");
  }
}

// ── Render fund list ───────────────────────────────────────────
function renderFundList(universe) {
  const container = document.getElementById("fund-list-container");
  container.innerHTML = "";

  for (const [cat, funds] of Object.entries(universe)) {
    const block = document.createElement("div");

    const header = document.createElement("div");
    header.innerHTML = `<b>${cat}</b> (${funds.length})`;

    const list = document.createElement("div");
    list.style.display = "none";

    funds.forEach(fund => {
      const item = document.createElement("div");

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
      list.style.display = list.style.display === "none" ? "block" : "none";
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

// ── Amount Inputs ──────────────────────────────────────────────
function renderAmountInputs() {
  const container = document.getElementById("amount-inputs");
  const section = document.getElementById("amount-section");

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
  document.getElementById("btn-analyze").addEventListener("click", runAnalysis);
}

// ── Analysis ───────────────────────────────────────────────────
async function runAnalysis() {
  clearError();

  if (selectedFunds.size < 3) {
    showError("Select at least 3 funds.");
    return;
  }

  const holdings = [];

  document.querySelectorAll("input[data-code]").forEach(inp => {
    const amt = parseFloat(inp.value);
    if (amt > 0) {
      holdings.push({
        scheme_code: inp.dataset.code,
        amount: amt
      });
    }
  });

  if (holdings.length < 3) {
    showError("Enter valid amounts for all funds.");
    return;
  }

  try {
    console.log("ANALYZE CLICKED");

    const res = await fetch(`${API_BASE}/api/analyze`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({ holdings })
    });

    const data = await res.json();

    console.log("API RESPONSE:", data);

    if (data.status !== "ok") {
      showError(data.message || "Analysis failed.");
      return;
    }

    frontier = data.frontier;
    frontierIndex = data.selected_frontier_index;

    renderDashboard(data);

  } catch (e) {
    console.error(e);
    showError("Something broke. Check console.");
  }
}

// ── Dashboard Render ───────────────────────────────────────────
function renderDashboard(data) {
  const curr = data.current_portfolio;
  const opt = data.optimal_portfolio;

  // Metrics
  setMetric("m-ret-curr", pct(curr.portfolio_return), true);
  setMetric("m-vol-curr", pct(curr.portfolio_volatility));
  setMetric("m-sr-curr", curr.sharpe.toFixed(2));

  setMetric("m-ret-opt", pct(opt.return), true);
  setMetric("m-vol-opt", pct(opt.volatility));
  setMetric("m-sr-opt", opt.sharpe.toFixed(2));

  renderInsights(data.insights);
}

// ── Insights ───────────────────────────────────────────────────
function renderInsights(insights) {
  const el = document.getElementById("insights-list");
  if (!el) return;
  el.innerHTML = insights.map(i => `<div>${i}</div>`).join("");
}

// ── Helpers (FIXED MISSING FUNCTIONS) ──────────────────────────
function setMetric(id, value, positive) {
  const el = document.getElementById(id);
  if (!el) return;

  el.textContent = value;

  if (positive === true) el.style.color = "#4fffb0";
  else if (positive === false) el.style.color = "#ff5f72";
  else el.style.color = "#e8ecf4";
}

function pct(v) {
  return (v * 100).toFixed(1) + "%";
}

function showError(msg) {
  console.error(msg);
  const el = document.getElementById("error-banner");
  if (el) {
    el.textContent = msg;
    el.style.display = "block";
  }
}

function clearError() {
  const el = document.getElementById("error-banner");
  if (el) el.style.display = "none";
}
