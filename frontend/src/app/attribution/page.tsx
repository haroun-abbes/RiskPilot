"use client";
import { useState } from "react";
import { useGet, usePostQuery } from "@/lib/api";
import { riskBody, useCtx } from "@/lib/store";
import type { Attribution } from "@/lib/types";
import { compactEur, confLabel, eur, pct } from "@/lib/format";
import { ErrorBox, Loading, Metric, MethodButton, Notices, PageHeader, Panel, inputCls } from "@/components/ui";
import { axis, C, Chart } from "@/components/chart";
import type { PortfolioItem } from "@/components/shell";

const DIMS = [
  { value: "position", label: "Instrument" },
  { value: "asset_class", label: "Asset class" },
  { value: "issuer", label: "Issuer" },
  { value: "sector", label: "Sector" },
  { value: "currency", label: "Currency" },
  { value: "country", label: "Country" },
];

type Cmp = Record<"a" | "b", { exposures: { net: number; gross: number }; attribution: Attribution; risk: { historical: { var?: number; es?: number }; parametric: { var?: number }; portfolio_value: number; meta: { portfolio: { name: string; as_of: string } } } }>;

export default function AttributionPage() {
  const c = useCtx();
  const q = usePostQuery<Attribution>("/api/attribution", riskBody(c));
  const [dim, setDim] = useState("asset_class");
  const a = q.data;
  const hz = `${c.horizon}d`;
  const rows = a?.available
    ? dim === "position"
      ? a.positions.map((p) => ({ key: p.name, es: p.es, var_param: p.var_param, es_pct: p.es / a.totals.es, weight_gross: Math.abs(p.mv_base) / a.positions.reduce((s, x) => s + Math.abs(x.mv_base), 0), mv: p.mv_base }))
      : a.groups[dim]
    : [];
  return (
    <>
      <PageHeader title="Risk attribution" lead={`Where the risk comes from: exact decomposition of historical ES (${confLabel(c.confidence)}, ${hz}) and Euler decomposition of delta-normal VaR by instrument, group and risk factor.`} />
      {q.error && <ErrorBox error={q.error} onRetry={() => q.mutate()} />}
      {!a && !q.error && <Loading />}
      {a && !a.available && <ErrorBox error={new Error(a.reason ?? "Attribution unavailable")} />}
      {a?.available && (
        <div className="space-y-4">
          <Panel>
            <div className="grid grid-cols-2 gap-6 md:grid-cols-4">
              <Metric label={`Historical ES, ${hz}`} method="component_es" value={compactEur(a.totals.es)} emphasis />
              <Metric label={`Delta-normal VaR, ${hz}`} method="component_var" value={compactEur(a.totals.var_param)} />
              <Metric label="Sum of stand-alone ES by factor class" value={compactEur(a.totals.sum_standalone_es_by_class)} sub="Each class moving alone" />
              <Metric label="Diversification across classes" value={compactEur(a.totals.diversification_es)} sub={pct(a.totals.diversification_es / a.totals.sum_standalone_es_by_class, 1) + " of the stand-alone sum"} toneClass="text-gain" />
            </div>
          </Panel>
          <Notices items={a.warnings} />
          <div className="grid gap-4 xl:grid-cols-12">
            <Panel className="xl:col-span-7" title="Contribution to risk against market-value weight" aside={
              <select aria-label="Group by" className={inputCls} value={dim} onChange={(e) => setDim(e.target.value)}>{DIMS.map((d) => <option key={d.value} value={d.value}>{d.label}</option>)}</select>
            }>
              <Chart
                height={Math.max(240, rows.length * 30 + 60)}
                ariaLabel="Share of expected shortfall compared with share of gross market value for each group"
                option={{
                  tooltip: { trigger: "axis", axisPointer: { type: "shadow" }, valueFormatter: (v) => `${(v as number).toFixed(1)}%` },
                  legend: { top: 0, right: 0, textStyle: { fontSize: 11.5 } },
                  grid: { top: 30 },
                  xAxis: axis.value(undefined, (v) => `${v}%`),
                  yAxis: { type: "category", data: [...rows].reverse().map((r) => r.key), axisLabel: { width: 160, overflow: "truncate" }, axisTick: { show: false } },
                  series: [
                    { name: "Share of ES", type: "bar", data: [...rows].reverse().map((r) => ({ value: (r.es_pct ?? 0) * 100, itemStyle: { color: (r.es_pct ?? 0) < 0 ? C.gain : C.accent } })), barWidth: 9 },
                    { name: "Share of gross value", type: "bar", data: [...rows].reverse().map((r) => (r.weight_gross ?? 0) * 100), itemStyle: { color: "#c3cbd8" }, barWidth: 9 },
                  ],
                }}
              />
              <p className="mt-1 text-[12.5px] text-muted">A group whose blue bar exceeds its grey bar carries more risk than its size suggests. Negative ES shares are hedges.</p>
            </Panel>
            <Panel className="xl:col-span-5" title="Detail" pad={false}>
              <div className="max-h-[520px] overflow-auto">
                <table className="dense w-full">
                  <thead><tr><th>{DIMS.find((d) => d.value === dim)?.label}</th><th className="r">ES contrib.</th><th className="r">% ES</th><th className="r">Euler VaR</th></tr></thead>
                  <tbody>
                    {rows.map((r) => (
                      <tr key={r.key}><td>{r.key}</td><td className={`r ${r.es < 0 ? "text-gain" : ""}`}>{eur(r.es)}</td><td className="r">{pct(r.es_pct, 1)}</td><td className="r">{eur(r.var_param)}</td></tr>
                    ))}
                    <tr className="font-semibold"><td>Total</td><td className="r">{eur(rows.reduce((s, r) => s + r.es, 0))}</td><td className="r">100.0%</td><td className="r">{eur(rows.reduce((s, r) => s + r.var_param, 0))}</td></tr>
                  </tbody>
                </table>
              </div>
            </Panel>
          </div>
          <div className="grid gap-4 xl:grid-cols-12">
            <Panel className="xl:col-span-5" title="By risk factor class" pad={false}>
              <table className="dense w-full">
                <thead><tr><th>Class</th><th className="r">Euler VaR (delta-normal)</th><th className="r">Stand-alone hist. ES</th></tr></thead>
                <tbody>
                  {a.factor_classes.map((f) => <tr key={f.class}><td>{({ equity: "Equity", rates: "Rates", spreads: "Credit spreads", fx: "FX" } as Record<string, string>)[f.class] ?? f.class}</td><td className="r">{eur(f.var_param)}</td><td className="r">{eur(f.standalone_es_hist)}</td></tr>)}
                </tbody>
              </table>
              <p className="px-4 py-3 text-[12.5px] text-muted">Euler contributions add up to total delta-normal VaR. Stand-alone ES revalues the portfolio with only one class of factors moving; their sum exceeds total ES by the diversification benefit. An exact factor split of historical ES with full revaluation is not defined, because of cross effects.</p>
            </Panel>
            <Panel className="xl:col-span-7" title={<span className="flex items-center gap-2">By individual risk factor <MethodButton k="sensitivity" /></span>} pad={false}>
              <div className="max-h-[380px] overflow-auto">
                <table className="dense w-full">
                  <thead><tr><th>Factor</th><th className="r">Euler VaR</th><th className="r">Stand-alone VaR</th><th className="r">Sensitivity</th><th>Unit</th></tr></thead>
                  <tbody>
                    {a.factors.map((f) => {
                      const s = a.sensitivities.find((x) => x.factor === f.factor);
                      return <tr key={f.factor}><td>{f.factor}</td><td className={`r ${f.var_param < 0 ? "text-gain" : ""}`}>{eur(f.var_param)}</td><td className="r">{eur(f.standalone_var_param)}</td><td className="r">{eur(s?.sensitivity)}</td><td className="text-[11.5px] text-faint">{s?.unit.replace("EUR ", "")}</td></tr>;
                    })}
                  </tbody>
                </table>
              </div>
            </Panel>
          </div>
          <ComparePanel />
        </div>
      )}
    </>
  );
}

