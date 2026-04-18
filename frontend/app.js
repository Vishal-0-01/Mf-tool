/* app.js — MF Portfolio Analyzer frontend logic */

// ✅ Backend URL
const API_BASE =
  window.MF_API_BASE ||
  (window.location.hostname === "localhost"
    ? "http://localhost:5000"
    : "https://mf-tool.onrender.com");

// ── State ──────────────────────────────────────────────────────
let fundUniverse = {};
let selectedFunds = new Set();
let fundAmounts = {};
let frontier = [];
let frontierIndex = null;

let donutChart = null;
let frontierChart = null;

// ── Helpers ────────────────────────────────────────────────────
function safe(fn) {
  try { fn(); } catch (e) { console.error("UI crash:", e); }
}

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

    if (!data || data.status !== "ok") throw new Error("Invalid backend");

    fundUniverse = data.funds;
    renderFundList(fundUniverse);

  } catch (e) {
    console.error(e);
    showError("Backend not reachable.");
  }
}

// ── Render Funds ───────────────────────────────────────────────
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
      <span class="cat-name">
        <span class="cat-dot ${CAT_DOTS[cat] || "large"}"></span>
        ${cat}
      </span>
      <span class="cat-count">${funds.length}</span>
    `;

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
        toggleFund(fund.scheme_code, cb.checked);
      });

      list.appendChild(item);
    });

    header.onclick = () => list.classList.toggle("hidden");

    block.appendChild(header);
    block.appendChild(list);
    container.appendChild(block);
  }
}

// ── Selection ──────────────────────────────────────────────────
function toggleFund(code, checked) {
  if (checked) selectedFunds.add(code);
  else {
    selectedFunds.delete(code);
    delete fundAmounts[code];
  }
  renderAmountInputs();
}

// ── Amounts ───────────────────────────────────────────────────
function renderAmountInputs() {
  const container = document.getElementById("amount-inputs");
  const section = document.getElementById("amount-section");

  if (!container || !section) return;

  if (!selectedFunds.size) {
    section.style.display = "none";
    return;
  }

  section.style.display = "block";
  container.innerHTML = "";

  for (const code of selectedFunds) {
    const row = document.createElement("div");

    const inp = document.createElement("input");
    inp.type = "number";
    inp.dataset.code = code;

    if (fundAmounts[code] !== undefined) {
      inp.value = fundAmounts[code];
    }

    inp.addEventListener("input", () => {
      fundAmounts[code] = inp.value;
    });

    row.appendChild(inp);
    container.appendChild(row);
  }
}

// ── Events ─────────────────────────────────────────────────────
function bindEvents() {
  document.getElementById("btn-analyze")?.addEventListener("click", runAnalysis);

  document.getElementById("frontier-slider")?.addEventListener("input", e => {
    frontierIndex = parseInt(e.target.value);
    updateFrontierHighlight();
  });

  document.getElementById("btn-reoptimize")?.addEventListener("click", reoptimizeWithSelected);

  // SEARCH (fixed placement)
  document.getElementById("fund-search")?.addEventListener("input", function () {
    const q = this.value.toLowerCase();

    document.querySelectorAll(".fund-item").forEach(i => {
      i.style.display = i.dataset.name.includes(q) ? "" : "none";
    });
  });
}

// ── Analysis ───────────────────────────────────────────────────
async function runAnalysis() {
  if (selectedFunds.size < 3) {
    showError("Select at least 3 funds");
    return;
  }

  const holdings = [];
  let valid = true;

  for (const code of selectedFunds) {
    const amt = parseFloat(fundAmounts[code]);
    if (!amt) valid = false;
    else holdings.push({ scheme_code: code, amount: amt });
  }

  if (!valid) {
    showError("Invalid amounts");
    return;
  }

  try {
    const res = await fetch(`${API_BASE}/api/analyze`, {
      method: "POST",
      headers: {"Content-Type":"application/json"},
      body: JSON.stringify({ holdings })
    });

    const data = await res.json();

    if (data.status !== "ok") {
      showError(data.message);
      return;
    }

    frontier = data.frontier;
    frontierIndex = data.selected_frontier_index;

    renderDashboard(data);

  } catch (e) {
    console.error(e);
    showError("Network error");
  }
}

// ── Dashboard ─────────────────────────────────────────────────
function renderDashboard(data) {
  safe(() => renderDonut(data.current_portfolio.category_weights));
  safe(() => renderFrontier(data.frontier, data.selected_frontier_index));
  safe(() => renderActions(data.actions));
}

// ── Charts ─────────────────────────────────────────────────────
function renderDonut(w) {
  const ctx = document.getElementById("donut-chart")?.getContext("2d");
  if (!ctx) return;

  if (donutChart) donutChart.destroy();

  donutChart = new Chart(ctx, {
    type: "doughnut",
    data: {
      labels: Object.keys(w),
      datasets: [{ data: Object.values(w).map(v => v * 100) }]
    }
  });
}

function renderFrontier(frt, idx) {
  const ctx = document.getElementById("frontier-chart")?.getContext("2d");
  if (!ctx) return;

  if (frontierChart) frontierChart.destroy();

  frontierChart = new Chart(ctx, {
    type: "scatter",
    data: {
      datasets: [{
        data: frt.map(p => ({ x: p.volatility*100, y: p.return*100 }))
      }]
    }
  });
}

// ── Actions ────────────────────────────────────────────────────
function renderActions(a) {
  const el = document.getElementById("actions-tbody");
  if (!el) return;

  el.innerHTML = a.actions.map(x => `
    <tr>
      <td>${x.name}</td>
      <td>${(x.current_weight*100).toFixed(1)}%</td>
      <td>${(x.optimal_weight*100).toFixed(1)}%</td>
    </tr>
  `).join("");
}

// ── Reoptimize (ONLY ONE VERSION NOW) ──────────────────────────
async function reoptimizeWithSelected() {
  if (!frontier.length) return;

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

  try {
    const res = await fetch(`${API_BASE}/api/analyze`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ holdings, frontier_index: frontierIndex })
    });

    const data = await res.json();

    if (data.status === "ok") renderDashboard(data);
    else showError(data.message);

  } catch (e) {
    console.error(e);
    showError("Reoptimize failed");
  }
}

// ── Misc ───────────────────────────────────────────────────────
function updateFrontierHighlight() {
  console.log("slider move");
}

function showError(msg) {
  console.error(msg);
}
