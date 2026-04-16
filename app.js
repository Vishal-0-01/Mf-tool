/* app.js — MF Portfolio Analyzer frontend logic */

const API_BASE = window.MF_API_BASE || "http://localhost:5000";

// ── State ──────────────────────────────────────────────────────
let fundUniverse = {};         // {category: [{scheme_code, name, category}]}
let selectedFunds = new Set(); // selected scheme_codes
let frontier = [];             // efficient frontier from API
let frontierIndex = null;      // selected index

// Chart instances
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
    fundUniverse = data.funds;
    renderFundList(fundUniverse);
  } catch (e) {
    showError("Failed to connect to backend. Is the server running?");
  }
}

// ── Render fund list ───────────────────────────────────────────
const CAT_DOTS = {
  "Large Cap": "large",
  "Flexi Cap": "flexi",
  "Mid Cap":   "mid",
  "Small Cap": "small",
  "Hybrid":    "hybrid",
};

function renderFundList(universe) {
  const container = document.getElementById("fund-list-container");
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
    lbl.title = fund ? fund.name : code;

    const inp = document.createElement("input");
    inp.type = "number";
    inp.className = "amount-input";
    inp.min = "1";
    inp.step = "100";
    inp.placeholder = "₹ amount";
    inp.dataset.code = code;
    inp.value = inp.value || "";

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

// ── Search ─────────────────────────────────────────────────────
function bindEvents() {
  document.getElementById("fund-search").addEventListener("input", function () {
    const q = this.value.toLowerCase().trim();
    document.querySelectorAll(".fund-item").forEach(item => {
      const match = !q || item.dataset.name.includes(q);
      item.classList.toggle("hidden-search", !match);
    });
    // Auto-expand categories with matches
    document.querySelectorAll(".category-block").forEach(block => {
      const visible = [...block.querySelectorAll(".fund-item")].some(
        i => !i.classList.contains("hidden-search")
      );
      const list = block.querySelector(".fund-list");
      const toggle = block.querySelector(".cat-toggle");
      if (q && visible) {
        list.classList.remove("hidden");
        toggle.classList.add("open");
      }
    });
  });

  document.getElementById("btn-analyze").addEventListener("click", runAnalysis);

  document.getElementById("frontier-slider").addEventListener("input", function () {
    frontierIndex = parseInt(this.value);
    updateFrontierHighlight();
  });

  document.getElementById("btn-reoptimize").addEventListener("click", reoptimizeWithSelected);
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

  if (!valid) { showError("Enter a valid amount (> 0) for every selected fund."); return; }

  const pe = parseFloat(document.getElementById("inp-pe").value) || 22.0;
  const pb = parseFloat(document.getElementById("inp-pb").value) || 3.2;

  showLoader(true);
  document.getElementById("btn-analyze").disabled = true;

  try {
    const res = await fetch(`${API_BASE}/api/analyze`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ holdings, pe, pb }),
    });
    const data = await res.json();

    if (data.status !== "ok") {
      showError(data.message || "Analysis failed.");
      return;
    }

    frontier = data.frontier;
    frontierIndex = data.selected_frontier_index;

    renderDashboard(data);
  } catch (e) {
    showError("Network error. Check backend connection.");
  } finally {
    showLoader(false);
    document.getElementById("btn-analyze").disabled = false;
  }
}

async function reoptimizeWithSelected() {
  if (!frontier.length) return;

  const holdings = [];
  document.querySelectorAll(".amount-input").forEach(inp => {
    const amt = parseFloat(inp.value);
    if (amt > 0) holdings.push({ scheme_code: inp.dataset.code, amount: amt });
  });

  const pe = parseFloat(document.getElementById("inp-pe").value) || 22.0;
  const pb = parseFloat(document.getElementById("inp-pb").value) || 3.2;

  showLoader(true);
  try {
    const res = await fetch(`${API_BASE}/api/analyze`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ holdings, pe, pb, frontier_index: frontierIndex }),
    });
    const data = await res.json();
    if (data.status === "ok") renderDashboard(data);
    else showError(data.message);
  } catch (e) {
    showError("Reoptimization failed.");
  } finally {
    showLoader(false);
  }
}

