/* app.js — MF Portfolio Analyzer frontend logic */

// 🔥 FIXED: Proper backend resolution
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
    fundUniverse = data.funds;
    renderFundList(fundUniverse);
  } catch (e) {
    showError("Backend not reachable. Check Render deployment.");
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
  container.innerHTML = "";

  for (const [cat, funds] of Object.entries(universe)) {
    const block = document.createElement("div");
    block.className = "category-block";

    const dotClass = CAT_DOTS[cat] || "large";

    const header = document.createElement("div");
    header.className = "cat-header";
    header.innerHTML = `
      <span class="cat-name">
        <span class="cat-dot ${dotClass}"></span>
        ${cat}
      </span>
      <div style="display:flex;gap:8px">
        <span class="cat-count">${funds.length}</span>
        <span class="cat-toggle">▶</span>
      </div>`;

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

  try {
    const res = await fetch(`${API_BASE}/api/analyze`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ holdings }),
    });

    const data = await res.json();

    if (data.status !== "ok") {
      showError(data.message);
      return;
    }

    console.log("SUCCESS:", data);
  } catch (e) {
    showError("Backend connection failed.");
  }
}

// ── Helpers ────────────────────────────────────────────────────
function showError(msg) {
  console.error(msg);
}
