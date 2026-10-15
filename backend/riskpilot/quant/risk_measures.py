"""Market-risk measures.

Sign convention: P&L > 0 is a gain. Loss L = -P&L. VaR and ES are reported
as **positive numbers expressed as losses** in the base currency.

Historical VaR / ES (n scenarios, confidence alpha, k = n (1 - alpha))
--------------------------------------------------------------------
Losses sorted in decreasing order L[1] >= L[2] >= ... >= L[n].
    VaR_alpha = L[floor(k) + 1]  = inf{ l : F_n(l) >= alpha }  (empirical quantile)
    ES_alpha  = (1/k) ( sum_{i<=floor(k)} L[i] + (k - floor(k)) L[floor(k)+1] )
This ES estimator (Acerbi & Tasche, 2002) is the average of the worst
100(1-alpha)% of outcomes; it is coherent and always >= VaR.

Parametric (delta-normal) VaR / ES with P&L ~ N(mu, sigma^2)
    VaR = z_alpha sigma - mu,   ES = sigma phi(z_alpha)/(1-alpha) - mu
By default mu = 0 (common for short horizons; documented choice).

Horizon scaling: X_h = X_1 * sqrt(h). Valid only under i.i.d. P&L with
zero mean; flagged in every result that uses it.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy import stats

MIN_OBS_HARD = 100  # below this no historical figure is produced
MIN_OBS_WARN = 250
MIN_TAIL_WARN = 5


class InsufficientDataError(ValueError):
    pass


def _clean_pnl(pnl) -> np.ndarray:
    x = np.asarray(pnl, dtype=float).ravel()
    if np.isnan(x).any():
        raise ValueError("P&L vector contains NaN values")
    return x


def _check_alpha(alpha: float):
    if not 0.5 < alpha < 1.0:
        raise ValueError("Confidence level must be in (0.5, 1)")


def data_sufficiency(n: int, alpha: float) -> list[str]:
    """Return warnings; raise if the sample cannot support an estimate."""
    _check_alpha(alpha)
    k = n * (1 - alpha)
    if n < MIN_OBS_HARD or k < 1:
        raise InsufficientDataError(
            f"{n} observations are insufficient for a {alpha:.1%} historical estimate "
            f"(minimum {MIN_OBS_HARD} and at least one tail observation)."
        )
    warnings = []
    if n < MIN_OBS_WARN:
        warnings.append(f"Only {n} observations (< {MIN_OBS_WARN}): estimate is imprecise.")
    if k < MIN_TAIL_WARN:
        warnings.append(
            f"The tail contains only {k:.1f} observations at {alpha:.1%}: ES rests on very few scenarios."
        )
    return warnings


def tail_weights(pnl, alpha: float) -> np.ndarray:
    """Weights w_t (sum = 1) such that ES = -sum w_t P&L_t.

    Worst floor(k) scenarios get weight 1/k, the next one (k - floor(k))/k.
    Used for the exact additive decomposition of historical ES.
    """
    x = _clean_pnl(pnl)
    n = x.size
    k = n * (1 - alpha)
    order = np.argsort(x, kind="stable")  # most negative P&L first
    m = int(math.floor(k + 1e-12))
    w = np.zeros(n)
    w[order[:m]] = 1.0 / k
    frac = k - m
    if frac > 1e-12 and m < n:
        w[order[m]] = frac / k
    return w


def historical_var_es(pnl, alpha: float) -> tuple[float, float]:
    x = _clean_pnl(pnl)
    n = x.size
    data_sufficiency(n, alpha)
    losses = np.sort(-x)[::-1]
    k = n * (1 - alpha)
    m = int(math.floor(k + 1e-12))
    var = float(losses[m]) if m < n else float(losses[-1])
    es = float((losses[:m].sum() + (k - m) * (losses[m] if m < n else 0.0)) / k)
    return var, es


def parametric_var_es(sigma: float, alpha: float, mu: float = 0.0) -> tuple[float, float]:
    _check_alpha(alpha)
    if sigma < 0:
        raise ValueError("sigma must be >= 0")
    z = stats.norm.ppf(alpha)
    var = z * sigma - mu
    es = sigma * stats.norm.pdf(z) / (1 - alpha) - mu
    return float(var), float(es)


def scale_horizon(value: float, horizon_days: int) -> float:
    if horizon_days < 1:
        raise ValueError("Horizon must be >= 1 day")
    return value * math.sqrt(horizon_days)


def component_parametric_var(position_pnl: np.ndarray, alpha: float) -> dict:
    """Euler decomposition of delta-normal VaR on position P&L series.

    position_pnl: T x N matrix of (linearised) position P&L.
    Cov = sample covariance (ddof=1). sigma_p^2 = 1' Cov 1.
    Component_i = z * (Cov 1)_i / sigma_p, sum_i Component_i = VaR.
    """
    X = np.asarray(position_pnl, dtype=float)
    if X.ndim != 2 or X.shape[0] < 2:
        raise ValueError("Need a T x N matrix with T >= 2")
    cov = np.atleast_2d(np.cov(X, rowvar=False, ddof=1))
    ones = np.ones(cov.shape[0])
    var_p = float(ones @ cov @ ones)
    sigma = math.sqrt(max(var_p, 0.0))
    z = stats.norm.ppf(alpha)
    if sigma == 0:
        comp = np.zeros(cov.shape[0])
        marginal = np.zeros(cov.shape[0])
    else:
        marginal = z * (cov @ ones) / sigma
        comp = marginal  # each position enters with unit weight
    stand_alone = z * np.sqrt(np.clip(np.diag(cov), 0, None))
    return {
        "sigma": sigma,
        "var": z * sigma,
        "component": comp,
        "stand_alone": stand_alone,
        "diversification": float(stand_alone.sum() - z * sigma),
    }


def component_historical_es(position_pnl: np.ndarray, alpha: float) -> dict:
    """Exact additive decomposition of historical ES.

    ES = -sum_t w_t P&L_t with tail weights w (see tail_weights);
    CES_i = -sum_t w_t P&L_{t,i}; sum_i CES_i = ES exactly.
    """
    X = np.asarray(position_pnl, dtype=float)
    total = X.sum(axis=1)
    w = tail_weights(total, alpha)
    comp = -(w @ X)
    return {"es": float(-(w @ total)), "component": comp, "weights": w}


def annualised_volatility(returns, periods_per_year: int = 252) -> float:
    r = np.asarray(returns, dtype=float)
    r = r[~np.isnan(r)]
    if r.size < 2:
        raise InsufficientDataError("At least two returns are required")
    return float(np.std(r, ddof=1) * math.sqrt(periods_per_year))


def ewma_volatility(returns, lam: float = 0.94, periods_per_year: int = 252) -> np.ndarray:
    """RiskMetrics EWMA: s2_t = lam s2_{t-1} + (1-lam) r_{t-1}^2 (zero mean).

    Seeded with the sample variance of the first 20 returns.
    Returns the annualised volatility path aligned with ``returns``.
    """
    r = np.asarray(returns, dtype=float)
    if r.size < 21:
        raise InsufficientDataError("EWMA needs at least 21 returns")
    s2 = np.empty_like(r)
    s2[0] = np.var(r[:20], ddof=1)
    for t in range(1, r.size):
        s2[t] = lam * s2[t - 1] + (1 - lam) * r[t - 1] ** 2
    return np.sqrt(s2 * periods_per_year)


def covariance_correlation(returns_matrix: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    X = np.asarray(returns_matrix, dtype=float)
    if np.isnan(X).any():
        raise ValueError("Returns contain NaN; align observations first")
    cov = np.atleast_2d(np.cov(X, rowvar=False, ddof=1))
    sd = np.sqrt(np.diag(cov))
    with np.errstate(invalid="ignore", divide="ignore"):
        corr = cov / np.outer(sd, sd)
    corr[~np.isfinite(corr)] = np.nan
    np.fill_diagonal(corr, 1.0)
    return cov, corr


@dataclass
class BacktestResult:
    n: int
    exceptions: int
    expected: float
    exception_dates_idx: list[int]
    var_series: np.ndarray
    kupiec_lr: float
    kupiec_pvalue: float
    traffic_light: str | None


def kupiec_pof(n: int, x: int, alpha: float) -> tuple[float, float]:
    """Kupiec (1995) proportion-of-failures LR test, chi2(1) under H0 p = 1-alpha."""
    p = 1 - alpha
    phat = x / n

    def ll(prob):
        a = (n - x) * math.log(1 - prob) if n - x > 0 else 0.0
        b = x * math.log(prob) if x > 0 else 0.0
        return a + b

    lr = -2 * (ll(p) - (ll(phat) if 0 < phat < 1 else 0.0))
    lr = max(lr, 0.0)
    return lr, float(1 - stats.chi2.cdf(lr, df=1))


def basel_traffic_light(exceptions: int, n: int, alpha: float) -> str | None:
    """Basel zones are defined for 250 observations at 99%."""
    if n != 250 or abs(alpha - 0.99) > 1e-9:
        return None
    if exceptions <= 4:
        return "green"
    if exceptions <= 9:
        return "yellow"
    return "red"


def backtest_historical_var(pnl, alpha: float, window: int, test_len: int = 250) -> BacktestResult:
    """Rolling historical VaR backtest: VaR_t estimated on [t-window, t-1],
    exception when the realised loss at t exceeds it."""
    x = _clean_pnl(pnl)
    if x.size < window + test_len:
        raise InsufficientDataError(
            f"Backtest needs {window + test_len} observations, {x.size} available"
        )
    start = x.size - test_len
    vars_, exc = [], []
    for t in range(start, x.size):
        v, _ = historical_var_es(x[t - window : t], alpha)
        vars_.append(v)
        if -x[t] > v:
            exc.append(t - start)
    lr, pv = kupiec_pof(test_len, len(exc), alpha)
    return BacktestResult(
        n=test_len,
        exceptions=len(exc),
        expected=test_len * (1 - alpha),
        exception_dates_idx=exc,
        var_series=np.array(vars_),
        kupiec_lr=lr,
        kupiec_pvalue=pv,
        traffic_light=basel_traffic_light(len(exc), test_len, alpha),
    )
