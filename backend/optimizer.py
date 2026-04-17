"""
optimizer.py — Efficient frontier via mean-variance optimization using scipy.
"""

import numpy as np
from scipy.optimize import minimize
from utils import portfolio_metrics, RF


MIN_WEIGHT = 0.00
MAX_WEIGHT = 1.00
N_FRONTIER_POINTS = 30


def _portfolio_volatility(weights, cov_matrix):
    return float(np.sqrt(weights @ cov_matrix @ weights))


def _neg_sharpe(weights, mean_returns, cov_matrix):
    ret, vol, sr = portfolio_metrics(weights, mean_returns, cov_matrix)
    return -sr


def _min_variance_portfolio(mean_returns, cov_matrix, n_funds):
    n = n_funds
    constraints = [
        {"type": "eq", "fun": lambda w: np.sum(w) - 1.0},
    ]
    bounds = tuple((MIN_WEIGHT, MAX_WEIGHT) for _ in range(n))
    x0 = np.full(n, 1.0 / n)
    result = minimize(
        _portfolio_volatility,
        x0,
        args=(cov_matrix,),
        method="SLSQP",
        bounds=bounds,
        constraints=constraints,
        options={"ftol": 1e-9, "maxiter": 1000},
    )
    if result.success:
        return result.x
    return x0


def _max_return_portfolio(mean_returns, n_funds):
    # Unconstrained max return = 100% in highest-return fund (subject to MAX_WEIGHT)
    n = n_funds
    x0 = np.full(n, 1.0 / n)
    constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}]
    bounds = tuple((MIN_WEIGHT, MAX_WEIGHT) for _ in range(n))
    result = minimize(
        lambda w: -float(np.dot(w, mean_returns)),
        x0,
        method="SLSQP",
        bounds=bounds,
        constraints=constraints,
        options={"ftol": 1e-9, "maxiter": 1000},
    )
    if result.success:
        return result.x
    return x0


def _target_return_portfolio(target_ret, mean_returns, cov_matrix, n_funds):
    n = n_funds
    constraints = [
        {"type": "eq", "fun": lambda w: np.sum(w) - 1.0},
        {"type": "eq", "fun": lambda w: float(np.dot(w, mean_returns)) - target_ret},
    ]
    bounds = tuple((MIN_WEIGHT, MAX_WEIGHT) for _ in range(n))
    x0 = np.full(n, 1.0 / n)
    result = minimize(
        _portfolio_volatility,
        x0,
        args=(cov_matrix,),
        method="SLSQP",
        bounds=bounds,
        constraints=constraints,
        options={"ftol": 1e-9, "maxiter": 1000},
    )
    if result.success and abs(np.sum(result.x) - 1.0) < 1e-4:
        return result.x
    return None


def generate_efficient_frontier(mean_returns, cov_matrix, codes, fund_names):
    """
    Returns list of frontier portfolio dicts:
    [{return, volatility, sharpe, weights: {code: w}, label}, ...]
    """
    mean_returns = np.array(mean_returns)
    cov_matrix = np.array(cov_matrix)
    n = len(mean_returns)

    if n < 3:
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
        weight_dict = {codes[i]: round(float(w[i]), 4) for i in range(n)}
        frontier.append({
            "return": round(ret, 4),
            "volatility": round(vol, 4),
            "sharpe": round(sr, 4),
            "weights": weight_dict,
        })

    # Also compute max-Sharpe point
    constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}]
    bounds = tuple((MIN_WEIGHT, MAX_WEIGHT) for _ in range(n))
    x0 = np.full(n, 1.0 / n)
    res_sharpe = minimize(
        _neg_sharpe,
        x0,
        args=(mean_returns, cov_matrix),
        method="SLSQP",
        bounds=bounds,
        constraints=constraints,
        options={"ftol": 1e-9, "maxiter": 1000},
    )
    if res_sharpe.success:
        w = res_sharpe.x
        ret, vol, sr = portfolio_metrics(w, mean_returns, cov_matrix)
        weight_dict = {codes[i]: round(float(w[i]), 4) for i in range(n)}
        frontier.append({
            "return": round(ret, 4),
            "volatility": round(vol, 4),
            "sharpe": round(sr, 4),
            "weights": weight_dict,
            "is_max_sharpe": True,
        })

    # Sort by volatility
    frontier.sort(key=lambda x: x["volatility"])
    return frontier


def build_optimal_portfolio(selected_frontier_point, macro_alloc, codes, fund_categories, fund_names):
    """
    Combine selected frontier weights with macro category allocation.
    selected_frontier_point: one dict from frontier list
    macro_alloc: dict from portfolio_engine.macro_equity_allocation
    Returns final_weights dict {code: weight}
    """
    base_weights = dict(selected_frontier_point["weights"])
    category_splits = macro_alloc["category_splits"]
    equity_pct = macro_alloc["equity_pct"]

    # Group codes by category
    cat_codes = {}
    for code in codes:
        cat = fund_categories.get(code, "Large Cap")
        if cat in category_splits:
            cat_codes.setdefault(cat, []).append(code)

    final_weights = {}
    for cat, target_frac in category_splits.items():
        target_w = target_frac * equity_pct
        members = cat_codes.get(cat, [])
        if not members:
            continue
        # Distribute target_w among members proportionally to frontier weights
        raw = {c: base_weights.get(c, 1.0 / len(members)) for c in members}
        raw_sum = sum(raw.values())
        if raw_sum == 0:
            raw_sum = 1.0
        for c in members:
            final_weights[c] = raw[c] / raw_sum * target_w

    # Normalize to 1
    total = sum(final_weights.values())
    if total > 0:
        for c in final_weights:
            final_weights[c] = round(final_weights[c] / total, 4)

    # Clamp to [MIN_WEIGHT, MAX_WEIGHT]
    for c in final_weights:
        final_weights[c] = max(MIN_WEIGHT, min(MAX_WEIGHT, final_weights[c]))

    # Re-normalize after clamping
    total = sum(final_weights.values())
    if total > 0:
        for c in final_weights:
            final_weights[c] = round(final_weights[c] / total, 4)

    return final_weights


def compute_actions(current_analysis, optimal_weights, fund_names, total_value):
    """
    Compare current weights vs optimal. Return buy/sell/hold actions.
    """
    current_weights = {
        current_analysis["codes"][i]: current_analysis["weights"][i]
        for i in range(len(current_analysis["codes"]))
    }

    all_codes = set(list(current_weights.keys()) + list(optimal_weights.keys()))
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

        name = fund_names.get(code, code)
        actions.append({
            "scheme_code": code,
            "name": name,
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
