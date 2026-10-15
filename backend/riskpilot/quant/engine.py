"""Portfolio valuation, risk-factor mapping and revaluation.

Base currency is EUR. FX factors are quoted as EUR per 1 unit of foreign
currency (``FX:USD`` = value of 1 USD in EUR), so a positive FX return means
the foreign currency appreciates against EUR.

Risk factors (column ids in a market dataset)
    EQ:<TICKER>         price level (local ccy)       change = simple return
    FX:<CCY>            EUR per unit of CCY           change = simple return
    IR:<CCY>:<TENOR>    government zero/par yield (decimal)  change = absolute
    CS:<CCY>:<IG|HY>    credit spread index (decimal)        change = absolute

Revaluation of one position for a factor move (eq return r_e, fx return r_x,
yield change dy):
    Equity / ETF   V1 = q P (1+r_e) X (1+r_x)
    Fixed bond     V1 = N/100 * P_dirty(y0 + dy) * X (1+r_x)   (full revaluation)
                   dy = sum_j w_j(T) dr_j + ds_bucket
    FX cash        V1 = A X (1+r_x)
Linearised (delta) P&L used by the parametric model:
    Equity  V0 (r_e + r_x);  Bond  V0 (-D_mod dy + r_x);  FX  V0 r_x
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd

from . import bonds as bd
from .instruments import (
    EquityPosition,
    FixedBondPosition,
    FxCashPosition,
    Portfolio,
    Position,
    rating_bucket,
)

BASE = "EUR"
ASSET_CLASS = {"EQUITY": "Equity", "ETF": "ETF", "BOND_FIXED": "Fixed income", "FX_CASH": "Cash & FX"}
STALE_FX_DAYS = 5


def tenor_years(tenor: str) -> float:
    m = re.fullmatch(r"(\d+(?:\.\d+)?)([MY])", tenor.strip().upper())
    if not m:
        raise ValueError(f"Bad tenor '{tenor}'")
    v = float(m.group(1))
    return v / 12.0 if m.group(2) == "M" else v


def interpolation_weights(tenors: list[float], t: float) -> np.ndarray:
    """Linear interpolation weights on a tenor grid, flat extrapolation."""
    ts = np.asarray(tenors, dtype=float)
    w = np.zeros(ts.size)
    if t <= ts[0]:
        w[0] = 1.0
    elif t >= ts[-1]:
        w[-1] = 1.0
    else:
        j = int(np.searchsorted(ts, t)) - 1
        a = (t - ts[j]) / (ts[j + 1] - ts[j])
        w[j], w[j + 1] = 1 - a, a
    return w


def curve_factors(columns, ccy: str) -> list[tuple[str, float]]:
    out = []
    for c in columns:
        parts = c.split(":")
        if len(parts) == 3 and parts[0] == "IR" and parts[1] == ccy:
            try:
                out.append((c, tenor_years(parts[2])))
            except ValueError:
                continue
    return sorted(out, key=lambda x: x[1])


@dataclass
class PositionValuation:
    id: str
    instrument_type: str
    asset_class: str
    name: str
    currency: str
    fx_rate: float | None
    mv_local: float | None
    mv_base: float | None
    attributes: dict = field(default_factory=dict)
    # bond analytics
    ytm: float | None = None
    accrued_base: float | None = None
    modified_duration: float | None = None
    convexity: float | None = None
    dv01_base: float | None = None
    # factor mapping
    eq_factor: str | None = None
    fx_factor: str | None = None
    ir_factors: list[str] = field(default_factory=list)
    ir_weights: list[float] = field(default_factory=list)
    cs_factor: str | None = None
    excluded: str | None = None  # reason why the position is excluded from risk
    warnings: list[str] = field(default_factory=list)
    _cf: object = None
    _qty: float = 0.0
    _price: float = 0.0

    def public(self) -> dict:
        d = {k: v for k, v in self.__dict__.items() if not k.startswith("_")}
        return d


def _fx_spot(levels: pd.DataFrame, ccy: str, as_of: date) -> tuple[float | None, str | None]:
    if ccy == BASE:
        return 1.0, None
    col = f"FX:{ccy}"
    if col not in levels.columns:
        return None, f"No FX series {col} in the dataset: position cannot be converted to {BASE}."
    s = levels[col].loc[: pd.Timestamp(as_of)].dropna()
    if s.empty:
        return None, f"No {col} observation on or before {as_of}."
    gap = (pd.Timestamp(as_of) - s.index[-1]).days
    warn = f"FX rate {col} is {gap} days old." if gap > STALE_FX_DAYS else None
    return float(s.iloc[-1]), warn


def value_portfolio(pf: Portfolio, levels: pd.DataFrame) -> list[PositionValuation]:
    if pf.base_currency != BASE:
        raise ValueError("This version supports EUR as base currency only")
    out = []
    cols = set(levels.columns)
    for p in pf.positions:
        out.append(_value_position(p, pf.as_of, levels, cols))
    return out


def _value_position(p: Position, as_of: date, levels: pd.DataFrame, cols: set) -> PositionValuation:
    ccy = p.currency.upper()
    fx, fx_msg = _fx_spot(levels, ccy, as_of)
    attrs = {
        "sector": getattr(p, "sector", None),
        "issuer": getattr(p, "issuer", None),
        "country": getattr(p, "country", None),
        "rating": getattr(p, "rating", None),
    }
    pv = PositionValuation(
        id=p.id,
        instrument_type=p.instrument_type,
        asset_class=ASSET_CLASS[p.instrument_type],
        name=p.name or getattr(p, "ticker", None) or p.id,
        currency=ccy,
        fx_rate=fx,
        mv_local=None,
        mv_base=None,
        attributes=attrs,
    )
    if fx_msg and fx is None:
        pv.excluded = fx_msg
    elif fx_msg:
        pv.warnings.append(fx_msg)
    if ccy != BASE:
        pv.fx_factor = f"FX:{ccy}"

    if isinstance(p, EquityPosition):
        pv.mv_local = p.quantity * p.price
        pv._qty, pv._price = p.quantity, p.price
        own, proxy = f"EQ:{p.ticker}", f"EQ:{p.risk_proxy}" if p.risk_proxy else None
        if own in cols:
            pv.eq_factor = own
        elif proxy and proxy in cols:
            pv.eq_factor = proxy
            pv.warnings.append(f"Risk mapped to proxy series {proxy} (no own price history).")
        elif pv.excluded is None:
            pv.excluded = f"No price history for {p.ticker} (and no usable risk proxy): excluded from risk measures."
    elif isinstance(p, FixedBondPosition):
        try:
            bond = bd.FixedRateBond(p.maturity, p.coupon_rate, p.frequency, p.daycount)
            cf = bd.cash_flows(bond, as_of)
            y = bd.yield_from_clean_price(cf, p.clean_price)
            an = bd.analytics(bond, as_of, ytm=y)
        except ValueError as e:
            pv.excluded = f"Bond cannot be valued: {e}"
            return pv
        pv._cf = cf
        pv.ytm = y
        pv.modified_duration = an.modified_duration
        pv.convexity = an.convexity
        pv.mv_local = p.nominal * an.dirty_price / 100.0
        if fx is not None:
            pv.accrued_base = p.nominal * an.accrued_interest / 100.0 * fx
            pv.dv01_base = an.dv01 * p.nominal / 100.0 * fx
        curve = curve_factors(cols, ccy)
        if not curve:
            if pv.excluded is None:
                pv.excluded = f"No {ccy} government curve in the dataset: rate risk cannot be measured."
        else:
            mat = (p.maturity - as_of).days / 365.25
            w = interpolation_weights([t for _, t in curve], mat)
            keep = w > 0
            pv.ir_factors = [c for (c, _), k in zip(curve, keep) if k]
            pv.ir_weights = [float(x) for x in w[keep]]
        if not p.is_sovereign:
            b = rating_bucket(p.rating)
            if b is None:
                pv.warnings.append("Unknown rating: no credit-spread factor, spread risk not captured.")
            else:
                cs = f"CS:{ccy}:{b}"
                if cs in cols:
                    pv.cs_factor = cs
                else:
                    pv.warnings.append(f"No spread series {cs}: spread risk not captured.")
        pv.attributes["maturity"] = p.maturity.isoformat()
        pv.attributes["coupon_rate"] = p.coupon_rate
    elif isinstance(p, FxCashPosition):
        pv.mv_local = p.amount
    if fx is not None and pv.mv_local is not None:
        pv.mv_base = pv.mv_local * fx
    return pv


def revalue(pv: PositionValuation, r_eq, r_fx, dy) -> tuple[np.ndarray, np.ndarray]:
    """Full and linearised P&L (base ccy) for arrays of factor moves."""
    r_eq = np.asarray(r_eq, dtype=float)
    r_fx = np.asarray(r_fx, dtype=float)
    dy = np.asarray(dy, dtype=float)
    shape = np.broadcast(r_eq, r_fx, dy).shape
    if pv.excluded or pv.mv_base is None:
        z = np.zeros(shape)
        return z, z
    V0, X = pv.mv_base, pv.fx_rate
    if pv.instrument_type in ("EQUITY", "ETF"):
        full = V0 * ((1 + r_eq) * (1 + r_fx) - 1)
        lin = V0 * (r_eq + r_fx)
    elif pv.instrument_type == "BOND_FIXED":
        nominal_over_100 = pv.mv_local / bd.dirty_price(pv._cf, pv.ytm)
        y1 = pv.ytm + np.broadcast_to(dy, shape)
        p1 = bd.dirty_price(pv._cf, y1)
        full = nominal_over_100 * p1 * X * (1 + r_fx) - V0
        lin = V0 * (-pv.modified_duration * dy + r_fx)
    else:
        full = V0 * r_fx * np.ones(shape)
        lin = full
    return np.broadcast_to(full, shape).astype(float), np.broadcast_to(lin, shape).astype(float)


def factor_changes(levels: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    sub = levels[cols]
    out = {}
    for c in cols:
        if c.startswith(("EQ:", "FX:")):
            out[c] = sub[c] / sub[c].shift(1) - 1.0
        else:
            out[c] = sub[c] - sub[c].shift(1)
    return pd.DataFrame(out, index=sub.index)


def required_factors(vals: list[PositionValuation]) -> list[str]:
    s = set()
    for v in vals:
        if v.excluded:
            continue
        for f in [v.eq_factor, v.fx_factor, v.cs_factor, *v.ir_factors]:
            if f:
                s.add(f)
    return sorted(s)


def moves_for_position(pv: PositionValuation, ch: pd.DataFrame | dict, n: int):
    def get(f):
        if f is None:
            return np.zeros(n)
        v = ch[f] if f in ch else 0.0
        return np.asarray(v, dtype=float) * np.ones(n)

    r_eq = get(pv.eq_factor)
    r_fx = get(pv.fx_factor)
    dy = np.zeros(n)
    for f, w in zip(pv.ir_factors, pv.ir_weights):
        dy = dy + w * get(f)
    if pv.cs_factor:
        dy = dy + get(pv.cs_factor)
    return r_eq, r_fx, dy


@dataclass
class HistoricalSimulation:
    dates: list[pd.Timestamp]
    pnl_full: np.ndarray  # T x N
    pnl_linear: np.ndarray  # T x N
    position_ids: list[str]
    factor_changes: pd.DataFrame
    dropped_dates: int
    window_requested: int


def historical_simulation(vals: list[PositionValuation], levels: pd.DataFrame, as_of: date, window: int) -> HistoricalSimulation:
    active = [v for v in vals if not v.excluded and v.mv_base is not None]
    facs = required_factors(active)
    hist = levels.loc[: pd.Timestamp(as_of)]
    if facs:
        ch = factor_changes(hist, facs).iloc[1:]
        tail = ch.iloc[-window:]
        clean = tail.dropna(how="any")
        dropped = len(tail) - len(clean)
    else:
        clean = pd.DataFrame(index=hist.index[-window:])
        dropped = 0
    n = len(clean)
    full = np.zeros((n, len(active)))
    lin = np.zeros((n, len(active)))
    for j, v in enumerate(active):
        r_eq, r_fx, dy = moves_for_position(v, clean, n)
        full[:, j], lin[:, j] = revalue(v, r_eq, r_fx, dy)
    return HistoricalSimulation(
        dates=list(clean.index),
        pnl_full=full,
        pnl_linear=lin,
        position_ids=[v.id for v in active],
        factor_changes=clean,
        dropped_dates=dropped,
        window_requested=window,
    )


def sensitivities(vals: list[PositionValuation]) -> list[dict]:
    """First-order exposures per risk factor (base currency).

    EQ  : delta = EUR P&L for +1% in the price factor
    FX  : delta = EUR P&L for +1% in the foreign currency
    IR  : key-rate DV01 = EUR P&L for +1bp on that tenor (negative for long bonds)
    CS  : CS01 = EUR P&L for +1bp spread widening
    """
    agg: dict[str, float] = {}

    def add(k, v):
        agg[k] = agg.get(k, 0.0) + v

    for v in vals:
        if v.excluded or v.mv_base is None:
            continue
        if v.eq_factor:
            add(v.eq_factor, 0.01 * v.mv_base)
        if v.fx_factor:
            add(v.fx_factor, 0.01 * v.mv_base)
        if v.instrument_type == "BOND_FIXED" and v.dv01_base is not None:
            for f, w in zip(v.ir_factors, v.ir_weights):
                add(f, -w * v.dv01_base)
            if v.cs_factor:
                add(v.cs_factor, -v.dv01_base)
    unit = {"EQ": "EUR per +1%", "FX": "EUR per +1%", "IR": "EUR per +1bp", "CS": "EUR per +1bp"}
    return [
        {"factor": k, "factor_class": k.split(":")[0], "sensitivity": val, "unit": unit[k.split(":")[0]]}
        for k, val in sorted(agg.items())
    ]
