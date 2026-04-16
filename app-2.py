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
from utils import build_returns_matrix, annualized_return, annualized_volatility, sharpe_ratio

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# ── Load NAV data once at startup ─────────────────────────────────────────────
NAV_DATA = {}

@app.before_request
def ensure_nav_loaded():
    global NAV_DATA
    if not NAV_DATA:
        logger.info("Loading NAV data...")
        NAV_DATA = load_nav_data()
        logger.info(f"NAV data loaded for {len(NAV_DATA)} funds.")


# ── Routes ────────────────────────────────────────────────────────────────────

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
    """
    Body:
    {
      "holdings": [{"scheme_code": "...", "amount": 10000}, ...],
      "pe": 22.5,
      "pb": 3.1,
      "frontier_index": 15   // optional: which frontier point user selected (0-indexed)
    }
    """
    global NAV_DATA

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
            return jsonify({"status": "error", "message": f"Amount must be > 0 for {h['scheme_code']}"}), 400

    # 1. Current portfolio analysis
    try:
        current = analyze_current_portfolio(holdings, NAV_DATA)
    except Exception as e:
        logger.exception("Error in current portfolio analysis")
        return jsonify({"status": "error", "message": str(e)}), 500

    codes = current["codes"]
    mean_returns = current["mean_returns"]
    cov_matrix = current["cov_matrix"]
    fund_names = {f["scheme_code"]: f["name"] for f in current["funds"]}
    fund_categories = {f["scheme_code"]: f["category"] for f in current["funds"]}

    # 2. Efficient frontier
    try:
        frontier = generate_efficient_frontier(
            mean_returns, cov_matrix, codes,
            [fund_names.get(c, c) for c in codes]
        )
    except Exception as e:
        logger.exception("Error generating frontier")
        return jsonify({"status": "error", "message": "Frontier generation failed: " + str(e)}), 500

    if not frontier:
        return jsonify({"status": "error", "message": "Could not compute efficient frontier. Try different funds."}), 400

    # 3. Macro allocation
    macro = macro_equity_allocation(pe, pb)

    # 4. Select frontier point
    if frontier_index is None:
        # Default: max Sharpe
        max_sharpe_idx = max(range(len(frontier)), key=lambda i: frontier[i]["sharpe"])
        selected = frontier[max_sharpe_idx]
        selected_idx = max_sharpe_idx
    else:
        selected_idx = max(0, min(int(frontier_index), len(frontier) - 1))
        selected = frontier[selected_idx]

    # 5. Optimal portfolio
    try:
        optimal_weights = build_optimal_portfolio(
            selected, macro, codes, fund_categories, fund_names
        )
    except Exception as e:
        logger.exception("Error building optimal portfolio")
        return jsonify({"status": "error", "message": str(e)}), 500

    # 6. Actions
    action_result = compute_actions(current, optimal_weights, fund_names, current["total_value"])

    # 7. Optimal metrics
    import numpy as np
    from utils import portfolio_metrics
    w_arr = np.array([optimal_weights.get(c, 0.0) for c in codes])
    w_arr = w_arr / w_arr.sum()
    opt_ret, opt_vol, opt_sr = portfolio_metrics(w_arr, np.array(mean_returns), np.array(cov_matrix))

    # 8. Insights
    insights = _generate_insights(current, macro, action_result, opt_ret, opt_vol, opt_sr)

    return jsonify({
        "status": "ok",
        "current_portfolio": {
            "funds": current["funds"],
            "portfolio_return": current["portfolio_return"],
            "portfolio_volatility": current["portfolio_volatility"],
            "sharpe": current["sharpe"],
            "total_value": current["total_value"],
            "category_weights": current["category_weights"],
        },
        "optimal_portfolio": {
            "weights": optimal_weights,
            "return": round(opt_ret, 4),
            "volatility": round(opt_vol, 4),
            "sharpe": round(opt_sr, 4),
        },
        "frontier": frontier,
        "selected_frontier_index": selected_idx,
        "macro": macro,
        "actions": action_result,
        "insights": insights,
    })


@app.route("/api/reload", methods=["POST"])
def reload_nav():
    """Force refresh NAV cache."""
    global NAV_DATA
    NAV_DATA = load_nav_data(force_refresh=True)
    return jsonify({"status": "ok", "message": f"Reloaded {len(NAV_DATA)} funds."})


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "nav_funds": len(NAV_DATA)})


# ── Helpers ───────────────────────────────────────────────────────────────────

def _generate_insights(current, macro, action_result, opt_ret, opt_vol, opt_sr):
    insights = []

    z = macro["z_score"]
    eq_pct = macro["equity_pct"]
    if z > 1.0:
        insights.append(f"⚠️ Market appears overvalued (z={z:.2f}). Equity allocation reduced to {eq_pct*100:.0f}%.")
    elif z < -1.0:
        insights.append(f"✅ Market appears undervalued (z={z:.2f}). Equity allocation increased to {eq_pct*100:.0f}%.")
    else:
        insights.append(f"📊 Market at fair value (z={z:.2f}). Equity allocation: {eq_pct*100:.0f}%.")

    ret_improvement = opt_ret - current["portfolio_return"]
    vol_change = opt_vol - current["portfolio_volatility"]

    if ret_improvement > 0.005:
        insights.append(f"📈 Optimized portfolio improves expected return by {ret_improvement*100:.1f}% p.a.")
    if vol_change < -0.005:
        insights.append(f"🛡️ Optimized portfolio reduces volatility by {abs(vol_change)*100:.1f}%.")
    if opt_sr > current["sharpe"] + 0.05:
        insights.append(f"🏆 Sharpe ratio improves from {current['sharpe']:.2f} → {opt_sr:.2f}.")

    turnover = action_result["turnover"]
    if turnover > 0.3:
        insights.append(f"🔄 High portfolio turnover ({turnover*100:.0f}%). Consider phased rebalancing.")
    elif turnover < 0.1:
        insights.append("✅ Low turnover — rebalancing is cost-efficient.")

    cost = action_result["transaction_cost_inr"]
    if cost > 0:
        insights.append(f"💸 Estimated transaction cost: ₹{cost:,.0f} ({action_result['transaction_cost_pct']*100:.2f}%).")

    return insights


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
