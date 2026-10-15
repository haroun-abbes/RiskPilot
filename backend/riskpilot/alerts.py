"""Deterministic alert rules on market factors.

rule_type
  level  : x_t compared to threshold
  change : Delta_L x_t = x_t / x_{t-L} - 1 (EQ, FX)  or  x_t - x_{t-L} (IR, CS)
  zscore : Delta_1 x_t / sd(Delta_1 x over the previous 250 obs, excluding t)
direction
  above : value > threshold ;  below : value < threshold ;  abs : |value| > threshold
Pure functions, no randomness, no text generation: the message is a template.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

ZSCORE_WINDOW = 250


def _is_ratio(factor: str) -> bool:
    return factor.startswith(("EQ:", "FX:"))


def rule_values(series: pd.Series, factor: str, rule_type: str, lookback: int) -> pd.Series:
    s = series.dropna()
    if rule_type == "level":
        return s
    if rule_type == "change":
        if lookback < 1:
            raise ValueError("lookback must be >= 1")
        return (s / s.shift(lookback) - 1) if _is_ratio(factor) else (s - s.shift(lookback))
    if rule_type == "zscore":
        d = (s / s.shift(1) - 1) if _is_ratio(factor) else s.diff()
        sd = d.shift(1).rolling(ZSCORE_WINDOW, min_periods=60).std(ddof=1)
        return d / sd
    raise ValueError(f"Unknown rule type {rule_type}")


def triggered(values: pd.Series, direction: str, threshold: float) -> pd.Series:
    v = values.dropna()
    if direction == "above":
        mask = v > threshold
    elif direction == "below":
        mask = v < threshold
    elif direction == "abs":
        mask = v.abs() > threshold
    else:
        raise ValueError(f"Unknown direction {direction}")
    return v[mask]


def fmt_value(factor: str, rule_type: str, x: float) -> str:
    if rule_type == "zscore":
        return f"{x:+.2f} sd"
    if rule_type == "change":
        return f"{x:+.2%}" if _is_ratio(factor) else f"{x * 1e4:+.1f} bp"
    if factor.startswith(("IR:", "CS:")):
        return f"{x:.3%}"
    return f"{x:,.4f}"


def evaluate(series: pd.Series, factor: str, rule_type: str, direction: str, threshold: float, lookback: int, name: str) -> list[dict]:
    hits = triggered(rule_values(series, factor, rule_type, lookback), direction, threshold)
    thr = fmt_value(factor, rule_type, threshold)
    return [
        {"date": d.date(), "value": float(x), "message": f"{name}: {factor} {rule_type} = {fmt_value(factor, rule_type, x)} ({direction} {thr})"}
        for d, x in hits.items()
        if np.isfinite(x)
    ]
