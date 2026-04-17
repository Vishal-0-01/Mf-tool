"""
optimizer.py — Efficient frontier via mean-variance optimization using scipy.
FINAL STABLE + CONSTRAINED VERSION
"""

import numpy as np
from scipy.optimize import minimize
from utils import portfolio_metrics


# 🔥 REALISTIC CONSTRAINTS (KEY FIX)
MIN_WEIGHT = 0.05     # prevents zero allocation
MAX_WEIGHT = 0.40     # prevents concentration
N_FRONTIER_POINTS = 30


# ─────────────────────────────────────────────────────────────
# Core math
# ─────────────────────────────────────────────────────────────
def _portfolio_volatility(weights, cov_matrix):
    return float(np.sqrt(weights @ cov_matrix @ weights))


def _neg_sharpe(weights, mean_returns, cov_matrix):
    ret, vol, sr = portfolio_metrics(weights, mean_returns, cov_matrix)
    return -sr


# ─────────────────────────────────────────────────────────────
# Portfolio builders
# ─────────────────────────────────────────────────────────────
def _min_variance_portfolio(mean_returns, cov_matrix, n):
    constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}]
    bounds = tuple((MIN_WEIGHT, MAX_WEIGHT) for _ in range(n))
    x0 = np.full(n, 1.0 / n)

    res = minimize(
        _portfolio_volatility,
        x0,
        args=(cov_matrix,),
        method="SLSQP",
        bounds=bounds,
        constraints=constraints,
        options={"maxiter": 500}
    )
    return res.x if res.success else x0


def _max_return_portfolio(mean_returns, n):
    constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}]
    bounds = tuple((MIN_WEIGHT, MAX_WEIGHT) for _ in range(n))
    x0 = np.full(n, 1.0 / n)

    res = minimize(
        lambda w: -float(np.dot(w, mean_returns)),
        x0,
        method="SLSQP",
        bounds=bounds,
        constraints=constraints,
        options={"maxiter": 500}
    )
    return res.x if res.success else x0


def _target_return_portfolio(target_ret, mean_returns, cov_matrix, n):
    constraints = [
        {"type": "eq", "fun": lambda w: np.sum(w) - 1.0},
        {"type": "eq", "fun": lambda w: float(np.dot(w, mean_returns)) - target_ret},
    ]
    bounds = tuple((MIN_WEIGHT, MAX_WEIGHT) for _ in range(n))
    x0 = np.full(n, 1.0 / n)

    res = minimize(
        _portfolio_volatility,
        x0,
        args=(cov_matrix,),
        method="SLSQP",
        bounds=bounds,
        constraints=constraints,
        options={"maxiter": 500}
    )

    if res.success and abs(np.sum(res.x) - 1.0) < 1e-4:
        return res.x
    return None


# ─────────────────────────────────────────────────────────────
# Efficient Frontier
# ─────────────────────────────────────────────────────────────
def generate_efficient_frontier(mean_returns, cov_matrix, codes, fund_names):
    mean_returns = np.array(mean_returns)
    cov_matrix = np.array(cov_matrix)
    n = len(mean_returns)

    if n < 2:
        return []

    w_min = _min_variance_portfolio(mean_returns, cov_matrix, n)
    w_max = _max_return_portfolio(mean_returns, n)

    ret_min = float(np.dot(w_min, mean_returns))
    ret_max = float(np.dot(w_max, mean_returns))

    if ret_max <= ret_min:
        ret_max = ret_min + 0.01

    target_returns = np.linspace(ret_min, ret_max, N_FRONTIER_POINTS)

    frontier = []
    for tr in target_returns:
        w = _target_return_portfolio(tr, mean_returns, cov_matrix, n)
        if w is None:
            continue

        ret, vol, sr = portfolio_metrics(w, mean_returns, cov_matrix)

        frontier.append({
            "return": round(ret, 4),
            "volatility": round(vol, 4),
            "sharpe": round(sr, 4),
            "weights": {codes[i]: round(float(w[i]), 4) for i in range(n)},
        })

    # ── Max Sharpe portfolio ──
    constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}]
    bounds = tuple((MIN_WEIGHT, MAX_WEIGHT) for _ in range(n))
    x0 = np.full(n, 1.0 / n)

    res = minimize(
        _neg_sharpe,
        x0,
        args=(mean_returns, cov_matrix),
        method="SLSQP",
        bounds=bounds,
        constraints=constraints,
        options={"maxiter": 500}
    )

    if res.success:
        w = res.x
        ret, vol, sr = portfolio_metrics(w, mean_returns, cov_matrix)

        frontier.append({
            "return": round(ret, 4),
            "volatility": round(vol, 4),
            "sharpe": round(sr, 4),
            "weights": {codes[i]: round(float(w[i]), 4) for i in range(n)},
            "is_max_sharpe": True,
        })

    frontier.sort(key=lambda x: x["volatility"])
    return frontier


