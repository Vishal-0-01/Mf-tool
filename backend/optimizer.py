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


# ═════════════════════════════════════════════════════════════════
# NEW FEATURES — added without modifying any existing code above
# ═════════════════════════════════════════════════════════════════

# ─────────────────────────────────────────────────────────────
# Unconstrained frontier (long-only, fully-invested, no caps)
# ─────────────────────────────────────────────────────────────
def _unc_min_variance(mean_returns, cov_matrix, n):
    constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}]
    bounds = tuple((0.0, 1.0) for _ in range(n))
    x0 = np.full(n, 1.0 / n)
    res = minimize(_portfolio_volatility, x0, args=(cov_matrix,),
                   method="SLSQP", bounds=bounds, constraints=constraints,
                   options={"maxiter": 500})
    return res.x if res.success else x0


def _unc_max_return(mean_returns, n):
    constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}]
    bounds = tuple((0.0, 1.0) for _ in range(n))
    x0 = np.full(n, 1.0 / n)
    res = minimize(lambda w: -float(np.dot(w, mean_returns)), x0,
                   method="SLSQP", bounds=bounds, constraints=constraints,
                   options={"maxiter": 500})
    return res.x if res.success else x0


def _unc_target_return(target_ret, mean_returns, cov_matrix, n):
    constraints = [
        {"type": "eq", "fun": lambda w: np.sum(w) - 1.0},
        {"type": "eq", "fun": lambda w: float(np.dot(w, mean_returns)) - target_ret},
    ]
    bounds = tuple((0.0, 1.0) for _ in range(n))
    x0 = np.full(n, 1.0 / n)
    res = minimize(_portfolio_volatility, x0, args=(cov_matrix,),
                   method="SLSQP", bounds=bounds, constraints=constraints,
                   options={"maxiter": 500})
    if res.success and abs(np.sum(res.x) - 1.0) < 1e-4:
        return res.x
    return None


def generate_unconstrained_frontier(mean_returns, cov_matrix, codes):
    """Long-only, fully-invested, no per-fund caps. Pure benchmark frontier."""
    mean_returns = np.array(mean_returns)
    cov_matrix   = np.array(cov_matrix)
    n = len(mean_returns)
    if n < 2:
        return []

    w_min = _unc_min_variance(mean_returns, cov_matrix, n)
    w_max = _unc_max_return(mean_returns, n)
    ret_min = float(np.dot(w_min, mean_returns))
    ret_max = float(np.dot(w_max, mean_returns))
    if ret_max <= ret_min:
        ret_max = ret_min + 0.01

    frontier = []
    for tr in np.linspace(ret_min, ret_max, N_FRONTIER_POINTS):
        w = _unc_target_return(tr, mean_returns, cov_matrix, n)
        if w is None:
            continue
        ret, vol, sr = portfolio_metrics(w, mean_returns, cov_matrix)
        frontier.append({
            "return":     round(float(ret), 4),
            "volatility": round(float(vol), 4),
            "sharpe":     round(float(sr),  4),
            "weights":    {codes[i]: round(float(w[i]), 4) for i in range(n)},
        })

    frontier.sort(key=lambda x: x["volatility"])
    return frontier


# ─────────────────────────────────────────────────────────────
# Target-risk optimizer (unconstrained benchmark at given vol)
# ─────────────────────────────────────────────────────────────
def optimize_target_risk(mean_returns, cov_matrix, codes, target_volatility):
    """
    Maximize return s.t. vol ≤ target_volatility, long-only, fully invested.
    No macro, no category caps, no per-fund caps.
    """
    mean_returns = np.array(mean_returns)
    cov_matrix   = np.array(cov_matrix)
    n = len(mean_returns)

    constraints = [
        {"type": "eq",  "fun": lambda w: np.sum(w) - 1.0},
        {"type": "ineq","fun": lambda w: target_volatility - _portfolio_volatility(w, cov_matrix)},
    ]
    bounds = tuple((0.0, 1.0) for _ in range(n))
    x0 = np.full(n, 1.0 / n)

    res = minimize(
        lambda w: -float(np.dot(w, mean_returns)),
        x0,
        method="SLSQP",
        bounds=bounds,
        constraints=constraints,
        options={"maxiter": 1000, "ftol": 1e-9},
    )

    w = res.x if res.success else x0
    w = np.clip(w, 0.0, 1.0)
    w = w / w.sum()

    ret, vol, sr = portfolio_metrics(w, mean_returns, cov_matrix)
    return {
        "weights":    {codes[i]: round(float(w[i]), 4) for i in range(n)},
        "return":     round(float(ret), 4),
        "volatility": round(float(vol), 4),
        "sharpe":     round(float(sr),  4),
    }


