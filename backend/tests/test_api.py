"""End-to-end API journeys (import -> risk -> stress -> bonds -> report)."""
import io

import httpx
import pytest

DS = "synthetic-demo-v1"


def test_health_and_bootstrap(client):
    assert client.get("/api/health").json()["status"] == "ok"
    ds = client.get("/api/datasets").json()
    assert ds[0]["id"] == DS and ds[0]["provenance"] == "SYNTHETIC"
    pfs = client.get("/api/portfolios").json()
    assert any(p["id"] == "demo" for p in pfs)


def test_risk_summary_demo(client):
    r = client.post("/api/risk/summary", json={"portfolio_id": "demo", "dataset_id": DS, "window": 500, "confidence": 0.99, "horizon_days": 10})
    assert r.status_code == 200
    j = r.json()
    h = j["historical"]
    assert h["available"] and h["es"] >= h["var"] > 0
    assert h["var"] == pytest.approx(h["var_1d"] * 10**0.5)
    assert sum(p["component_es"] for p in j["positions"]) == pytest.approx(h["es"], rel=1e-9)
    assert j["meta"]["dataset"]["provenance"] == "SYNTHETIC"
    assert any("sqrt(10)" in w for w in j["warnings"])
    assert j["backtest"]["n"] == 250


def test_risk_insufficient_window(client):
    r = client.post("/api/risk/summary", json={"portfolio_id": "demo", "dataset_id": DS, "window": 60, "confidence": 0.99, "horizon_days": 1})
    j = r.json()
    assert j["historical"]["available"] is False and "insufficient" in j["historical"]["reason"]


def test_factor_stats_and_correlation(client):
    j = client.post("/api/risk/factors", json={"portfolio_id": "demo", "dataset_id": DS, "window": 500}).json()
    assert j["covariance_check"]["symmetric"]
    n = len(j["labels"])
    assert len(j["correlation"]) == n and all(abs(j["correlation"][i][i] - 1) < 1e-12 for i in range(n))


def test_exposures(client):
    j = client.get(f"/api/portfolios/demo/exposures?dataset_id={DS}").json()
    t = j["totals"]
    assert t["gross"] >= abs(t["net"]) and t["short"] < 0
    assert sum(g["net"] for g in j["groups"]["asset_class"]) == pytest.approx(t["net"])
    assert j["fixed_income"]["dv01"] > 0


def _import(client, content: bytes, filename: str, as_of="2026-10-14"):
    r = client.post("/api/portfolios/import/preview", files={"file": (filename, content)})
    return r


def test_import_roundtrip_csv_and_xlsx(client):
    for fmt in ("csv", "xlsx"):
        raw = client.get(f"/api/templates/portfolio.{fmt}").content
        r = _import(client, raw, f"demo.{fmt}")
        assert r.status_code == 200, r.text
        pv = r.json()
        assert pv["suggested_mapping"]["coupon_rate"] == "coupon_rate"
        body = {"session_id": pv["session_id"], "mapping": pv["suggested_mapping"], "as_of": "2026-10-14", "name": f"Reimport {fmt}"}
        v = client.post("/api/portfolios/import/validate", json=body).json()
        assert v["errors"] == 0 and v["can_commit"], v["issues"]
        c = client.post("/api/portfolios/import/commit", json=body)
        assert c.status_code == 200
        pid = c.json()["id"]
        a = client.post("/api/risk/summary", json={"portfolio_id": pid, "dataset_id": DS}).json()
        b = client.post("/api/risk/summary", json={"portfolio_id": "demo", "dataset_id": DS}).json()
        assert a["historical"]["var"] == pytest.approx(b["historical"]["var"], rel=1e-6)


def test_import_invalid_rows(client):
    csv_bad = (
        "id,instrument_type,ticker,quantity,price,currency,nominal,clean_price,coupon_rate,frequency,maturity\n"
        "A,EQUITY,NRDB,100,10,EUR,,,,,\n"
        "A,EQUITY,HELX,100,-5,EUR,,,,,\n"
        "B,BOND_FIXED,,,,EUR,1000,99,3.5,3,2030-01-01\n"
        "C,BOND_FLOAT,,,,EUR,1000,99,,,2030-01-01\n"
        "D,EQUITY,ORBS,abc,10,XXX,,,,,\n"
        "E,BOND_FIXED,,,,EUR,1000,99,3.5,1,2020-01-01\n"
    ).encode()
    pv = _import(client, csv_bad, "bad.csv").json()
    v = client.post("/api/portfolios/import/validate", json={"session_id": pv["session_id"], "mapping": pv["suggested_mapping"], "as_of": "2026-10-14", "name": "bad"}).json()
    msgs = " | ".join(i["message"] for i in v["issues"])
    assert "Duplicate id" in msgs
    assert "strictly positive" in msgs
    assert "Frequency must be" in msgs
    assert "Floating-rate" in msgs
    assert "not a number" in msgs and "Unknown or unsupported currency" in msgs
    assert "not after the valuation date" in msgs
    assert not v["can_commit"]
    c = client.post("/api/portfolios/import/commit", json={"session_id": pv["session_id"], "mapping": pv["suggested_mapping"], "as_of": "2026-10-14", "name": "bad"})
    assert c.status_code == 422


