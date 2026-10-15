import math

import numpy as np
import pytest

from riskpilot.quant import risk_measures as rm


def test_historical_var_es_integer_tail():
    pnl = -np.arange(1, 501, dtype=float)  # losses 1..500
    var, es = rm.historical_var_es(pnl, 0.99)
    assert var == 495.0  # 6th largest loss = empirical 99% quantile
    assert es == pytest.approx(np.mean([500, 499, 498, 497, 496]))


def test_historical_var_es_fractional_tail():
    pnl = -np.arange(1, 251, dtype=float)
    var, es = rm.historical_var_es(pnl, 0.99)  # k = 2.5
    assert var == 248.0
    assert es == pytest.approx((250 + 249 + 0.5 * 248) / 2.5)


def test_var_is_empirical_quantile_definition():
    rng = np.random.default_rng(1)
    pnl = rng.standard_t(4, 1000)
    alpha = 0.975
    var, _ = rm.historical_var_es(pnl, alpha)
    losses = -pnl
    assert np.mean(losses <= var) >= alpha
    assert np.mean(losses < var) < alpha


def test_sign_convention_gains_only():
    pnl = np.linspace(1, 100, 300)  # only gains -> VaR negative (no loss at that quantile)
    var, es = rm.historical_var_es(pnl, 0.99)
    assert var < 0 and es < 0


def test_es_ge_var_random():
    rng = np.random.default_rng(7)
    for _ in range(50):
        pnl = rng.normal(size=rng.integers(120, 900))
        for a in (0.95, 0.975, 0.99):
            v, e = rm.historical_var_es(pnl, a)
            assert e >= v - 1e-12


def test_insufficient_data():
    with pytest.raises(rm.InsufficientDataError):
        rm.historical_var_es(np.zeros(50), 0.99)
    w = rm.data_sufficiency(150, 0.99)
    assert any("imprecise" in x for x in w) and any("tail" in x for x in w)


def test_nan_rejected():
    x = np.ones(300)
    x[3] = np.nan
    with pytest.raises(ValueError):
        rm.historical_var_es(x, 0.99)


def test_parametric_reference_values():
    var, es = rm.parametric_var_es(1.0, 0.99)
    assert var == pytest.approx(2.3263478740, abs=1e-9)
    assert es == pytest.approx(2.6652142203, abs=1e-9)
    var95, es975 = rm.parametric_var_es(1.0, 0.95)[0], rm.parametric_var_es(1.0, 0.975)[1]
    assert var95 == pytest.approx(1.6448536270, abs=1e-9)
    assert es975 == pytest.approx(2.3378027922, abs=1e-9)  # ES 97.5% ~ VaR 99% (FRTB)


def test_horizon_scaling():
    assert rm.scale_horizon(10.0, 10) == pytest.approx(10 * math.sqrt(10))
    with pytest.raises(ValueError):
        rm.scale_horizon(1.0, 0)


def test_covariance_symmetric_psd_and_correlation():
    rng = np.random.default_rng(3)
    X = rng.multivariate_normal([0, 0, 0], [[1, 0.5, 0.2], [0.5, 2, -0.3], [0.2, -0.3, 0.5]], 2000)
    cov, corr = rm.covariance_correlation(X)
    assert np.allclose(cov, cov.T)
    assert np.linalg.eigvalsh(cov).min() > 0
    assert np.allclose(np.diag(corr), 1.0)
    assert np.all(np.abs(corr) <= 1 + 1e-12)
    assert np.allclose(cov, np.cov(X.T, ddof=1))


def test_component_parametric_sums_to_total():
    rng = np.random.default_rng(5)
    X = rng.normal(size=(500, 4)) * [1, 2, 0.5, 3]
    res = rm.component_parametric_var(X, 0.99)
    assert res["component"].sum() == pytest.approx(res["var"])
    sigma_direct = np.std(X.sum(axis=1), ddof=1)
    assert res["sigma"] == pytest.approx(sigma_direct)
    assert res["diversification"] >= -1e-9


def test_component_historical_es_sums_exactly():
    rng = np.random.default_rng(11)
    X = rng.standard_t(3, size=(250, 5))
    res = rm.component_historical_es(X, 0.99)
    _, es = rm.historical_var_es(X.sum(axis=1), 0.99)
    assert res["es"] == pytest.approx(es)
    assert res["component"].sum() == pytest.approx(es)
    assert res["weights"].sum() == pytest.approx(1.0)


def test_kupiec_against_direct_formula():
    n, x, p = 250, 10, 0.01
    ph = x / n
    lr_ref = -2 * ((n - x) * math.log(1 - p) + x * math.log(p) - (n - x) * math.log(1 - ph) - x * math.log(ph))
    lr, pv = rm.kupiec_pof(n, x, 0.99)
    assert lr == pytest.approx(lr_ref)
    assert pv < 0.01
    lr0, pv0 = rm.kupiec_pof(250, 0, 0.99)
    assert lr0 == pytest.approx(-2 * 250 * math.log(0.99))
    assert rm.basel_traffic_light(4, 250, 0.99) == "green"
    assert rm.basel_traffic_light(5, 250, 0.99) == "yellow"
    assert rm.basel_traffic_light(10, 250, 0.99) == "red"
    assert rm.basel_traffic_light(3, 250, 0.95) is None


def test_backtest_normal_data_reasonable():
    rng = np.random.default_rng(0)
    pnl = rng.normal(size=1000)
    bt = rm.backtest_historical_var(pnl, 0.99, 500, 250)
    assert bt.n == 250 and len(bt.var_series) == 250
    assert bt.exceptions <= 10


def test_ewma_and_annualisation():
    rng = np.random.default_rng(2)
    r = rng.normal(scale=0.01, size=2000)
    assert rm.annualised_volatility(r) == pytest.approx(0.01 * math.sqrt(252), rel=0.05)
    path = rm.ewma_volatility(r)
    assert path.shape == r.shape and np.all(path > 0)


def test_reproducibility():
    rng = np.random.default_rng(9)
    pnl = rng.normal(size=400)
    assert rm.historical_var_es(pnl, 0.99) == rm.historical_var_es(pnl.copy(), 0.99)
