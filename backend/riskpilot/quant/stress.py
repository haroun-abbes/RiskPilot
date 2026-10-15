"""Stress-testing engine.

Two scenario kinds, kept strictly separate:

* ``hypothetical`` – user-defined instantaneous shocks:
    equity : decimal returns, resolution priority ticker > sector > country > all
    rates  : bp per currency, parallel + optional tenor points (linearly
             interpolated across the curve, flat beyond end points)
    spreads: bp per rating bucket (IG / HY), applied to non-sovereign bonds
    fx     : decimal change of the foreign currency value in EUR
* ``historical`` – replays the cumulative factor moves observed in the
  loaded dataset between two dates (equity/FX: L_end/L_start - 1;
  rates/spreads: L_end - L_start). Its provenance is that of the dataset:
  a replay on synthetic data is a synthetic scenario.

Revaluation is instantaneous (no carry, no roll-down, no rebalancing).
Bonds are fully revalued; the duration-convexity approximation is reported
alongside for comparison. Factor-class contributions are computed by
shocking one class at a time; the remainder is reported as ``interaction``
(cross effects, e.g. FX x equity) so the waterfall always adds up.
"""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from . import bonds as bd
from .engine import (
    PositionValuation,
    interpolation_weights,
    moves_for_position,
    revalue,
    tenor_years,
)

CLASSES = ("equity", "rates", "spreads", "fx")


def _tenor_curve_shift(rates_ccy: dict, maturity_years: float) -> float:
    """Rate shock (decimal) at a maturity from a {parallel_bp, tenor_bp} spec."""
    par = float(rates_ccy.get("parallel_bp", 0.0))
    pts = rates_ccy.get("tenor_bp") or {}
    extra = 0.0
    if pts:
        items = sorted((tenor_years(k), float(v)) for k, v in pts.items())
        ts = [t for t, _ in items]
        vs = np.array([v for _, v in items])
        extra = float(interpolation_weights(ts, maturity_years) @ vs)
    return (par + extra) / 10_000.0


def hypothetical_moves(pv: PositionValuation, spec: dict, as_of: date) -> dict:
    """Per-position moves split by factor class for a hypothetical scenario."""
    eq = spec.get("equity") or {}
    rates = spec.get("rates") or {}
    spreads = spec.get("spreads") or {}
    fx = spec.get("fx") or {}
    a = pv.attributes or {}
    moves = {"r_eq": 0.0, "r_fx": 0.0, "dy_rates": 0.0, "dy_spread": 0.0}
    if pv.instrument_type in ("EQUITY", "ETF"):
        ticker = pv.eq_factor.split(":", 1)[1] if pv.eq_factor else None
        r = eq.get("all", 0.0)
        if a.get("country") and a["country"] in (eq.get("by_country") or {}):
            r = eq["by_country"][a["country"]]
        if a.get("sector") and a["sector"] in (eq.get("by_sector") or {}):
            r = eq["by_sector"][a["sector"]]
        if ticker and ticker in (eq.get("by_ticker") or {}):
            r = eq["by_ticker"][ticker]
        moves["r_eq"] = float(r)
    if pv.instrument_type == "BOND_FIXED":
        mat = (date.fromisoformat(a["maturity"]) - as_of).days / 365.25
        if pv.currency in rates:
            moves["dy_rates"] = _tenor_curve_shift(rates[pv.currency], mat)
        if pv.cs_factor:
            bucket = pv.cs_factor.split(":")[-1]
            moves["dy_spread"] = float(spreads.get(bucket, 0.0)) / 10_000.0
        # sovereign or unmapped bonds receive no spread shock (documented)
    if pv.currency != "EUR":
        moves["r_fx"] = float(fx.get(pv.currency, 0.0))
    return moves