@pytest.mark.parametrize("name,content,expect", [
    ("x.csv", b"", "empty"),
    ("x.pdf", b"%PDF-1.4", "Unsupported file type"),
    ("x.xlsx", b"not a zip", "Not a valid .xlsx"),
    ("x.csv", b"id,id\n1,2\n", "Duplicate column"),
    ("x.csv", b"id,type\n", "at least one position"),
    ("x.csv", b"\x00\x01\x02binary", "Binary"),
])
def test_import_malformed_files(client, name, content, expect):
    r = _import(client, content, name)
    assert r.status_code == 422 and expect in r.json()["detail"]


def test_unmapped_required_field(client):
    pv = _import(client, b"id,instrument_type,ticker,quantity,price,currency\nA,EQUITY,NRDB,1,1,EUR\n", "m.csv").json()
    m = dict(pv["suggested_mapping"])
    m["price"] = None
    v = client.post("/api/portfolios/import/validate", json={"session_id": pv["session_id"], "mapping": m, "as_of": "2026-10-14", "name": "m"}).json()
    assert v["errors"] == 1 and "no column is mapped" in v["issues"][0]["message"]


def test_scenarios_crud_and_stress(client):
    scs = client.get("/api/scenarios").json()
    builtin = scs[0]
    assert builtin["is_builtin"]
    assert client.put(f"/api/scenarios/{builtin['id']}", json={"name": "x", "kind": "hypothetical", "definition": {}}).status_code == 409
    dup = client.post(f"/api/scenarios/{builtin['id']}/duplicate").json()
    upd = client.put(f"/api/scenarios/{dup['id']}", json={"name": "Rates +200", "kind": "hypothetical", "definition": {"rates": {"EUR": {"parallel_bp": 200}}}})
    assert upd.status_code == 200
    bad = client.post("/api/scenarios", json={"name": "bad", "kind": "historical", "definition": {"start": "2025-05-01", "end": "2025-01-01"}})
    assert bad.status_code == 422
    hist = next(s for s in scs if s["kind"] == "historical")
    r = client.post("/api/stress/run", json={"portfolio_id": "demo", "dataset_id": DS, "scenario_ids": [dup["id"], hist["id"]]}).json()
    rates = r["results"][0]
    assert rates["total_pnl"] < 0 and rates["by_class"]["equity"] == 0
    assert sum(rates["by_class"].values()) + rates["interaction"] == pytest.approx(rates["total_pnl"])
    assert "Replay" in r["results"][1]["provenance_note"]
    assert r["reference"]["es_10d"] > 0
    assert client.delete(f"/api/scenarios/{dup['id']}").status_code == 200


def test_bond_endpoints(client):
    r = client.post("/api/bonds/analytics", json={"maturity": "2036-06-15", "coupon_pct": 5, "frequency": 1, "daycount": "30E/360", "settlement": "2026-06-15", "ytm_pct": 6, "currency": "EUR", "dataset_id": DS}).json()
    assert r["analytics"]["clean_price"] == pytest.approx(92.6399, abs=1e-4)
    assert r["spread"]["kind"].startswith("G-spread")
    assert len(r["cash_flows"]) == 10
    both = client.post("/api/bonds/analytics", json={"maturity": "2036-06-15", "coupon_pct": 5, "settlement": "2026-06-15", "ytm_pct": 6, "clean_price": 90})
    assert both.status_code == 422
    bad_dc = client.post("/api/bonds/analytics", json={"maturity": "2036-06-15", "coupon_pct": 5, "settlement": "2026-06-15", "ytm_pct": 6, "daycount": "BUS/252"})
    assert bad_dc.status_code == 422
    pb = client.get(f"/api/portfolios/demo/bonds?dataset_id={DS}").json()
    sov = next(b for b in pb["bonds"] if b["id"] == "BD-EUGOV-31")
    assert sov["spread"]["spread_bp"] == pytest.approx(10, abs=0.5)  # demo built with +10bp


