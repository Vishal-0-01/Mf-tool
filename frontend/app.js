app.js — MF Portfolio Analyzer frontend logic */

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
const res = await fetch(${API_BASE}/api/analyze, {
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

async function loadFunds() {
try {
const res = await fetch(${API_BASE}/api/funds);
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
const item = document.querySelector(.fund-item[data-code="${code}"]);
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
async function runAnalysis() {
console.log("ANALYZE CLICKED");

clearError();

if (selectedFunds.size < 3) {
showError("Please select at least 3 funds.");
return;
}

const holdings = [];
let valid = true;

for (const code of selectedFunds) {
const amt = parseFloat(fundAmounts[code]);

if (!amt || amt <= 0) {
valid = false;
} else {
holdings.push({ scheme_code: code, amount: amt });
}

}

if (!valid) {
showError("Enter valid amount for all funds.");
return;
}

try {
showLoader(true);

const res = await fetch(${API_BASE}/api/analyze, {
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
<span class="macro-chip">Equity ${pct(m.equity_pct)}</span>   <span class="macro-chip">z = ${m.z_score.toFixed(2)}</span>;

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
const res = await fetch(${API_BASE}/api/analyze, {
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
? +${(a.delta * 100).toFixed(1)}%
: ${(a.delta * 100).toFixed(1)}%;

const amt = a.amount_change >= 0
? +₹${fmt(a.amount_change)}
: -₹${fmt(Math.abs(a.amount_change))};

tr.innerHTML = `

  <td>${a.name}</td>    
  <td>${(a.current_weight * 100).toFixed(1)}%</td>    
  <td>${(a.optimal_weight * 100).toFixed(1)}%</td>    
  <td style="color:${a.delta >= 0 ? '#4fffb0' : '#ff6b6b'}">${delta}</td>    
  <td>${a.action}</td>    
  <td>${amt}</td>    
`;    tbody.appendChild(tr);

});

// 🔥 THIS WAS MISSING
const turnoverEl = document.getElementById("turnover-val");
const costEl = document.getElementById("txn-cost-val");

if (turnoverEl) {
turnoverEl.textContent = pct(actionData.turnover);
}

if (costEl) {
costEl.textContent = ₹${fmt(actionData.transaction_cost_inr)} (${pct(actionData.transaction_cost_pct)});
}
}

// Insights
function renderInsights(insights) {
const el = document.getElementById("insights-list");
if (!el) return;

el.innerHTML = insights.map(i => <div>${i}</div>).join("");
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
const res = await fetch(${API_BASE}/api/analyze, {
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
