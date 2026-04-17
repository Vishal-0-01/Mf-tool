"""
optimizer.py — Efficient frontier with dynamic constraints + diversification control.
"""

import numpy as np
from scipy.optimize import minimize
from utils import portfolio_metrics

# ── CONFIG ─────────────────────────────────────────────
N_FRONTIER_POINTS = 30
DIVERSIFICATION_PENALTY = 0.15  # higher = more diversification

# ───────────────────────────────────────────────────────


def get_weight_bounds(n):
    """
    Dynamic bounds to avoid concentration + infeasibility
    """
    MIN_WEIGHT = 0.0
    MAX_WEIGHT = min(0.40, 2.5 / n)  # adaptive cap
    return MIN_WEIGHT, MAX_WEIGHT


# ───────────────────────────────────────────────────────

def _portfolio_volatility(weights, cov_matrix):
    return float(np.sqrt(weights @ cov_matrix @ weights))


def _concentration_penalty(weights):
    return np.sum(weights**2)


def _neg_sharpe(weights, mean_returns, cov_matrix):
    ret, vol, sr = portfolio_metrics(weights, mean_returns, cov_matrix)

    penalty = _concentration_penalty(weights)

    return -(sr - DIVERSIFICATION_PENALTY * penalty)


# ───────────────────────────────────────────────────────

def _min_variance_portfolio(mean_returns, cov_matrix, n):
    min_w, max_w = get_weight_bounds(n)

    constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}]
    bounds = tuple((min_w, max_w) for _ in range(n))
    x0 = np.full(n, 1.0 / n)

    result = minimize(
        _portfolio_volatility,
        x0,
        args=(cov_matrix,),
        method="SLSQP",
        bounds=bounds,
        constraints=constraints,
    )

    return result.x if result.success else x0


def _max_return_portfolio(mean_returns, n):
    min_w, max_w = get_weight_bounds(n)

    constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}]
    bounds = tuple((min_w, max_w) for _ in range(n))
    x0 = np.full(n, 1.0 / n)

    result = minimize(
        lambda w: -np.dot(w, mean_returns),
        x0,
        method="SLSQP",
        bounds=bounds,
        constraints=constraints,
    )

    return result.x if result.success else x0


def _target_return_portfolio(target_ret, mean_returns, cov_matrix, n):
    min_w, max_w = get_weight_bounds(n)

    constraints = [
        {"type": "eq", "fun": lambda w: np.sum(w) - 1.0},
        {"type": "eq", "fun": lambda w: np.dot(w, mean_returns) - target_ret},
    ]

    bounds = tuple((min_w, max_w) for _ in range(n))
    x0 = np.full(n, 1.0 / n)

    result = minimize(
        _portfolio_volatility,
        x0,
        args=(cov_matrix,),
        method="SLSQP",
        bounds=bounds,
        constraints=constraints,
    )

    return result.x if result.success else None


# ───────────────────────────────────────────────────────

def generate_efficient_frontier(mean_returns, cov_matrix, codes, fund_names):
    mean_returns = np.array(mean_returns)
    cov_matrix = np.array(cov_matrix)
    n = len(mean_returns)

    if n < 3:
        return []

    w_min = _min_variance_portfolio(mean_returns, cov_matrix, n)
    w_max = _max_return_portfolio(mean_returns, n)

    ret_min = np.dot(w_min, mean_returns)
    ret_max = np.dot(w_max, mean_returns)

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
            "return": round(float(ret), 4),
            "volatility": round(float(vol), 4),
            "sharpe": round(float(sr), 4),
            "weights": {codes[i]: round(float(w[i]), 4) for i in range(n)},
        })

    # ── Max Sharpe with diversification penalty ──
    min_w, max_w = get_weight_bounds(n)

    constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}]
    bounds = tuple((min_w, max_w) for _ in range(n))
    x0 = np.full(n, 1.0 / n)

    res = minimize(
        _neg_sharpe,
        x0,
        args=(mean_returns, cov_matrix),
        method="SLSQP",
        bounds=bounds,
        constraints=constraints,
    )

    if res.success:
        w = res.x
        ret, vol, sr = portfolio_metrics(w, mean_returns, cov_matrix)

        frontier.append({
            "return": round(float(ret), 4),
            "volatility": round(float(vol), 4),
            "sharpe": round(float(sr), 4),
            "weights": {codes[i]: round(float(w[i]), 4) for i in range(n)},
            "is_max_sharpe": True,
        })

    frontier.sort(key=lambda x: x["volatility"])
    return frontier


# ───────────────────────────────────────────────────────

def build_optimal_portfolio(selected_point, macro_alloc, codes, fund_categories, fund_names):
    base_weights = selected_point["weights"]
    category_splits = macro_alloc["category_splits"]
    equity_pct = macro_alloc["equity_pct"]

    final_weights = {}

    # group funds by category
    category_map = {}
    for c in codes:
        cat = fund_categories.get(c, "Large Cap")
        category_map.setdefault(cat, []).append(c)

    # allocate per category
    for cat, target_frac in category_splits.items():
        members = category_map.get(cat, [])
        if not members:
            continue

        target_weight = target_frac * equity_pct

        raw = np.array([base_weights.get(m, 0.0) for m in members])

        if raw.sum() == 0:
            raw = np.ones(len(members))

        raw = raw / raw.sum()

        for i, m in enumerate(members):
            final_weights[m] = raw[i] * target_weight

    # ── Apply dynamic caps ──
    n = len(final_weights)
    min_w, max_w = get_weight_bounds(n)

    for k in final_weights:
        final_weights[k] = min(max_w, max(0.0, final_weights[k]))

    # normalize
    total = sum(final_weights.values())
    if total > 0:
        final_weights = {k: round(v / total, 4) for k, v in final_weights.items()}

    return final_weights


# ───────────────────────────────────────────────────────

def compute_actions(current_analysis, optimal_weights, fund_names, total_value):
    current_weights = {
        current_analysis["codes"][i]: current_analysis["weights"][i]
        for i in range(len(current_analysis["codes"]))
    }

    all_codes = set(current_weights) | set(optimal_weights)

    actions = []
    total_buy = total_sell = 0.0

    for code in all_codes:
        curr = current_weights.get(code, 0.0)
        opt = optimal_weights.get(code, 0.0)
        delta = opt - curr

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
            "current_weight": round(curr, 4),
            "optimal_weight": round(opt, 4),
            "delta": round(delta, 4),
            "action": action,
            "amount_change": round(delta * total_value, 2),
        })

    actions.sort(key=lambda x: abs(x["delta"]), reverse=True)

    turnover = (total_buy + total_sell) / 2
    cost_pct = turnover * 0.002

    return {
        "actions": actions,
        "turnover": round(turnover, 4),
        "transaction_cost_pct": round(cost_pct, 4),
        "transaction_cost_inr": round(cost_pct * total_value, 2),
    }
