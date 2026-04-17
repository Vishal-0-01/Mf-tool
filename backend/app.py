"""
app.py — Flask backend for MF Portfolio Analyzer
Run: gunicorn app:app
"""

import logging
import os
import numpy as np
import traceback

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

# ── Logging ─────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ── App init ─────────────────────────────────────────────────────────────
app = Flask(__name__)
CORS(app)

# ── Load NAV data ───────────────────────────────────────────────────────
logger.info("Loading NAV data...")
NAV_DATA = load_nav_data()
logger.info(f"NAV data loaded for {len(NAV_DATA)} funds.")

# ── Safe JSON conversion ────────────────────────────────────────────────
def to_serializable(obj):
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, (np.float64, np.float32, np.float16)):
        return float(obj)
    elif isinstance(obj, (np.int64, np.int32)):
        return int(obj)
    elif isinstance(obj, dict):
        return {k: to_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [to_serializable(i) for i in obj]
    return obj


# ── Routes ───────────────────────────────────────────────────────────────

@app.route("/api/funds", methods=["GET"])
def get_funds():
    result = {}
    for fund in FUND_UNIVERSE:
        result.setdefault(fund["category"], []).append({
            "scheme_code": fund["scheme_code"],
            "name": fund["name"],
            "category": fund["category"],
        })
    return jsonify({"status": "ok", "funds": result})


@app.route("/api/analyze", methods=["POST"])
def analyze():
    try:
        body = request.get_json(force=True)

        holdings = body.get("holdings", [])
        pe = float(body.get("pe", 22.0))
        pb = float(body.get("pb", 3.2))
        frontier_index = body.get("frontier_index", None)

        # ── Validation ─────────────────────────────────────────
        if len(holdings) < 3:
            return jsonify({"status": "error", "message": "Select at least 3 funds."}), 400

        for h in holdings:
            if float(h.get("amount", 0)) <= 0:
                return jsonify({
                    "status": "error",
                    "message": f"Amount must be > 0 for {h['scheme_code']}"
                }), 400

        # ── 1. Current portfolio ───────────────────────────────
        current = analyze_current_portfolio(holdings, NAV_DATA)

        codes = current["codes"]
        mean_returns = np.array(current["mean_returns"], dtype=float)
        cov_matrix = np.array(current["cov_matrix"], dtype=float)

        fund_names = {f["scheme_code"]: f["name"] for f in current["funds"]}
        fund_categories = {f["scheme_code"]: f["category"] for f in current["funds"]}

        # ── 2. Efficient frontier ─────────────────────────────
        frontier = generate_efficient_frontier(
            mean_returns,
            cov_matrix,
            codes,
            [fund_names.get(c, c) for c in codes]
        )

        # 🔥 HARD FALLBACK (prevents crash)
        if not frontier:
            n = len(codes)
            w = np.full(n, 1.0 / n)
            ret, vol, sr = portfolio_metrics(w, mean_returns, cov_matrix)

            frontier = [{
                "return": float(round(ret, 4)),
                "volatility": float(round(vol, 4)),
                "sharpe": float(round(sr, 4)),
                "weights": {codes[i]: float(round(w[i], 4)) for i in range(n)}
            }]

        # ── 3. Macro allocation ───────────────────────────────
        macro = macro_equity_allocation(pe, pb)

        # ── 4. Select frontier point ──────────────────────────
        def safe_sharpe(x):
            return float(x.get("sharpe", 0))

        if frontier_index is None:
            idx = max(range(len(frontier)), key=lambda i: safe_sharpe(frontier[i]))
        else:
            idx = max(0, min(int(frontier_index), len(frontier) - 1))

        selected = frontier[idx]

        # ── 5. Optimal portfolio ──────────────────────────────
        optimal_weights = build_optimal_portfolio(
            selected,
            macro,
            codes,
            fund_categories,
            fund_names
        )

        # 🔥 fallback if optimizer gives garbage
        if not optimal_weights or sum(optimal_weights.values()) == 0:
            n = len(codes)
            optimal_weights = {codes[i]: 1.0 / n for i in range(n)}

        # ── 6. Actions ───────────────────────────────────────
        action_result = compute_actions(
            current,
            optimal_weights,
            fund_names,
            current["total_value"]
        )

        # ── 7. Metrics ───────────────────────────────────────
        w_arr = np.array([optimal_weights.get(c, 0.0) for c in codes], dtype=float)

        if w_arr.sum() == 0:
            w_arr = np.full(len(codes), 1.0 / len(codes))
        else:
            w_arr = w_arr / w_arr.sum()

        # prevent NaNs
        w_arr = np.nan_to_num(w_arr, nan=0.0)

        try:
            opt_ret, opt_vol, opt_sr = portfolio_metrics(
                w_arr,
                mean_returns,
                cov_matrix
            )
        except Exception:
            opt_ret, opt_vol, opt_sr = 0.0, 0.0, 0.0

        # ── 8. Insights ──────────────────────────────────────
        insights = _generate_insights(
            current, macro, action_result, opt_ret, opt_vol, opt_sr
        )

        response = {
            "status": "ok",
            "current_portfolio": current,
            "optimal_portfolio": {
                "weights": optimal_weights,
                "return": float(round(opt_ret, 4)),
                "volatility": float(round(opt_vol, 4)),
                "sharpe": float(round(opt_sr, 4)),
            },
            "frontier": frontier,
            "selected_frontier_index": idx,
            "macro": macro,
            "actions": action_result,
            "insights": insights,
        }

        return jsonify(to_serializable(response))

    except Exception as e:
        logger.error(traceback.format_exc())
        return jsonify({
            "status": "error",
            "message": str(e),
            "trace": traceback.format_exc()
        }), 500


@app.route("/api/reload", methods=["POST"])
def reload_nav():
    global NAV_DATA
    NAV_DATA = load_nav_data(force_refresh=True)
    return jsonify({"status": "ok", "message": f"Reloaded {len(NAV_DATA)} funds."})


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "nav_funds": len(NAV_DATA)})


# ── Insights ─────────────────────────────────────────────────────────────
def _generate_insights(current, macro, action_result, opt_ret, opt_vol, opt_sr):
    insights = []

    z = macro["z_score"]
    eq_pct = macro["equity_pct"]

    if z > 1.0:
        insights.append(f"Market overvalued → Equity {eq_pct*100:.0f}%")
    elif z < -1.0:
        insights.append(f"Market undervalued → Equity {eq_pct*100:.0f}%")
    else:
        insights.append(f"Market fair → Equity {eq_pct*100:.0f}%")

    if opt_ret > current["portfolio_return"]:
        insights.append("Return improved")

    if opt_vol < current["portfolio_volatility"]:
        insights.append("Volatility reduced")

    if opt_sr > current["sharpe"]:
        insights.append("Sharpe improved")

    return insights


# ── Run ──────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
