"""(De)serialisation of positions to JSON-compatible dicts and to template rows."""
from __future__ import annotations

from dataclasses import asdict
from datetime import date

from ..quant.instruments import EquityPosition, FixedBondPosition, FxCashPosition, Position


def to_dict(p: Position) -> dict:
    d = asdict(p)
    if isinstance(p, FixedBondPosition):
        d["maturity"] = p.maturity.isoformat()
    return d


def from_dict(d: dict) -> Position:
    t = d["instrument_type"]
    if t in ("EQUITY", "ETF"):
        return EquityPosition(**d)
    if t == "BOND_FIXED":
        d = dict(d)
        d["maturity"] = date.fromisoformat(d["maturity"])
        return FixedBondPosition(**d)
    if t == "FX_CASH":
        return FxCashPosition(**d)
    raise ValueError(f"Unknown instrument type {t}")


TEMPLATE_COLUMNS = [
    "id", "instrument_type", "ticker", "name", "quantity", "price", "nominal", "clean_price",
    "coupon_rate", "frequency", "maturity", "daycount", "currency", "amount", "sector",
    "issuer", "country", "rating", "is_sovereign", "risk_proxy",
]


def to_template_row(p: Position) -> dict:
    d = to_dict(p)
    row = {c: "" for c in TEMPLATE_COLUMNS}
    for k, v in d.items():
        if k in row and v is not None:
            row[k] = v
    if isinstance(p, FixedBondPosition):
        row["coupon_rate"] = round(p.coupon_rate * 100, 6)
        row["is_sovereign"] = "TRUE" if p.is_sovereign else "FALSE"
    else:
        row["is_sovereign"] = ""
    return row
