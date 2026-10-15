"""Data-quality checks on a market dataset (levels, one column per factor).

Checks per factor
* coverage (first/last observation, count)
* missing observations inside the series range (NaN on dataset dates)
* calendar gaps > 5 calendar days between consecutive observations
* stale values: >= 5 consecutive identical observations
* non-positive levels for price / FX factors
* implausible rate or spread level (|x| > 0.5 in decimal, likely percent units)
* outlier moves: |robust z| > 8 on daily changes (MAD scaled to sigma)
Nothing is ever corrected or filled automatically; issues are reported.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def factor_report(name: str, s: pd.Series) -> dict:
    issues = []
    obs = s.dropna()
    if obs.empty:
        return {"factor": name, "count": 0, "missing": int(len(s)), "first": None, "last": None, "issues": [{"severity": "error", "check": "empty", "message": "No observations"}]}
    inside = s.loc[obs.index[0] : obs.index[-1]]
    missing = int(inside.isna().sum())
    if missing:
        issues.append({"severity": "warning", "check": "missing", "message": f"{missing} missing observation(s) within range"})
    gaps = obs.index.to_series().diff().dt.days
    big = gaps[gaps > 5]
    if len(big):
        issues.append({"severity": "warning", "check": "gap", "message": f"{len(big)} gap(s) > 5 calendar days, largest {int(big.max())} days ending {big.idxmax().date()}"})
    runs = (obs != obs.shift()).cumsum()
    longest = int(obs.groupby(runs).size().max())
    if longest >= 5:
        issues.append({"severity": "warning", "check": "stale", "message": f"{longest} consecutive identical values (possible stale feed)"})
    cls = name.split(":")[0]
    if cls in ("EQ", "FX") and (obs <= 0).any():
        issues.append({"severity": "error", "check": "non_positive", "message": "Non-positive price level"})
    if cls in ("IR", "CS") and (obs.abs() > 0.5).any():
        issues.append({"severity": "error", "check": "units", "message": "Level above 50%: values are probably in percent, expected decimal"})
    ch = (obs / obs.shift(1) - 1) if cls in ("EQ", "FX") else obs.diff()
    ch = ch.dropna()
    if len(ch) > 20:
        med = ch.median()
        mad = (ch - med).abs().median() * 1.4826
        if mad > 0:
            z = (ch - med) / mad
            out = z[z.abs() > 8]
            if len(out):
                issues.append({"severity": "info", "check": "outlier", "message": f"{len(out)} daily move(s) beyond 8 robust sigmas (largest on {out.abs().idxmax().date()})"})
    return {
        "factor": name,
        "count": int(obs.size),
        "missing": missing,
        "first": obs.index[0].date().isoformat(),
        "last": obs.index[-1].date().isoformat(),
        "last_value": float(obs.iloc[-1]),
        "issues": issues,
    }


def dataset_report(levels: pd.DataFrame) -> dict:
    factors = [factor_report(c, levels[c]) for c in levels.columns]
    sev = {"error": 0, "warning": 0, "info": 0}
    for f in factors:
        for i in f["issues"]:
            sev[i["severity"]] += 1
    lasts = [f["last"] for f in factors if f["last"]]
    return {
        "n_factors": len(factors),
        "n_dates": int(len(levels)),
        "start": levels.index[0].date().isoformat() if len(levels) else None,
        "end": levels.index[-1].date().isoformat() if len(levels) else None,
        "stale_factors": sorted({f["factor"] for f in factors if f["last"] and lasts and f["last"] < max(lasts)}),
        "issue_counts": sev,
        "factors": factors,
    }
