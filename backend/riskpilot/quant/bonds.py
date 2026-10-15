"""Fixed-rate bullet bond analytics (street / ICMA convention).

Notation (per 100 of nominal)
-----------------------------
c   annual coupon rate (decimal), f coupons per year, C = 100 c / f coupon amount
y   yield to maturity, annual rate compounded f times a year (decimal)
t0  previous coupon date, t1 next coupon date, s settlement date
w   fraction of the current period remaining:  w = 1 - YF(t0, s) / YF(t0, t1)
n_k = k - 1 + w  number of periods until cash flow k  (k = 1..N)

Dirty price   P(y) = sum_k CF_k (1 + y/f)^(-n_k)
Accrued       AI   = 100 c YF(t0, s)          (YF under the bond's day count)
Clean price   P_clean = P - AI
Macaulay      D_mac = (1/P) sum_k t_k PV_k,   t_k = n_k / f   (years)
Modified      D_mod = D_mac / (1 + y/f) = -(1/P) dP/dy
Convexity     Cx = (1/P) d2P/dy2 = (1/P) sum_k PV_k t_k (t_k + 1/f) / (1 + y/f)^2
DV01          = D_mod * P / 10_000   (per 100 nominal, price units per 1bp)

Price change approximation:  dP/P ~ -D_mod dy + 1/2 Cx dy^2

Assumptions: regular coupon periods, unadjusted dates, coupons of C every
period, redemption at par (100), no default, settlement = valuation date.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import numpy as np
from scipy.optimize import brentq

from .daycount import coupon_schedule, normalize_daycount, year_fraction


@dataclass(frozen=True)
class FixedRateBond:
    maturity: date
    coupon_rate: float  # decimal, e.g. 0.035
    frequency: int = 1
    daycount: str = "ACT/ACT ICMA"
    redemption: float = 100.0

    def __post_init__(self):
        if self.coupon_rate < 0:
            raise ValueError("Coupon rate must be >= 0")
        if self.redemption <= 0:
            raise ValueError("Redemption must be > 0")
        object.__setattr__(self, "daycount", normalize_daycount(self.daycount))


@dataclass
class CashFlowSchedule:
    settlement: date
    previous_coupon: date
    dates: list[date]
    amounts: np.ndarray  # per 100 nominal
    periods: np.ndarray  # n_k
    times: np.ndarray  # t_k in years = n_k / f
    accrued: float
    w: float
    frequency: int


def cash_flows(bond: FixedRateBond, settlement: date) -> CashFlowSchedule:
    sched = coupon_schedule(bond.maturity, bond.frequency, settlement)
    t0, rest = sched[0], sched[1:]
    t1 = rest[0]
    f = bond.frequency
    kw = dict(period_start=t0, period_end=t1, frequency=f)
    yf_acc = year_fraction(t0, settlement, bond.daycount, **kw)
    yf_period = year_fraction(t0, t1, bond.daycount, **kw)
    if yf_period <= 0:
        raise ValueError("Degenerate coupon period")
    w = 1.0 - yf_acc / yf_period
    coupon = 100.0 * bond.coupon_rate / f
    accrued = 100.0 * bond.coupon_rate * yf_acc
    n = len(rest)
    amounts = np.full(n, coupon)
    amounts[-1] += bond.redemption
    periods = np.arange(n, dtype=float) + w
    return CashFlowSchedule(
        settlement=settlement,
        previous_coupon=t0,
        dates=rest,
        amounts=amounts,
        periods=periods,
        times=periods / f,
        accrued=accrued,
        w=w,
        frequency=f,
    )


def _check_yield(y, f):
    if np.any(1.0 + np.asarray(y) / f <= 0):
        raise ValueError("Yield must satisfy 1 + y/f > 0")


def dirty_price(cf: CashFlowSchedule, y):
    """Dirty price per 100 nominal. ``y`` may be a scalar or a numpy array."""
    f = cf.frequency
    y_arr = np.asarray(y, dtype=float)
    _check_yield(y_arr, f)
    disc = (1.0 + y_arr[..., None] / f) ** (-cf.periods)
    out = (disc * cf.amounts).sum(axis=-1)
    return float(out) if np.ndim(y) == 0 else out


def clean_price(cf: CashFlowSchedule, y):
    return dirty_price(cf, y) - cf.accrued


def yield_from_clean_price(cf: CashFlowSchedule, clean: float, lo: float = -0.5, hi: float = 2.0) -> float:
    """Solve P_dirty(y) = clean + AI with Brent's method (tolerance 1e-12)."""
    if clean <= 0:
        raise ValueError("Clean price must be strictly positive")
    target = clean + cf.accrued
    lo = max(lo, -cf.frequency * 0.999)

    def g(y):
        return dirty_price(cf, y) - target

    glo, ghi = g(lo), g(hi)
    if glo * ghi > 0:
        raise ValueError(
            f"No yield in [{lo:.2%}, {hi:.2%}] reproduces clean price {clean:.4f}; check inputs"
        )
    return float(brentq(g, lo, hi, xtol=1e-14, rtol=1e-14, maxiter=500))


