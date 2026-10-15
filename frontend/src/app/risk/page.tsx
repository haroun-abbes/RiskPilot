"use client";
import { usePostQuery } from "@/lib/api";
import { riskBody, useCtx } from "@/lib/store";
import type { RiskSummary } from "@/lib/types";
import { compactEur, confLabel, eur, num, pct } from "@/lib/format";
import { Badge, ErrorBox, Loading, MethodButton, Notices, PageHeader, Panel } from "@/components/ui";
import { BacktestChart, DistributionChart } from "@/components/risk-charts";
import { C, Chart } from "@/components/chart";

type Factors = { factors: { factor: string; name: string; class: string; vol: number | null; ewma_vol: number | null; unit: string; n_obs: number }[]; labels: string[]; correlation: (number | null)[][] | null; covariance_check: { symmetric: boolean; min_eigenvalue: number } | null; n_obs: number };

function Row({ label, hist, param, method }: { label: string; hist?: number; param?: number; method?: string }) {
  return (
    <tr>
      <td><span className="flex items-center gap-2">{label}{method && <MethodButton k={method} />}</span></td>
      <td className="r text-[15px] font-semibold text-ink">{eur(hist)}</td>
      <td className="r text-[15px]">{eur(param)}</td>
    </tr>
  );
}

export default function RiskPage() {
  const c = useCtx();
  const body = riskBody(c);
  const q = usePostQuery<RiskSummary>("/api/risk/summary", body);
  const f = usePostQuery<Factors>("/api/risk/factors", body);
  const r = q.data;
  const h = r?.historical;
  const p = r?.parametric;
  const hz = c.horizon;
  return (
    <>
      <PageHeader title="Risk analytics" lead={`Value at Risk and Expected Shortfall at ${confLabel(c.confidence)}, ${hz}-day horizon. Losses are reported as positive amounts in EUR.`} />
      {q.error && <ErrorBox error={q.error} onRetry={() => q.mutate()} />}
      {!r && !q.error && <Loading />}
      {r && h && p && (
        <div className="space-y-4">
          <div className="grid gap-4 xl:grid-cols-12">
            <Panel className="xl:col-span-5" title="Risk measures" pad={false} aside={<span>{r.window.start} to {r.window.end}</span>}>
              {!h.available && <div className="m-4"><ErrorBox error={new Error(h.reason ?? "Insufficient data")} /></div>}
              <div className="overflow-x-auto"><table className="dense w-full">
                <thead><tr><th>Measure ({hz}-day)</th><th className="r">Historical</th><th className="r">Delta-normal</th></tr></thead>
                <tbody>
                  <Row label={`VaR ${confLabel(c.confidence)}`} hist={h.var} param={p.var} method="hist_var" />
                  <Row label={`ES ${confLabel(c.confidence)}`} hist={h.es} param={p.es} method="hist_es" />
                  <tr><td>1-day VaR / ES</td><td className="r">{compactEur(h.var_1d)} / {compactEur(h.es_1d)}</td><td className="r">{compactEur(p.var_1d)} / {compactEur(p.es_1d)}</td></tr>
                  <tr><td>VaR as % of value in scope</td><td className="r">{h.var !== undefined ? pct(h.var / r.portfolio_value) : "n/a"}</td><td className="r">{p.var !== undefined ? pct(p.var / r.portfolio_value) : "n/a"}</td></tr>
                </tbody>
              </table></div>
              <dl className="grid grid-cols-2 gap-x-6 gap-y-1.5 border-t border-line px-4 py-3 text-[12.5px]">
                <dt className="text-muted">Scenarios (window)</dt><dd className="num text-right">{r.window.n_obs}{r.window.dropped ? ` (${r.window.dropped} dropped)` : ""}</dd>
                <dt className="text-muted">Tail observations n(1−α)</dt><dd className="num text-right">{num(h.tail_obs, 1)}</dd>
                <dt className="text-muted">Daily P&L σ (delta-normal)</dt><dd className="num text-right">{eur(p.sigma_1d)}</dd>
                <dt className="text-muted">P&L skewness</dt><dd className="num text-right">{num(p.skew)}</dd>
                <dt className="text-muted">P&L excess kurtosis</dt><dd className="num text-right">{num(p.excess_kurtosis)}</dd>
                <dt className="text-muted">Corr(full reval., delta P&L)</dt><dd className="num text-right">{num(p.delta_approx_corr, 5)}</dd>
                <dt className="text-muted">Diversification (delta-normal, 1d)</dt><dd className="num text-right">{eur(p.diversification_1d)}</dd>
              </dl>
              <p className="border-t border-line px-4 py-3 text-[12.5px] text-muted">
                {h.var !== undefined && p.var !== undefined && h.var > p.var * 1.1
                  ? `Historical VaR is ${pct(h.var / p.var - 1, 0)} above the normal model: the P&L distribution has fatter tails than a Gaussian.`
                  : "Historical and delta-normal estimates are close on this window."}{" "}
                VaR is a quantile, not a maximum loss.
              </p>
            </Panel>
            <Panel className="xl:col-span-7" title="Distribution of 1-day P&L scenarios" aside={<span>Today&apos;s positions, historical moves</span>}>
              <DistributionChart r={r} height={330} />
            </Panel>
          </div>

          <Notices items={r.warnings} />

          <Panel
            title={<span className="flex items-center gap-2">Backtest of 1-day historical VaR <MethodButton k="backtest" /></span>}
            aside={r.backtest && (
              <>
                <span className="num">{r.backtest.exceptions} exceptions, {r.backtest.expected.toFixed(1)} expected, Kupiec p = {r.backtest.kupiec_pvalue.toFixed(2)}</span>
                {r.backtest.traffic_light && <Badge tone={r.backtest.traffic_light === "green" ? "gain" : r.backtest.traffic_light === "yellow" ? "warn" : "loss"}>Basel {r.backtest.traffic_light}</Badge>}
              </>
            )}
          >
            {r.backtest ? <BacktestChart r={r} /> : <p className="text-[13px] text-muted">Not enough history for a 250-day backtest with this window.</p>}
          </Panel>

          <Panel title="Positions" pad={false} aside={<span>{hz}-day figures</span>}>
            <div className="overflow-auto">
              <table className="dense w-full min-w-[860px]">
                <thead>
                  <tr>
                    <th>Position</th><th>Class</th><th className="r">Value (EUR)</th><th className="r">Volatility (ann.)</th>
                    <th className="r"><span className="inline-flex items-center gap-1">ES contribution <MethodButton k="component_es" /></span></th><th className="r">Share of ES</th>
                    <th className="r"><span className="inline-flex items-center gap-1">Euler VaR (normal) <MethodButton k="component_var" /></span></th><th className="r">Stand-alone VaR (normal)</th>
                  </tr>
                </thead>
                <tbody>
                  {r.positions.map((x) => (
                    <tr key={x.id}>
                      <td className="font-medium text-ink">{x.name}</td><td>{x.asset_class}</td><td className="r">{eur(x.mv_base)}</td><td className="r">{pct(x.vol_annual, 1)}</td>
                      <td className={`r ${x.component_es !== null && x.component_es < 0 ? "text-gain" : ""}`}>{eur(x.component_es)}</td><td className="r">{pct(x.component_es_pct, 1)}</td>
                      <td className="r">{eur(x.component_var_param)}</td><td className="r">{eur(x.standalone_var_param)}</td>
                    </tr>
                  ))}
                  {r.excluded.map((x) => (
                    <tr key={x.id}><td className="text-faint">{x.id}</td><td colSpan={7} className="text-[12px] text-loss">{x.reason}</td></tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>

          {f.data && (
            <div className="grid gap-4 xl:grid-cols-12">
              <Panel className="xl:col-span-5" title={<span className="flex items-center gap-2">Risk factor volatility <MethodButton k="volatility" /></span>} pad={false} aside={<span>{f.data.n_obs} obs.</span>}>
                <div className="max-h-[440px] overflow-auto">
                  <table className="dense w-full">
                    <thead><tr><th>Factor</th><th className="r">Historical</th><th className="r">EWMA (λ 0.94)</th><th>Unit</th></tr></thead>
                    <tbody>
                      {f.data.factors.map((x) => {
                        const ratio = x.class === "EQ" || x.class === "FX";
                        return (
                          <tr key={x.factor}>
                            <td title={x.name}>{x.factor}</td>
                            <td className="r">{ratio ? pct(x.vol, 1) : num(x.vol, 1)}</td>
                            <td className="r">{ratio ? pct(x.ewma_vol, 1) : num(x.ewma_vol, 1)}</td>
                            <td className="text-[11.5px] text-faint">{ratio ? "return" : "bp / year"}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </Panel>
              <Panel className="xl:col-span-7" title="Correlation of daily factor moves" aside={f.data.covariance_check && <span>Covariance symmetric: {f.data.covariance_check.symmetric ? "yes" : "no"}, min eigenvalue {f.data.covariance_check.min_eigenvalue.toExponential(2)}</span>}>
                {f.data.correlation && <Heatmap labels={f.data.labels} m={f.data.correlation} />}
              </Panel>
            </div>
          )}
        </div>
      )}
    </>
  );
}

function Heatmap({ labels, m }: { labels: string[]; m: (number | null)[][] }) {
  const data: [number, number, number | null][] = [];
  m.forEach((row, i) => row.forEach((v, j) => data.push([j, labels.length - 1 - i, v === null ? null : Number(v.toFixed(2))])));
  const rev = [...labels].reverse();
  return (
    <Chart
      height={Math.max(360, labels.length * 18 + 90)}
      ariaLabel="Correlation matrix heatmap of risk factor daily moves"
      option={{
        tooltip: { trigger: "item", formatter: (p: unknown) => { const v = (p as { value: [number, number, number] }).value; return `${labels[v[0]]} / ${rev[v[1]]}: ${v[2]}`; } },
        grid: { left: 8, right: 8, top: 8, bottom: 50, containLabel: true },
        xAxis: { type: "category", data: labels, axisLabel: { rotate: 60, fontSize: 10 }, splitArea: { show: false } },
        yAxis: { type: "category", data: rev, axisLabel: { fontSize: 10 } },
        visualMap: { min: -1, max: 1, calculable: false, orient: "horizontal", left: "center", bottom: 0, itemHeight: 140, inRange: { color: [C.loss, "#f3c7c1", "#ffffff", "#bfcff4", C.accent] }, textStyle: { fontSize: 10 } },
        series: [{ type: "heatmap", data, emphasis: { itemStyle: { borderColor: C.ink, borderWidth: 1 } } }],
      }}
    />
  );
}
