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
let frontier = [];
let frontierIndex = null;

let donutChart = null;
let frontierChart = null;

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
    block.dataset.category = cat;

    const dotClass = CAT_DOTS[cat] || "large";

    const header = document.createElement("div");
    header.className = "cat-header";
    header.innerHTML = `
      <span class="cat-name">
        <span class="cat-dot ${dotClass}"></span>
        ${cat}
      </span>
      <div style="display:flex;align-items:center;gap:8px">
        <span class="cat-count">${funds.length}</span>
        <span class="cat-toggle">▶</span>
      </div>`;

    const list = document.createElement("div");
    list.className = "fund-list hidden";

    funds.forEach(fund => {
      const item = document.createElement("div");
      item.className = "fund-item";
      item.dataset.code = fund.scheme_code;
      item.dataset.name = fund.name.toLowerCase();

      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.className = "fund-cb";
      cb.dataset.code = fund.scheme_code;

      const label = document.createElement("span");
      label.className = "fund-name";
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
      const toggle = header.querySelector(".cat-toggle");
      list.classList.toggle("hidden");
      toggle.classList.toggle("open");
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
    row.className = "amount-row";

    const lbl = document.createElement("div");
    lbl.className = "amount-label";
    lbl.textContent = fund ? fund.name : code;

    const inp = document.createElement("input");
    inp.type = "number";
    inp.className = "amount-input";
    inp.placeholder = "₹ amount";
    inp.dataset.code = code;

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

  document.getElementById("frontier-slider")?.addEventListener("input", function () {
    frontierIndex = parseInt(this.value);
    updateFrontierHighlight();
  });

  document.getElementById("btn-reoptimize")?.addEventListener("click", reoptimizeWithSelected);
}

// ── Analysis ───────────────────────────────────────────────────
async function runAnalysis() {
  console.log("ANALYZE CLICKED");

  clearError();

  if (selectedFunds.size < 3) {
    showError("Please select at least 3 funds.");
    return;
  }

  const holdings = [];
  let valid = true;

  document.querySelectorAll(".amount-input").forEach(inp => {
    const amt = parseFloat(inp.value);
    if (!amt || amt <= 0) {
      valid = false;
      inp.style.borderColor = "var(--sell)";
    } else {
      inp.style.borderColor = "";
      holdings.push({ scheme_code: inp.dataset.code, amount: amt });
    }
  });

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
    console.log("API RESPONSE:", data);

    if (!data || data.status !== "ok") {
      showError(data?.message || "Analysis failed.");
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

  // ── Metrics ──
  setMetric("m-ret-curr", pct(curr.portfolio_return), curr.portfolio_return >= 0);
  setMetric("m-vol-curr", pct(curr.portfolio_volatility));
  setMetric("m-sr-curr", curr.sharpe.toFixed(2));

  setMetric("m-ret-opt", pct(opt.return), opt.return >= 0);
  setMetric("m-vol-opt", pct(opt.volatility));
  setMetric("m-sr-opt", opt.sharpe.toFixed(2));

  // ── Macro ──
  const m = data.macro;
  document.getElementById("macro-result").innerHTML =
    `<span class="macro-chip">Equity ${pct(m.equity_pct)}</span>
     <span class="macro-chip">z = ${m.z_score.toFixed(2)}</span>`;

  // 🔥 CRITICAL — these were missing/breaking
  renderDonut(curr.category_weights, opt.weights, data);
  renderFrontier(data.frontier, data.selected_frontier_index, curr, opt);
  renderActions(data.actions);
  renderInsights(data.insights);

  // slider
  const slider = document.getElementById("frontier-slider");
  if (slider) {
    slider.max = data.frontier.length - 1;
    slider.value = data.selected_frontier_index;
  }
}
// ── Helpers ────────────────────────────────────────────────────
function pct(v) { return (v * 100).toFixed(1) + "%"; }
function fmt(v) { return v.toLocaleString("en-IN", { maximumFractionDigits: 0 }); }

function showError(msg) {
  console.error(msg);
  const el = document.getElementById("error-banner");
  if (el) {
    el.textContent = msg;
    el.classList.add("visible");
  } else {
    alert(msg);
  }
}

function clearError() {
  document.getElementById("error-banner")?.classList.remove("visible");
}

function showLoader(show) {
  document.getElementById("loader")?.classList.toggle("visible", show);
}
// ───────────────── FIX: Missing helpers ─────────────────

function setMetric(id, value, positive) {
  const el = document.getElementById(id);
  if (!el) return;

  el.textContent = value;

  // preserve your UI styling (don’t override classes if they exist)
  if (positive === true) el.classList.add("positive");
  else if (positive === false) el.classList.add("negative");
}

function pct(v) {
  return (v * 100).toFixed(1) + "%";
}

function fmt(v) {
  return Number(v).toLocaleString("en-IN", {
    maximumFractionDigits: 0,
  });
}

function showError(msg) {
  console.error(msg);

  const el = document.getElementById("error-banner");
  if (el) {
    el.textContent = msg;
    el.classList.add("visible"); // match your UI
  }
}

function clearError() {
  const el = document.getElementById("error-banner");
  if (el) el.classList.remove("visible");
}
