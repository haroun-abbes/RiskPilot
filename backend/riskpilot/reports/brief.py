"""Decision Brief: reproducible risk summary built only from engine outputs.

The commentary is produced by deterministic rules over computed figures
(no language model): every sentence references a number already computed.
"""
from __future__ import annotations

import csv
import io
import zipfile
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from ..services import analytics as an

NAVY = colors.HexColor("#14213D")
GREY = colors.HexColor("#5B6475")
LINE = colors.HexColor("#D9DEE7")
RED = colors.HexColor("#B42318")


def eur(x, d=0):
    return "n/a" if x is None else f"{x:,.{d}f} EUR".replace(",", " ")


def keur(x):
    return "n/a" if x is None else f"{x / 1000:,.1f}k".replace(",", " ")


def pct(x, d=1):
    return "n/a" if x is None else f"{x * 100:.{d}f}%"


def build(ctx: an.Context, window: int, alpha: float, horizon: int, scenarios: list[dict], alerts: list[dict]) -> dict:
    expo = an.exposures(ctx)
    risk = an.risk_summary(ctx, window, alpha, horizon)
    attr = an.attribution(ctx, window, alpha, horizon)
    stress = an.stress(ctx, scenarios) if scenarios else None
    findings, follow_up = [], []
    h, p = risk["historical"], risk["parametric"]
    pv = risk["portfolio_value"]
    if h.get("available"):
        findings.append(f"Historical {pct(alpha, 1)} {horizon}-day VaR is {eur(h['var'])} ({pct(h['var'] / pv, 2)} of the value in scope); ES is {eur(h['es'])}.")
    else:
        follow_up.append(f"Historical VaR/ES not produced: {h.get('reason')}")
    if p.get("available") and h.get("available"):
        ratio = h["var"] / p["var"] if p["var"] else None
        if ratio and ratio > 1.15:
            findings.append(f"Historical VaR exceeds delta-normal VaR by {pct(ratio - 1, 0)}; P&L excess kurtosis is {p['excess_kurtosis']:.2f}, so the normal model understates tail risk.")
    if attr.get("available") and attr["positions"]:
        top = attr["positions"][0]
        share = top["es"] / attr["totals"]["es"] if attr["totals"]["es"] else None
        findings.append(f"Largest ES contributor: {top['name']} ({eur(top['es'])}, {pct(share)} of ES).")
        if share and share > 0.25:
            follow_up.append(f"Concentration: {top['name']} alone explains {pct(share)} of ES.")
        hedges = [x for x in attr["positions"] if x["es"] < 0]
        if hedges:
            findings.append(f"{len(hedges)} position(s) reduce ES (negative contribution), led by {hedges[-1]['name']} ({eur(hedges[-1]['es'])}).")
    bt = risk.get("backtest")
    if bt:
        findings.append(f"Backtest (last {bt['n']} days, constant holdings): {bt['exceptions']} exceptions vs {bt['expected']:.1f} expected; Kupiec p-value {bt['kupiec_pvalue']:.2f}" + (f", Basel zone {bt['traffic_light']}." if bt["traffic_light"] else "."))
        if bt["kupiec_pvalue"] < 0.05:
            follow_up.append("VaR model rejected by the Kupiec test at 5%: review window length and method.")
    if stress:
        worst = min((r for r in stress["results"] if "total_pnl" in r), key=lambda r: r["total_pnl"], default=None)
        if worst:
            findings.append(f"Worst selected scenario: '{worst['name']}' with {eur(worst['total_pnl'])} ({pct(worst['total_pnl_pct'], 2)}).")
            if stress.get("reference") and -worst["total_pnl"] > stress["reference"]["es_10d"]:
                follow_up.append(f"Scenario '{worst['name']}' loss exceeds the 10-day historical ES ({eur(stress['reference']['es_10d'])}).")
    if risk["excluded"]:
        follow_up.append(f"{len(risk['excluded'])} position(s) excluded from risk measures (missing data); see limitations.")
    if ctx.drow.provenance == "SYNTHETIC":
        follow_up.append("All market data are SYNTHETIC: figures illustrate the methodology only.")
    if alerts:
        findings.append(f"{len(alerts)} alert(s) triggered in the last 20 observations of the dataset.")
    return {
        "meta": risk["meta"],
        "exposures": expo,
        "risk": {k: v for k, v in risk.items() if k not in ("pnl_series", "backcast")},
        "attribution": attr,
        "stress": stress,
        "alerts": alerts,
        "findings": findings,
        "follow_up": follow_up,
        "methodology": [
            "Historical simulation with full revaluation: today's positions revalued under each observed daily factor move in the window.",
            f"VaR = empirical {pct(alpha, 1)} quantile of losses; ES = average of the worst {pct(1 - alpha, 1)} of losses (Acerbi-Tasche estimator). Losses are positive numbers.",
            "Parametric VaR/ES: delta-normal, zero mean, sample covariance of linearised position P&L.",
            "ES contributions: exact decomposition by averaging each position's P&L over the tail scenarios. Parametric contributions: Euler allocation.",
            "Bonds: fixed-rate, regular coupons, yield from clean price (ICMA), yield change = interpolated government curve change + rating-bucket spread change.",
            "Multi-day figures are sqrt-time scaled 1-day figures." if horizon > 1 else "Horizon: 1 business day.",
        ],
        "limitations": risk["warnings"],
    }


