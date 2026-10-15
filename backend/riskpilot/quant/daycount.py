"""Day-count conventions and coupon schedule generation.

Supported conventions
---------------------
* ``ACT/ACT ICMA`` – year fraction within a regular coupon period
  = days(d1, d2) / (f * days(period_start, period_end)).
* ``30E/360`` – Eurobond basis (ISDA 2006 §4.16(g)): D1=31→30, D2=31→30.
* ``30/360`` – US bond basis: D1=31→30; D2=31→30 only if D1 is 30 or 31.
* ``ACT/365F`` – actual days / 365.
* ``ACT/360`` – actual days / 360.

Schedules are generated backwards from maturity in steps of 12/f months,
**without business-day adjustment** and assuming **regular periods**
(no odd first/last coupon). These limits are documented in docs/METHODOLOGY.md.
"""
from __future__ import annotations

import calendar
from datetime import date

SUPPORTED_DAYCOUNTS = ("ACT/ACT ICMA", "30E/360", "30/360", "ACT/365F", "ACT/360")
SUPPORTED_FREQUENCIES = (1, 2, 4, 12)

_ALIASES = {
    "ACT/ACT": "ACT/ACT ICMA",
    "ACTUAL/ACTUAL": "ACT/ACT ICMA",
    "ACT/ACT ISMA": "ACT/ACT ICMA",
    "ACT/ACT ICMA": "ACT/ACT ICMA",
    "30E/360": "30E/360",
    "30/360 ICMA": "30E/360",
    "EUROBOND": "30E/360",
    "30/360": "30/360",
    "30/360 US": "30/360",
    "BOND BASIS": "30/360",
    "ACT/365": "ACT/365F",
    "ACT/365F": "ACT/365F",
    "ACT/365 FIXED": "ACT/365F",
    "ACT/360": "ACT/360",
}


def normalize_daycount(name: str) -> str:
    key = str(name).strip().upper()
    if key not in _ALIASES:
        raise ValueError(
            f"Unsupported day-count convention '{name}'. Supported: {', '.join(SUPPORTED_DAYCOUNTS)}"
        )
    return _ALIASES[key]


def add_months(d: date, months: int, eom: bool = False) -> date:
    """Add calendar months. If ``eom`` the result is forced to month end."""
    m = d.month - 1 + months
    y = d.year + m // 12
    m = m % 12 + 1
    last = calendar.monthrange(y, m)[1]
    day = last if eom else min(d.day, last)
    return date(y, m, day)


def is_end_of_month(d: date) -> bool:
    return d.day == calendar.monthrange(d.year, d.month)[1]


def _d30(d1: date, d2: date, us: bool) -> int:
    y1, m1, dd1 = d1.year, d1.month, d1.day
    y2, m2, dd2 = d2.year, d2.month, d2.day
    if us:
        if dd1 == 31:
            dd1 = 30
        if dd2 == 31 and dd1 >= 30:
            dd2 = 30
    else:
        dd1 = min(dd1, 30)
        dd2 = min(dd2, 30)
    return 360 * (y2 - y1) + 30 * (m2 - m1) + (dd2 - dd1)


def year_fraction(
    d1: date,
    d2: date,
    convention: str,
    period_start: date | None = None,
    period_end: date | None = None,
    frequency: int | None = None,
) -> float:
    """Year fraction between d1 and d2 under ``convention``.

    ACT/ACT ICMA requires the enclosing regular coupon period and frequency.
    """
    conv = normalize_daycount(convention)
    if conv == "ACT/365F":
        return (d2 - d1).days / 365.0
    if conv == "ACT/360":
        return (d2 - d1).days / 360.0
    if conv == "30E/360":
        return _d30(d1, d2, us=False) / 360.0
    if conv == "30/360":
        return _d30(d1, d2, us=True) / 360.0
    # ACT/ACT ICMA
    if period_start is None or period_end is None or not frequency:
        raise ValueError("ACT/ACT ICMA needs the coupon period and frequency")
    period_days = (period_end - period_start).days
    return (d2 - d1).days / (frequency * period_days)


def coupon_schedule(maturity: date, frequency: int, settlement: date) -> list[date]:
    """Coupon dates generated backwards from maturity.

    Returns ``[previous_coupon, next_coupon, ..., maturity]`` where
    ``previous_coupon <= settlement < next_coupon``. Settlement on a coupon
    date means that coupon has already been paid to the seller.
    """
    if frequency not in SUPPORTED_FREQUENCIES:
        raise ValueError(f"Unsupported coupon frequency {frequency}; supported: {SUPPORTED_FREQUENCIES}")
    if settlement >= maturity:
        raise ValueError("Settlement date must be strictly before maturity")
    step = 12 // frequency
    eom = is_end_of_month(maturity)
    dates = [maturity]
    k = 1
    while dates[-1] > settlement:
        dates.append(add_months(maturity, -step * k, eom=eom))
        k += 1
    dates.reverse()
    return dates
