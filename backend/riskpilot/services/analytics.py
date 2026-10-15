"""Orchestration of the quantitative engine for the API. No formula lives here:
every number comes from riskpilot.quant; this module only selects inputs,
aggregates additive quantities and attaches metadata."""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, timezone

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from ..config import ENGINE_VERSION
from ..db.models import DatasetRow, PortfolioRow
from ..quant import bonds as bd
from ..quant import engine as eng
from ..quant import risk_measures as rm
from ..quant import stress as st
from ..quant.engine import interpolation_weights
from ..quant.instruments import Portfolio
from . import store

PROVENANCE_LABEL = {
    "SYNTHETIC": "Synthetic data (simulated, not market data)",
    "HISTORICAL_REAL": "Historical market data (end of day)",
    "DELAYED": "Delayed market data",
    "USER_IMPORT": "User-imported portfolio",
}


@dataclass
class Context:
    prow: PortfolioRow
    pf: Portfolio
    drow: DatasetRow
    levels: pd.DataFrame
    vals: list[eng.PositionValuation]


def context(db: Session, portfolio_id: str, dataset_id: str) -> Context:
    prow, pf = store.get_portfolio(db, portfolio_id)
    drow, levels = store.get_dataset(db, dataset_id)
    vals = eng.value_portfolio(pf, levels)
    return Context(prow, pf, drow, levels, vals)


def _f(x):
    if x is None:
        return None
    x = float(x)
    return x if math.isfinite(x) else None


def meta(ctx: Context, params: dict) -> dict:
    return {
        "computed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "engine_version": ENGINE_VERSION,
        "params": params,
        "portfolio": {"id": ctx.prow.id, "name": ctx.prow.name, "as_of": ctx.pf.as_of.isoformat(), "provenance": ctx.prow.provenance, "hash": ctx.prow.content_hash[:12]},
        "dataset": {
            "id": ctx.drow.id,
            "name": ctx.drow.name,
            "provenance": ctx.drow.provenance,
            "provenance_label": PROVENANCE_LABEL.get(ctx.drow.provenance, ctx.drow.provenance),
            "source": ctx.drow.source,
            "hash": ctx.drow.content_hash[:12],
            "end": ctx.levels.index[-1].date().isoformat(),
        },
    }


def _data_warnings(ctx: Context) -> list[str]:
    w = []
    end = ctx.levels.index[-1].date()
    if end < ctx.pf.as_of:
        w.append(f"Dataset ends on {end}, before the valuation date {ctx.pf.as_of}: the risk window ends on {end}.")
    for v in ctx.vals:
        if v.excluded:
            w.append(f"{v.id}: {v.excluded}")
        for x in v.warnings:
            w.append(f"{v.id}: {x}")
    return w


# ------------------------------------------------------------------ exposures
def exposures(ctx: Context) -> dict:
    rows = []
    for v in ctx.vals:
        d = v.public()
        d["included_in_risk"] = v.excluded is None
        rows.append(d)
    valued = [v for v in ctx.vals if v.mv_base is not None]
    gross = sum(abs(v.mv_base) for v in valued)
    net = sum(v.mv_base for v in valued)

    def group(key):
        g = {}
        for v in valued:
            k = key(v) or "Unspecified"
            e = g.setdefault(k, {"key": k, "net": 0.0, "gross": 0.0, "long": 0.0, "short": 0.0, "count": 0})
            e["net"] += v.mv_base
            e["gross"] += abs(v.mv_base)
            e["long" if v.mv_base >= 0 else "short"] += v.mv_base
            e["count"] += 1
        out = sorted(g.values(), key=lambda e: -e["gross"])
        for e in out:
            e["pct_gross"] = e["gross"] / gross if gross else None
        return out

    bonds = [v for v in valued if v.instrument_type == "BOND_FIXED"]
    bond_mv = sum(v.mv_base for v in bonds)
    fi = None
    if bonds:
        fi = {
            "market_value": bond_mv,
            "modified_duration": sum(v.modified_duration * v.mv_base for v in bonds) / bond_mv if bond_mv else None,
            "dv01": sum(v.dv01_base for v in bonds),
            "cs01": sum(v.dv01_base for v in bonds if v.cs_factor),
            "accrued": sum(v.accrued_base for v in bonds),
            "ytm_mv_weighted": sum(v.ytm * v.mv_base for v in bonds) / bond_mv if bond_mv else None,
        }
    return {
        "positions": rows,
        "totals": {
            "net": net,
            "gross": gross,
            "long": sum(v.mv_base for v in valued if v.mv_base > 0),
            "short": sum(v.mv_base for v in valued if v.mv_base < 0),
            "n_positions": len(ctx.vals),
            "n_excluded": sum(1 for v in ctx.vals if v.excluded),
        },
        "groups": {
            "asset_class": group(lambda v: v.asset_class),
            "currency": group(lambda v: v.currency),
            "sector": group(lambda v: v.attributes.get("sector")),
            "issuer": group(lambda v: v.attributes.get("issuer")),
            "country": group(lambda v: v.attributes.get("country")),
            "rating": group(lambda v: v.attributes.get("rating") if v.instrument_type == "BOND_FIXED" else None),
        },
        "fixed_income": fi,
        "sensitivities": eng.sensitivities(ctx.vals),
        "warnings": _data_warnings(ctx),
    }


