"""Position models. Each instrument type has its own schema (no one-size-fits-all)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Literal, Union

InstrumentType = Literal["EQUITY", "ETF", "BOND_FIXED", "FX_CASH"]
SUPPORTED_TYPES = ("EQUITY", "ETF", "BOND_FIXED", "FX_CASH")
UNSUPPORTED_TYPES_MESSAGES = {
    "BOND_FLOAT": "Floating-rate notes need a forward curve and fixing history; not valued by this engine.",
    "FRN": "Floating-rate notes need a forward curve and fixing history; not valued by this engine.",
    "OPTION": "Options require a volatility surface and an option pricer; not supported.",
    "FUTURE": "Futures are not supported in this version.",
    "SWAP": "Swaps are not supported in this version.",
    "CDS": "CDS are not supported in this version.",
}

IG_RATINGS = {
    "AAA", "AA+", "AA", "AA-", "A+", "A", "A-", "BBB+", "BBB", "BBB-",
}
HY_RATINGS = {
    "BB+", "BB", "BB-", "B+", "B", "B-", "CCC+", "CCC", "CCC-", "CC", "C", "D",
}


def rating_bucket(rating: str | None) -> str | None:
    if not rating:
        return None
    r = rating.strip().upper()
    if r in IG_RATINGS:
        return "IG"
    if r in HY_RATINGS:
        return "HY"
    return None


@dataclass
class EquityPosition:
    id: str
    ticker: str
    quantity: float
    price: float  # local currency per share
    currency: str
    instrument_type: Literal["EQUITY", "ETF"] = "EQUITY"
    name: str | None = None
    sector: str | None = None
    issuer: str | None = None
    country: str | None = None
    risk_proxy: str | None = None  # ticker of a proxy series if no own history


@dataclass
class FixedBondPosition:
    id: str
    nominal: float  # face amount in local currency (negative = short)
    clean_price: float  # % of par
    coupon_rate: float  # decimal
    frequency: int
    maturity: date
    currency: str
    daycount: str = "ACT/ACT ICMA"
    instrument_type: Literal["BOND_FIXED"] = "BOND_FIXED"
    name: str | None = None
    issuer: str | None = None
    rating: str | None = None
    sector: str | None = None
    country: str | None = None
    is_sovereign: bool = False


@dataclass
class FxCashPosition:
    id: str
    currency: str
    amount: float  # in ``currency``
    instrument_type: Literal["FX_CASH"] = "FX_CASH"
    name: str | None = None


Position = Union[EquityPosition, FixedBondPosition, FxCashPosition]


@dataclass
class Portfolio:
    name: str
    base_currency: str
    as_of: date
    positions: list[Position] = field(default_factory=list)
