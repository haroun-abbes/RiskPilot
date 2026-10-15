from __future__ import annotations

import hashlib
import io
import math
from datetime import date, datetime, timezone

import numpy as np
import pandas as pd
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .. import alerts as al
from ..config import ENABLE_ECB, ENGINE_VERSION
from ..data import ecb, quality
from ..data.market_csv import MarketFileError, parse_market_csv
from ..db.models import AlertEventRow, AlertRuleRow, DatasetRow, ImportSessionRow, PortfolioRow, ReportRow, ScenarioRow, WatchlistRow
from ..db.session import get_db
from ..portfolio import demo, importer
from ..quant.instruments import Portfolio
from ..reports import brief
from ..services import analytics as an
from ..services import store
from . import schemas as S

router = APIRouter(prefix="/api")


def clean(o):
    """Make engine output JSON-safe: numpy -> python, NaN/inf -> None."""
    if isinstance(o, dict):
        return {str(k): clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, np.ndarray):
        return [clean(v) for v in o.tolist()]
    if isinstance(o, (np.floating, float)):
        f = float(o)
        return f if math.isfinite(f) else None
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.bool_):
        return bool(o)
    if isinstance(o, (date, datetime, pd.Timestamp)):
        return o.isoformat()
    return o


def _ctx(db, pid, dsid):
    try:
        return an.context(db, pid, dsid)
    except store.NotFound as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(422, str(e))


@router.get("/health")
def health():
    return {"status": "ok", "engine_version": ENGINE_VERSION}


# ======================================================== datasets & providers
def _ds_dict(r: DatasetRow) -> dict:
    return {"id": r.id, "name": r.name, "provenance": r.provenance, "provenance_label": an.PROVENANCE_LABEL.get(r.provenance), "source": r.source, "description": r.description, "license_note": r.license_note, "frequency": r.frequency, "updated_at": r.updated_at, "hash": r.content_hash[:12], "n_factors": len(r.factor_meta or {})}


@router.get("/datasets")
def list_datasets(db: Session = Depends(get_db)):
    out = []
    for r in db.scalars(select(DatasetRow).order_by(DatasetRow.created_at)):
        d = _ds_dict(r)
        _, lv = store.get_dataset(db, r.id)
        d.update({"start": lv.index[0].date(), "end": lv.index[-1].date(), "n_dates": len(lv), "n_factors": lv.shape[1]})
        out.append(d)
    return clean(out)


@router.get("/datasets/{ds_id}/quality")
def dataset_quality(ds_id: str, db: Session = Depends(get_db)):
    try:
        row, lv = store.get_dataset(db, ds_id)
    except store.NotFound as e:
        raise HTTPException(404, str(e))
    rep = quality.dataset_report(lv)
    for f in rep["factors"]:
        f["meta"] = (row.factor_meta or {}).get(f["factor"], {})
    return clean({"dataset": _ds_dict(row), **rep})


@router.get("/datasets/{ds_id}/series")
def dataset_series(ds_id: str, factors: str, start: date | None = None, db: Session = Depends(get_db)):
    try:
        row, lv = store.get_dataset(db, ds_id)
    except store.NotFound as e:
        raise HTTPException(404, str(e))
    fs = [f for f in factors.split(",") if f]
    missing = [f for f in fs if f not in lv.columns]
    if missing:
        raise HTTPException(404, f"Unknown factor(s): {', '.join(missing)}")
    sub = lv[fs]
    if start:
        sub = sub.loc[pd.Timestamp(start):]
    out = {}
    for f in fs:
        s = sub[f].dropna()
        cls = f.split(":")[0]
        last = float(s.iloc[-1]) if len(s) else None

        def chg(k):
            if len(s) <= k:
                return None
            a, b = s.iloc[-1 - k], s.iloc[-1]
            return (b / a - 1) if cls in ("EQ", "FX") else (b - a)

        ytd = s.loc[str(s.index[-1].year)] if len(s) else s
        out[f] = {
            "meta": (row.factor_meta or {}).get(f, {}),
            "class": cls,
            "change_kind": "return" if cls in ("EQ", "FX") else "absolute",
            "last": last,
            "last_date": s.index[-1].date() if len(s) else None,
            "chg_1d": chg(1), "chg_5d": chg(5), "chg_21d": chg(21),
            "chg_ytd": ((s.iloc[-1] / ytd.iloc[0] - 1) if cls in ("EQ", "FX") else (s.iloc[-1] - ytd.iloc[0])) if len(ytd) else None,
            "points": [[d.date().isoformat(), float(v)] for d, v in s.items()],
        }
    return clean({"dataset": _ds_dict(row), "series": out})


