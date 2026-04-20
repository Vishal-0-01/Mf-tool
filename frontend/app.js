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
let fundAmounts = {};  // 🔥 persists amounts
let frontier = [];
let frontierIndex = null;

let donutChart = null;
let frontierChart = null;

// ── GLOBAL HELPERS (MUST BE ABOVE EVERYTHING THAT USES THEM) ──

function safe(fn) {
  try {
    fn();
  } catch (e) {
    console.error("UI crash:", e);
  }
}

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

  if (holdings.length < 3) {
    showError("Need valid amounts for reoptimization.");
    return;
  }

  try {
    const res = await fetch(`${API_BASE}/api/analyze`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
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
  </div>`;    const list = document.createElement("div");
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
    // 🔥 remove stale amount
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
    row.className = "amount-row";

    const lbl = document.createElement("div");
    lbl.className = "amount-label";
    lbl.textContent = fund ? fund.name : code;

    const inp = document.createElement("input");
    inp.type = "number";
    inp.placeholder = "₹ amount";
    inp.dataset.code = code;

    // 🔥 restore old value if exists
    if (fundAmounts[code] !== undefined) {
      inp.value = fundAmounts[code];
    }

    // 🔥 save on change
    inp.addEventListener("input", () => {
      fundAmounts[code] = inp.value;
    });
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

// ── Analysis ───────────────────────────────────────────────────
//-----Analysis chatgpt-------------//
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
      body: JSON.stringify({
        holdings,
        pe: parseFloat(document.getElementById("inp-pe").value),
        pb: parseFloat(document.getElementById("inp-pb").value)
      })
    });
    console.log("PE:", document.getElementById("inp-pe").value);
    console.log("PB:", document.getElementById("inp-pb").value);

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
  finally {
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
  // ── Macro ──
  const m = data.macro;
  document.getElementById("macro-result").innerHTML =
  `<span class="macro-chip">Equity ${pct(m.equity_pct)}</span>
   <span class="macro-chip">z = ${m.z_score.toFixed(2)}</span>`;
  
  // 🔥 CRITICAL — these were missing/breaking
  safe(() => renderDonut(curr.category_weights));
  safe(() => renderFrontier(
    data.frontier,
    data.selected_frontier_index,
    curr,
    opt
  ));
  safe(() => renderActions(data.actions));
  safe(() => renderInsights(data.insights));
  // ── NEW renders ──
  safe(() => renderTargetComparison(data));
  safe(() => renderDiagnostics(data));

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


// ── FALLBACK UI FUNCTIONS (RESTORE MISSING ONES) ──

// Donut (category allocation)

function renderDonut(categoryWeights) {
  const canvas = document.getElementById("donut-chart");
  if (!canvas) return;

  const ctx = canvas.getContext("2d");

  if (window.donutChart) {
    window.donutChart.destroy();
  }

  const labels = Object.keys(categoryWeights);
  const values = labels.map(k => categoryWeights[k] * 100);

  window.donutChart = new Chart(ctx, {
    type: "doughnut",
    data: {
      labels,
      datasets: [{
        data: values,
        backgroundColor: ["#4fffb0", "#3de8ff", "#ffb347", "#c77dff"],
      }],
    },
    options: {
      plugins: {
        legend: {
          labels: { color: "#aaa" }
        }
      }
    }
  });
}
// Frontier (simple table instead of chart)
function renderFrontier(frontier, selectedIndex, curr, opt) {
  const canvas = document.getElementById("frontier-chart");
  if (!canvas) return;

  const ctx = canvas.getContext("2d");

  if (window.frontierChart) {
    window.frontierChart.destroy();
  }

  const points = frontier.map(p => ({
    x: p.volatility * 100,
    y: p.return * 100
  }));

  const selected = frontier[selectedIndex];

  window.frontierChart = new Chart(ctx, {
    type: "scatter",
    data: {
      datasets: [
        {
          label: "Frontier",
          data: points,
          showLine: true,
          borderColor: "#4fffb0",
        },
        {
          label: "Selected",
          data: selected ? [{
            x: selected.volatility * 100,
            y: selected.return * 100
          }] : [],
          backgroundColor: "#fff",
          pointRadius: 6
        }
      ]
    },
    options: {
      scales: {
        x: {
          title: { display: true, text: "Volatility (%)" }
        },
        y: {
          title: { display: true, text: "Return (%)" }
        }
      }
    }
  });
}

// Actions table
function renderActions(actionData) {
  const tbody = document.getElementById("actions-tbody");
  if (!tbody) return;

  tbody.innerHTML = "";

  actionData.actions.forEach(a => {
    const tr = document.createElement("tr");

    const delta = a.delta >= 0
      ? `+${(a.delta * 100).toFixed(1)}%`
      : `${(a.delta * 100).toFixed(1)}%`;

    const amt = a.amount_change >= 0
      ? `+₹${fmt(a.amount_change)}`
      : `-₹${fmt(Math.abs(a.amount_change))}`;

    tr.innerHTML = `
      <td>${a.name}</td>
      <td>${(a.current_weight * 100).toFixed(1)}%</td>
      <td>${(a.optimal_weight * 100).toFixed(1)}%</td>
      <td style="color:${a.delta >= 0 ? '#4fffb0' : '#ff6b6b'}">${delta}</td>
      <td>${a.action}</td>
      <td>${amt}</td>
    `;

    tbody.appendChild(tr);
  });

  // ✅ KEEP THIS INSIDE
  const turnoverEl = document.getElementById("turnover-val");
  const costEl = document.getElementById("txn-cost-val");

  if (turnoverEl) {
    turnoverEl.textContent = pct(actionData.turnover);
  }

  if (costEl) {
    costEl.textContent = `₹${fmt(actionData.transaction_cost_inr)} (${pct(actionData.transaction_cost_pct)})`;
  }
}

// Insights
function renderInsights(insights) {
  const el = document.getElementById("insights-list");
  if (!el) return;

  el.innerHTML = insights.map(i => `<div>${i}</div>`).join("");
}

// ─────────────────────────────────────────────
// MISSING FUNCTION FIXES (DO NOT TOUCH ABOVE)
// ─────────────────────────────────────────────

// Prevent slider crash
function updateFrontierHighlight() {
  if (!frontier || !frontier.length) return;

  const sel = frontier[frontierIndex];
  if (!sel) return;

  console.log("Selected frontier point:", sel);

  // If chart exists → update
  if (window.frontierChart && window.frontierChart.data?.datasets?.[1]) {
    window.frontierChart.data.datasets[1].data = [{
      x: +(sel.volatility * 100).toFixed(2),
      y: +(sel.return * 100).toFixed(2),
    }];
    window.frontierChart.update();
  }
}

// Prevent reoptimize crash
async function reoptimizeWithSelected() {
  if (!frontier.length) return;

  const holdings = [];
  document.querySelectorAll("input[data-code]").forEach(inp => {
    const amt = parseFloat(inp.value);
    if (amt > 0) {
      holdings.push({ scheme_code: inp.dataset.code, amount: amt });
    }
  });

  try {
    const res = await fetch(`${API_BASE}/api/analyze`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        holdings,
        frontier_index: frontierIndex
      }),
    });

    const data = await res.json();

    if (data.status === "ok") {
      renderDashboard(data);
    } else {
      showError(data.message || "Reoptimize failed");
    }

  } catch (e) {
    console.error(e);
    showError("Reoptimize failed");
  }
}

// ═══════════════════════════════════════════════════════════════
// NEW FEATURE RENDERS — appended, nothing above touched
// ═══════════════════════════════════════════════════════════════

// ── Target Portfolio & Same-Risk Comparison ──────────────────
function renderTargetComparison(data) {
  const tp = data.target_portfolio;
  const ci = data.constraint_impact;
  const sr = data.comparison?.same_risk;

  // Target metrics
  setMetric("m-ret-target", tp ? pct(tp.return) : "—", tp && tp.return >= 0);
  setMetric("m-vol-target", tp ? pct(tp.volatility) : "—");
  setMetric("m-sr-target",  tp ? tp.sharpe.toFixed(2) : "—");

  // Constraint impact
  const ciEl = document.getElementById("constraint-impact-row");
  if (ciEl && ci) {
    ciEl.innerHTML =
      `<span class="macro-chip" style="border-color:${ci.return_loss > 0 ? '#ff6b6b' : '#4fffb0'}">
         Return cost: ${ci.return_loss > 0 ? "-" : "+"}${pct(Math.abs(ci.return_loss))}
       </span>
       <span class="macro-chip" style="border-color:${ci.sharpe_loss > 0 ? '#ff6b6b' : '#4fffb0'}">
         Sharpe cost: ${ci.sharpe_loss > 0 ? "-" : "+"}${Math.abs(ci.sharpe_loss).toFixed(3)}
       </span>`;
  }

  // Same-risk comparison table
  const tbody = document.getElementById("comparison-tbody");
  if (tbody && sr) {
    tbody.innerHTML = `
      <tr>
        <td>User Portfolio</td>
        <td>${pct(sr.user_return)}</td>
        <td>${sr.user_sharpe.toFixed(2)}</td>
      </tr>
      <tr>
        <td>Target (Unconstrained)</td>
        <td style="color:var(--accent)">${pct(sr.target_return)}</td>
        <td style="color:var(--accent)">${sr.target_sharpe.toFixed(2)}</td>
      </tr>
      <tr>
        <td>Constrained Optimal</td>
        <td style="color:var(--accent2)">${pct(sr.optimal_return)}</td>
        <td style="color:var(--accent2)">${sr.optimal_sharpe.toFixed(2)}</td>
      </tr>`;
  }

  // Dual frontier chart
  if (data.frontier_unconstrained?.length && data.frontier_constrained?.length) {
    renderDualFrontier(data.frontier_constrained, data.frontier_unconstrained,
                       data.selected_frontier_index);
  }
}

// ── Dual Frontier chart ──────────────────────────────────────
let dualFrontierChart = null;

function renderDualFrontier(constrained, unconstrained, selIdx) {
  const canvas = document.getElementById("dual-frontier-chart");
  if (!canvas) return;

  if (dualFrontierChart) dualFrontierChart.destroy();
  const ctx = canvas.getContext("2d");

  const conPoints = constrained.map(p => ({ x: +(p.volatility*100).toFixed(2), y: +(p.return*100).toFixed(2) }));
  const uncPoints = unconstrained.map(p => ({ x: +(p.volatility*100).toFixed(2), y: +(p.return*100).toFixed(2) }));
  const selPt = constrained[selIdx] ? [{ x: +(constrained[selIdx].volatility*100).toFixed(2), y: +(constrained[selIdx].return*100).toFixed(2) }] : [];

  dualFrontierChart = new Chart(ctx, {
    type: "scatter",
    data: {
      datasets: [
        { label: "Unconstrained", data: uncPoints, showLine: true, borderColor: "#4fffb0",
          backgroundColor: "rgba(79,255,176,0.3)", pointRadius: 3, borderWidth: 1.5, tension: 0.3 },
        { label: "Constrained",   data: conPoints, showLine: true, borderColor: "#3de8ff",
          backgroundColor: "rgba(61,232,255,0.3)", pointRadius: 3, borderWidth: 1.5, tension: 0.3, borderDash: [5,3] },
        { label: "Selected",      data: selPt,     backgroundColor: "#fff",
          borderColor: "#ffb347", pointRadius: 7, borderWidth: 2 },
      ]
    },
    options: {
      responsive: true,
      scales: {
        x: { title: { display: true, text: "Volatility (%)", color: "#6b7590",
                       font: { family: "DM Mono", size: 10 } },
             grid: { color: "#1a1f2a" }, ticks: { color: "#6b7590", font: { family: "DM Mono", size: 10 } } },
        y: { title: { display: true, text: "Return (%)",    color: "#6b7590",
                       font: { family: "DM Mono", size: 10 } },
             grid: { color: "#1a1f2a" }, ticks: { color: "#6b7590", font: { family: "DM Mono", size: 10 } } },
      },
      plugins: {
        legend: { labels: { color: "#6b7590", font: { family: "DM Mono", size: 10 },
                             boxWidth: 10, padding: 10 } },
        tooltip: { backgroundColor: "#181c24", borderColor: "#252934", borderWidth: 1,
                   titleColor: "#e8ecf4", bodyColor: "#6b7590",
                   callbacks: { label: ctx => ` Vol: ${ctx.parsed.x}%  Ret: ${ctx.parsed.y}%` } }
      }
    }
  });
}

// ── Diagnostics panel ────────────────────────────────────────
function renderDiagnostics(data) {
  const diag = data.diagnostics;
  if (!diag) return;

  // Exposure
  const exp = data.exposure;
  const expEl = document.getElementById("exposure-row");
  if (expEl && exp) {
    expEl.innerHTML =
      `<span class="macro-chip">Equity ${pct(exp.equity_pct)}</span>
       <span class="macro-chip">Debt ${pct(exp.debt_pct)}</span>
       ${Object.entries(exp.categories).map(([c,v]) => `<span class="macro-chip">${c} ${pct(v)}</span>`).join("")}`;
  }

  // Concentration
  const conc = diag.concentration;
  const concEl = document.getElementById("concentration-row");
  if (concEl && conc) {
    concEl.innerHTML =
      `<span class="macro-chip">Max weight ${pct(conc.max_weight)}</span>
       <span class="macro-chip">Top-3 weight ${pct(conc.top3_weight)}</span>`;
  }

  // Redundancy
  const redEl = document.getElementById("redundancy-list");
  if (redEl) {
    const red = diag.redundancy || [];
    if (red.length === 0) {
      redEl.innerHTML = `<div class="insight-item" style="border-left-color:var(--accent)">✅ No highly correlated fund pairs detected (&gt;0.80)</div>`;
    } else {
      redEl.innerHTML = red.map(r =>
        `<div class="insight-item" style="border-left-color:var(--warn)">
           ⚠️ Corr ${r.correlation.toFixed(2)}: ${r.fund1} ↔ ${r.fund2}
         </div>`
      ).join("");
    }
  }

  // Risk contribution bar
  renderRiskContrib(diag.risk_contribution, data.current_portfolio?.funds);

  // Macro sensitivity heat row
  renderMacroSensitivity(data.macro_sensitivity);
}

function renderRiskContrib(rc, funds) {
  const el = document.getElementById("risk-contrib-list");
  if (!el || !rc) return;

  const total = Object.values(rc).reduce((a, b) => a + b, 0) || 1;
  const sorted = Object.entries(rc).sort((a, b) => b[1] - a[1]).slice(0, 8);

  const nameMap = {};
  (funds || []).forEach(f => { nameMap[f.scheme_code] = f.name; });

  el.innerHTML = sorted.map(([code, val]) => {
    const pctVal = (val / total * 100).toFixed(1);
    const name = nameMap[code] || code;
    return `<div style="margin-bottom:6px">
      <div style="display:flex;justify-content:space-between;font-size:11px;color:var(--muted);margin-bottom:3px">
        <span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:200px">${name}</span>
        <span style="font-family:var(--font-mono)">${pctVal}%</span>
      </div>
      <div style="height:5px;background:var(--border);border-radius:3px;overflow:hidden">
        <div style="height:100%;width:${pctVal}%;background:var(--accent2);border-radius:3px"></div>
      </div>
    </div>`;
  }).join("");
}

function renderMacroSensitivity(sensitivity) {
  const el = document.getElementById("macro-sensitivity-grid");
  if (!el || !sensitivity?.length) return;

  // Show as compact grid: rows = PE, cols = PB
  const peVals = [...new Set(sensitivity.map(s => s.pe))].sort((a,b) => a-b);
  const pbVals = [...new Set(sensitivity.map(s => s.pb))].sort((a,b) => a-b);

  const lookup = {};
  sensitivity.forEach(s => { lookup[`${s.pe}_${s.pb}`] = s.equity_pct; });

  const minEq = Math.min(...sensitivity.map(s => s.equity_pct));
  const maxEq = Math.max(...sensitivity.map(s => s.equity_pct));
  const range = maxEq - minEq || 0.01;

  let html = `<div style="overflow-x:auto"><table style="width:100%;border-collapse:collapse;font-size:11px">
    <thead><tr>
      <th style="padding:5px 8px;color:var(--muted);font-family:var(--font-mono);text-align:left">PE\\PB</th>
      ${pbVals.map(pb => `<th style="padding:5px 8px;color:var(--muted);font-family:var(--font-mono)">${pb}</th>`).join("")}
    </tr></thead>
    <tbody>
      ${peVals.map(pe => `<tr>
        <td style="padding:5px 8px;color:var(--muted);font-family:var(--font-mono)">${pe}</td>
        ${pbVals.map(pb => {
          const eq = lookup[`${pe}_${pb}`] ?? 0;
          const intensity = (eq - minEq) / range;
          const bg = `rgba(79,255,176,${(0.1 + intensity * 0.5).toFixed(2)})`;
          return `<td style="padding:5px 8px;text-align:center;background:${bg};
                             color:var(--text);font-family:var(--font-mono)">${(eq*100).toFixed(0)}%</td>`;
        }).join("")}
      </tr>`).join("")}
    </tbody>
  </table></div>`;

  el.innerHTML = html;
}
