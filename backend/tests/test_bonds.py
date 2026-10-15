"""Fixed-income analytics checked against independent closed forms."""
from datetime import date

import numpy as np
import pytest

from riskpilot.quant import bonds as bd
from riskpilot.quant.daycount import add_months, coupon_schedule, year_fraction


# ---------- day count ----------
def test_30e_vs_30us():
    assert year_fraction(date(2025, 1, 15), date(2025, 3, 31), "30E/360") * 360 == 75
    assert year_fraction(date(2025, 1, 15), date(2025, 3, 31), "30/360") * 360 == 76
    assert year_fraction(date(2025, 1, 30), date(2025, 3, 31), "30/360") * 360 == 60


def test_act_conventions():
    d1, d2 = date(2025, 1, 1), date(2025, 7, 1)  # 181 days
    assert year_fraction(d1, d2, "ACT/365F") == pytest.approx(181 / 365)
    assert year_fraction(d1, d2, "ACT/360") == pytest.approx(181 / 360)
    assert year_fraction(d1, d2, "ACT/ACT ICMA", period_start=d1, period_end=date(2026, 1, 1), frequency=1) == pytest.approx(181 / 365)


def test_unknown_daycount_rejected():
    with pytest.raises(ValueError):
        year_fraction(date(2025, 1, 1), date(2025, 2, 1), "BUS/252")


def test_schedule_end_of_month():
    s = coupon_schedule(date(2030, 2, 28), 2, date(2029, 6, 1))
    assert s == [date(2029, 2, 28), date(2029, 8, 31), date(2030, 2, 28)]
    assert add_months(date(2024, 1, 31), 1) == date(2024, 2, 29)


def test_settlement_on_coupon_date_excludes_that_coupon():
    s = coupon_schedule(date(2030, 6, 15), 1, date(2026, 6, 15))
    assert s[0] == date(2026, 6, 15) and s[1] == date(2027, 6, 15)


# ---------- pricing ----------
def annuity_price(c, y, n, f=1):
    """Independent closed form on a coupon date, per 100."""
    cpn = 100 * c / f
    r = y / f
    return cpn * (1 - (1 + r) ** -n) / r + 100 * (1 + r) ** -n


def test_textbook_price_10y_5pct_at_6pct():
    b = bd.FixedRateBond(date(2036, 6, 15), 0.05, 1, "30E/360")
    a = bd.analytics(b, date(2026, 6, 15), ytm=0.06)
    assert a.accrued_interest == pytest.approx(0.0)
    assert a.dirty_price == pytest.approx(annuity_price(0.05, 0.06, 10), abs=1e-10)
    assert a.dirty_price == pytest.approx(92.6399, abs=1e-4)


def test_semiannual_closed_form():
    b = bd.FixedRateBond(date(2031, 3, 1), 0.04, 2, "30E/360")
    a = bd.analytics(b, date(2026, 3, 1), ytm=0.035)
    assert a.clean_price == pytest.approx(annuity_price(0.04, 0.035, 10, 2), abs=1e-10)


def test_par_bond_on_coupon_date():
    b = bd.FixedRateBond(date(2033, 5, 10), 0.0325, 1, "ACT/ACT ICMA")
    a = bd.analytics(b, date(2026, 5, 10), ytm=0.0325)
    assert a.clean_price == pytest.approx(100.0, abs=1e-10)


def test_zero_coupon_duration_equals_maturity():
    b = bd.FixedRateBond(date(2031, 4, 1), 0.0, 1, "ACT/ACT ICMA")
    a = bd.analytics(b, date(2026, 4, 1), ytm=0.03)
    assert a.dirty_price == pytest.approx(100 / 1.03**5, abs=1e-10)
    assert a.macaulay_duration == pytest.approx(5.0, abs=1e-12)
    assert a.modified_duration == pytest.approx(5.0 / 1.03, abs=1e-12)
    # convexity of a zero: T (T + 1/f) / (1+y/f)^2
    assert a.convexity == pytest.approx(5 * 6 / 1.03**2, abs=1e-10)


