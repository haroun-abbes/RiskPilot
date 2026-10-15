"""Persistence helpers: datasets (CSV files + metadata row), portfolios, bootstrap."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from functools import lru_cache

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import DATA_DIR
from ..db.models import AlertRuleRow, DatasetRow, PortfolioRow, PositionRow, ScenarioRow, WatchlistRow
from ..portfolio import demo
from ..portfolio.serde import from_dict, to_dict
from ..quant.instruments import Portfolio


class NotFound(LookupError):
    pass


# ---------------- datasets ----------------
def save_dataset(db: Session, ds_id: str, info: dict, levels: pd.DataFrame, meta: dict) -> DatasetRow:
    path = DATA_DIR / "datasets" / f"{ds_id}.csv"
    levels.to_csv(path, date_format="%Y-%m-%d", float_format="%.10g")
    h = hashlib.sha256(path.read_bytes()).hexdigest()
    row = db.get(DatasetRow, ds_id)
    now = datetime.now(timezone.utc)
    if row is None:
        row = DatasetRow(id=ds_id, created_at=now)
        db.add(row)
    row.name = info["name"]
    row.provenance = info["provenance"]
    row.source = info["source"]
    row.description = info.get("description", "")
    row.license_note = info.get("license_note", "")
    row.frequency = info.get("frequency", "")
    row.file_path = str(path)
    row.content_hash = h
    row.factor_meta = meta
    row.updated_at = now
    db.commit()
    return row


@lru_cache(maxsize=16)
def _read_levels(path: str, content_hash: str) -> pd.DataFrame:
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    df.index.name = "date"
    return df.sort_index()


def get_dataset(db: Session, ds_id: str) -> tuple[DatasetRow, pd.DataFrame]:
    row = db.get(DatasetRow, ds_id)
    if row is None:
        raise NotFound(f"Dataset '{ds_id}' not found")
    return row, _read_levels(row.file_path, row.content_hash)


# ---------------- portfolios ----------------
def portfolio_hash(pf: Portfolio) -> str:
    payload = json.dumps({"as_of": pf.as_of.isoformat(), "base": pf.base_currency, "positions": [to_dict(p) for p in pf.positions]}, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


def save_portfolio(db: Session, pf: Portfolio, provenance: str, filename: str | None = None, pid: str | None = None) -> PortfolioRow:
    row = PortfolioRow(name=pf.name, base_currency=pf.base_currency, as_of=pf.as_of, provenance=provenance, source_filename=filename, content_hash=portfolio_hash(pf))
    if pid:
        row.id = pid
    for i, p in enumerate(pf.positions):
        row.positions.append(PositionRow(seq=i, position_id=p.id, instrument_type=p.instrument_type, payload=to_dict(p)))
    db.add(row)
    db.commit()
    return row


def get_portfolio(db: Session, pid: str) -> tuple[PortfolioRow, Portfolio]:
    row = db.get(PortfolioRow, pid)
    if row is None:
        raise NotFound(f"Portfolio '{pid}' not found")
    pf = Portfolio(row.name, row.base_currency, row.as_of, [from_dict(dict(p.payload)) for p in row.positions])
    return row, pf


# ---------------- bootstrap ----------------
BUILTIN_SCENARIOS = [
    ("Rates +100bp parallel (EUR, USD)", "hypothetical", "Instantaneous parallel shift of the EUR and USD government curves.", {"rates": {"EUR": {"parallel_bp": 100}, "USD": {"parallel_bp": 100}}}),
    ("Rates -100bp parallel (EUR, USD)", "hypothetical", "Instantaneous parallel fall of the EUR and USD government curves.", {"rates": {"EUR": {"parallel_bp": -100}, "USD": {"parallel_bp": -100}}}),
    ("EUR bear steepener", "hypothetical", "EUR curve: +25bp at 2Y rising linearly to +100bp at 30Y (flat beyond the end points).", {"rates": {"EUR": {"parallel_bp": 0, "tenor_bp": {"2Y": 25, "10Y": 60, "30Y": 100}}}}),
    ("Credit spread widening", "hypothetical", "Corporate spreads: investment grade +75bp, high yield +250bp. Sovereign bonds are not shocked.", {"spreads": {"IG": 75, "HY": 250}}),
    ("Equity sell-off -25% (Tech -35%)", "hypothetical", "All equities and ETFs -25%, Technology sector -35%.", {"equity": {"all": -0.25, "by_sector": {"Technology": -0.35}}}),
    ("USD -10% vs EUR", "hypothetical", "USD loses 10% of its value in EUR.", {"fx": {"USD": -0.10}}),
    (
        "Combined risk-off",
        "hypothetical",
        "Stylised hypothetical risk-off: equities -20%, IG +100bp, HY +300bp, govt curves -50bp, USD/CHF +5%, JPY +8% vs EUR. Not a reconstruction of any historical crisis.",
        {"equity": {"all": -0.20}, "spreads": {"IG": 100, "HY": 300}, "rates": {"EUR": {"parallel_bp": -50}, "USD": {"parallel_bp": -50}}, "fx": {"USD": 0.05, "CHF": 0.05, "JPY": 0.08}},
    ),
    (
        "Replay: dataset stress window (2025-03-21 to 2025-05-02)",
        "historical",
        "Replays the cumulative factor moves recorded in the selected dataset over this window. On the synthetic dataset this is a synthetic episode, not a real crisis.",
        {"start": "2025-03-21", "end": "2025-05-02"},
    ),
]


def bootstrap(db: Session) -> None:
    from ..data import synthetic

    if db.get(DatasetRow, synthetic.DATASET_INFO["id"]) is None:
        levels, meta = synthetic.generate()
        save_dataset(db, synthetic.DATASET_INFO["id"], synthetic.DATASET_INFO, levels, meta)
    if db.scalar(select(PortfolioRow).where(PortfolioRow.provenance == "SYNTHETIC")) is None:
        _, levels = get_dataset(db, synthetic.DATASET_INFO["id"])
        save_portfolio(db, demo.build(levels), "SYNTHETIC", "demo_portfolio.csv", pid="demo")
    if db.scalar(select(ScenarioRow).where(ScenarioRow.is_builtin.is_(True))) is None:
        for name, kind, desc, d in BUILTIN_SCENARIOS:
            db.add(ScenarioRow(name=name, kind=kind, description=desc, definition=d, is_builtin=True))
    if db.scalar(select(WatchlistRow)) is None:
        db.add(WatchlistRow(name="Portfolio drivers", factors=["EQ:SXEU", "EQ:SXUS", "IR:EUR:10Y", "IR:USD:10Y", "CS:EUR:IG", "CS:EUR:HY", "FX:USD", "FX:GBP"]))
        db.add(WatchlistRow(name="Rates", factors=["IR:EUR:2Y", "IR:EUR:10Y", "IR:EUR:30Y", "IR:USD:2Y", "IR:USD:10Y"]))
    if db.scalar(select(AlertRuleRow)) is None:
        db.add(AlertRuleRow(name="Euro equity ETF daily move", factor="EQ:SXEU", rule_type="change", direction="abs", threshold=0.03, lookback=1))
        db.add(AlertRuleRow(name="EUR 10Y above 3%", factor="IR:EUR:10Y", rule_type="level", direction="above", threshold=0.03, lookback=1))
        db.add(AlertRuleRow(name="EUR HY spread +50bp in 20 days", factor="CS:EUR:HY", rule_type="change", direction="above", threshold=0.005, lookback=20))
        db.add(AlertRuleRow(name="USD unusual daily move", factor="FX:USD", rule_type="zscore", direction="abs", threshold=3.0, lookback=1))
    db.commit()