// ── Render dashboard ───────────────────────────────────────────
function renderDashboard(data) {
  const dash = document.getElementById("dashboard");
  document.getElementById("empty-state").style.display = "none";
  dash.style.display = "flex";

  const curr = data.current_portfolio;
  const opt  = data.optimal_portfolio;

  // ── Metrics ──
  setMetric("m-ret-curr",  pct(curr.portfolio_return),  curr.portfolio_return >= 0);
  setMetric("m-vol-curr",  pct(curr.portfolio_volatility));
  setMetric("m-sr-curr",   curr.sharpe.toFixed(2));
  setMetric("m-ret-opt",   pct(opt.return),  opt.return >= 0);
  setMetric("m-vol-opt",   pct(opt.volatility));
  setMetric("m-sr-opt",    opt.sharpe.toFixed(2));

  // ── Macro ──
  const m = data.macro;
  document.getElementById("macro-result").innerHTML =
    `<span class="macro-chip">Equity ${pct(m.equity_pct)}</span>
     <span class="macro-chip">z = ${m.z_score.toFixed(2)}</span>
     <span class="macro-chip">z_PE ${m.z_pe.toFixed(2)}</span>
     <span class="macro-chip">z_PB ${m.z_pb.toFixed(2)}</span>
     ${Object.entries(m.category_splits).map(([c,v]) => `<span class="macro-chip">${c} ${pct(v)}</span>`).join("")}`;

  // ── Charts ──
  renderDonut(curr.category_weights, opt.weights, data);
  renderFrontier(data.frontier, data.selected_frontier_index, curr, opt);

  // ── Actions ──
  renderActions(data.actions);

  // ── Insights ──
  renderInsights(data.insights);

  // ── Frontier slider ──
  const slider = document.getElementById("frontier-slider");
  slider.max = frontier.length - 1;
  slider.value = frontierIndex ?? data.selected_frontier_index;
}

function setMetric(id, value, positive) {
  const el = document.getElementById(id);
  if (!el) return;
  el.textContent = value;
  el.className = "metric-value" + (positive === true ? " positive" : positive === false ? " negative" : "");
}

// ── Donut chart (allocation) ───────────────────────────────────
function renderDonut(catWeights, optWeights, data) {
  if (donutChart) donutChart.destroy();
  const ctx = document.getElementById("donut-chart").getContext("2d");

  const labels = Object.keys(catWeights);
  const values = labels.map(l => catWeights[l]);
  const colors = ["#4fffb0","#3de8ff","#ffb347","#c77dff","#ff6b6b"];

  donutChart = new Chart(ctx, {
    type: "doughnut",
    data: {
      labels,
      datasets: [{
        data: values.map(v => (v * 100).toFixed(1)),
        backgroundColor: colors,
        borderColor: "#0a0b0f",
        borderWidth: 2,
        hoverOffset: 6,
      }],
    },
    options: {
      responsive: true,
      cutout: "68%",
      plugins: {
        legend: {
          position: "bottom",
          labels: {
            color: "#6b7590",
            font: { family: "DM Mono", size: 10 },
            boxWidth: 10,
            padding: 14,
          },
        },
        tooltip: {
          backgroundColor: "#181c24",
          borderColor: "#252934",
          borderWidth: 1,
          titleColor: "#e8ecf4",
          bodyColor: "#6b7590",
          callbacks: { label: ctx => ` ${ctx.label}: ${ctx.parsed}%` },
        },
      },
    },
  });
}