# ------------------------------------------------------------------ risk
def _factor_pnl_linear(hs: eng.HistoricalSimulation, vals) -> pd.DataFrame:
    """Linear P&L per risk factor: column f = exposure_f * Delta f_t.
    Sum over factors equals the linearised portfolio P&L exactly."""
    act = {v.id: v for v in vals}
    ch = hs.factor_changes
    cols: dict[str, np.ndarray] = {}

    def add(f, x):
        cols[f] = cols.get(f, 0.0) + x

    for pid in hs.position_ids:
        v = act[pid]
        V0 = v.mv_base
        if v.eq_factor:
            add(v.eq_factor, V0 * ch[v.eq_factor].values)
        if v.fx_factor:
            add(v.fx_factor, V0 * ch[v.fx_factor].values)
        if v.instrument_type == "BOND_FIXED":
            for f, w in zip(v.ir_factors, v.ir_weights):
                add(f, -v.modified_duration * V0 * w * ch[f].values)
            if v.cs_factor:
                add(v.cs_factor, -v.modified_duration * V0 * ch[v.cs_factor].values)
    return pd.DataFrame(cols, index=hs.dates)


def risk_summary(ctx: Context, window: int, alpha: float, horizon: int) -> dict:
    params = {"window": window, "confidence": alpha, "horizon_days": horizon, "as_of": ctx.pf.as_of.isoformat()}
    hs = eng.historical_simulation(ctx.vals, ctx.levels, ctx.pf.as_of, window)
    warnings = _data_warnings(ctx)
    if hs.dropped_dates:
        warnings.append(f"{hs.dropped_dates} date(s) dropped in the window because at least one required factor was missing (no filling applied).")
    n = len(hs.dates)
    if n < window:
        warnings.append(f"Only {n} usable observations for a requested window of {window}.")
    total = hs.pnl_full.sum(axis=1)
    total_lin = hs.pnl_linear.sum(axis=1)
    sqrt_h = math.sqrt(horizon)
    hist = {"available": False}
    try:
        warnings += rm.data_sufficiency(n, alpha)
        var1, es1 = rm.historical_var_es(total, alpha)
        ces = rm.component_historical_es(hs.pnl_full, alpha)
        hist = {"available": True, "var_1d": var1, "es_1d": es1, "var": var1 * sqrt_h, "es": es1 * sqrt_h, "n_obs": n, "tail_obs": n * (1 - alpha)}
    except rm.InsufficientDataError as e:
        hist["reason"] = str(e)
        ces = None
    param = {"available": False}
    cvar = None
    if n >= 30 and hs.pnl_linear.shape[1]:
        cvar = rm.component_parametric_var(hs.pnl_linear, alpha)
        v1, e1 = rm.parametric_var_es(cvar["sigma"], alpha)
        param = {"available": True, "sigma_1d": cvar["sigma"], "var_1d": v1, "es_1d": e1, "var": v1 * sqrt_h, "es": e1 * sqrt_h, "diversification_1d": cvar["diversification"]}
        # normality diagnostics on the full-revaluation P&L
        param["skew"] = _f(pd.Series(total).skew())
        param["excess_kurtosis"] = _f(pd.Series(total).kurt())
        param["delta_approx_corr"] = _f(np.corrcoef(total, total_lin)[0, 1]) if np.std(total) > 0 else None
    valued_mv = sum(v.mv_base for v in ctx.vals if v.mv_base is not None and not v.excluded)
    gross_all = sum(abs(v.mv_base) for v in ctx.vals if v.mv_base is not None)
    gross_in = sum(abs(v.mv_base) for v in ctx.vals if v.mv_base is not None and not v.excluded)
    # distribution
    counts, edges = np.histogram(total, bins=min(50, max(10, n // 10))) if n else (np.array([]), np.array([]))
    # positions table
    act = {v.id: v for v in ctx.vals}
    pos_rows = []
    for j, pid in enumerate(hs.position_ids):
        v = act[pid]
        col = hs.pnl_full[:, j]
        pos_rows.append(
            {
                "id": pid,
                "name": v.name,
                "asset_class": v.asset_class,
                "currency": v.currency,
                "mv_base": v.mv_base,
                "vol_annual": _f(np.std(col, ddof=1) * math.sqrt(252) / abs(v.mv_base)) if n > 1 and v.mv_base else None,
                "component_es": _f(ces["component"][j] * sqrt_h) if ces else None,
                "component_es_pct": _f(ces["component"][j] / ces["es"]) if ces and ces["es"] else None,
                "component_var_param": _f(cvar["component"][j] * sqrt_h) if cvar else None,
                "standalone_var_param": _f(cvar["stand_alone"][j] * sqrt_h) if cvar else None,
            }
        )
    pos_rows.sort(key=lambda r: -(r["component_es"] or 0))
    # full-history backcast and backtest
    hs_all = eng.historical_simulation(ctx.vals, ctx.levels, ctx.pf.as_of, 100_000)
    tot_all = hs_all.pnl_full.sum(axis=1)
    backtest = None
    if window < rm.MIN_OBS_HARD or window * (1 - alpha) < 1:
        warnings.append("Backtest not run: the window is too short to estimate VaR at this confidence level.")
    elif len(tot_all) >= window + 250:
        bt = rm.backtest_historical_var(tot_all, alpha, window, 250)
        dates_bt = hs_all.dates[-250:]
        backtest = {
            "n": bt.n,
            "exceptions": bt.exceptions,
            "expected": bt.expected,
            "kupiec_lr": bt.kupiec_lr,
            "kupiec_pvalue": bt.kupiec_pvalue,
            "traffic_light": bt.traffic_light,
            "series": [{"date": d.date().isoformat(), "var": float(vv), "pnl": float(p)} for d, vv, p in zip(dates_bt, bt.var_series, tot_all[-250:])],
        }
    else:
        warnings.append(f"Backtest needs {window + 250} observations; {len(tot_all)} available.")
    if horizon > 1:
        warnings.append(f"{horizon}-day figures are 1-day figures scaled by sqrt({horizon}); this assumes i.i.d. zero-mean daily P&L.")
    return {
        "meta": meta(ctx, params),
        "portfolio_value": valued_mv,
        "coverage_gross": gross_in / gross_all if gross_all else None,
        "window": {"start": hs.dates[0].date().isoformat() if n else None, "end": hs.dates[-1].date().isoformat() if n else None, "n_obs": n, "dropped": hs.dropped_dates},
        "historical": hist,
        "parametric": param,
        "distribution": {"edges": edges.tolist(), "counts": counts.tolist()},
        "pnl_series": [{"date": d.date().isoformat(), "pnl": float(p)} for d, p in zip(hs.dates, total)],
        "backcast": [{"date": d.date().isoformat(), "cum_pnl": float(c)} for d, c in zip(hs_all.dates, np.cumsum(tot_all))],
        "backtest": backtest,
        "positions": pos_rows,
        "excluded": [{"id": v.id, "reason": v.excluded} for v in ctx.vals if v.excluded],
        "warnings": warnings,
    }


def factor_stats(ctx: Context, window: int) -> dict:
    hs = eng.historical_simulation(ctx.vals, ctx.levels, ctx.pf.as_of, window)
    ch = hs.factor_changes
    facs = list(ch.columns)
    meta_f = ctx.drow.factor_meta or {}
    rows = []
    for f in facs:
        x = ch[f].values
        cls = f.split(":")[0]
        vol = rm.annualised_volatility(x) if len(x) > 1 else None
        ewma = rm.ewma_volatility(x)[-1] if len(x) > 21 else None
        unit = "annualised vol of returns" if cls in ("EQ", "FX") else "annualised vol of daily changes, bp"
        scale = 1.0 if cls in ("EQ", "FX") else 1e4
        rows.append({"factor": f, "name": meta_f.get(f, {}).get("name", f), "class": cls, "vol": _f(vol * scale) if vol else None, "ewma_vol": _f(ewma * scale) if ewma is not None else None, "unit": unit, "n_obs": int(len(x))})
    corr = cov = None
    if len(facs) > 1 and len(ch) > 2:
        cov_m, corr_m = rm.covariance_correlation(ch.values)
        corr = [[_f(v) for v in r] for r in corr_m]
        cov = {"symmetric": bool(np.allclose(cov_m, cov_m.T)), "min_eigenvalue": float(np.linalg.eigvalsh(cov_m).min())}
    return {"meta": meta(ctx, {"window": window}), "factors": rows, "labels": facs, "correlation": corr, "covariance_check": cov, "n_obs": int(len(ch))}


# ------------------------------------------------------------------ attribution
def attribution(ctx: Context, window: int, alpha: float, horizon: int) -> dict:
    params = {"window": window, "confidence": alpha, "horizon_days": horizon}
    hs = eng.historical_simulation(ctx.vals, ctx.levels, ctx.pf.as_of, window)
    n = len(hs.dates)
    sqrt_h = math.sqrt(horizon)
    warnings = _data_warnings(ctx)
    try:
        warnings += rm.data_sufficiency(n, alpha)
    except rm.InsufficientDataError as e:
        return {"meta": meta(ctx, params), "available": False, "reason": str(e), "warnings": warnings}
    act = {v.id: v for v in ctx.vals}
    ces = rm.component_historical_es(hs.pnl_full, alpha)
    cvar = rm.component_parametric_var(hs.pnl_linear, alpha)
    pos = []
    for j, pid in enumerate(hs.position_ids):
        v = act[pid]
        pos.append({"id": pid, "name": v.name, "asset_class": v.asset_class, "currency": v.currency, "sector": v.attributes.get("sector"), "issuer": v.attributes.get("issuer"), "country": v.attributes.get("country"), "mv_base": v.mv_base, "es": float(ces["component"][j] * sqrt_h), "var_param": float(cvar["component"][j] * sqrt_h), "standalone_var_param": float(cvar["stand_alone"][j] * sqrt_h)})
    es_tot = ces["es"] * sqrt_h
    var_tot = cvar["var"] * sqrt_h
    mv_gross = sum(abs(p["mv_base"]) for p in pos)

    def grp(key):
        g = {}
        for p in pos:
            k = p.get(key) or "Unspecified"
            e = g.setdefault(k, {"key": k, "es": 0.0, "var_param": 0.0, "mv": 0.0, "gross": 0.0})
            e["es"] += p["es"]
            e["var_param"] += p["var_param"]
            e["mv"] += p["mv_base"]
            e["gross"] += abs(p["mv_base"])
        out = sorted(g.values(), key=lambda e: -e["es"])
        for e in out:
            e["es_pct"] = e["es"] / es_tot if es_tot else None
            e["weight_gross"] = e["gross"] / mv_gross if mv_gross else None
        return out

    # factor-level Euler decomposition (delta-normal)
    fpnl = _factor_pnl_linear(hs, ctx.vals)
    fac_rows = []
    by_class_param = {}
    if fpnl.shape[1]:
        fc = rm.component_parametric_var(fpnl.values, alpha)
        for f, c, s in zip(fpnl.columns, fc["component"], fc["stand_alone"]):
            cls = f.split(":")[0]
            fac_rows.append({"factor": f, "class": cls, "var_param": float(c * sqrt_h), "standalone_var_param": float(s * sqrt_h)})
            by_class_param[cls] = by_class_param.get(cls, 0.0) + float(c * sqrt_h)
        fac_rows.sort(key=lambda r: -r["var_param"])
    # historical stand-alone ES per factor class (one class moving at a time)
    cls_map = {"EQ": "equity", "FX": "fx", "IR": "rates", "CS": "spreads"}
    standalone_hist = {}
    for cls, label in cls_map.items():
        cols = [c for c in hs.factor_changes.columns if c.startswith(cls + ":")]
        if not cols:
            continue
        ch = hs.factor_changes.copy()
        for c in ch.columns:
            if c not in cols:
                ch[c] = 0.0
        tot = np.zeros(n)
        for pid in hs.position_ids:
            v = act[pid]
            r_eq, r_fx, dy = eng.moves_for_position(v, ch, n)
            tot += eng.revalue(v, r_eq, r_fx, dy)[0]
        standalone_hist[label] = rm.historical_var_es(tot, alpha)[1] * sqrt_h
    names = {"EQ": "equity", "FX": "fx", "IR": "rates", "CS": "spreads"}
    return {
        "meta": meta(ctx, params),
        "available": True,
        "totals": {"es": es_tot, "var_param": var_tot, "sum_standalone_es_by_class": sum(standalone_hist.values()), "diversification_es": sum(standalone_hist.values()) - es_tot},
        "positions": sorted(pos, key=lambda p: -p["es"]),
        "groups": {k: grp(k) for k in ("asset_class", "currency", "sector", "issuer", "country")},
        "factors": fac_rows,
        "factor_classes": [{"class": names[c], "var_param": v, "standalone_es_hist": standalone_hist.get(names[c])} for c, v in sorted(by_class_param.items(), key=lambda x: -x[1])],
        "sensitivities": eng.sensitivities(ctx.vals),
        "warnings": warnings,
    }


# ------------------------------------------------------------------ stress
def stress(ctx: Context, scenarios: list[dict], ref_alpha: float = 0.99, ref_window: int = 500) -> dict:
    results = []
    for sc in scenarios:
        try:
            r = st.run_scenario(ctx.vals, sc, ctx.pf.as_of, ctx.levels)
            r.update({"scenario_id": sc.get("id"), "name": sc.get("name"), "description": sc.get("description"), "definition": sc.get("definition")})
            if sc.get("kind") == "historical":
                r["provenance_note"] = f"Replay of moves recorded in dataset '{ctx.drow.name}' ({PROVENANCE_LABEL.get(ctx.drow.provenance)})."
            results.append(r)
        except (ValueError, KeyError) as e:
            results.append({"scenario_id": sc.get("id"), "name": sc.get("name"), "error": str(e)})
    reference = None
    try:
        hs = eng.historical_simulation(ctx.vals, ctx.levels, ctx.pf.as_of, ref_window)
        v1, e1 = rm.historical_var_es(hs.pnl_full.sum(axis=1), ref_alpha)
        reference = {"label": f"Historical {ref_alpha:.0%} 10-day ES (window {len(hs.dates)}, sqrt-time scaled)", "es_10d": e1 * math.sqrt(10), "var_10d": v1 * math.sqrt(10)}
    except rm.InsufficientDataError:
        pass
    return {"meta": meta(ctx, {"scenarios": [s.get("id") for s in scenarios]}), "base_value": sum(v.mv_base for v in ctx.vals if v.mv_base is not None and not v.excluded), "results": results, "reference": reference, "warnings": _data_warnings(ctx)}


# ------------------------------------------------------------------ fixed income
def curve_at(levels: pd.DataFrame, ccy: str, on: date) -> list[tuple[str, float, float]] | None:
    cf = eng.curve_factors(levels.columns, ccy)
    if not cf:
        return None
    sub = levels.loc[: pd.Timestamp(on), [c for c, _ in cf]].dropna(how="any")
    if sub.empty:
        return None
    last = sub.iloc[-1]
    return [(c, t, float(last[c])) for c, t in cf], sub.index[-1].date()


def bond_report(maturity: date, coupon_pct: float, frequency: int, daycount: str, settlement: date, clean: float | None, ytm_pct: float | None, ccy: str | None = None, levels: pd.DataFrame | None = None) -> dict:
    bond = bd.FixedRateBond(maturity, coupon_pct / 100.0, frequency, daycount)
    a = bd.analytics(bond, settlement, clean=clean, ytm=None if ytm_pct is None else ytm_pct / 100.0)
    cf = bd.cash_flows(bond, settlement)
    y0 = a.yield_to_maturity
    grid = np.round(np.arange(-300, 301, 10), 6)
    exact = bd.dirty_price(cf, y0 + grid / 1e4)
    approx_d = a.dirty_price * (1 - a.modified_duration * grid / 1e4)
    approx_dc = a.dirty_price * (1 + bd.price_change_approximation(a.modified_duration, a.convexity, grid / 1e4))
    out = {
        "inputs": {"maturity": maturity.isoformat(), "coupon_pct": coupon_pct, "frequency": frequency, "daycount": bond.daycount, "settlement": settlement.isoformat()},
        "analytics": {k: v for k, v in a.__dict__.items() if k != "cash_flows"},
        "previous_coupon": cf.previous_coupon.isoformat(),
        "next_coupon": cf.dates[0].isoformat(),
        "cash_flows": a.cash_flows,
        "sensitivity_curve": [{"dy_bp": float(g), "exact": float(e), "duration": float(d), "duration_convexity": float(dc)} for g, e, d, dc in zip(grid, exact, approx_d, approx_dc)],
        "spread": None,
    }
    if ccy and levels is not None:
        got = curve_at(levels, ccy, settlement)
        if got:
            pts, on = got
            t = (maturity - settlement).days / 365.25
            w = interpolation_weights([p[1] for p in pts], t)
            base = float(np.dot(w, [p[2] for p in pts]))
            out["spread"] = {
                "kind": "G-spread (approximation)",
                "benchmark_yield": base,
                "spread_bp": (y0 - base) * 1e4,
                "curve_date": on.isoformat(),
                "curve": [{"factor": c, "tenor_years": t_, "yield": y_} for c, t_, y_ in pts],
                "note": "Bond yield minus the government curve linearly interpolated at the bond's maturity. Not a Z-spread or OAS; the curve's own compounding convention may differ from the bond's.",
            }
    return out
