import numpy as np
import pandas as pd
import pytest

from riskpilot import alerts as al


def s(vals):
    return pd.Series(vals, index=pd.bdate_range("2026-01-01", periods=len(vals)), dtype=float)


def test_level_and_change_rules():
    x = s([100, 101, 97, 98, 105])
    assert [h["date"].isoformat() for h in al.evaluate(x, "EQ:X", "level", "above", 100, 1, "r")] == ["2026-01-02", "2026-01-07"]
    ch = al.evaluate(x, "EQ:X", "change", "abs", 0.03, 1, "r")
    assert len(ch) == 2 and ch[0]["value"] == pytest.approx(97 / 101 - 1)
    r = s([0.02, 0.021, 0.0265])
    hits = al.evaluate(r, "IR:EUR:10Y", "change", "above", 0.005, 2, "r")
    assert len(hits) == 1 and "+65.0 bp" in hits[0]["message"]


def test_zscore_uses_only_past_data():
    rng = np.random.default_rng(0)
    v = 100 * np.cumprod(1 + rng.normal(0, 0.01, 300))
    v[-1] = v[-2] * 1.08
    hits = al.evaluate(s(v), "EQ:X", "zscore", "abs", 4, 1, "r")
    assert hits[-1]["date"] == s(v).index[-1].date()
    assert hits[-1]["value"] > 6


def test_deterministic():
    x = s(np.linspace(1, 2, 50))
    assert al.evaluate(x, "FX:USD", "level", "below", 1.5, 1, "r") == al.evaluate(x.copy(), "FX:USD", "level", "below", 1.5, 1, "r")
    with pytest.raises(ValueError):
        al.evaluate(x, "FX:USD", "level", "sideways", 1.5, 1, "r")
