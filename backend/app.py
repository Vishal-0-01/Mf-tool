"""
app.py — Flask backend for MF Portfolio Analyzer
Run: gunicorn app:app
"""

import logging
import os
from flask import Flask, jsonify, request
from flask_cors import CORS

from data_fetcher import FUND_UNIVERSE, load_nav_data
from portfolio_engine import analyze_current_portfolio, macro_equity_allocation
from optimizer import (
    generate_efficient_frontier,
    build_optimal_portfolio,
    compute_actions,
)
from utils import portfolio_metrics

import numpy as np

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# ── GLOBAL STATE ──────────────────────────────────────────────────────────────
NAV_DATA = None


# ── SAFE NAV LOADER ───────────────────────────────────────────────────────────
def get_nav_data():
    global NAV_DATA
    if NAV_DATA is None:
        logger.info("Loading NAV data (lazy load)...")
        NAV_DATA = load_nav_data()
        logger.info(f"NAV loaded for {len(NAV_DATA)} funds")
    return NAV_DATA


# ── ROUTES ────────────────────────────────────────────────────────────────────

@app.route("/api/funds", methods=["GET"])
def get_funds():
    """Return fund universe grouped by category."""
    result = {}
    for fund in FUND_UNIVERSE:
        cat = fund["category"]
        if cat not in result:
            result[cat] = []
        result[cat].append({
            "scheme_code": fund["scheme_code"],
            "name": fund["name"],
            "category": cat,
        })
    return jsonify({"status": "ok", "funds": result})


@app.route("/api/analyze", methods=["POST"])
def analyze():
    NAV = get_nav_data()

    body = request.get_json(force=True)
    holdings = body.get("holdings", [])
    pe = float(body.get("pe", 22.0))
    pb = float(body.get("pb", 3.2))
    frontier_index = body.get("frontier_index", None)

    # Validation
    if len(holdings) < 3:
        return jsonify({"status": "error", "message": "Select at least 3 funds."}), 400

    for h in holdings:
        if float(h.get("amount", 0)) <= 0:
            return jsonify({"status": "error", "message": f"Invalid amount for {h['scheme_code']}"}), 400

    # 1. Current portfolio
    try:
        current = analyze_current_portfolio(holdings, NAV)
    except Exception as e:
        logger.exception("Portfolio analysis failed")
        return jsonify({"status": "error", "message": str(e)}), 500

    codes = current["codes"]
    mean_returns = current["mean_returns"]
    cov_matrix = current["cov_matrix"]

    fund_names = {f["scheme_code"]: f["name"] for f in current["funds"]}
    fund_categories = {f["scheme_code"]: f["category"] for f in current["funds"]}

    # 2. Frontier
    try:
        frontier = generate_efficient_frontier(
            mean_returns, cov_matrix, codes,
            [fund_names.get(c, c) for c in codes]
        )
    except Exception as e:
        logger.exception("Frontier failed")
        return jsonify({"status": "error", "message": str(e)}), 500

    if not frontier:
        return jsonify({"status": "error", "message": "Frontier failed"}), 400

    # 3. Macro
    macro = macro_equity_allocation(pe, pb)

    # 4. Select point
    if frontier_index is None:
        idx = max(range(len(frontier)), key=lambda i: frontier[i]["sharpe"])
    else:
        idx = max(0, min(int(frontier_index), len(frontier) - 1))

    selected = frontier[idx]

    # 5. Optimal weights
    try:
        optimal_weights = build_optimal_portfolio(
            selected, macro, codes, fund_categories, fund_names
        )
    except Exception as e:
        logger.exception("Optimization failed")
        return jsonify({"status": "error", "message": str(e)}), 500

    # 6. Actions
    action_result = compute_actions(
        current,
        optimal_weights,
        fund_names,
        current["total_value"]
    )

    # 7. Metrics
    w = np.array([optimal_weights.get(c, 0.0) for c in codes])
    w = w / w.sum()

    opt_ret, opt_vol, opt_sr = portfolio_metrics(
        w,
        np.array(mean_returns),
        np.array(cov_matrix)
    )

    return jsonify({
        "status": "ok",
        "current": current,
        "optimal": {
            "weights": optimal_weights,
            "return": round(opt_ret, 4),
            "vol": round(opt_vol, 4),
            "sharpe": round(opt_sr, 4),
        },
        "frontier": frontier,
        "selected_index": idx,
        "macro": macro,
        "actions": action_result,
    })


@app.route("/api/reload", methods=["POST"])
def reload_nav():
    global NAV_DATA
    NAV_DATA = load_nav_data(force_refresh=True)
    return jsonify({"status": "ok"})


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})
    

# ── MAIN ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
