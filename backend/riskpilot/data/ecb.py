"""European Central Bank Data Portal connector (public SDMX REST API, no key).

Series used
* EXR  D.<CCY>.EUR.SP00.A  – euro foreign exchange reference rates, quoted as
  units of CCY per 1 EUR. Converted here to EUR per 1 CCY (``FX:<CCY>``).
  Published once per TARGET business day around 16:00 CET: reference rates,
  not tradable quotes and **not real time**.
* YC   B.U2.EUR.4F.G_N_A.SV_C_YM.SR_<T> – euro area AAA government bond spot
  (zero-coupon) yield curve, Svensson model, in percent. Converted to decimal
  (``IR:EUR:<T>``). This is a zero curve, not par yields.

Terms: ECB statistics may be reused provided the source is cited
("Source: ECB Data Portal"). See https://www.ecb.europa.eu/stats/ecb_statistics/governance_and_quality_framework/html/usage_policy.en.html

The connector never fabricates data: any network or parsing failure is
raised and reported as a failed connection.
"""
from __future__ import annotations

import io
import os
from datetime import date

import httpx
import pandas as pd

BASE_URL = os.environ.get("ECB_BASE_URL", "https://data-api.ecb.europa.eu/service/data")
FX_CCYS = ("USD", "GBP", "CHF", "JPY")
YC_TENORS = ("3M", "1Y", "2Y", "5Y", "10Y", "30Y")
TIMEOUT = float(os.environ.get("ECB_TIMEOUT_S", "15"))

DATASET_INFO = {
    "provenance": "HISTORICAL_REAL",
    "source": "ECB Data Portal (EXR reference rates, YC AAA euro area spot curve)",
    "license_note": "Reuse permitted with source citation: 'Source: ECB Data Portal'.",
    "frequency": "Daily reference values (published ~16:00 CET, not real time)",
}


class ProviderError(RuntimeError):
    pass


def _series_url(flow: str, key: str, start: date) -> str:
    return f"{BASE_URL}/{flow}/{key}?startPeriod={start.isoformat()}&format=csvdata"


def parse_csvdata(text: str) -> pd.Series:
    df = pd.read_csv(io.StringIO(text))
    if "TIME_PERIOD" not in df.columns or "OBS_VALUE" not in df.columns:
        raise ProviderError("Unexpected ECB response: TIME_PERIOD/OBS_VALUE columns missing")
    s = pd.Series(pd.to_numeric(df["OBS_VALUE"], errors="coerce").values, index=pd.to_datetime(df["TIME_PERIOD"]))
    s = s[~s.index.duplicated()].sort_index().dropna()
    if s.empty:
        raise ProviderError("ECB returned no observations")
    return s


def fetch(start: date, client: httpx.Client | None = None) -> tuple[pd.DataFrame, dict]:
    own = client is None
    client = client or httpx.Client(timeout=TIMEOUT, headers={"Accept": "text/csv"})
    out, meta = {}, {}
    try:
        for c in FX_CCYS:
            r = client.get(_series_url("EXR", f"D.{c}.EUR.SP00.A", start))
            if r.status_code != 200:
                raise ProviderError(f"EXR {c}: HTTP {r.status_code}")
            s = parse_csvdata(r.text)
            out[f"FX:{c}"] = 1.0 / s
            meta[f"FX:{c}"] = {"name": f"ECB reference rate, EUR per 1 {c}", "class": "FX", "unit": f"EUR per {c}", "currency": c}
        for t in YC_TENORS:
            r = client.get(_series_url("YC", f"B.U2.EUR.4F.G_N_A.SV_C_YM.SR_{t}", start))
            if r.status_code != 200:
                raise ProviderError(f"YC {t}: HTTP {r.status_code}")
            out[f"IR:EUR:{t}"] = parse_csvdata(r.text) / 100.0
            meta[f"IR:EUR:{t}"] = {"name": f"Euro area AAA govt spot rate {t} (ECB)", "class": "IR", "unit": "decimal yield", "currency": "EUR"}
    except httpx.HTTPError as e:
        raise ProviderError(f"Network error contacting ECB Data Portal: {e}") from e
    finally:
        if own:
            client.close()
    df = pd.DataFrame(out).sort_index()
    df.index.name = "date"
    return df, meta


def test_connection(client: httpx.Client | None = None) -> dict:
    """One real request; returns {ok, detail}. Never reports success without data."""
    own = client is None
    client = client or httpx.Client(timeout=TIMEOUT)
    try:
        r = client.get(_series_url("EXR", "D.USD.EUR.SP00.A", date.today().replace(day=1)))
        if r.status_code != 200:
            return {"ok": False, "detail": f"HTTP {r.status_code}"}
        s = parse_csvdata(r.text)
        return {"ok": True, "detail": f"Latest EUR/USD reference rate observation: {s.index[-1].date()}"}
    except Exception as e:  # report any failure verbatim
        return {"ok": False, "detail": f"{type(e).__name__}: {e}"}
    finally:
        if own:
            client.close()
