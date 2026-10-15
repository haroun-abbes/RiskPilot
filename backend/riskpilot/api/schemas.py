from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class RiskParams(BaseModel):
    portfolio_id: str
    dataset_id: str
    window: int = Field(500, ge=50, le=5000)
    confidence: float = Field(0.99, gt=0.5, lt=1.0)
    horizon_days: int = Field(1, ge=1, le=250)


class MappingRequest(BaseModel):
    session_id: str
    mapping: dict[str, str | None]
    as_of: date
    name: str = Field(..., min_length=1, max_length=200)


class EquityShocks(BaseModel):
    all: float = 0.0
    by_sector: dict[str, float] = {}
    by_country: dict[str, float] = {}
    by_ticker: dict[str, float] = {}


class CurveShock(BaseModel):
    parallel_bp: float = 0.0
    tenor_bp: dict[str, float] = {}


class HypotheticalDefinition(BaseModel):
    equity: EquityShocks = EquityShocks()
    rates: dict[str, CurveShock] = {}
    spreads: dict[Literal["IG", "HY"], float] = {}
    fx: dict[str, float] = {}

    @field_validator("fx")
    @classmethod
    def fx_bounds(cls, v):
        for k, x in v.items():
            if not -0.9 < x < 5:
                raise ValueError(f"FX shock for {k} must be a decimal return in (-0.9, 5)")
        return v


class HistoricalDefinition(BaseModel):
    start: date
    end: date

    @field_validator("end")
    @classmethod
    def order(cls, v, info):
        if "start" in info.data and v <= info.data["start"]:
            raise ValueError("end must be after start")
        return v


class ScenarioIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    kind: Literal["hypothetical", "historical"]
    description: str = ""
    definition: dict

    def validated_definition(self) -> dict:
        if self.kind == "hypothetical":
            d = HypotheticalDefinition.model_validate(self.definition)
            return d.model_dump()
        d = HistoricalDefinition.model_validate(self.definition)
        return {"start": d.start.isoformat(), "end": d.end.isoformat()}


class StressRequest(BaseModel):
    portfolio_id: str
    dataset_id: str
    scenario_ids: list[str] = []
    adhoc: list[ScenarioIn] = []


class BondRequest(BaseModel):
    maturity: date
    coupon_pct: float = Field(..., ge=0, le=30)
    frequency: Literal[1, 2, 4, 12] = 1
    daycount: str = "ACT/ACT ICMA"
    settlement: date
    clean_price: float | None = Field(None, gt=0, lt=300)
    ytm_pct: float | None = Field(None, gt=-50, lt=100)
    currency: str | None = None
    dataset_id: str | None = None
    label: str | None = None


class BondCompareRequest(BaseModel):
    bonds: list[BondRequest] = Field(..., min_length=1, max_length=8)


class WatchlistIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    factors: list[str]


class AlertRuleIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    factor: str
    rule_type: Literal["level", "change", "zscore"]
    direction: Literal["above", "below", "abs"]
    threshold: float
    lookback: int = Field(1, ge=1, le=260)
    active: bool = True


class CompareRequest(BaseModel):
    portfolio_a: str
    portfolio_b: str
    dataset_id: str
    window: int = Field(500, ge=50, le=5000)
    confidence: float = Field(0.99, gt=0.5, lt=1.0)
    horizon_days: int = Field(1, ge=1, le=250)


class ReportRequest(BaseModel):
    portfolio_id: str
    dataset_id: str
    window: int = Field(500, ge=50, le=5000)
    confidence: float = Field(0.99, gt=0.5, lt=1.0)
    horizon_days: int = Field(1, ge=1, le=250)
    scenario_ids: list[str] = []
    title: str | None = None