@router.get("/datasets/{ds_id}/factors")
def dataset_factors(ds_id: str, db: Session = Depends(get_db)):
    try:
        row, lv = store.get_dataset(db, ds_id)
    except store.NotFound as e:
        raise HTTPException(404, str(e))
    return [{"factor": c, "class": c.split(":")[0], **(row.factor_meta or {}).get(c, {})} for c in lv.columns]


@router.post("/datasets/upload")
async def upload_dataset(
    file: UploadFile = File(...),
    name: str = Form(...),
    provenance: str = Form(...),
    source: str = Form(...),
    license_note: str = Form(""),
    db: Session = Depends(get_db),
):
    if provenance not in ("SYNTHETIC", "HISTORICAL_REAL", "DELAYED"):
        raise HTTPException(422, "provenance must be SYNTHETIC, HISTORICAL_REAL or DELAYED")
    if not source.strip():
        raise HTTPException(422, "A source description is required")
    raw = await file.read()
    try:
        lv = parse_market_csv(raw)
    except MarketFileError as e:
        raise HTTPException(422, {"errors": e.errors})
    rep = quality.dataset_report(lv)
    if rep["issue_counts"]["error"]:
        errs = [f"{f['factor']}: {i['message']}" for f in rep["factors"] for i in f["issues"] if i["severity"] == "error"]
        raise HTTPException(422, {"errors": errs})
    ds_id = "user-" + hashlib.sha256(raw).hexdigest()[:12]
    meta = {c: {"name": c, "class": c.split(":")[0]} for c in lv.columns}
    row = store.save_dataset(db, ds_id, {"name": name, "provenance": provenance, "source": source, "license_note": license_note, "description": f"Uploaded file {file.filename}", "frequency": "As provided by the user"}, lv, meta)
    return clean(_ds_dict(row))


@router.delete("/datasets/{ds_id}")
def delete_dataset(ds_id: str, db: Session = Depends(get_db)):
    row = db.get(DatasetRow, ds_id)
    if row is None:
        raise HTTPException(404, "Dataset not found")
    if row.id == "synthetic-demo-v1":
        raise HTTPException(409, "The built-in synthetic dataset cannot be deleted")
    db.delete(row)
    db.commit()
    return {"deleted": ds_id}


@router.get("/providers")
def providers(db: Session = Depends(get_db)):
    ecb_row = db.get(DatasetRow, "ecb-eur")
    return [
        {"id": "synthetic", "name": "Synthetic generator", "status": "available", "kind": "SYNTHETIC", "detail": "Local deterministic generator; always available.", "realtime": False},
        {"id": "csv", "name": "CSV upload", "status": "available", "kind": "USER", "detail": "User-supplied end-of-day history; provenance declared at upload.", "realtime": False},
        {
            "id": "ecb",
            "name": "ECB Data Portal",
            "status": ("disabled" if not ENABLE_ECB else ("loaded" if ecb_row else "not_loaded")),
            "kind": "HISTORICAL_REAL",
            "detail": "EUR reference FX rates and euro area AAA spot curve. Daily reference values, not real time. " + ecb.DATASET_INFO["license_note"],
            "last_update": ecb_row.updated_at if ecb_row else None,
            "realtime": False,
        },
    ]


