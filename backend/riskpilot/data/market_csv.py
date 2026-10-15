"""Import of user-supplied market history (CSV).

Accepted layouts
* wide : ``date,EQ:ABC,FX:USD,IR:EUR:10Y,...`` (one column per factor)
* long : ``date,factor,value``
Units: equity prices in local currency, FX as EUR per 1 unit of currency,
rates and spreads in **decimal** (0.025 = 2.5%).
"""
from __future__ import annotations

import io
import re

import pandas as pd

FACTOR_RE = re.compile(r"^(EQ:[A-Z0-9.\-_]{1,20}|FX:[A-Z]{3}|IR:[A-Z]{3}:\d+(\.\d+)?[MY]|CS:[A-Z]{3}:(IG|HY))$")
MAX_BYTES = 20 * 1024 * 1024


class MarketFileError(ValueError):
    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


def parse_market_csv(raw: bytes) -> pd.DataFrame:
    if len(raw) > MAX_BYTES:
        raise MarketFileError([f"File larger than {MAX_BYTES // 1024 // 1024} MB"])
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise MarketFileError(["File is not UTF-8 text"])
    try:
        df = pd.read_csv(io.StringIO(text), sep=None, engine="python")
    except Exception as e:
        raise MarketFileError([f"Unreadable CSV: {e}"])
    cols = [c.strip() for c in df.columns]
    df.columns = cols
    lower = [c.lower() for c in cols]
    if lower[:3] == ["date", "factor", "value"]:
        df = df.pivot_table(index="date", columns="factor", values="value", aggfunc="last")
        df = df.reset_index()
        cols = list(df.columns)
    if cols[0].lower() != "date":
        raise MarketFileError(["First column must be 'date'"])
    errors = []
    bad = [c for c in cols[1:] if not FACTOR_RE.match(str(c))]
    if bad:
        errors.append(f"Invalid factor id(s): {', '.join(map(str, bad[:10]))}. Expected EQ:TICKER, FX:CCY, IR:CCY:10Y, CS:CCY:IG|HY")
    dates = pd.to_datetime(df.iloc[:, 0], errors="coerce")
    if dates.isna().any():
        errors.append(f"{int(dates.isna().sum())} unparseable date(s) (use YYYY-MM-DD)")
    if dates.duplicated().any():
        errors.append(f"{int(dates.duplicated().sum())} duplicated date(s)")
    vals = df.iloc[:, 1:].apply(pd.to_numeric, errors="coerce")
    nonnum = int((vals.isna() & df.iloc[:, 1:].notna()).sum().sum())
    if nonnum:
        errors.append(f"{nonnum} non-numeric value(s)")
    if errors:
        raise MarketFileError(errors)
    vals.index = dates
    vals.index.name = "date"
    vals = vals.sort_index()
    if len(vals) < 2:
        raise MarketFileError(["At least two dates are required"])
    return vals