def historical_moves(pv: PositionValuation, levels: pd.DataFrame, start: date, end: date) -> tuple[dict, list[str]]:
    lv = levels.loc[pd.Timestamp(start) : pd.Timestamp(end)]
    if len(lv) < 2:
        raise ValueError("Historical window must contain at least two observations")
    first, last = lv.iloc[0], lv.iloc[-1]
    issues = []
    ch = {}
    for f in [pv.eq_factor, pv.fx_factor, pv.cs_factor, *pv.ir_factors]:
        if not f:
            continue
        a, b = first.get(f, np.nan), last.get(f, np.nan)
        if pd.isna(a) or pd.isna(b):
            issues.append(f"{f} missing at window boundary; move set to 0 for {pv.id}")
            ch[f] = 0.0
        elif f.startswith(("EQ:", "FX:")):
            ch[f] = b / a - 1.0
        else:
            ch[f] = b - a
    r_eq, r_fx, dy = moves_for_position(pv, ch, 1)
    dy_sp = ch.get(pv.cs_factor, 0.0) if pv.cs_factor else 0.0
    return {
        "r_eq": float(r_eq[0]),
        "r_fx": float(r_fx[0]),
        "dy_rates": float(dy[0] - dy_sp),
        "dy_spread": float(dy_sp),
    }, issues


def _pnl(pv, m, use=("equity", "rates", "spreads", "fx")):
    r_eq = m["r_eq"] if "equity" in use else 0.0
    r_fx = m["r_fx"] if "fx" in use else 0.0
    dy = (m["dy_rates"] if "rates" in use else 0.0) + (m["dy_spread"] if "spreads" in use else 0.0)
    full, _ = revalue(pv, np.array([r_eq]), np.array([r_fx]), np.array([dy]))
    return float(full[0])


def run_scenario(vals: list[PositionValuation], scenario: dict, as_of: date, levels: pd.DataFrame | None = None) -> dict:
    kind = scenario.get("kind", "hypothetical")
    spec = scenario.get("definition") or {}
    rows, issues = [], []
    total_mv = sum(v.mv_base for v in vals if v.mv_base is not None and not v.excluded)
    by_class = {c: 0.0 for c in CLASSES}
    interaction = 0.0
    for v in vals:
        if v.excluded or v.mv_base is None:
            continue
        if kind == "historical":
            if levels is None:
                raise ValueError("Historical scenario requires a market dataset")
            m, iss = historical_moves(v, levels, date.fromisoformat(spec["start"]), date.fromisoformat(spec["end"]))
            issues += iss
        else:
            m = hypothetical_moves(v, spec, as_of)
        total = _pnl(v, m)
        parts = {c: _pnl(v, m, (c,)) for c in CLASSES}
        inter = total - sum(parts.values())
        for c in CLASSES:
            by_class[c] += parts[c]
        interaction += inter
        approx = None
        if v.instrument_type == "BOND_FIXED":
            dy = m["dy_rates"] + m["dy_spread"]
            rel = float(bd.price_change_approximation(v.modified_duration, v.convexity, dy))
            # duration-convexity applied to the local dirty value, then FX
            approx = v.mv_base * ((1 + rel) * (1 + m["r_fx"]) - 1)
        rows.append(
            {
                "id": v.id,
                "name": v.name,
                "asset_class": v.asset_class,
                "currency": v.currency,
                "mv_base": v.mv_base,
                "pnl": total,
                "pnl_pct": total / v.mv_base if v.mv_base else None,
                "pnl_duration_convexity": approx,
                "moves": m,
                "by_class": parts,
                "interaction": inter,
            }
        )
    rows.sort(key=lambda r: r["pnl"])
    total_pnl = sum(r["pnl"] for r in rows)
    return {
        "kind": kind,
        "total_pnl": total_pnl,
        "total_pnl_pct": total_pnl / total_mv if total_mv else None,
        "portfolio_value": total_mv,
        "by_class": by_class,
        "interaction": interaction,
        "positions": rows,
        "issues": issues,
        "excluded": [{"id": v.id, "reason": v.excluded} for v in vals if v.excluded],
    }