function ComparePanel() {
  const c = useCtx();
  const { data: pfs } = useGet<PortfolioItem[]>("/api/portfolios");
  const other = c.compareId && c.compareId !== c.portfolioId ? c.compareId : null;
  const q = usePostQuery<Cmp>(other ? "/api/attribution/compare" : null, { portfolio_a: c.portfolioId, portfolio_b: other, dataset_id: c.datasetId, window: c.window, confidence: c.confidence, horizon_days: c.horizon });
  const d = q.data;
  const classes = d ? Array.from(new Set([...d.a.attribution.groups.asset_class.map((g) => g.key), ...d.b.attribution.groups.asset_class.map((g) => g.key)])) : [];
  const g = (k: "a" | "b", key: string) => d?.[k].attribution.groups.asset_class.find((x) => x.key === key)?.es ?? 0;
  return (
    <Panel title="Compare with another portfolio or another date" aside={
      <select aria-label="Portfolio to compare" className={inputCls} value={other ?? ""} onChange={(e) => c.set({ compareId: e.target.value || null })}>
        <option value="">Choose a portfolio</option>
        {pfs?.filter((p) => p.id !== c.portfolioId).map((p) => <option key={p.id} value={p.id}>{p.name} ({p.as_of})</option>)}
      </select>
    }>
      {!other && <p className="text-[13px] text-muted">Import a second portfolio (another book, or the same book at another date) to compare risk levels and their decomposition on the same market data and parameters.</p>}
      {q.error && <ErrorBox error={q.error} />}
      {other && !d && !q.error && <Loading />}
      {d && (
        <div className="overflow-auto">
          <table className="dense w-full min-w-[640px]">
            <thead><tr><th>Measure</th><th className="r">{d.a.risk.meta.portfolio.name} ({d.a.risk.meta.portfolio.as_of})</th><th className="r">{d.b.risk.meta.portfolio.name} ({d.b.risk.meta.portfolio.as_of})</th><th className="r">Difference</th></tr></thead>
            <tbody>
              {[
                ["Net market value", d.a.exposures.net, d.b.exposures.net],
                ["Historical VaR", d.a.risk.historical.var, d.b.risk.historical.var],
                ["Historical ES", d.a.risk.historical.es, d.b.risk.historical.es],
                ["Delta-normal VaR", d.a.risk.parametric.var, d.b.risk.parametric.var],
                ...classes.map((k) => [`ES contribution: ${k}`, g("a", k), g("b", k)]),
              ].map(([l, x, y]) => (
                <tr key={l as string}><td>{l as string}</td><td className="r">{eur(x as number)}</td><td className="r">{eur(y as number)}</td><td className="r">{eur((y as number) - (x as number))}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  );
}
