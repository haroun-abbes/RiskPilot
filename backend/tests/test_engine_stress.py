from datetime import date

import numpy as np
import pandas as pd
import pytest

from riskpilot.quant import bonds as bd
from riskpilot.quant import engine as eng
from riskpilot.quant import stress
from riskpilot.quant.instruments import EquityPosition, FixedBondPosition, FxCashPosition, Portfolio

AS_OF = date(2026, 10, 14)


def make_levels(n=300, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range(end=pd.Timestamp(AS_OF), periods=n)
    eq = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
    fx = 0.9 * np.exp(np.cumsum(rng.normal(0, 0.004, n)))
    df = pd.DataFrame(
        {
            "EQ:AAA": eq,
            "FX:USD": fx,
            "IR:EUR:2Y": 0.02 + np.cumsum(rng.normal(0, 0.0004, n)),
            "IR:EUR:10Y": 0.027 + np.cumsum(rng.normal(0, 0.0005, n)),
            "CS:EUR:IG": 0.011 + np.cumsum(rng.normal(0, 0.0001, n)),
        },
        index=idx,
    )
    return df


def portfolio():
    return Portfolio(
        "t",
        "EUR",
        AS_OF,
        [
            EquityPosition("E1", "AAA", 1000, 50.0, "USD", sector="Tech", country="US"),
            EquityPosition("E2", "ZZZ", 10, 10.0, "EUR"),  # no history
            FixedBondPosition("B1", 1_000_000, 98.5, 0.03, 1, date(2032, 6, 15), "EUR", rating="A"),
            FxCashPosition("C1", "USD", 100_000),
            FxCashPosition("C2", "EUR", 50_000),
        ],
    )


def test_valuation_and_mapping():
    lv = make_levels()
    vals = {v.id: v for v in eng.value_portfolio(portfolio(), lv)}
    fx = lv["FX:USD"].iloc[-1]
    assert vals["E1"].mv_base == pytest.approx(1000 * 50 * fx)
    assert vals["E1"].eq_factor == "EQ:AAA" and vals["E1"].fx_factor == "FX:USD"
    assert vals["E2"].excluded and "No price history" in vals["E2"].excluded
    b = vals["B1"]
    ref = bd.analytics(bd.FixedRateBond(date(2032, 6, 15), 0.03, 1), AS_OF, clean=98.5)
    assert b.mv_base == pytest.approx(1_000_000 * ref.dirty_price / 100)
    assert b.ir_factors == ["IR:EUR:2Y", "IR:EUR:10Y"]  # 5.7y maturity -> interpolated
    t = (date(2032, 6, 15) - AS_OF).days / 365.25
    a = (t - 2) / 8
    assert b.ir_weights == pytest.approx([1 - a, a])
    assert b.cs_factor == "CS:EUR:IG"
    assert vals["C2"].mv_base == 50_000 and vals["C2"].fx_factor is None


def test_interpolation_weights():
    w = eng.interpolation_weights([2, 10], 6.0)
    assert w.tolist() == [0.5, 0.5]
    assert eng.interpolation_weights([2, 10], 1.0).tolist() == [1, 0]
    assert eng.interpolation_weights([2, 10], 40).tolist() == [0, 1]


def test_equity_fx_revaluation_exact():
    vals = {v.id: v for v in eng.value_portfolio(portfolio(), make_levels())}
    v = vals["E1"]
    full, lin = eng.revalue(v, np.array([0.1]), np.array([-0.05]), np.array([0.0]))
    assert full[0] == pytest.approx(v.mv_base * (1.1 * 0.95 - 1))
    assert lin[0] == pytest.approx(v.mv_base * 0.05)


def test_bond_revaluation_matches_repricing():
    vals = {v.id: v for v in eng.value_portfolio(portfolio(), make_levels())}
    b = vals["B1"]
    full, _ = eng.revalue(b, 0.0, 0.0, np.array([0.01]))
    cf = bd.cash_flows(bd.FixedRateBond(date(2032, 6, 15), 0.03, 1), AS_OF)
    exp = 1_000_000 / 100 * (bd.dirty_price(cf, b.ytm + 0.01) - bd.dirty_price(cf, b.ytm))
    assert full[0] == pytest.approx(exp)
    assert full[0] < 0


def test_historical_simulation_reproduces_factor_moves():
    lv = make_levels()
    vals = eng.value_portfolio(portfolio(), lv)
    hs = eng.historical_simulation(vals, lv, AS_OF, 250)
    assert hs.pnl_full.shape == (250, 4)  # E2 excluded
    j = hs.position_ids.index("E1")
    v = next(x for x in vals if x.id == "E1")
    r = lv["EQ:AAA"].pct_change().iloc[-250:].values
    x = lv["FX:USD"].pct_change().iloc[-250:].values
    assert np.allclose(hs.pnl_full[:, j], v.mv_base * ((1 + r) * (1 + x) - 1))
    # EUR cash has zero P&L
    assert np.allclose(hs.pnl_full[:, hs.position_ids.index("C2")], 0)


def test_missing_data_dropped_not_filled():
    lv = make_levels()
    lv.iloc[-10, 0] = np.nan
    vals = eng.value_portfolio(portfolio(), lv)
    hs = eng.historical_simulation(vals, lv, AS_OF, 250)
    assert hs.dropped_dates == 2  # the NaN breaks two consecutive returns
    assert len(hs.dates) == 248


def test_stress_rates_up_hurts_long_bond_and_waterfall_adds_up():
    lv = make_levels()
    vals = eng.value_portfolio(portfolio(), lv)
    res = stress.run_scenario(
        vals,
        {"kind": "hypothetical", "definition": {"equity": {"all": -0.2}, "rates": {"EUR": {"parallel_bp": 100}}, "spreads": {"IG": 50}, "fx": {"USD": -0.1}}},
        AS_OF,
    )
    bond = next(r for r in res["positions"] if r["id"] == "B1")
    assert bond["pnl"] < 0
    assert bond["moves"]["dy_rates"] == pytest.approx(0.01)
    assert bond["moves"]["dy_spread"] == pytest.approx(0.005)
    assert sum(res["by_class"].values()) + res["interaction"] == pytest.approx(res["total_pnl"])
    eq = next(r for r in res["positions"] if r["id"] == "E1")
    assert eq["pnl"] == pytest.approx(eq["mv_base"] * (0.8 * 0.9 - 1))
    assert eq["interaction"] == pytest.approx(eq["mv_base"] * 0.02)  # (-0.2)(-0.1)
    assert abs(bond["pnl_duration_convexity"] - bond["pnl"]) < 0.002 * bond["mv_base"]


def test_stress_priority_and_tenor_interpolation():
    vals = eng.value_portfolio(portfolio(), make_levels())
    e1 = next(v for v in vals if v.id == "E1")
    m = stress.hypothetical_moves(e1, {"equity": {"all": -0.1, "by_sector": {"Tech": -0.3}, "by_ticker": {"AAA": -0.5}}}, AS_OF)
    assert m["r_eq"] == -0.5
    shift = stress._tenor_curve_shift({"parallel_bp": 10, "tenor_bp": {"2Y": 0, "10Y": 80}}, 6.0)
    assert shift == pytest.approx((10 + 40) / 1e4)


def test_historical_replay():
    lv = make_levels()
    vals = eng.value_portfolio(portfolio(), lv)
    s, e = lv.index[-60].date(), lv.index[-1].date()
    res = stress.run_scenario(vals, {"kind": "historical", "definition": {"start": s.isoformat(), "end": e.isoformat()}}, AS_OF, lv)
    eq = next(r for r in res["positions"] if r["id"] == "E1")
    r = lv["EQ:AAA"].iloc[-1] / lv["EQ:AAA"].iloc[-60] - 1
    x = lv["FX:USD"].iloc[-1] / lv["FX:USD"].iloc[-60] - 1
    assert eq["pnl"] == pytest.approx(eq["mv_base"] * ((1 + r) * (1 + x) - 1))


def test_sensitivities_signs_and_totals():
    vals = eng.value_portfolio(portfolio(), make_levels())
    s = {x["factor"]: x["sensitivity"] for x in eng.sensitivities(vals)}
    b = next(v for v in vals if v.id == "B1")
    ir = sum(v for k, v in s.items() if k.startswith("IR:"))
    assert ir == pytest.approx(-b.dv01_base)
    assert s["CS:EUR:IG"] == pytest.approx(-b.dv01_base)
    assert s["FX:USD"] > 0