def test_attribution_and_compare(client):
    a = client.post("/api/attribution", json={"portfolio_id": "demo", "dataset_id": DS}).json()
    assert sum(p["es"] for p in a["positions"]) == pytest.approx(a["totals"]["es"])
    assert sum(f["var_param"] for f in a["factors"]) == pytest.approx(a["totals"]["var_param"])
    for g in a["groups"].values():
        assert sum(x["es"] for x in g) == pytest.approx(a["totals"]["es"])
    c = client.post("/api/attribution/compare", json={"portfolio_a": "demo", "portfolio_b": "demo", "dataset_id": DS}).json()
    assert c["a"]["risk"]["historical"]["var"] == c["b"]["risk"]["historical"]["var"]


def test_market_watch_and_alerts(client):
    s = client.get(f"/api/datasets/{DS}/series?factors=EQ:SXEU,IR:EUR:10Y").json()
    assert s["series"]["IR:EUR:10Y"]["change_kind"] == "absolute"
    assert client.get(f"/api/datasets/{DS}/series?factors=EQ:NOPE").status_code == 404
    rule = client.post("/api/alerts/rules", json={"name": "t", "factor": "EQ:SXEU", "rule_type": "level", "direction": "above", "threshold": 1e9}).json()
    ev = client.post(f"/api/alerts/evaluate?dataset_id={DS}").json()
    assert all(e["rule_id"] != rule["id"] for e in ev["events"])
    assert ev["n_events"] > 0
    assert len(client.get(f"/api/alerts/events?dataset_id={DS}&limit=5000").json()) == ev["n_events"]
    wl = client.post("/api/watchlists", json={"name": "w", "factors": ["FX:USD"]}).json()
    assert client.delete(f"/api/watchlists/{wl['id']}").status_code == 200


def test_quality_and_market_upload(client):
    q = client.get(f"/api/datasets/{DS}/quality").json()
    assert q["n_factors"] == 32 and q["issue_counts"]["error"] == 0
    good = b"date,EQ:TEST,IR:EUR:10Y\n2026-01-02,10,0.025\n2026-01-05,10.5,0.026\n2026-01-06,10.2,0.0255\n"
    r = client.post("/api/datasets/upload", files={"file": ("m.csv", good)}, data={"name": "t", "provenance": "HISTORICAL_REAL", "source": "unit test"})
    assert r.status_code == 200 and r.json()["provenance"] == "HISTORICAL_REAL"
    pct = b"date,IR:EUR:10Y\n2026-01-02,2.5\n2026-01-05,2.6\n"
    r = client.post("/api/datasets/upload", files={"file": ("m.csv", pct)}, data={"name": "t", "provenance": "HISTORICAL_REAL", "source": "x"})
    assert r.status_code == 422 and "percent" in str(r.json())
    bad = b"date,PRICE_X\n2026-01-02,1\n"
    assert client.post("/api/datasets/upload", files={"file": ("m.csv", bad)}, data={"name": "t", "provenance": "SYNTHETIC", "source": "x"}).status_code == 422


def test_report_pdf_csv_reproducible(client):
    scs = [s["id"] for s in client.get("/api/scenarios").json()[:3]]
    body = {"portfolio_id": "demo", "dataset_id": DS, "scenario_ids": scs}
    r1 = client.post("/api/reports", json=body).json()
    r2 = client.post("/api/reports", json=body).json()
    assert r1["report"]["risk"]["historical"] == r2["report"]["risk"]["historical"]
    assert r1["report"]["findings"]
    pdf = client.get(f"/api/reports/{r1['id']}/pdf")
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"
    z = client.get(f"/api/reports/{r1['id']}/csv")
    import zipfile
    names = zipfile.ZipFile(io.BytesIO(z.content)).namelist()
    assert "positions.csv" in names and "stress_results.csv" in names


def test_ecb_parser_and_failure_reporting(monkeypatch):
    """Parsing is tested on a hand-written fixture in the documented SDMX-CSV
    layout (not a recorded live response). Failures must surface, never succeed."""
    from riskpilot.data import ecb

    csv_text = "KEY,FREQ,TIME_PERIOD,OBS_VALUE\nEXR.D.USD.EUR.SP00.A,D,2026-10-12,1.10\nEXR.D.USD.EUR.SP00.A,D,2026-10-13,1.08\n"

    def handler(req):
        if "EXR" in str(req.url):
            return httpx.Response(200, text=csv_text)
        return httpx.Response(200, text="KEY,TIME_PERIOD,OBS_VALUE\nYC,2026-10-13,2.5\n")

    df, _ = ecb.fetch(__import__("datetime").date(2026, 10, 1), httpx.Client(transport=httpx.MockTransport(handler)))
    assert df["FX:USD"].iloc[-1] == pytest.approx(1 / 1.08)
    assert df["IR:EUR:10Y"].iloc[-1] == pytest.approx(0.025)
    fail = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(503)))
    assert ecb.test_connection(fail)["ok"] is False
    with pytest.raises(ecb.ProviderError):
        ecb.fetch(__import__("datetime").date(2026, 10, 1), fail)