@dataclass
class BondAnalytics:
    yield_to_maturity: float
    dirty_price: float
    clean_price: float
    accrued_interest: float
    macaulay_duration: float
    modified_duration: float
    convexity: float
    dv01: float  # per 100 nominal
    effective_duration: float  # finite-difference check (+/- 1bp)
    effective_convexity: float
    cash_flows: list[dict] = field(default_factory=list)


def analytics(bond: FixedRateBond, settlement: date, *, clean: float | None = None, ytm: float | None = None) -> BondAnalytics:
    if (clean is None) == (ytm is None):
        raise ValueError("Provide exactly one of clean price or yield")
    cf = cash_flows(bond, settlement)
    y = yield_from_clean_price(cf, clean) if clean is not None else float(ytm)
    f = cf.frequency
    disc = (1.0 + y / f) ** (-cf.periods)
    pv = cf.amounts * disc
    P = float(pv.sum())
    d_mac = float((cf.times * pv).sum() / P)
    d_mod = d_mac / (1.0 + y / f)
    cx = float((pv * cf.times * (cf.times + 1.0 / f)).sum() / (P * (1.0 + y / f) ** 2))
    h = 1e-4
    p_up, p_dn = dirty_price(cf, y + h), dirty_price(cf, y - h)
    eff_dur = (p_dn - p_up) / (2 * P * h)
    eff_cx = (p_up + p_dn - 2 * P) / (P * h * h)
    flows = [
        {
            "date": d.isoformat(),
            "amount": float(a),
            "time_years": float(t),
            "discount_factor": float(df),
            "present_value": float(v),
            "type": "coupon+redemption" if i == len(cf.dates) - 1 else "coupon",
        }
        for i, (d, a, t, df, v) in enumerate(zip(cf.dates, cf.amounts, cf.times, disc, pv))
    ]
    return BondAnalytics(
        yield_to_maturity=y,
        dirty_price=P,
        clean_price=P - cf.accrued,
        accrued_interest=cf.accrued,
        macaulay_duration=d_mac,
        modified_duration=d_mod,
        convexity=cx,
        dv01=d_mod * P / 10_000.0,
        effective_duration=float(eff_dur),
        effective_convexity=float(eff_cx),
        cash_flows=flows,
    )


def price_change_approximation(modified_duration: float, convexity: float, dy) -> np.ndarray:
    """Relative dirty price change: -D_mod dy + 1/2 Cx dy^2."""
    dy = np.asarray(dy, dtype=float)
    return -modified_duration * dy + 0.5 * convexity * dy**2


def years_between(d1: date, d2: date) -> float:
    return (d2 - d1).days / 365.25
