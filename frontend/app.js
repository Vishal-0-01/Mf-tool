/* app.js — MF Portfolio Analyzer frontend logic */

// ✅ FIX 1: Correct backend URL (critical)
const API_BASE =
  window.MF_API_BASE ||
  (window.location.hostname === "localhost"
    ? "http://localhost:5000"
    : "https://mf-tool.onrender.com");

// ── State ──────────────────────────────────────────────────────
let fundUniverse = {};
let selectedFunds = new Set();
let fundAmounts = {};  // persists amounts
let frontier = [];
let frontierIndex = null;

let donutChart = null;
let frontierChart = null;

// ── GLOBAL HELPERS ─────────────────────────────────────────────
function safe(fn) {
  try { fn(); } catch (e) { console.error("UI crash:", e); }
}

// ✅ SINGLE SOURCE OF TRUTH (FIXED)
async function reoptimizeWithSelected() {
  if (!frontier.length) return;

  const holdings = [];

  for (const code of selectedFunds) {
    const amt = parseFloat(fundAmounts[code]);
    if (amt > 0) {
      holdings.push({ scheme_code: code, amount: amt });
    }
  }

  if (holdings.length < 3) {
    showError("Need valid amounts for reoptimization.");
    return;
  }

  try {
    const res = await fetch(`${API_BASE}/api/analyze`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        holdings,
        frontier_index: frontierIndex
      })
    });

    const data = await res.json();

    if (data.status === "ok") {
      renderDashboard(data);
    } else {
      showError(data.message || "Reoptimization failed.");
    }

  } catch (e) {
    console.error(e);
    showError("Reoptimization failed.");
  }
}

// ── Init ───────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", async () => {
  await loadFunds();
  bindEvents();
});

async function loadFunds() {
  try {
    const res = await fetch(`${API_BASE}/api/funds`);
    const data = await res.json();

    if (!data || data.status !== "ok") {
      throw new Error("Invalid backend response");
    }

    fundUniverse = data.funds;
    renderFundList(fundUniverse);

  } catch (e) {
    console.error(e);
    showError("Backend not reachable. Check Render.");
  }
}

// ── Render fund list ───────────────────────────────────────────
const CAT_DOTS = {
  "Large Cap": "large",
  "Flexi Cap": "flexi",
  "Mid Cap": "mid",
  "Small Cap": "small",
  "Hybrid": "hybrid",
};

