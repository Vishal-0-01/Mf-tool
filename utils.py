"""
utils.py — Shared math utilities.
"""

import numpy as np
import pandas as pd

RF = 0.065  # risk-free rate (6.5% p.a.)
TRADING_DAYS = 252


def compute_daily_returns(nav_series: pd.Series) -> pd.Series:
    return nav_series.pct_change().dropna()


def annualized_return(daily_returns: pd.Series) -> float:
    n = len(daily_returns)
    if n < 2:
        return 0.0
    cum = (1 + daily_returns).prod()
    return float(cum ** (TRADING_DAYS / n) - 1)


def annualized_volatility(daily_returns: pd.Series) -> float:
    return float(daily_returns.std() * np.sqrt(TRADING_DAYS))


def sharpe_ratio(ret: float, vol: float, rf: float = RF) -> float:
    if vol == 0:
        return 0.0
    return (ret - rf) / vol


def sortino_ratio(daily_returns: pd.Series, ann_ret: float, rf: float = RF) -> float:
    downside = daily_returns[daily_returns < 0]
    if len(downside) < 2:
        return 0.0
    downside_std = float(downside.std() * np.sqrt(TRADING_DAYS))
    if downside_std == 0:
        return 0.0
    return (ann_ret - rf) / downside_std


def build_returns_matrix(nav_data: dict, codes: list) -> pd.DataFrame:
    """
    Build aligned daily-returns DataFrame for selected scheme codes.
    Uses pairwise NaN handling (outer join, then each pair cov is computed independently).
    """
    series_list = {}
    for code in codes:
        if code in nav_data:
            dr = compute_daily_returns(nav_data[code])
            series_list[code] = dr
    df = pd.DataFrame(series_list)
    return df


def covariance_matrix(returns_df: pd.DataFrame) -> pd.DataFrame:
    """pandas cov with min_periods for pairwise NaN handling."""
    return returns_df.cov(min_periods=30) * TRADING_DAYS


def portfolio_metrics(weights: np.ndarray, mean_returns: np.ndarray, cov_matrix: np.ndarray):
    """
    weights: 1D array summing to 1
    mean_returns: annualized returns array
    cov_matrix: annualized cov matrix
    Returns: (portfolio_return, portfolio_volatility, sharpe)
    """
    ret = float(np.dot(weights, mean_returns))
    vol = float(np.sqrt(weights @ cov_matrix @ weights))
    sr = sharpe_ratio(ret, vol)
    return ret, vol, sr