# ─────────────────────────────────────────────────────────────
# Allocation Engine (FIXED)
# ─────────────────────────────────────────────────────────────
def build_optimal_portfolio(selected_frontier_point, macro_alloc, codes, fund_categories, fund_names):
    base_weights = dict(selected_frontier_point["weights"])
    category_splits = macro_alloc["category_splits"]
    equity_pct = macro_alloc["equity_pct"]

    final_weights = {}

    # Assign categories safely
    adjusted_categories = {}
    for code in codes:
        cat = fund_categories.get(code)
        if cat not in category_splits:
            cat = "Flexi Cap"
        adjusted_categories[code] = cat

    # Group funds
    cat_codes = {}
    for code, cat in adjusted_categories.items():
        cat_codes.setdefault(cat, []).append(code)

    # Allocate per category
    for cat, target_frac in category_splits.items():
        members = cat_codes.get(cat, [])
        if not members:
            continue

        target_w = target_frac * equity_pct
        raw = {c: base_weights.get(c, 1.0 / len(members)) for c in members}
        raw_sum = sum(raw.values()) or 1.0

        for c in members:
            final_weights[c] = raw[c] / raw_sum * target_w

    # Fill leftover weight
    assigned = sum(final_weights.values())
    leftover = max(0.0, 1.0 - assigned)

    if leftover > 0:
        total_base = sum(base_weights.values()) or 1.0
        for c in base_weights:
            final_weights[c] = final_weights.get(c, 0) + (base_weights[c] / total_base) * leftover

    # 🔥 FINAL SAFETY: enforce caps again
    for c in final_weights:
        final_weights[c] = max(MIN_WEIGHT, min(MAX_WEIGHT, final_weights[c]))

    # Normalize
    total = sum(final_weights.values())
    if total > 0:
        for c in final_weights:
            final_weights[c] = round(final_weights[c] / total, 4)

    return final_weights


# ─────────────────────────────────────────────────────────────
# Actions Engine
# ─────────────────────────────────────────────────────────────
def compute_actions(current_analysis, optimal_weights, fund_names, total_value):
    current_weights = {
        current_analysis["codes"][i]: current_analysis["weights"][i]
        for i in range(len(current_analysis["codes"]))
    }

    all_codes = set(current_weights) | set(optimal_weights)

    actions = []
    total_buy = 0.0
    total_sell = 0.0

    for code in all_codes:
        curr_w = current_weights.get(code, 0.0)
        opt_w = optimal_weights.get(code, 0.0)
        delta = opt_w - curr_w

        if delta > 0.01:
            action = "BUY"
            total_buy += delta
        elif delta < -0.01:
            action = "SELL"
            total_sell += abs(delta)
        else:
            action = "HOLD"

        actions.append({
            "scheme_code": code,
            "name": fund_names.get(code, code),
            "current_weight": round(curr_w, 4),
            "optimal_weight": round(opt_w, 4),
            "delta": round(delta, 4),
            "action": action,
            "amount_change": round(delta * total_value, 2),
        })

    actions.sort(key=lambda x: abs(x["delta"]), reverse=True)

    turnover = (total_buy + total_sell) / 2.0
    transaction_cost = turnover * 0.002

    return {
        "actions": actions,
        "turnover": round(turnover, 4),
        "transaction_cost_pct": round(transaction_cost, 4),
        "transaction_cost_inr": round(transaction_cost * total_value, 2),
    }
