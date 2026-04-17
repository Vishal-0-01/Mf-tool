"""
data_fetcher.py — Fetches NAV history using mftool; falls back to synthetic data.
Corrected Scheme Codes for HDFC and Franklin Flexi Cap.
"""

import os
import pickle
import logging
from datetime import datetime, timedelta
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# FUND UNIVERSE  (~60 funds across 5 categories)
# ─────────────────────────────────────────────
# Note: Codes updated to Regular - Growth (AMFI Standards)
FUND_UNIVERSE = [
    # Large Cap
    {"name": "Mirae Asset Large Cap Fund",          "scheme_code": "118989", "category": "Large Cap"},
    {"name": "Axis Bluechip Fund",                  "scheme_code": "120465", "category": "Large Cap"},
    {"name": "Canara Robeco Bluechip Equity Fund",  "scheme_code": "103504", "category": "Large Cap"},
    {"name": "HDFC Top 100 Fund",                   "scheme_code": "118533", "category": "Large Cap"},
    {"name": "ICICI Pru Bluechip Fund",             "scheme_code": "120586", "category": "Large Cap"},
    {"name": "Nippon India Large Cap Fund",         "scheme_code": "118701", "category": "Large Cap"},
    {"name": "Kotak Bluechip Fund",                 "scheme_code": "120230", "category": "Large Cap"},
    {"name": "SBI Bluechip Fund",                   "scheme_code": "119598", "category": "Large Cap"},
    {"name": "DSP Top 100 Equity Fund",             "scheme_code": "119285", "category": "Large Cap"},
    {"name": "Franklin India Bluechip Fund",        "scheme_code": "100032", "category": "Large Cap"},
    {"name": "UTI Mastershare Fund",                "scheme_code": "100091", "category": "Large Cap"},
    {"name": "Invesco India Largecap Fund",         "scheme_code": "119617", "category": "Large Cap"},

    # Flexi Cap
    {"name": "Parag Parikh Flexi Cap Fund",         "scheme_code": "122639", "category": "Flexi Cap"},
    {"name": "UTI Flexi Cap Fund",                  "scheme_code": "120716", "category": "Flexi Cap"},
    {"name": "Quant Flexi Cap Fund",                "scheme_code": "120842", "category": "Flexi Cap"},
    {"name": "HDFC Flexi Cap Fund",                 "scheme_code": "100375", "category": "Flexi Cap"}, # Corrected from 100033
    {"name": "PGIM India Flexi Cap Fund",           "scheme_code": "120594", "category": "Flexi Cap"},
    {"name": "JM Flexicap Fund",                    "scheme_code": "100048", "category": "Flexi Cap"},
    {"name": "Canara Robeco Flexi Cap Fund",        "scheme_code": "103503", "category": "Flexi Cap"},
    {"name": "Franklin India Flexi Cap Fund",       "scheme_code": "100525", "category": "Flexi Cap"}, # Corrected from 100033
    {"name": "Axis Flexi Cap Fund",                 "scheme_code": "120503", "category": "Flexi Cap"},
    {"name": "Kotak Flexicap Fund",                 "scheme_code": "120255", "category": "Flexi Cap"},
    {"name": "Aditya Birla SL Flexi Cap Fund",      "scheme_code": "119533", "category": "Flexi Cap"},
    {"name": "ICICI Pru Flexicap Fund",             "scheme_code": "120604", "category": "Flexi Cap"},

    # Mid Cap
    {"name": "Quant Mid Cap Fund",                  "scheme_code": "120844", "category": "Mid Cap"},
    {"name": "Axis Midcap Fund",                    "scheme_code": "120468", "category": "Mid Cap"},
    {"name": "PGIM India Midcap Opp Fund",          "scheme_code": "120492", "category": "Mid Cap"},
    {"name": "Mirae Asset Midcap Fund",             "scheme_code": "125354", "category": "Mid Cap"},
    {"name": "Nippon India Growth Fund",            "scheme_code": "118704", "category": "Mid Cap"},
    {"name": "Kotak Emerging Equity Fund",          "scheme_code": "120238", "category": "Mid Cap"},
    {"name": "HDFC Mid-Cap Opportunities Fund",     "scheme_code": "118577", "category": "Mid Cap"},
    {"name": "SBI Magnum Midcap Fund",              "scheme_code": "119593", "category": "Mid Cap"},
    {"name": "Edelweiss Mid Cap Fund",              "scheme_code": "120684", "category": "Mid Cap"},
    {"name": "DSP Midcap Fund",                     "scheme_code": "119289", "category": "Mid Cap"},
    {"name": "Canara Robeco Emerging Equities",     "scheme_code": "103509", "category": "Mid Cap"},
    {"name": "Invesco India Midcap Fund",           "scheme_code": "120648", "category": "Mid Cap"},

    # Small Cap
    {"name": "Quant Small Cap Fund",                "scheme_code": "120843", "category": "Small Cap"},
    {"name": "Nippon India Small Cap Fund",         "scheme_code": "118778", "category": "Small Cap"},
    {"name": "HDFC Small Cap Fund",                 "scheme_code": "118576", "category": "Small Cap"},
    {"name": "SBI Small Cap Fund",                  "scheme_code": "125497", "category": "Small Cap"},
    {"name": "Axis Small Cap Fund",                 "scheme_code": "120474", "category": "Small Cap"},
    {"name": "Kotak Small Cap Fund",                "scheme_code": "120243", "category": "Small Cap"},
    {"name": "DSP Small Cap Fund",                  "scheme_code": "119290", "category": "Small Cap"},
    {"name": "Union Small Cap Fund",                "scheme_code": "120849", "category": "Small Cap"},
    {"name": "Canara Robeco Small Cap Fund",        "scheme_code": "147622", "category": "Small Cap"},
    {"name": "Edelweiss Small Cap Fund",            "scheme_code": "147623", "category": "Small Cap"},
    {"name": "ICICI Pru Smallcap Fund",             "scheme_code": "120601", "category": "Small Cap"},
    {"name": "Tata Small Cap Fund",                 "scheme_code": "145552", "category": "Small Cap"},

    # Hybrid
    {"name": "ICICI Pru Balanced Advantage Fund",  "scheme_code": "120587", "category": "Hybrid"},
    {"name": "HDFC Balanced Advantage Fund",        "scheme_code": "118578", "category": "Hybrid"},
    {"name": "Kotak Equity Hybrid Fund",            "scheme_code": "120241", "category": "Hybrid"},
    {"name": "SBI Equity Hybrid Fund",              "scheme_code": "119597", "category": "Hybrid"},
    {"name": "DSP Equity & Bond Fund",              "scheme_code": "119288", "category": "Hybrid"},
    {"name": "Canara Robeco Equity Hybrid Fund",    "scheme_code": "103507", "category": "Hybrid"},
    {"name": "Mirae Asset Hybrid Equity Fund",      "scheme_code": "119648", "category": "Hybrid"},
    {"name": "Axis Regular Saver Fund",             "scheme_code": "120466", "category": "Hybrid"},
    {"name": "Franklin India Equity Hybrid Fund",   "scheme_code": "100299", "category": "Hybrid"},
    {"name": "Nippon India Equity Hybrid Fund",     "scheme_code": "118706", "category": "Hybrid"},
    {"name": "Quant Absolute Fund",                 "scheme_code": "120841", "category": "Hybrid"},
    {"name": "Aditya Birla SL Equity Hybrid 95",   "scheme_code": "119532", "category": "Hybrid"},
]