def to_pdf(report: dict, title: str) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=16 * mm, title=title, author="RiskPilot")
    ss = getSampleStyleSheet()
    H1 = ParagraphStyle("h1", parent=ss["Heading1"], textColor=NAVY, fontSize=16, spaceAfter=2)
    H2 = ParagraphStyle("h2", parent=ss["Heading2"], textColor=NAVY, fontSize=11.5, spaceBefore=10, spaceAfter=4)
    B = ParagraphStyle("b", parent=ss["BodyText"], fontSize=8.8, leading=12, alignment=TA_LEFT)
    S = ParagraphStyle("s", parent=B, fontSize=7.6, textColor=GREY, leading=10)
    m = report["meta"]
    el = [Paragraph(title, H1)]
    banner = f"Portfolio <b>{m['portfolio']['name']}</b> as of {m['portfolio']['as_of']} &nbsp;|&nbsp; Dataset <b>{m['dataset']['name']}</b> ({m['dataset']['provenance_label']})"
    el.append(Paragraph(banner, S))
    el.append(Paragraph(f"Computed {m['computed_at']} UTC &nbsp;|&nbsp; engine v{m['engine_version']} &nbsp;|&nbsp; portfolio hash {m['portfolio']['hash']} &nbsp;|&nbsp; dataset hash {m['dataset']['hash']}", S))
    if m["dataset"]["provenance"] == "SYNTHETIC":
        el.append(Spacer(1, 4))
        el.append(Paragraph("<font color='#B42318'><b>SYNTHETIC DATA</b></font> - fictitious instruments and simulated market data. Not investment advice.", B))

    def table(data, widths, align_right_from=1, left_cols=()):
        t = Table(data, colWidths=widths, repeatRows=1)
        t.setStyle(TableStyle([
            ("FONT", (0, 0), (-1, -1), "Helvetica", 7.8),
            ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 7.8),
            ("TEXTCOLOR", (0, 0), (-1, 0), NAVY),
            ("LINEBELOW", (0, 0), (-1, 0), 0.8, NAVY),
            ("LINEBELOW", (0, 1), (-1, -1), 0.25, LINE),
            ("ALIGN", (align_right_from, 0), (-1, -1), "RIGHT"),
            ("TOPPADDING", (0, 0), (-1, -1), 2.5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
        ] + [("ALIGN", (c, 0), (c, -1), "LEFT") for c in left_cols]))
        return t

    p = m["params"]
    el.append(Paragraph("Key indicators", H2))
    r, t = report["risk"], report["exposures"]["totals"]
    h, pr = r["historical"], r["parametric"]
    hz = p["horizon_days"]
    rows = [["Indicator", "Value", "Method / reference"]]
    rows += [
        ["Net market value", eur(t["net"]), f"{t['n_positions']} positions, {t['n_excluded']} excluded from risk"],
        ["Gross exposure", eur(t["gross"]), "Sum of absolute market values"],
        [f"VaR {pct(p['confidence'], 1)}, {hz}d (historical)", eur(h.get("var")), f"{r['window']['n_obs']} obs. {r['window']['start']} to {r['window']['end']}"],
        [f"ES {pct(p['confidence'], 1)}, {hz}d (historical)", eur(h.get("es")), "Average of tail losses"],
        [f"VaR {pct(p['confidence'], 1)}, {hz}d (delta-normal)", eur(pr.get("var")), "Zero mean, sample covariance"],
        [f"ES {pct(p['confidence'], 1)}, {hz}d (delta-normal)", eur(pr.get("es")), "Normal ES"],
    ]
    fi = report["exposures"].get("fixed_income")
    if fi:
        rows += [["Bond modified duration", f"{fi['modified_duration']:.2f}", "MV-weighted"], ["Bond DV01", eur(fi["dv01"]), "P&L for +1bp on all yields (loss if positive)"]]
    el.append(table(rows, [62 * mm, 38 * mm, 74 * mm], left_cols=(2,)))

    el.append(Paragraph("Findings", H2))
    for f in report["findings"]:
        el.append(Paragraph("&bull; " + f, B))
    el.append(Paragraph("Points requiring further analysis", H2))
    for f in report["follow_up"] or ["None flagged by the rules."]:
        el.append(Paragraph("&bull; " + f, B))

    el.append(Paragraph("Main exposures (asset class)", H2))
    rows = [["Asset class", "Net", "Gross", "% gross"]]
    for g in report["exposures"]["groups"]["asset_class"]:
        rows.append([g["key"], eur(g["net"]), eur(g["gross"]), pct(g["pct_gross"])])
    el.append(table(rows, [60 * mm, 38 * mm, 38 * mm, 38 * mm]))

    a = report["attribution"]
    if a.get("available"):
        el.append(Paragraph("Top risk contributors (historical ES, exact decomposition)", H2))
        rows = [["Position", "Class", "Market value", "ES contrib.", "% of ES"]]
        for x in a["positions"][:10]:
            rows.append([x["name"][:38], x["asset_class"], eur(x["mv_base"]), eur(x["es"]), pct(x["es"] / a["totals"]["es"])])
        el.append(table(rows, [62 * mm, 26 * mm, 30 * mm, 30 * mm, 26 * mm], 2))
        rows = [["Risk factor class", "Delta-normal VaR contrib.", "Stand-alone hist. ES"]]
        for x in a["factor_classes"]:
            rows.append([x["class"], eur(x["var_param"]), eur(x["standalone_es_hist"])])
        el.append(Spacer(1, 4))
        el.append(table(rows, [60 * mm, 57 * mm, 57 * mm]))

    s = report.get("stress")
    if s:
        el.append(Paragraph("Stress scenarios (instantaneous revaluation)", H2))
        rows = [["Scenario", "Type", "P&L (kEUR)", "% value", "Equity", "Rates", "Spreads", "FX"]]
        for x in s["results"]:
            if "total_pnl" not in x:
                rows.append([Paragraph(x["name"], S), "", "error", "", "", "", "", ""])
                continue
            bc = x["by_class"]
            rows.append([Paragraph(x["name"], S), x["kind"], keur(x["total_pnl"]), pct(x["total_pnl_pct"], 2), keur(bc["equity"]), keur(bc["rates"]), keur(bc["spreads"]), keur(bc["fx"])])
        el.append(table(rows, [52 * mm, 20 * mm, 20 * mm, 15 * mm, 17 * mm, 17 * mm, 17 * mm, 16 * mm], 2))
        el.append(Paragraph("Factor-class columns shock one class at a time; the difference to the total is the cross (interaction) effect.", S))
        if s.get("reference"):
            el.append(Paragraph(f"Reference: {s['reference']['label']} = {eur(s['reference']['es_10d'])}.", S))

    if report["alerts"]:
        el.append(Paragraph("Recent alerts (deterministic rules)", H2))
        rows = [["Date", "Alert"]] + [[x["date"], Paragraph(x["message"], S)] for x in report["alerts"][:12]]
        el.append(table(rows, [24 * mm, 150 * mm], 9))

    el.append(KeepTogether([Paragraph("Methodology", H2)] + [Paragraph("&bull; " + x, S) for x in report["methodology"]]))
    el.append(Paragraph("Data limitations", H2))
    for x in report["limitations"] or ["No limitation flagged."]:
        el.append(Paragraph("&bull; " + x, S))
    el.append(Spacer(1, 6))
    el.append(Paragraph("RiskPilot is an analysis and simulation tool. It does not execute orders and does not provide investment recommendations. VaR is not a maximum loss.", S))

    def footer(canvas, d):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(GREY)
        canvas.drawString(18 * mm, 9 * mm, f"RiskPilot Decision Brief - {m['portfolio']['name']}")
        canvas.drawRightString(A4[0] - 18 * mm, 9 * mm, f"Page {d.page}")
        canvas.restoreState()

    doc.build(el, onFirstPage=footer, onLaterPages=footer)
    return buf.getvalue()