# ─────────────────────────────────────────────────────────────
# Adjusted user portfolio (scale to macro equity constraint)
# ─────────────────────────────────────────────────────────────
def compute_adjusted_user_portfolio(current_analysis, macro_alloc, mean_returns, cov_matrix, codes):
    """
    Scale user weights proportionally so total equity weight = macro equity_pct.
    No optimization — just proportional rescaling.
    """
    mean_returns = np.array(mean_returns)
    cov_matrix   = np.array(cov_matrix)

    code_to_idx = {c: i for i, c in enumerate(current_analysis["codes"])}
    raw_weights  = np.array(current_analysis["weights"])
    equity_target = macro_alloc["equity_pct"]

    # All funds in current analysis are equity (Hybrid counted at 60% equity proxy)
    hybrid_equity_factor = 0.60
    equity_weights = np.zeros(len(raw_weights))
    for i, fs in enumerate(current_analysis["funds"]):
        if fs["category"] == "Hybrid":
            equity_weights[i] = raw_weights[i] * hybrid_equity_factor
        else:
            equity_weights[i] = raw_weights[i]

    current_equity_total = equity_weights.sum()
    if current_equity_total > 0:
        scale = equity_target / current_equity_total
    else:
        scale = 1.0

    adj_raw = raw_weights * scale
    total = adj_raw.sum()
    if total > 0:
        adj_raw = adj_raw / total

    # Map back to filtered codes for metrics
    filtered_weights = np.array([adj_raw[code_to_idx[c]] if c in code_to_idx else 0.0 for c in codes])
    if filtered_weights.sum() > 0:
        filtered_weights = filtered_weights / filtered_weights.sum()

    ret, vol, sr = portfolio_metrics(filtered_weights, mean_returns, cov_matrix)

    return {
        "weights":    {current_analysis["codes"][i]: round(float(adj_raw[i]), 4)
                       for i in range(len(current_analysis["codes"]))},
        "return":     round(float(ret), 4),
        "volatility": round(float(vol), 4),
        "sharpe":     round(float(sr),  4),
    }


# ─────────────────────────────────────────────────────────────
# Exposure decomposition
# ─────────────────────────────────────────────────────────────
def compute_exposure(current_analysis):
    """Break portfolio into equity%, debt%, and category distribution."""
    HYBRID_EQUITY = 0.60
    HYBRID_DEBT   = 0.40

    equity_pct = 0.0
    debt_pct   = 0.0
    categories = {}

    for i, fs in enumerate(current_analysis["funds"]):
        w   = float(current_analysis["weights"][i])
        cat = fs["category"]
        if cat == "Hybrid":
            equity_pct += w * HYBRID_EQUITY
            debt_pct   += w * HYBRID_DEBT
        else:
            equity_pct += w

        categories[cat] = round(categories.get(cat, 0.0) + w, 4)

    return {
        "equity_pct":  round(equity_pct, 4),
        "debt_pct":    round(debt_pct,   4),
        "categories":  categories,
    }


# ─────────────────────────────────────────────────────────────
# Risk contribution
# ─────────────────────────────────────────────────────────────
def compute_risk_contribution(weights_list, cov_matrix, codes):
    """
    RC_i = w_i * (Cov @ w)_i  — marginal contribution * weight.
    Returns dict {code: RC_i} (unnormalized, sums to portfolio variance).
    """
    w = np.array(weights_list)
    C = np.array(cov_matrix)
    marginal = C @ w
    rc = w * marginal
    return {codes[i]: round(float(rc[i]), 6) for i in range(len(codes))}


# ─────────────────────────────────────────────────────────────
# Concentration metrics
# ─────────────────────────────────────────────────────────────
def compute_concentration(weights_list, codes):
    pairs = sorted(zip(weights_list, codes), reverse=True)
    max_w  = pairs[0][0] if pairs else 0.0
    top3_w = sum(p[0] for p in pairs[:3])
    return {
        "max_weight":  round(float(max_w),  4),
        "top3_weight": round(float(top3_w), 4),
    }


# ─────────────────────────────────────────────────────────────
# Redundancy detection (correlation > threshold)
# ─────────────────────────────────────────────────────────────
def compute_redundancy(returns_df, codes, threshold=0.80):
    """
    Detect pairs with Pearson correlation > threshold.
    returns_df: pd.DataFrame of daily returns.
    """
    import pandas as pd
    sub = returns_df.reindex(columns=codes).dropna(how="all")
    if sub.shape[1] < 2:
        return []

    corr = sub.corr(min_periods=30)
    redundant = []
    n = len(codes)
    for i in range(n):
        for j in range(i + 1, n):
            c1, c2 = codes[i], codes[j]
            if c1 in corr.columns and c2 in corr.columns:
                val = corr.loc[c1, c2]
                if not np.isnan(val) and val > threshold:
                    redundant.append({
                        "fund1":       c1,
                        "fund2":       c2,
                        "correlation": round(float(val), 4),
                    })
    return redundant


# ─────────────────────────────────────────────────────────────
# Macro sensitivity sweep
# ─────────────────────────────────────────────────────────────
def compute_macro_sensitivity(base_pe, base_pb):
    """
    Vary PE ±3 and PB ±0.5 in small steps; return equity_pct for each combo.
    Imports macro_equity_allocation inline to avoid circular imports.
    """
    from portfolio_engine import macro_equity_allocation

    results = []
    for pe_delta in [-3, -1.5, 0, 1.5, 3]:
        for pb_delta in [-0.5, -0.25, 0, 0.25, 0.5]:
            pe_val = round(base_pe + pe_delta, 2)
            pb_val = round(base_pb + pb_delta, 2)
            alloc  = macro_equity_allocation(pe_val, pb_val)
            results.append({
                "pe":         pe_val,
                "pb":         pb_val,
                "equity_pct": alloc["equity_pct"],
                "z_score":    alloc["z_score"],
            })
    return results