function renderFundList(universe) {
  const container = document.getElementById("fund-list-container");
  if (!container) return;

  container.innerHTML = "";

  for (const [cat, funds] of Object.entries(universe)) {
    const block = document.createElement("div");
    block.className = "category-block";

    const header = document.createElement("div");
    header.className = "cat-header";
    header.innerHTML = `
      <span class="cat-name">${cat}</span>
      <span class="cat-toggle">▶</span>`;

    const list = document.createElement("div");
    list.className = "fund-list hidden";

    funds.forEach(fund => {
      const item = document.createElement("div");
      item.className = "fund-item";
      item.dataset.code = fund.scheme_code;
      item.dataset.name = fund.name.toLowerCase();

      const cb = document.createElement("input");
      cb.type = "checkbox";

      const label = document.createElement("span");
      label.textContent = fund.name;

      item.appendChild(cb);
      item.appendChild(label);

      item.addEventListener("click", (e) => {
        if (e.target !== cb) cb.checked = !cb.checked;
        toggleFund(fund.scheme_code, fund.name, cb.checked);
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

function toggleFund(code, name, checked) {
  const item = document.querySelector(`.fund-item[data-code="${code}"]`);

  if (checked) {
    selectedFunds.add(code);
    item?.classList.add("selected");
  } else {
    selectedFunds.delete(code);
    item?.classList.remove("selected");
    delete fundAmounts[code];
  }

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
    const fund = findFund(code);

    const row = document.createElement("div");

    const lbl = document.createElement("div");
    lbl.textContent = fund ? fund.name : code;

    const inp = document.createElement("input");
    inp.type = "number";
    inp.dataset.code = code;

    if (fundAmounts[code] !== undefined) {
      inp.value = fundAmounts[code];
    }

    inp.addEventListener("input", () => {
      fundAmounts[code] = inp.value;
    });

    row.appendChild(lbl);
    row.appendChild(inp);
    container.appendChild(row);
  }
}

function findFund(code) {
  for (const funds of Object.values(fundUniverse)) {
    const f = funds.find(f => f.scheme_code === code);
    if (f) return f;
  }
  return null;
}

// ── Events ─────────────────────────────────────────────────────
function bindEvents() {
  document.getElementById("btn-analyze")?.addEventListener("click", runAnalysis);

  document.getElementById("btn-reoptimize")?.addEventListener("click", reoptimizeWithSelected);

  document.getElementById("frontier-slider")?.addEventListener("input", function () {
    frontierIndex = parseInt(this.value);
    updateFrontierHighlight();
  });

  // ✅ RESTORE SEARCH (this is what broke)
  document.getElementById("fund-search")?.addEventListener("input", function () {
    const q = this.value.toLowerCase().trim();

    document.querySelectorAll(".fund-item").forEach(item => {
      const match = !q || item.dataset.name.includes(q);
      item.style.display = match ? "" : "none";
    });

    // auto-expand categories with matches
    document.querySelectorAll(".category-block").forEach(block => {
      const visible = [...block.querySelectorAll(".fund-item")]
        .some(i => i.style.display !== "none");

      const list = block.querySelector(".fund-list");
      const toggle = block.querySelector(".cat-toggle");

      if (q && visible) {
        list.classList.remove("hidden");
        toggle?.classList.add("open");
      }
    });
  });
}

// ── Analysis ───────────────────────────────────────────────────
async function runAnalysis() {
  clearError();

  if (selectedFunds.size < 3) {
    showError("Please select at least 3 funds.");
    return;
  }

  const holdings = [];
  let valid = true;

  for (const code of selectedFunds) {
    const amt = parseFloat(fundAmounts[code]);

    if (!amt || amt <= 0) valid = false;
    else holdings.push({ scheme_code: code, amount: amt });
  }

  if (!valid) {
    showError("Enter valid amount for all funds.");
    return;
  }

  try {
    showLoader(true);

    const res = await fetch(`${API_BASE}/api/analyze`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ holdings }),
    });

    const data = await res.json();

    if (data.status !== "ok") {
      showError(data.message || "Analysis failed.");
      return;
    }

    frontier = data.frontier || [];
    frontierIndex = data.selected_frontier_index ?? 0;

    renderDashboard(data);

  } catch (e) {
    console.error(e);
    showError("Network error.");
  } finally {
    showLoader(false);
  }
}

// ── Dashboard ──────────────────────────────────────────────────
function renderDashboard(data) {
  const dash = document.getElementById("dashboard");
  document.getElementById("empty-state").style.display = "none";
  dash.style.display = "flex";

  const curr = data.current_portfolio;
  const opt  = data.optimal_portfolio;

  setMetric("m-ret-curr", pct(curr.portfolio_return));
  setMetric("m-vol-curr", pct(curr.portfolio_volatility));
  setMetric("m-sr-curr", curr.sharpe.toFixed(2));

  setMetric("m-ret-opt", pct(opt.return));
  setMetric("m-vol-opt", pct(opt.volatility));
  setMetric("m-sr-opt", opt.sharpe.toFixed(2));

  safe(() => renderDonut(curr.category_weights));
  safe(() => renderFrontier(data.frontier, data.selected_frontier_index, curr, opt));
  safe(() => renderActions(data.actions));
  safe(() => renderInsights(data.insights));
}

// ── Utils ──────────────────────────────────────────────────────
function pct(v) { return (v * 100).toFixed(1) + "%"; }

function setMetric(id, value) {
  const el = document.getElementById(id);
  if (el) el.textContent = value;
}

function showError(msg) {
  console.error(msg);
  const el = document.getElementById("error-banner");
  if (el) {
    el.textContent = msg;
    el.classList.add("visible");
  }
}

function clearError() {
  document.getElementById("error-banner")?.classList.remove("visible");
}

function showLoader(show) {
  document.getElementById("loader")?.classList.toggle("visible", show);
}

// ── Minimal charts/actions (unchanged logic) ──