// ── Frontier scatter ───────────────────────────────────────────
function renderFrontier(frt, selIdx, curr, opt) {
  if (frontierChart) frontierChart.destroy();
  const ctx = document.getElementById("frontier-chart").getContext("2d");

  const frtPoints = frt.map(p => ({ x: +(p.volatility * 100).toFixed(2), y: +(p.return * 100).toFixed(2) }));
  const selPoint  = frt[selIdx] ? [{ x: +(frt[selIdx].volatility*100).toFixed(2), y: +(frt[selIdx].return*100).toFixed(2) }] : [];
  const currPoint = [{ x: +(curr.portfolio_volatility*100).toFixed(2), y: +(curr.portfolio_return*100).toFixed(2) }];
  const optPoint  = [{ x: +(opt.volatility*100).toFixed(2), y: +(opt.return*100).toFixed(2) }];

  frontierChart = new Chart(ctx, {
    type: "scatter",
    data: {
      datasets: [
        {
          label: "Efficient Frontier",
          data: frtPoints,
          backgroundColor: "rgba(79,255,176,0.5)",
          borderColor: "rgba(79,255,176,0.8)",
          pointRadius: 4,
          pointHoverRadius: 6,
          showLine: true,
          borderWidth: 1.5,
          tension: 0.4,
        },
        {
          label: "Selected",
          data: selPoint,
          backgroundColor: "#fff",
          borderColor: "#4fffb0",
          pointRadius: 8,
          pointHoverRadius: 10,
          borderWidth: 2,
        },
        {
          label: "Current",
          data: currPoint,
          backgroundColor: "rgba(255,95,114,0.8)",
          borderColor: "#ff5f72",
          pointRadius: 8,
          pointStyle: "triangle",
        },
        {
          label: "Optimal",
          data: optPoint,
          backgroundColor: "rgba(61,232,255,0.9)",
          borderColor: "#3de8ff",
          pointRadius: 8,
          pointStyle: "star",
        },
      ],
    },
    options: {
      responsive: true,
      scales: {
        x: {
          title: { display: true, text: "Volatility (%)", color: "#6b7590", font: { family: "DM Mono", size: 10 } },
          grid: { color: "#1a1f2a" },
          ticks: { color: "#6b7590", font: { family: "DM Mono", size: 10 } },
        },
        y: {
          title: { display: true, text: "Return (%)", color: "#6b7590", font: { family: "DM Mono", size: 10 } },
          grid: { color: "#1a1f2a" },
          ticks: { color: "#6b7590", font: { family: "DM Mono", size: 10 } },
        },
      },
      plugins: {
        legend: {
          labels: { color: "#6b7590", font: { family: "DM Mono", size: 10 }, boxWidth: 10, padding: 12 },
        },
        tooltip: {
          backgroundColor: "#181c24",
          borderColor: "#252934",
          borderWidth: 1,
          titleColor: "#e8ecf4",
          bodyColor: "#6b7590",
          callbacks: {
            label: ctx => ` Vol: ${ctx.parsed.x}%  Ret: ${ctx.parsed.y}%`,
          },
        },
      },
    },
  });
}

function updateFrontierHighlight() {
  if (!frontierChart || !frontier.length) return;
  const sel = frontier[frontierIndex];
  if (!sel) return;
  frontierChart.data.datasets[1].data = [{
    x: +(sel.volatility*100).toFixed(2),
    y: +(sel.return*100).toFixed(2),
  }];
  frontierChart.update();
}

// ── Actions table ──────────────────────────────────────────────
function renderActions(actionData) {
  const tbody = document.getElementById("actions-tbody");
  tbody.innerHTML = "";
  for (const a of actionData.actions) {
    const tr = document.createElement("tr");
    const badgeClass = `badge-${a.action.toLowerCase()}`;
    const delta = a.delta >= 0 ? `+${pct(a.delta)}` : pct(a.delta);
    const amtSign = a.amount_change >= 0 ? `+₹${fmt(a.amount_change)}` : `-₹${fmt(Math.abs(a.amount_change))}`;
    tr.innerHTML = `
      <td>${a.name}</td>
      <td>${pct(a.current_weight)}</td>
      <td>${pct(a.optimal_weight)}</td>
      <td style="color:${a.delta >= 0 ? 'var(--buy)' : 'var(--sell)'}">${delta}</td>
      <td><span class="badge ${badgeClass}">${a.action}</span></td>
      <td style="font-family:var(--font-mono)">${amtSign}</td>`;
    tbody.appendChild(tr);
  }

  document.getElementById("turnover-val").textContent = pct(actionData.turnover);
  document.getElementById("txn-cost-val").textContent = `₹${fmt(actionData.transaction_cost_inr)} (${pct(actionData.transaction_cost_pct)})`;
}

// ── Insights ───────────────────────────────────────────────────
function renderInsights(insights) {
  const list = document.getElementById("insights-list");
  list.innerHTML = insights.map(i => `<div class="insight-item">${i}</div>`).join("");
}

// ── Helpers ────────────────────────────────────────────────────
function pct(v) { return (v * 100).toFixed(1) + "%"; }
function fmt(v) { return v.toLocaleString("en-IN", { maximumFractionDigits: 0 }); }

function showError(msg) {
  const el = document.getElementById("error-banner");
  el.textContent = msg;
  el.classList.add("visible");
}
function clearError() {
  document.getElementById("error-banner").classList.remove("visible");
}
function showLoader(show) {
  document.getElementById("loader").classList.toggle("visible", show);
}
