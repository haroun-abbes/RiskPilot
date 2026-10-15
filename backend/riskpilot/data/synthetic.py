"""Deterministic SYNTHETIC market dataset for demonstration.

Every instrument here is fictitious (invented issuers and tickers) so that no
synthetic price can be mistaken for a real market quote.

Model (daily, business days)
* Two regional equity market factors (EU, US): GARCH(1,1) volatility with
  Student-t(5) innovations (unit variance), correlation 0.75, plus a
  scripted risk-off episode to provide a stress window.
* Single stocks: r_i = beta_i m_region + sigma_i eps_i (t(5)).
* ETFs track the regional index with small tracking noise.
* Government curves (EUR, USD): level / slope factors with weak mean
  reversion; level changes positively correlated with equities.
* Credit spreads (IG, HY): widen when equities fall, mean reverting.
* FX (EUR per unit): USD, CHF, JPY appreciate in risk-off.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

SEED = 42
START, END = "2022-10-03", "2026-10-14"
STRESS_START, STRESS_DAYS = "2025-03-24", 18

EQUITIES = [
    # ticker, name, sector, country, ccy, region, beta, idio vol (daily), start price
    ("NRDB", "Nordbank AG", "Financials", "DE", "EUR", "EU", 1.25, 0.012, 24.0),
    ("HELX", "Helix Pharma SE", "Health Care", "FR", "EUR", "EU", 0.70, 0.010, 88.0),
    ("VLTA", "Volta Energie SA", "Utilities", "FR", "EUR", "EU", 0.55, 0.008, 15.5),
    ("ORBS", "Orbis Software NV", "Technology", "NL", "EUR", "EU", 1.35, 0.015, 142.0),
    ("CALD", "Caldera Industrie SpA", "Industrials", "IT", "EUR", "EU", 1.10, 0.011, 37.0),
    ("MERI", "Meridian Retail SA", "Consumer Discretionary", "ES", "EUR", "EU", 1.00, 0.012, 21.0),
    ("ATLC", "Atlas Cloud Inc.", "Technology", "US", "USD", "US", 1.40, 0.016, 210.0),
    ("PNCL", "Pinnacle Health Corp.", "Health Care", "US", "USD", "US", 0.80, 0.010, 64.0),
    ("THMS", "Thames Utilities plc", "Utilities", "GB", "GBP", "EU", 0.50, 0.008, 9.4),
    ("ALPN", "Alpine Foods AG", "Consumer Staples", "CH", "CHF", "EU", 0.60, 0.008, 102.0),
]
ETFS = [
    ("SXEU", "Synthetic Euro Equity ETF", "EUR", "EU", 48.0),
    ("SXUS", "Synthetic US Equity ETF", "USD", "US", 61.0),
]
TENORS = ["3M", "1Y", "2Y", "5Y", "10Y", "30Y"]
TENOR_Y = np.array([0.25, 1, 2, 5, 10, 30])
CURVES = {
    "EUR": np.array([0.0215, 0.0205, 0.0210, 0.0235, 0.0270, 0.0305]),
    "USD": np.array([0.0420, 0.0400, 0.0385, 0.0395, 0.0425, 0.0460]),
}
SPREADS = {("EUR", "IG"): 0.0110, ("EUR", "HY"): 0.0360, ("USD", "IG"): 0.0100, ("USD", "HY"): 0.0340}
FX = {"USD": (0.92, 0.0045, -0.12), "GBP": (1.16, 0.0040, 0.02), "CHF": (1.04, 0.0040, -0.08), "JPY": (0.0062, 0.0060, -0.15)}


def _t(rng, size, df=5):
    return rng.standard_t(df, size) / np.sqrt(df / (df - 2))


def generate() -> tuple[pd.DataFrame, dict]:
    rng = np.random.default_rng(SEED)
    idx = pd.bdate_range(START, END)
    n = len(idx)
    stress_i0 = idx.get_indexer([pd.Timestamp(STRESS_START)], method="bfill")[0]
    stress = np.zeros(n)
    stress[stress_i0 : stress_i0 + STRESS_DAYS] = 1.0

    # --- equity market factors with GARCH(1,1)
    lr_var = 0.0105**2
    a, b = 0.08, 0.90
    omega = lr_var * (1 - a - b)
    z = _t(rng, (n, 2))
    z[:, 1] = 0.75 * z[:, 0] + np.sqrt(1 - 0.75**2) * z[:, 1]
    m = np.zeros((n, 2))
    h = np.full(2, lr_var)
    for t in range(n):
        drift = np.array([0.00045, 0.00050]) - stress[t] * np.array([0.007, 0.0055])
        if stress[t]:
            h = np.maximum(h, 4.0 * lr_var)
        m[t] = drift + np.sqrt(h) * z[t]
        h = omega + a * (m[t] - drift) ** 2 + b * h

    data, meta = {}, {}
    region_col = {"EU": 0, "US": 1}
    for tk, name, sector, ctry, ccy, reg, beta, ivol, p0 in EQUITIES:
        r = beta * m[:, region_col[reg]] + ivol * _t(rng, n)
        data[f"EQ:{tk}"] = p0 * np.cumprod(1 + r)
        meta[f"EQ:{tk}"] = {"name": name, "class": "EQ", "unit": f"{ccy} per share", "currency": ccy, "sector": sector, "country": ctry}
    for tk, name, ccy, reg, p0 in ETFS:
        r = m[:, region_col[reg]] + 0.0012 * rng.standard_normal(n)
        data[f"EQ:{tk}"] = p0 * np.cumprod(1 + r)
        meta[f"EQ:{tk}"] = {"name": name, "class": "EQ", "unit": f"{ccy} per unit", "currency": ccy, "sector": "Equity ETF", "country": reg}

    # --- curves
    slope_load = (np.log(TENOR_Y) - np.log(TENOR_Y).mean()) / np.ptp(np.log(TENOR_Y))
    for ccy, base in CURVES.items():
        col = 0 if ccy == "EUR" else 1
        lvl_shock = 0.00045 * (0.3 * z[:, col] + np.sqrt(1 - 0.09) * rng.standard_normal(n))
        slp_shock = 0.00022 * rng.standard_normal(n)
        lvl_shock -= stress * 0.0006  # flight to quality
        curve = np.zeros((n, len(TENORS)))
        cur = base.copy()
        for t in range(n):
            cur = cur + 0.006 * (base - cur) + lvl_shock[t] + slp_shock[t] * slope_load
            curve[t] = cur
        for j, tn in enumerate(TENORS):
            data[f"IR:{ccy}:{tn}"] = curve[:, j]
            meta[f"IR:{ccy}:{tn}"] = {"name": f"{ccy} government curve {tn} (synthetic)", "class": "IR", "unit": "decimal yield", "currency": ccy}

    # --- spreads
    for (ccy, bucket), s0 in SPREADS.items():
        col = 0 if ccy == "EUR" else 1
        beta, noise = (0.030, 0.00012) if bucket == "IG" else (0.11, 0.0004)
        s = np.zeros(n)
        cur = s0
        for t in range(n):
            cur = max(0.002, cur + 0.004 * (s0 - cur) - beta * m[t, col] + noise * rng.standard_normal())
            s[t] = cur
        data[f"CS:{ccy}:{bucket}"] = s
        meta[f"CS:{ccy}:{bucket}"] = {"name": f"{ccy} {bucket} corporate spread index (synthetic)", "class": "CS", "unit": "decimal spread", "currency": ccy}

    # --- FX (EUR per unit of foreign currency)
    for ccy, (x0, vol, beta) in FX.items():
        r = beta * m[:, 0] + vol * _t(rng, n)
        data[f"FX:{ccy}"] = x0 * np.cumprod(1 + r)
        meta[f"FX:{ccy}"] = {"name": f"{ccy} in EUR (EUR per 1 {ccy})", "class": "FX", "unit": f"EUR per {ccy}", "currency": ccy}

    df = pd.DataFrame(data, index=idx)
    df.index.name = "date"
    return df.round(8), meta


DATASET_INFO = {
    "id": "synthetic-demo-v1",
    "name": "Synthetic demo market data",
    "provenance": "SYNTHETIC",
    "source": f"RiskPilot synthetic generator v1 (seed {SEED})",
    "description": (
        "Fictitious instruments and simulated end-of-day levels (GARCH equity factors, "
        "t-distributed shocks, mean-reverting curves and spreads, scripted risk-off episode "
        f"starting {STRESS_START}). Not market data."
    ),
    "license_note": "Generated locally; free to use. Must never be presented as market data.",
    "frequency": "Daily (business days), end of day",
}
