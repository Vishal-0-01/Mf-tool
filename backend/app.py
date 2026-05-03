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

# ── Logging ─────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ── App init ────────────────────────────────────────────
app = Flask(__name__)
CORS(app)

# ── Load NAV data ───────────────────────────────────────
logger.info("Loading NAV data...")
NAV_DATA = load_nav_data()
logger.info(f"NAV data loaded for {len(NAV_DATA)} funds.")


# ── JSON safe conversion ────────────────────────────────
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


# ── Routes ─────────────────────────────────────────────

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

        # ── Validation ─────────────────────────
        if len(holdings) < 3:
            return jsonify({"status": "error", "message": "Select at least 3 funds."}), 400

        for h in holdings:
            if float(h.get("amount", 0)) <= 0:
                return jsonify({
                    "status": "error",
                    "message": f"Amount must be > 0 for {h['scheme_code']}"
                }), 400

        # ── 1. Portfolio analysis ──────────────
        current = analyze_current_portfolio(holdings, NAV_DATA)

        # 🔥 USE FILTERED DATA (CORE FIX)
        codes = current["filtered_codes"]
        mean_returns = np.array(current["filtered_returns"], dtype=float)
        cov_matrix = np.array(current["filtered_cov_matrix"], dtype=float)

        # full maps (then filtered)
        full_names = {f["scheme_code"]: f["name"] for f in current["funds"]}
        full_categories = {f["scheme_code"]: f["category"] for f in current["funds"]}

        fund_names = {k: v for k, v in full_names.items() if k in codes}
        fund_categories = {k: v for k, v in full_categories.items() if k in codes}

        # ── 2. Efficient frontier ─────────────
        frontier = generate_efficient_frontier(
            mean_returns,
            cov_matrix,
            codes,
            [fund_names.get(c, c) for c in codes]
        )

        # fallback
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

        # ── 3. Macro ──────────────────────────
        macro = macro_equity_allocation(pe, pb)

        # ── 4. Select point ───────────────────
        def safe_sharpe(x):
            return float(x.get("sharpe", 0))

        if frontier_index is None:
            idx = max(range(len(frontier)), key=lambda i: safe_sharpe(frontier[i]))
        else:
            idx = max(0, min(int(frontier_index), len(frontier) - 1))

        selected = frontier[idx]

        # ── 5. Optimal allocation ─────────────
        optimal_weights = build_optimal_portfolio(
            selected,
            macro,
            codes,  # filtered only
            fund_categories,
            fund_names
        )

        if not optimal_weights or sum(optimal_weights.values()) == 0:
            n = len(codes)
            optimal_weights = {codes[i]: 1.0 / n for i in range(n)}

        # ── 6. Actions (FULL portfolio context) ──
        action_result = compute_actions(
            current,  # full portfolio
            optimal_weights,
            full_names,
            current["total_value"]
        )

        # ── 7. Metrics (on filtered set) ───────
        w_arr = np.array([optimal_weights.get(c, 0.0) for c in codes], dtype=float)

        if w_arr.sum() == 0:
            w_arr = np.full(len(codes), 1.0 / len(codes))
        else:
            w_arr = w_arr / w_arr.sum()

        w_arr = np.nan_to_num(w_arr, nan=0.0)

        try:
            opt_ret, opt_vol, opt_sr = portfolio_metrics(
                w_arr,
                mean_returns,
                cov_matrix
            )
        except Exception:
            opt_ret, opt_vol, opt_sr = 0.0, 0.0, 0.0

        # ── 8. Insights ───────────────────────
        insights = _generate_insights(
            current, macro, action_result, opt_ret, opt_vol, opt_sr
        )

        # ── NEW FEATURES ───────────────────────

# 1. Unconstrained frontier
        try:
            frontier_unconstrained = generate_unconstrained_frontier(
                 mean_returns, cov_matrix, codes
            )
        except Exception:
            frontier_unconstrained = []

# 2. Target portfolio (same risk)
        target_vol = current["portfolio_volatility"]
        try:
            target_portfolio = optimize_target_risk(
                mean_returns, cov_matrix, codes, target_vol
            )
        except Exception:
            target_portfolio = {}

# 3. Adjusted user portfolio
        try:
            adjusted_user_portfolio = compute_adjusted_user_portfolio(
                current, macro, mean_returns, cov_matrix, codes
            )
        except Exception:
            adjusted_user_portfolio = {}

# 4. Comparison
        comparison = {
            "same_risk": {
                "target_volatility": target_vol,
                "user_return": current["portfolio_return"],
                "target_return": target_portfolio.get("return", 0),
                "optimal_return": opt_ret,
                "user_sharpe": current["sharpe"],
                "target_sharpe": target_portfolio.get("sharpe", 0),
                "optimal_sharpe": opt_sr,
            }
        }

# 5. Constraint impact
        constraint_impact = {
            "return_loss": target_portfolio.get("return", 0) - opt_ret,
            "sharpe_loss": target_portfolio.get("sharpe", 0) - opt_sr,
        }

# 6. Exposure
        try:
            exposure = compute_exposure(current)
        except:
            exposure = {}

# 7. Diagnostics
        try:
            risk_contribution = compute_risk_contribution(
                [optimal_weights.get(c, 0.0) for c in codes],
                cov_matrix,
                codes
            )
        except:
            risk_contribution = {}

        try:
            concentration = compute_concentration(
                current["weights"],
                current["codes"]
            )
        except:
            concentration = {}

        try:
            redundancy = compute_redundancy(
                build_returns_matrix(NAV_DATA, codes),
                codes
            )
        except:
            redundancy = []

        diagnostics = {
            "risk_contribution": risk_contribution,
            "concentration": concentration,
            "redundancy": redundancy,
        }

# 8. Macro sensitivity
        try:
            macro_sensitivity = compute_macro_sensitivity(pe, pb)
        except:
            macro_sensitivity = []

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
            "frontier_constrained": frontier,
            "frontier_unconstrained": frontier_unconstrained,
            "selected_frontier_index": idx,
            "macro": macro,
            "actions": action_result,
            "insights": insights,

    # 🔥 THESE WERE MISSING
            "target_portfolio": target_portfolio,
            "adjusted_user_portfolio": adjusted_user_portfolio,
            "comparison": comparison,
            "constraint_impact": constraint_impact,
            "exposure": exposure,
            "diagnostics": diagnostics,
            "macro_sensitivity": macro_sensitivity,
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


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
