"""
portfolio_engine.py — Computes current portfolio metrics and macro allocation.
"""

import numpy as np
import pandas as pd
from utils import (
    build_returns_matrix,
    covariance_matrix,
    annualized_return,
    annualized_volatility,
    sharpe_ratio,
    sortino_ratio,
    portfolio_metrics,
    RF,
)
from data_fetcher import FUND_UNIVERSE


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────
def get_fund_meta(scheme_code: str) -> dict:
    for f in FUND_UNIVERSE:
        if f["scheme_code"] == scheme_code:
            return f
    return {}


# ─────────────────────────────────────────────
# Portfolio Analysis
# ─────────────────────────────────────────────
def analyze_current_portfolio(holdings: list, nav_data: dict) -> dict:
    """
    holdings: [{"scheme_code": str, "amount": float}, ...]
    Returns current portfolio analysis dict.
    """

    if not holdings:
        raise ValueError("No holdings provided")

    codes = [h["scheme_code"] for h in holdings]
    amounts = np.array([h["amount"] for h in holdings], dtype=float)

    total = amounts.sum()
    if total <= 0:
        raise ValueError("Total investment must be > 0")

    weights = amounts / total

    # ── Returns Matrix ──
    returns_df = build_returns_matrix(nav_data, codes)

    if returns_df.empty:
        raise ValueError("No NAV/returns data available")

    returns_df = returns_df.dropna(how="all")

    # ── Fund-level stats ──
    fund_stats = []
    mean_ann_returns = []

    for i, code in enumerate(codes):
        dr = returns_df[code].dropna() if code in returns_df.columns else pd.Series(dtype=float)

        if len(dr) > 1:
            ann_ret = annualized_return(dr)
            ann_vol = annualized_volatility(dr)
            sr = sharpe_ratio(ann_ret, ann_vol)
            so = sortino_ratio(dr, ann_ret)
        else:
            ann_ret, ann_vol, sr, so = 0.0, 0.0, 0.0, 0.0

        meta = get_fund_meta(code)

        fund_stats.append({
            "scheme_code": code,
            "name": meta.get("name", code),
            "category": meta.get("category", "Unknown"),
            "weight": round(float(weights[i]), 4),
            "amount": round(float(amounts[i]), 2),
            "annualized_return": round(ann_ret, 4),
            "annualized_volatility": round(ann_vol, 4),
            "sharpe": round(sr, 4),
            "sortino": round(so, 4),
        })

        mean_ann_returns.append(ann_ret)

    mean_ann_returns = np.array(mean_ann_returns)

    # ── Covariance Matrix ──
    cov = covariance_matrix(returns_df.reindex(columns=codes))
    cov_np = cov.values

    # 🔥 FULL NaN HANDLING (critical fix)
    cov_np = np.nan_to_num(cov_np, nan=0.0)

    # Ensure diagonal stability
    for i in range(len(codes)):
        if cov_np[i, i] <= 0:
            dr = returns_df[codes[i]].dropna() if codes[i] in returns_df else pd.Series()
            if len(dr) > 1:
                cov_np[i, i] = (dr.std() ** 2) * 252
            else:
                cov_np[i, i] = 0.04  # fallback (20% vol)

    # ── Portfolio Metrics ──
    try:
        p_ret, p_vol, p_sr = portfolio_metrics(weights, mean_ann_returns, cov_np)
    except Exception:
        # fallback safe values
        p_ret, p_vol, p_sr = 0.0, 0.0, 0.0

    # ── Category Breakdown ──
    category_weights = {}
    for i, fs in enumerate(fund_stats):
        cat = fs["category"]
        category_weights[cat] = category_weights.get(cat, 0) + float(weights[i])

    # Normalize category weights (safety)
    total_cat = sum(category_weights.values())
    if total_cat > 0:
        category_weights = {k: v / total_cat for k, v in category_weights.items()}

    return {
        "funds": fund_stats,
        "weights": weights.tolist(),
        "codes": codes,
        "total_value": round(total, 2),
        "portfolio_return": round(p_ret, 4),
        "portfolio_volatility": round(p_vol, 4),
        "sharpe": round(p_sr, 4),
        "category_weights": {k: round(v, 4) for k, v in category_weights.items()},
        "mean_returns": mean_ann_returns.tolist(),
        "cov_matrix": cov_np.tolist(),
    }


# ─────────────────────────────────────────────
# Macro Allocation
# ─────────────────────────────────────────────
def macro_equity_allocation(pe: float, pb: float) -> dict:
    """
    Compute equity allocation % and category splits from PE/PB z-scores.
    """

    PE_MEAN, PE_STD = 22.0, 5.0
    PB_MEAN, PB_STD = 3.2, 0.7

    z_pe = (pe - PE_MEAN) / PE_STD
    z_pb = (pb - PB_MEAN) / PB_STD
    z = (z_pe + z_pb) / 2.0

    # Clamp z
    z_clamped = max(-2.0, min(2.0, z))

    # Equity allocation
    equity_pct = 0.70 - (z_clamped / 2.0) * 0.20
    equity_pct = max(0.50, min(0.90, equity_pct))

    # Category tilts
    large_w = 0.35 + z_clamped * 0.03
    small_w = 0.15 - z_clamped * 0.03
    mid_w   = 0.25 - z_clamped * 0.01
    flexi_w = 0.25 - z_clamped * 0.01

    total_eq = large_w + flexi_w + mid_w + small_w

    if total_eq == 0:
        total_eq = 1.0  # safety

    cat_splits = {
        "Large Cap": round(large_w / total_eq, 4),
        "Flexi Cap": round(flexi_w / total_eq, 4),
        "Mid Cap":   round(mid_w / total_eq, 4),
        "Small Cap": round(small_w / total_eq, 4),
    }

    return {
        "equity_pct": round(equity_pct, 4),
        "z_score": round(z, 4),
        "z_pe": round(z_pe, 4),
        "z_pb": round(z_pb, 4),
        "category_splits": cat_splits,
    }