@router.post("/providers/ecb/test")
def ecb_test():
    if not ENABLE_ECB:
        raise HTTPException(409, "ECB provider disabled by configuration")
    return {"checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), **ecb.test_connection()}


@router.post("/providers/ecb/fetch")
def ecb_fetch(start: date = date(2021, 1, 1), db: Session = Depends(get_db)):
    if not ENABLE_ECB:
        raise HTTPException(409, "ECB provider disabled by configuration")
    try:
        lv, meta = ecb.fetch(start)
    except ecb.ProviderError as e:
        raise HTTPException(502, f"ECB fetch failed: {e}")
    info = {"name": "ECB reference rates & AAA euro curve", "description": "FX reference rates (EUR per unit) and euro area AAA government spot curve.", **ecb.DATASET_INFO}
    row = store.save_dataset(db, "ecb-eur", info, lv, meta)
    return clean(_ds_dict(row))


# ======================================================== portfolios
def _pf_dict(r: PortfolioRow) -> dict:
    return {"id": r.id, "name": r.name, "as_of": r.as_of, "base_currency": r.base_currency, "provenance": r.provenance, "source_filename": r.source_filename, "n_positions": len(r.positions), "created_at": r.created_at, "hash": r.content_hash[:12]}


@router.get("/portfolios")
def list_portfolios(db: Session = Depends(get_db)):
    return clean([_pf_dict(r) for r in db.scalars(select(PortfolioRow).order_by(PortfolioRow.created_at))])


@router.delete("/portfolios/{pid}")
def delete_portfolio(pid: str, db: Session = Depends(get_db)):
    row = db.get(PortfolioRow, pid)
    if row is None:
        raise HTTPException(404, "Portfolio not found")
    if row.id == "demo":
        raise HTTPException(409, "The demo portfolio cannot be deleted")
    db.delete(row)
    db.commit()
    return {"deleted": pid}


@router.get("/portfolios/{pid}/exposures")
def portfolio_exposures(pid: str, dataset_id: str, db: Session = Depends(get_db)):
    ctx = _ctx(db, pid, dataset_id)
    return clean({"meta": an.meta(ctx, {}), **an.exposures(ctx)})


@router.get("/templates/portfolio.{fmt}")
def template(fmt: str, db: Session = Depends(get_db)):
    _, lv = store.get_dataset(db, "synthetic-demo-v1")
    pf = demo.build(lv)
    if fmt == "csv":
        return Response(demo.to_csv(pf), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=riskpilot_demo_portfolio_SYNTHETIC.csv"})
    if fmt == "xlsx":
        return Response(demo.to_xlsx(pf), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": "attachment; filename=riskpilot_demo_portfolio_SYNTHETIC.xlsx"})
    raise HTTPException(404, "Use csv or xlsx")


@router.get("/templates/fields")
def template_fields():
    return {"fields": importer.FIELDS, "required": importer.REQUIRED}


@router.post("/portfolios/import/preview")
async def import_preview(file: UploadFile = File(...), db: Session = Depends(get_db)):
    raw = await file.read()
    try:
        header, body = importer.parse_file(file.filename or "", raw)
    except importer.ImportFileError as e:
        raise HTTPException(422, str(e))
    rows = [[None if v is None else (v.isoformat() if isinstance(v, (date, datetime)) else v) for v in r] for r in body]
    sess = ImportSessionRow(filename=file.filename or "upload", header=header, rows=rows)
    db.add(sess)
    db.commit()
    return clean({"session_id": sess.id, "filename": sess.filename, "header": header, "n_rows": len(rows), "preview": rows[:15], "suggested_mapping": importer.suggest_mapping(header), "fields": importer.FIELDS, "required": importer.REQUIRED})


def _validate(db, req: S.MappingRequest):
    sess = db.get(ImportSessionRow, req.session_id)
    if sess is None:
        raise HTTPException(404, "Import session expired or unknown; upload the file again")
    try:
        positions, issues, preview = importer.validate(sess.header, sess.rows, req.mapping, req.as_of)
    except importer.ImportFileError as e:
        raise HTTPException(422, str(e))
    return sess, positions, issues, preview


@router.post("/portfolios/import/validate")
def import_validate(req: S.MappingRequest, db: Session = Depends(get_db)):
    sess, positions, issues, preview = _validate(db, req)
    n_err = sum(1 for i in issues if i["severity"] == "error")
    by_type = {}
    for p in positions:
        by_type[p.instrument_type] = by_type.get(p.instrument_type, 0) + 1
    return clean({"valid_positions": len(positions), "rows": len(sess.rows), "errors": n_err, "warnings": len(issues) - n_err, "issues": issues, "rows_status": preview, "by_type": by_type, "can_commit": n_err == 0 and len(positions) > 0})


@router.post("/portfolios/import/commit")
def import_commit(req: S.MappingRequest, db: Session = Depends(get_db)):
    sess, positions, issues, _ = _validate(db, req)
    if any(i["severity"] == "error" for i in issues):
        raise HTTPException(422, "Blocking errors remain; fix the file or the mapping first")
    if not positions:
        raise HTTPException(422, "No valid position to import")
    row = store.save_portfolio(db, Portfolio(req.name, "EUR", req.as_of, positions), "USER_IMPORT", sess.filename)
    db.delete(sess)
    db.commit()
    return clean(_pf_dict(row))


# ======================================================== risk
@router.post("/risk/summary")
def risk_summary(p: S.RiskParams, db: Session = Depends(get_db)):
    ctx = _ctx(db, p.portfolio_id, p.dataset_id)
    return clean(an.risk_summary(ctx, p.window, p.confidence, p.horizon_days))


@router.post("/risk/factors")
def risk_factors(p: S.RiskParams, db: Session = Depends(get_db)):
    ctx = _ctx(db, p.portfolio_id, p.dataset_id)
    return clean(an.factor_stats(ctx, p.window))


@router.post("/attribution")
def attribution(p: S.RiskParams, db: Session = Depends(get_db)):
    ctx = _ctx(db, p.portfolio_id, p.dataset_id)
    return clean(an.attribution(ctx, p.window, p.confidence, p.horizon_days))


@router.post("/attribution/compare")
def attribution_compare(p: S.CompareRequest, db: Session = Depends(get_db)):
    out = {}
    for k, pid in (("a", p.portfolio_a), ("b", p.portfolio_b)):
        ctx = _ctx(db, pid, p.dataset_id)
        out[k] = {"exposures": an.exposures(ctx)["totals"], "attribution": an.attribution(ctx, p.window, p.confidence, p.horizon_days), "risk": {k2: v for k2, v in an.risk_summary(ctx, p.window, p.confidence, p.horizon_days).items() if k2 in ("historical", "parametric", "portfolio_value", "meta")}}
    return clean(out)


# ======================================================== scenarios & stress
def _sc_dict(r: ScenarioRow) -> dict:
    return {"id": r.id, "name": r.name, "kind": r.kind, "description": r.description, "definition": r.definition, "is_builtin": r.is_builtin, "updated_at": r.updated_at}


@router.get("/scenarios")
def list_scenarios(db: Session = Depends(get_db)):
    return clean([_sc_dict(r) for r in db.scalars(select(ScenarioRow).order_by(ScenarioRow.is_builtin.desc(), ScenarioRow.created_at))])


@router.post("/scenarios")
def create_scenario(s: S.ScenarioIn, db: Session = Depends(get_db)):
    try:
        d = s.validated_definition()
    except ValueError as e:
        raise HTTPException(422, str(e))
    r = ScenarioRow(name=s.name, kind=s.kind, description=s.description, definition=d)
    db.add(r)
    db.commit()
    return clean(_sc_dict(r))


@router.put("/scenarios/{sid}")
def update_scenario(sid: str, s: S.ScenarioIn, db: Session = Depends(get_db)):
    r = db.get(ScenarioRow, sid)
    if r is None:
        raise HTTPException(404, "Scenario not found")
    if r.is_builtin:
        raise HTTPException(409, "Built-in scenarios are read-only; duplicate it to edit")
    try:
        r.definition = s.validated_definition()
    except ValueError as e:
        raise HTTPException(422, str(e))
    r.name, r.kind, r.description = s.name, s.kind, s.description
    r.updated_at = datetime.now(timezone.utc)
    db.commit()
    return clean(_sc_dict(r))


@router.post("/scenarios/{sid}/duplicate")
def duplicate_scenario(sid: str, db: Session = Depends(get_db)):
    r = db.get(ScenarioRow, sid)
    if r is None:
        raise HTTPException(404, "Scenario not found")
    c = ScenarioRow(name=f"{r.name} (copy)", kind=r.kind, description=r.description, definition=dict(r.definition))
    db.add(c)
    db.commit()
    return clean(_sc_dict(c))


@router.delete("/scenarios/{sid}")
def delete_scenario(sid: str, db: Session = Depends(get_db)):
    r = db.get(ScenarioRow, sid)
    if r is None:
        raise HTTPException(404, "Scenario not found")
    if r.is_builtin:
        raise HTTPException(409, "Built-in scenarios cannot be deleted")
    db.delete(r)
    db.commit()
    return {"deleted": sid}


def _load_scenarios(db, ids: list[str]) -> list[dict]:
    out = []
    for i in ids:
        r = db.get(ScenarioRow, i)
        if r is None:
            raise HTTPException(404, f"Scenario {i} not found")
        out.append(_sc_dict(r))
    return out


@router.post("/stress/run")
def stress_run(req: S.StressRequest, db: Session = Depends(get_db)):
    ctx = _ctx(db, req.portfolio_id, req.dataset_id)
    scs = _load_scenarios(db, req.scenario_ids)
    for a in req.adhoc:
        try:
            scs.append({"id": None, "name": a.name, "kind": a.kind, "description": a.description, "definition": a.validated_definition()})
        except ValueError as e:
            raise HTTPException(422, str(e))
    if not scs:
        raise HTTPException(422, "Select at least one scenario")
    return clean(an.stress(ctx, scs))


# ======================================================== fixed income
def _bond(req: S.BondRequest, db):
    if (req.clean_price is None) == (req.ytm_pct is None):
        raise HTTPException(422, "Provide exactly one of clean_price or ytm_pct")
    lv = None
    if req.dataset_id:
        try:
            _, lv = store.get_dataset(db, req.dataset_id)
        except store.NotFound as e:
            raise HTTPException(404, str(e))
    try:
        out = an.bond_report(req.maturity, req.coupon_pct, req.frequency, req.daycount, req.settlement, req.clean_price, req.ytm_pct, req.currency, lv)
    except ValueError as e:
        raise HTTPException(422, str(e))
    out["label"] = req.label or f"{req.coupon_pct:g}% {req.maturity.isoformat()}"
    return out


@router.post("/bonds/analytics")
def bond_analytics(req: S.BondRequest, db: Session = Depends(get_db)):
    return clean(_bond(req, db))


@router.post("/bonds/compare")
def bond_compare(req: S.BondCompareRequest, db: Session = Depends(get_db)):
    return clean([_bond(b, db) for b in req.bonds])


@router.get("/portfolios/{pid}/bonds")
def portfolio_bonds(pid: str, dataset_id: str, db: Session = Depends(get_db)):
    ctx = _ctx(db, pid, dataset_id)
    out = []
    for p in ctx.pf.positions:
        if p.instrument_type != "BOND_FIXED":
            continue
        try:
            r = an.bond_report(p.maturity, p.coupon_rate * 100, p.frequency, p.daycount, ctx.pf.as_of, p.clean_price, None, p.currency, ctx.levels)
        except ValueError as e:
            out.append({"id": p.id, "name": p.name, "error": str(e)})
            continue
        out.append({"id": p.id, "name": p.name, "issuer": p.issuer, "rating": p.rating, "currency": p.currency, "nominal": p.nominal, "clean_price": p.clean_price, "coupon_pct": p.coupon_rate * 100, "frequency": p.frequency, "daycount": p.daycount, "maturity": p.maturity, "is_sovereign": p.is_sovereign, "analytics": r["analytics"], "spread": r["spread"]})
    return clean({"meta": an.meta(ctx, {}), "bonds": out})


# ======================================================== market watch & alerts
@router.get("/watchlists")
def list_watchlists(db: Session = Depends(get_db)):
    return clean([{"id": w.id, "name": w.name, "factors": w.factors} for w in db.scalars(select(WatchlistRow).order_by(WatchlistRow.created_at))])


@router.post("/watchlists")
def create_watchlist(w: S.WatchlistIn, db: Session = Depends(get_db)):
    r = WatchlistRow(name=w.name, factors=w.factors)
    db.add(r)
    db.commit()
    return {"id": r.id, "name": r.name, "factors": r.factors}


@router.put("/watchlists/{wid}")
def update_watchlist(wid: str, w: S.WatchlistIn, db: Session = Depends(get_db)):
    r = db.get(WatchlistRow, wid)
    if r is None:
        raise HTTPException(404, "Watchlist not found")
    r.name, r.factors = w.name, w.factors
    db.commit()
    return {"id": r.id, "name": r.name, "factors": r.factors}


@router.delete("/watchlists/{wid}")
def delete_watchlist(wid: str, db: Session = Depends(get_db)):
    r = db.get(WatchlistRow, wid)
    if r is None:
        raise HTTPException(404, "Watchlist not found")
    db.delete(r)
    db.commit()
    return {"deleted": wid}


def _rule_dict(r: AlertRuleRow):
    return {"id": r.id, "name": r.name, "factor": r.factor, "rule_type": r.rule_type, "direction": r.direction, "threshold": r.threshold, "lookback": r.lookback, "active": r.active}


@router.get("/alerts/rules")
def list_rules(db: Session = Depends(get_db)):
    return [_rule_dict(r) for r in db.scalars(select(AlertRuleRow).order_by(AlertRuleRow.created_at))]


@router.post("/alerts/rules")
def create_rule(a: S.AlertRuleIn, db: Session = Depends(get_db)):
    r = AlertRuleRow(**a.model_dump())
    db.add(r)
    db.commit()
    return _rule_dict(r)


@router.put("/alerts/rules/{rid}")
def update_rule(rid: str, a: S.AlertRuleIn, db: Session = Depends(get_db)):
    r = db.get(AlertRuleRow, rid)
    if r is None:
        raise HTTPException(404, "Rule not found")
    for k, v in a.model_dump().items():
        setattr(r, k, v)
    db.commit()
    return _rule_dict(r)


@router.delete("/alerts/rules/{rid}")
def delete_rule(rid: str, db: Session = Depends(get_db)):
    r = db.get(AlertRuleRow, rid)
    if r is None:
        raise HTTPException(404, "Rule not found")
    db.delete(r)
    db.commit()
    return {"deleted": rid}


def evaluate_rules(db: Session, dataset_id: str, last_n: int | None = None) -> list[dict]:
    try:
        _, lv = store.get_dataset(db, dataset_id)
    except store.NotFound as e:
        raise HTTPException(404, str(e))
    events = []
    for r in db.scalars(select(AlertRuleRow).where(AlertRuleRow.active.is_(True))):
        if r.factor not in lv.columns:
            events.append({"rule_id": r.id, "rule": r.name, "date": None, "value": None, "message": f"{r.name}: factor {r.factor} not in dataset, rule not evaluated", "status": "not_evaluated"})
            continue
        hits = al.evaluate(lv[r.factor], r.factor, r.rule_type, r.direction, r.threshold, r.lookback, r.name)
        if last_n:
            cutoff = lv.index[-last_n].date()
            hits = [h for h in hits if h["date"] >= cutoff]
        for h in hits:
            events.append({"rule_id": r.id, "rule": r.name, "status": "triggered", **h})
    events.sort(key=lambda e: (e["date"] is not None, e["date"] or date.min), reverse=True)
    return events


@router.post("/alerts/evaluate")
def alerts_evaluate(dataset_id: str, db: Session = Depends(get_db)):
    events = evaluate_rules(db, dataset_id)
    db.execute(delete(AlertEventRow).where(AlertEventRow.dataset_id == dataset_id))
    for e in events:
        if e["status"] == "triggered":
            db.add(AlertEventRow(rule_id=e["rule_id"], dataset_id=dataset_id, obs_date=e["date"], value=e["value"], message=e["message"]))
    db.commit()
    return clean({"evaluated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "n_events": sum(1 for e in events if e["status"] == "triggered"), "events": events})


@router.get("/alerts/events")
def alerts_events(dataset_id: str, limit: int = 200, db: Session = Depends(get_db)):
    q = select(AlertEventRow).where(AlertEventRow.dataset_id == dataset_id).order_by(AlertEventRow.obs_date.desc()).limit(limit)
    return clean([{"id": e.id, "rule_id": e.rule_id, "date": e.obs_date, "value": e.value, "message": e.message, "recorded_at": e.created_at} for e in db.scalars(q)])


# ======================================================== reports
@router.post("/reports")
def create_report(req: S.ReportRequest, db: Session = Depends(get_db)):
    ctx = _ctx(db, req.portfolio_id, req.dataset_id)
    scs = _load_scenarios(db, req.scenario_ids)
    alerts = [e for e in evaluate_rules(db, req.dataset_id, last_n=20) if e["status"] == "triggered"]
    rep = clean(brief.build(ctx, req.window, req.confidence, req.horizon_days, scs, alerts))
    title = req.title or brief.default_title(ctx.prow.name, datetime.now(timezone.utc))
    row = ReportRow(title=title, params=req.model_dump(), results=rep, portfolio_hash=ctx.prow.content_hash, dataset_hash=ctx.drow.content_hash, engine_version=ENGINE_VERSION)
    db.add(row)
    db.commit()
    return {"id": row.id, "title": title, "created_at": row.created_at.isoformat(), "report": rep}


@router.get("/reports")
def list_reports(db: Session = Depends(get_db)):
    return clean([{"id": r.id, "title": r.title, "created_at": r.created_at, "params": r.params, "engine_version": r.engine_version} for r in db.scalars(select(ReportRow).order_by(ReportRow.created_at.desc()))])


@router.get("/reports/{rid}")
def get_report(rid: str, db: Session = Depends(get_db)):
    r = db.get(ReportRow, rid)
    if r is None:
        raise HTTPException(404, "Report not found")
    return {"id": r.id, "title": r.title, "created_at": r.created_at.isoformat(), "params": r.params, "report": r.results}


@router.get("/reports/{rid}/pdf")
def report_pdf(rid: str, db: Session = Depends(get_db)):
    r = db.get(ReportRow, rid)
    if r is None:
        raise HTTPException(404, "Report not found")
    pdf = brief.to_pdf(r.results, r.title)
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename=riskpilot_brief_{r.id[:8]}.pdf"})


@router.get("/reports/{rid}/csv")
def report_csv(rid: str, db: Session = Depends(get_db)):
    r = db.get(ReportRow, rid)
    if r is None:
        raise HTTPException(404, "Report not found")
    return Response(brief.to_csv_zip(r.results), media_type="application/zip", headers={"Content-Disposition": f"attachment; filename=riskpilot_brief_{r.id[:8]}_tables.zip"})


@router.delete("/reports/{rid}")
def delete_report(rid: str, db: Session = Depends(get_db)):
    r = db.get(ReportRow, rid)
    if r is None:
        raise HTTPException(404, "Report not found")
    db.delete(r)
    db.commit()
    return {"deleted": rid}
