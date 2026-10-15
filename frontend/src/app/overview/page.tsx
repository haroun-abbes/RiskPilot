"use client";
import Link from "next/link";
import { api, useGet, usePostQuery } from "@/lib/api";
import { riskBody, useCtx } from "@/lib/store";
import type { Exposures, RiskSummary } from "@/lib/types";
import { compactEur, confLabel, eur, pct } from "@/lib/format";
import { Badge, Button, ErrorBox, Loading, Metric, Notices, PageHeader, Panel } from "@/components/ui";
import { BackcastChart, DistributionChart, HBar } from "@/components/risk-charts";

type AlertEvent = { id: number; date: string; message: string };

export default function Overview() {
  const c = useCtx();
  const risk = usePostQuery<RiskSummary>("/api/risk/summary", riskBody(c));
  const expo = useGet<Exposures>(`/api/portfolios/${c.portfolioId}/exposures?dataset_id=${c.datasetId}`);
  const alerts = useGet<AlertEvent[]>(`/api/alerts/events?dataset_id=${c.datasetId}&limit=6`);
  const r = risk.data;
  const e = expo.data;
  const hz = `${c.horizon}d`;
  return (
    <>
      <PageHeader
        title={r?.meta.portfolio.name ?? "Overview"}
        lead={r ? `Valued on ${r.meta.portfolio.as_of}. Risk measured on ${r.window.n_obs} daily scenarios from ${r.window.start} to ${r.window.end}.` : undefined}
      />
      {risk.error && <ErrorBox error={risk.error} onRetry={() => risk.mutate()} />}
      {!r && !risk.error && <Loading />}
      {r && e && (
        <div className="space-y-4">
          <Panel>
            <div className="grid grid-cols-2 gap-x-6 gap-y-5 md:grid-cols-3 xl:grid-cols-6">
              <Metric label="Net market value" value={compactEur(e.totals.net)} sub={`Gross ${compactEur(e.totals.gross)}`} emphasis />
              <Metric label={`VaR ${confLabel(c.confidence)}, ${hz}`} method="hist_var" value={r.historical.available ? compactEur(r.historical.var) : "n/a"} sub={r.historical.available ? `${pct((r.historical.var ?? 0) / r.portfolio_value)} of value in scope` : r.historical.reason} emphasis />
              <Metric label={`ES ${confLabel(c.confidence)}, ${hz}`} method="hist_es" value={r.historical.available ? compactEur(r.historical.es) : "n/a"} sub="Historical, full revaluation" emphasis />
              <Metric label={`Delta-normal VaR, ${hz}`} method="param_var" value={compactEur(r.parametric.var)} sub={r.parametric.excess_kurtosis != null ? `P&L excess kurtosis ${r.parametric.excess_kurtosis.toFixed(1)}` : undefined} />
              <Metric label="Bond DV01" method="duration" value={e.fixed_income ? eur(e.fixed_income.dv01) : "n/a"} sub={e.fixed_income ? `Mod. duration ${e.fixed_income.modified_duration.toFixed(2)}` : "No bonds"} />
              <Metric label="Risk coverage" value={pct(r.coverage_gross, 1)} sub={`${e.totals.n_excluded} of ${e.totals.n_positions} positions excluded`} toneClass={r.coverage_gross !== null && r.coverage_gross < 1 ? "text-warn" : ""} />
            </div>
          </Panel>

          <Notices items={r.warnings} />

          <div className="grid gap-4 xl:grid-cols-12">
            <Panel className="xl:col-span-7" title="Daily P&L scenarios" aside={<span>1-day, {r.window.n_obs} scenarios</span>}>
              <DistributionChart r={r} />
              <p className="mt-2 text-[12.5px] text-muted">
                Bars in red lie beyond the 1-day VaR. The worst {r.historical.tail_obs?.toFixed(1)} scenarios average {eur(r.historical.es_1d)}, which is the 1-day ES.
              </p>
            </Panel>
            <Panel className="xl:col-span-5" title="Largest contributors to ES" aside={<Link className="text-accent" href="/attribution">Full attribution</Link>}>
              <HBar ariaLabel="Top contributors to expected shortfall" items={r.positions.slice(0, 8).map((p) => ({ label: p.name, value: p.component_es ?? 0 }))} />
              <p className="mt-1 text-[12.5px] text-muted">Average P&L of each position on the portfolio&apos;s worst days. Values add up to ES; green bars hedge.</p>
            </Panel>
          </div>

          <div className="grid gap-4 xl:grid-cols-12">
            <Panel className="xl:col-span-4" title="Allocation by asset class">
              <table className="dense w-full">
                <thead>
                  <tr><th>Class</th><th className="r">Net</th><th className="r">Gross share</th></tr>
                </thead>
                <tbody>
                  {e.groups.asset_class.map((g) => (
                    <tr key={g.key}><td>{g.key}</td><td className="r">{compactEur(g.net)}</td><td className="r">{pct(g.pct_gross, 1)}</td></tr>
                  ))}
                </tbody>
              </table>
              <p className="mt-2 text-[12px] text-faint">Market-value weights, not risk contributions.</p>
            </Panel>
            <Panel className="xl:col-span-5" title="Current holdings replayed over the dataset" aside={<span>Backcast, not actual performance</span>}>
              <BackcastChart r={r} />
            </Panel>
            <Panel className="xl:col-span-3" title="Recent alerts" aside={<Link className="text-accent" href="/market">Rules</Link>}>
              {alerts.data && alerts.data.length === 0 && (
                <div className="text-[13px] text-muted">
                  <p>No alert recorded for this dataset yet.</p>
                  <Button className="mt-2" onClick={async () => { await api.post(`/api/alerts/evaluate?dataset_id=${c.datasetId}`); alerts.mutate(); }}>Evaluate alert rules</Button>
                </div>
              )}
              <ul className="space-y-2.5">
                {alerts.data?.map((a) => (
                  <li key={a.id} className="text-[12.5px]">
                    <div className="num text-faint">{a.date}</div>
                    <div className="text-text">{a.message}</div>
                  </li>
                ))}
              </ul>
            </Panel>
          </div>
          <div className="flex flex-wrap gap-2 text-[12px] text-faint">
            <Badge>Computed {r.meta.computed_at.replace("T", " ").replace("+00:00", " UTC")}</Badge>
            <Badge>Engine v{r.meta.engine_version}</Badge>
            <Badge>Portfolio #{r.meta.portfolio.hash}</Badge>
            <Badge>Dataset #{r.meta.dataset.hash}</Badge>
          </div>
        </div>
      )}
    </>
  );
}
