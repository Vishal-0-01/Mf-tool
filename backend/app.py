"""
app.py — Flask backend for MF Portfolio Analyzer
Run: gunicorn app:app
"""

import logging
import os
import numpy as np
import traceback
NAV_DATA = None

from flask import Flask, jsonify, request
from flask_cors import CORS

from data_fetcher import FUND_UNIVERSE, load_nav_data
from portfolio_engine import analyze_current_portfolio, macro_equity_allocation
from optimizer import (
    generate_efficient_frontier,
    build_optimal_portfolio,
    compute_actions,
    # ── NEW ──
    generate_unconstrained_frontier,
    optimize_target_risk,
    compute_adjusted_user_portfolio,
    compute_exposure,
    compute_risk_contribution,
    compute_concentration,
    compute_redundancy,
    compute_macro_sensitivity,
)
from utils import portfolio_metrics, build_returns_matrix

# ── Logging ─────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ── App init ────────────────────────────────────────────
app = Flask(__name__)
CORS(app)

# ── Load NAV data ───────────────────────────────────────
#logger.info("Loading NAV data...")
#NAV_DATA = load_nav_data()
#logger.info(f"NAV data loaded for {len(NAV_DATA)} funds.")


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
        global NAV_DATA

        if NAV_DATA is None:
            return jsonify({
               "status": "error",
               "message": "Server warming up. Try again in 30 seconds."
            }), 503

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

        # ════════════════════════════════════════════════
        # NEW FEATURES — appended, nothing above changed
        # ════════════════════════════════════════════════

        # 9. Unconstrained frontier
        try:
            frontier_unconstrained = generate_unconstrained_frontier(
                mean_returns, cov_matrix, codes
            )
        except Exception:
            frontier_unconstrained = []

        # 10. Target-risk portfolio (benchmark at user's portfolio vol)
        target_vol = float(body.get("target_volatility", current["portfolio_volatility"]))
        try:
            target_portfolio = optimize_target_risk(
                mean_returns, cov_matrix, codes, target_vol
            )
        except Exception:
            target_portfolio = {"weights": {}, "return": 0.0, "volatility": 0.0, "sharpe": 0.0}

        # 11. Adjusted user portfolio
        try:
            adjusted_user_portfolio = compute_adjusted_user_portfolio(
                current, macro, mean_returns, cov_matrix, codes
            )
        except Exception:
            adjusted_user_portfolio = {"weights": {}, "return": 0.0, "volatility": 0.0, "sharpe": 0.0}

        # 12. Same-risk comparison (all evaluated at user portfolio volatility)
        try:
            comparison = {
                "same_risk": {
                    "target_volatility": round(target_vol, 4),
                    "user_return":    current["portfolio_return"],
                    "target_return":  target_portfolio["return"],
                    "optimal_return": round(opt_ret, 4),
                    "user_sharpe":    current["sharpe"],
                    "target_sharpe":  target_portfolio["sharpe"],
                    "optimal_sharpe": round(opt_sr, 4),
                }
            }
        except Exception:
            comparison = {}

        # 13. Constraint impact
        try:
            constraint_impact = {
                "return_loss": round(target_portfolio["return"] - opt_ret, 4),
                "sharpe_loss": round(target_portfolio["sharpe"] - opt_sr, 4),
            }
        except Exception:
            constraint_impact = {}

        # 14. Exposure decomposition
        try:
            exposure = compute_exposure(current)
        except Exception:
            exposure = {}

        # 15. Diagnostics
        try:
            filtered_weights_for_diag = [optimal_weights.get(c, 0.0) for c in codes]
            risk_contribution = compute_risk_contribution(
                filtered_weights_for_diag, cov_matrix, codes
            )
        except Exception:
            risk_contribution = {}

        try:
            concentration = compute_concentration(
                [current["weights"][i] for i in range(len(current["codes"]))],
                current["codes"]
            )
        except Exception:
            concentration = {}

        try:
            returns_df_for_redund = build_returns_matrix(NAV_DATA, codes)
            redundancy = compute_redundancy(returns_df_for_redund, codes)
        except Exception:
            redundancy = []

        # 16. Macro sensitivity
        try:
            macro_sensitivity = compute_macro_sensitivity(pe, pb)
        except Exception:
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
            "selected_frontier_index": idx,
            "macro": macro,
            "actions": action_result,
            "insights": insights,
            # ── NEW fields ──
            "frontier_constrained":    frontier,
            "frontier_unconstrained":  frontier_unconstrained,
            "target_portfolio":        target_portfolio,
            "adjusted_user_portfolio": adjusted_user_portfolio,
            "comparison":              comparison,
            "constraint_impact":       constraint_impact,
            "exposure":                exposure,
            "macro_sensitivity":       macro_sensitivity,
            "diagnostics": {
                "risk_contribution": risk_contribution,
                "concentration":     concentration,
                "redundancy":        redundancy,
            },
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

    try:
        logger.info("Reloading NAV data...")

        NAV_DATA = load_nav_data(force_refresh=True)

        logger.info(f"NAV loaded: {len(NAV_DATA)} funds")

        return jsonify({
            "status": "ok",
            "message": f"Reloaded {len(NAV_DATA)} funds."
        })

    except Exception as e:
        logger.error("RELOAD FAILED:")
        logger.error(traceback.format_exc())

        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


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