CACHE_FILE = "nav_cache.pkl"
CACHE_TTL_HOURS = 12


def _load_cache():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "rb") as f:
                data = pickle.load(f)
            if datetime.now() - data.get("ts", datetime.min) < timedelta(hours=CACHE_TTL_HOURS):
                return data.get("nav_data")
        except Exception:
            pass
    return None


def _save_cache(nav_data):
    try:
        with open(CACHE_FILE, "wb") as f:
            pickle.dump({"ts": datetime.now(), "nav_data": nav_data}, f)
    except Exception as e:
        logger.warning(f"Cache save failed: {e}")


def _synthetic_nav(seed: int, n: int = 756) -> pd.Series:
    """Generate ~3 years of synthetic daily NAV."""
    rng = np.random.default_rng(seed)
    annual_ret = rng.uniform(0.08, 0.22)
    annual_vol = rng.uniform(0.12, 0.28)
    daily_ret = annual_ret / 252
    daily_vol = annual_vol / np.sqrt(252)
    returns = rng.normal(daily_ret, daily_vol, n)
    nav = 100 * np.cumprod(1 + returns)
    end = datetime.today()
    dates = pd.bdate_range(end=end, periods=n)
    return pd.Series(nav, index=dates)


def _clean_nav(series: pd.Series) -> pd.Series:
    """Sort asc, remove dups, business days only, forward-fill max 3 days."""
    series = series.sort_index()
    series = series[~series.index.duplicated(keep="last")]
    series = series[series.index.dayofweek < 5]
    series = series.asfreq("B")
    series = series.ffill(limit=3)
    series = series.dropna()
    return series


def _fetch_mftool(scheme_code: str, n_days: int = 756) -> pd.Series | None:
    try:
        from mftool import Mftool
        mf = Mftool()
        end = datetime.today()
        start = end - timedelta(days=n_days + 100)
        data = mf.get_scheme_historical_nav(
            scheme_code,
            start.strftime("%d-%m-%Y"),
            end.strftime("%d-%m-%Y"),
        )
        if not data or "data" not in data:
            return None
        records = data["data"]
        if not records:
            return None
        df = pd.DataFrame(records)
        df["date"] = pd.to_datetime(df["date"], dayfirst=True, errors="coerce")
        df["nav"] = pd.to_numeric(df["nav"], errors="coerce")
        df = df.dropna()
        series = pd.Series(df["nav"].values, index=df["date"].values)
        return series
    except Exception as e:
        logger.debug(f"mftool failed for {scheme_code}: {e}")
        return None


def load_nav_data(force_refresh: bool = False) -> dict:
    """
    Returns dict: {scheme_code: pd.Series (cleaned NAV)}
    Tries mftool; falls back to synthetic.
    """
    if not force_refresh:
        cached = _load_cache()
        if cached is not None:
            logger.info("Loaded NAV data from cache.")
            return cached

    nav_data = {}
    for i, fund in enumerate(FUND_UNIVERSE):
        code = fund["scheme_code"]
        series = _fetch_mftool(code)
        if series is None or len(series) < 60:
            logger.info(f"Synthetic NAV for: {fund['name']}")
            series = _synthetic_nav(seed=i + 1)
        else:
            logger.info(f"Live NAV fetched: {fund['name']}")
        nav_data[code] = _clean_nav(series)

    _save_cache(nav_data)
    logger.info(f"NAV data ready for {len(nav_data)} funds.")
    return nav_data