def test_accrued_interest_30e360():
    b = bd.FixedRateBond(date(2030, 9, 15), 0.04, 2, "30E/360")
    cf = bd.cash_flows(b, date(2026, 6, 15))  # 90 days of 30E/360 since 15 Mar
    assert cf.accrued == pytest.approx(4.0 * 90 / 360)
    assert cf.w == pytest.approx(0.5)


def test_accrued_interest_act_act_icma():
    b = bd.FixedRateBond(date(2030, 2, 15), 0.03, 1, "ACT/ACT ICMA")
    cf = bd.cash_flows(b, date(2025, 8, 15))
    days, period = (date(2025, 8, 15) - date(2025, 2, 15)).days, 365
    assert cf.accrued == pytest.approx(3.0 * days / period)


def test_mid_period_dirty_price_independent():
    """Dirty price between coupon dates = sum CF (1+y)^-(k-1+w), w from actual days."""
    b = bd.FixedRateBond(date(2029, 11, 20), 0.045, 1, "ACT/ACT ICMA")
    s = date(2026, 3, 3)
    y = 0.041
    a = bd.analytics(b, s, ytm=y)
    t0, t1 = date(2025, 11, 20), date(2026, 11, 20)
    w = (t1 - s).days / (t1 - t0).days
    ref = sum(4.5 / (1 + y) ** (k + w) for k in range(4)) + 100 / (1 + y) ** (3 + w)
    assert a.dirty_price == pytest.approx(ref, abs=1e-10)
    assert a.clean_price == pytest.approx(ref - 4.5 * (s - t0).days / (t1 - t0).days, abs=1e-10)


def test_yield_round_trip():
    b = bd.FixedRateBond(date(2034, 7, 1), 0.0275, 2, "30E/360")
    s = date(2026, 10, 15)
    for y in [-0.002, 0.0, 0.01, 0.05, 0.12]:
        clean = bd.clean_price(bd.cash_flows(b, s), y)
        a = bd.analytics(b, s, clean=clean)
        assert a.yield_to_maturity == pytest.approx(y, abs=1e-11)


def test_price_decreasing_and_convex_in_yield():
    cf = bd.cash_flows(bd.FixedRateBond(date(2040, 1, 1), 0.03, 1, "ACT/ACT ICMA"), date(2026, 10, 15))
    ys = np.linspace(-0.01, 0.10, 200)
    p = bd.dirty_price(cf, ys)
    assert np.all(np.diff(p) < 0)
    assert np.all(np.diff(p, 2) > 0)


def test_duration_convexity_match_finite_differences():
    b = bd.FixedRateBond(date(2036, 3, 15), 0.035, 2, "30E/360")
    a = bd.analytics(b, date(2026, 10, 15), ytm=0.031)
    assert a.modified_duration == pytest.approx(a.effective_duration, rel=1e-6)
    assert a.convexity == pytest.approx(a.effective_convexity, rel=1e-4)
    assert a.dv01 == pytest.approx(a.modified_duration * a.dirty_price / 1e4)


def test_duration_convexity_approximation_quality():
    b = bd.FixedRateBond(date(2036, 3, 15), 0.035, 2, "30E/360")
    s = date(2026, 10, 15)
    a = bd.analytics(b, s, ytm=0.03)
    cf = bd.cash_flows(b, s)
    for dy in (-0.01, 0.01):
        exact = bd.dirty_price(cf, 0.03 + dy) / a.dirty_price - 1
        d_only = -a.modified_duration * dy
        dc = bd.price_change_approximation(a.modified_duration, a.convexity, dy)
        assert abs(dc - exact) < abs(d_only - exact)
        assert abs(dc - exact) < 5e-4


def test_invalid_inputs():
    with pytest.raises(ValueError):
        bd.cash_flows(bd.FixedRateBond(date(2026, 1, 1), 0.03), date(2026, 1, 1))
    with pytest.raises(ValueError):
        bd.FixedRateBond(date(2030, 1, 1), 0.03, 3)  # bad frequency surfaces at schedule
        bd.cash_flows(bd.FixedRateBond(date(2030, 1, 1), 0.03, 3), date(2026, 1, 1))
    with pytest.raises(ValueError):
        bd.analytics(bd.FixedRateBond(date(2030, 1, 1), 0.03), date(2026, 1, 1), clean=-5)