def to_csv_zip(report: dict) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        def put(name, rows, fields):
            s = io.StringIO()
            w = csv.DictWriter(s, fieldnames=fields, extrasaction="ignore")
            w.writeheader()
            for r in rows:
                w.writerow(r)
            z.writestr(name, s.getvalue())

        m = report["meta"]
        z.writestr("README.txt", f"RiskPilot Decision Brief export\ncomputed_at={m['computed_at']}\nengine={m['engine_version']}\nparams={m['params']}\nportfolio={m['portfolio']}\ndataset={m['dataset']}\nUnits: EUR. Losses (VaR/ES) are positive numbers.\n")
        put("positions.csv", report["exposures"]["positions"], ["id", "instrument_type", "asset_class", "name", "currency", "fx_rate", "mv_local", "mv_base", "ytm", "modified_duration", "convexity", "dv01_base", "included_in_risk", "excluded"])
        if report["attribution"].get("available"):
            put("risk_contributions.csv", report["attribution"]["positions"], ["id", "name", "asset_class", "currency", "mv_base", "es", "var_param", "standalone_var_param"])
            put("factor_contributions.csv", report["attribution"]["factors"], ["factor", "class", "var_param", "standalone_var_param"])
        put("sensitivities.csv", report["exposures"]["sensitivities"], ["factor", "factor_class", "sensitivity", "unit"])
        if report.get("stress"):
            rows = []
            for r in report["stress"]["results"]:
                if "total_pnl" in r:
                    rows.append({"scenario": r["name"], "kind": r["kind"], "total_pnl": r["total_pnl"], "total_pnl_pct": r["total_pnl_pct"], **{f"pnl_{k}": v for k, v in r["by_class"].items()}, "interaction": r["interaction"]})
            put("stress_results.csv", rows, ["scenario", "kind", "total_pnl", "total_pnl_pct", "pnl_equity", "pnl_rates", "pnl_spreads", "pnl_fx", "interaction"])
    return out.getvalue()


def default_title(name: str, when: datetime) -> str:
    return f"Decision Brief - {name} - {when:%Y-%m-%d}"
