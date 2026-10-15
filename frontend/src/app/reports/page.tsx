"use client";
import { useState } from "react";
import { api, useGet } from "@/lib/api";
import { useCtx } from "@/lib/store";
import type { Scenario } from "@/lib/types";
import { compactEur, confLabel, eur, pct, signedPct, tone } from "@/lib/format";
import { Badge, Button, ErrorBox, Field, inputCls, PageHeader, Panel } from "@/components/ui";

type Report = {
  meta: { computed_at: string; engine_version: string; params: Record<string, unknown>; portfolio: { name: string; as_of: string; hash: string }; dataset: { name: string; provenance: string; provenance_label: string; hash: string } };
  findings: string[];
  follow_up: string[];
  methodology: string[];
  limitations: string[];
  risk: { historical: { var?: number; es?: number }; parametric: { var?: number; es?: number }; portfolio_value: number; window: { n_obs: number; start: string; end: string } };
  exposures: { totals: { net: number; gross: number }; groups: { asset_class: { key: string; net: number; pct_gross: number }[] } };
  attribution: { available: boolean; totals: { es: number }; positions: { name: string; es: number; asset_class: string }[] };
  stress: null | { results: { name: string; kind: string; total_pnl: number; total_pnl_pct: number; error?: string }[] };
  alerts: { date: string; message: string }[];
};
type Saved = { id: string; title: string; created_at: string; params: Record<string, unknown>; engine_version: string };

export default function Reports() {
  const c = useCtx();
  const scs = useGet<Scenario[]>("/api/scenarios");
  const list = useGet<Saved[]>("/api/reports");
  const [picked, setPicked] = useState<string[]>([]);
  const [title, setTitle] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<Error | null>(null);
  const [cur, setCur] = useState<{ id: string; title: string; report: Report } | null>(null);

  async function generate() {
    setBusy(true);
    setErr(null);
    try {
      const r = await api.post<{ id: string; title: string; report: Report }>("/api/reports", { portfolio_id: c.portfolioId, dataset_id: c.datasetId, window: c.window, confidence: c.confidence, horizon_days: c.horizon, scenario_ids: picked, title: title || null });
      setCur(r);
      list.mutate();
    } catch (e) {
      setErr(e as Error);
    } finally {
      setBusy(false);
    }
  }
  async function open(id: string) {
    setErr(null);
    try {
      setCur(await api.get(`/api/reports/${id}`));
    } catch (e) {
      setErr(e as Error);
    }
  }

  return (
    <>
      <PageHeader title="Decision brief" lead="A reproducible summary of the portfolio's risk, built only from engine results. Parameters, input hashes and computation time are stored with each brief." />
      <div className="grid gap-4 xl:grid-cols-12">
        <div className="min-w-0 space-y-4 xl:col-span-4">
          <Panel title="New brief">
            <p className="text-[13px] text-text">Uses the current context: portfolio, dataset, {confLabel(c.confidence)} confidence, {c.horizon}-day horizon, {c.window}-day window.</p>
            <div className="mt-3"><Field label="Title (optional)"><input className={`${inputCls} w-full`} value={title} onChange={(e) => setTitle(e.target.value)} /></Field></div>
            <div className="mt-3 text-[12.5px] text-muted">Scenarios to include</div>
            <div className="mt-1 max-h-[220px] space-y-1 overflow-auto">
              {scs.data?.map((s) => (
                <label key={s.id} className="flex items-start gap-2 text-[13px]">
                  <input type="checkbox" className="mt-1 accent-[#14213d]" checked={picked.includes(s.id)} onChange={() => setPicked(picked.includes(s.id) ? picked.filter((x) => x !== s.id) : [...picked, s.id])} />
                  <span>{s.name}</span>
                </label>
              ))}
            </div>
            <Button className="mt-4" variant="primary" onClick={generate} disabled={busy}>{busy ? "Generating…" : "Generate brief"}</Button>
            {err && <div className="mt-3"><ErrorBox error={err} /></div>}
          </Panel>
          <Panel title="Saved briefs" pad={false}>
            {list.data?.length === 0 && <p className="p-4 text-[13px] text-muted">No brief generated yet.</p>}
            <ul className="divide-y divide-line">
              {list.data?.map((r) => (
                <li key={r.id} className="px-4 py-2.5 text-[13px]">
                  <button className="text-left font-medium text-ink hover:text-accent" onClick={() => open(r.id)}>{r.title}</button>
                  <div className="text-[12px] text-faint">{r.created_at.replace("T", " ").slice(0, 19)} UTC, engine v{r.engine_version}</div>
                  <div className="mt-1 flex gap-3 text-[12.5px]">
                    <a className="text-accent hover:underline" href={`/api/reports/${r.id}/pdf`}>PDF</a>
                    <a className="text-accent hover:underline" href={`/api/reports/${r.id}/csv`}>CSV tables</a>
                    <button className="text-loss hover:underline" onClick={async () => { await api.del(`/api/reports/${r.id}`); if (cur?.id === r.id) setCur(null); list.mutate(); }}>Delete</button>
                  </div>
                </li>
              ))}
            </ul>
          </Panel>
        </div>
        <div className="min-w-0 xl:col-span-8">
          {!cur && <Panel><p className="py-10 text-center text-[13px] text-muted">Generate a brief or open a saved one to preview it here.</p></Panel>}
          {cur && <Preview id={cur.id} title={cur.title} r={cur.report} />}
        </div>
      </div>
    </>
  );
}

function Preview({ id, title, r }: { id: string; title: string; r: Report }) {
  const m = r.meta;
  return (
    <article className="rounded-md border border-line bg-panel">
      <header className="border-b border-line px-6 py-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-[19px] font-semibold text-ink">{title}</h2>
            <p className="mt-1 text-[12.5px] text-muted">{m.portfolio.name}, valued {m.portfolio.as_of}. Market data: {m.dataset.name} ({m.dataset.provenance_label}).</p>
            <p className="text-[12px] text-faint">Computed {m.computed_at.replace("T", " ")} with engine v{m.engine_version}. Portfolio #{m.portfolio.hash}, dataset #{m.dataset.hash}.</p>
          </div>
          <div className="flex gap-2">
            <a href={`/api/reports/${id}/pdf`} className="rounded-sm border border-ink bg-ink px-3 py-1.5 text-[13px] font-medium text-white">Download PDF</a>
            <a href={`/api/reports/${id}/csv`} className="rounded-sm border border-line-strong px-3 py-1.5 text-[13px] font-medium text-ink">CSV tables</a>
          </div>
        </div>
        {m.dataset.provenance === "SYNTHETIC" && <div className="mt-3"><Badge tone="warn">Synthetic data: figures illustrate the method only</Badge></div>}
      </header>
      <div className="space-y-6 px-6 py-5 text-[13.5px]">
        <section className="grid grid-cols-2 gap-4 md:grid-cols-4">
          <div><div className="text-[12px] text-muted">Net value</div><div className="num text-[18px] font-semibold">{compactEur(r.exposures.totals.net)}</div></div>
          <div><div className="text-[12px] text-muted">Historical VaR</div><div className="num text-[18px] font-semibold">{compactEur(r.risk.historical.var)}</div></div>
          <div><div className="text-[12px] text-muted">Historical ES</div><div className="num text-[18px] font-semibold">{compactEur(r.risk.historical.es)}</div></div>
          <div><div className="text-[12px] text-muted">Delta-normal VaR</div><div className="num text-[18px] font-semibold">{compactEur(r.risk.parametric.var)}</div></div>
        </section>
        <section>
          <h3 className="font-semibold text-ink">Findings</h3>
          <ul className="mt-1.5 list-disc space-y-1 pl-5">{r.findings.map((f) => <li key={f}>{f}</li>)}</ul>
        </section>
        <section>
          <h3 className="font-semibold text-ink">Points requiring further analysis</h3>
          <ul className="mt-1.5 list-disc space-y-1 pl-5">{(r.follow_up.length ? r.follow_up : ["None flagged by the rules."]).map((f) => <li key={f}>{f}</li>)}</ul>
        </section>
        <div className="grid gap-6 md:grid-cols-2">
          <section>
            <h3 className="font-semibold text-ink">Main exposures</h3>
            <table className="dense mt-1.5 w-full"><tbody>{r.exposures.groups.asset_class.map((g) => <tr key={g.key}><td>{g.key}</td><td className="r">{compactEur(g.net)}</td><td className="r">{pct(g.pct_gross, 1)}</td></tr>)}</tbody></table>
          </section>
          {r.attribution.available && (
            <section>
              <h3 className="font-semibold text-ink">Top ES contributors</h3>
              <table className="dense mt-1.5 w-full"><tbody>{r.attribution.positions.slice(0, 6).map((p) => <tr key={p.name}><td>{p.name}</td><td className="r">{eur(p.es)}</td><td className="r">{pct(p.es / r.attribution.totals.es, 1)}</td></tr>)}</tbody></table>
            </section>
          )}
        </div>
        {r.stress && (
          <section>
            <h3 className="font-semibold text-ink">Scenarios</h3>
            <table className="dense mt-1.5 w-full"><tbody>{r.stress.results.map((s) => <tr key={s.name}><td>{s.name}</td><td>{s.kind}</td><td className={`r ${tone(s.total_pnl)}`}>{s.error ? s.error : compactEur(s.total_pnl)}</td><td className={`r ${tone(s.total_pnl)}`}>{signedPct(s.total_pnl_pct)}</td></tr>)}</tbody></table>
          </section>
        )}
        {r.alerts.length > 0 && (
          <section>
            <h3 className="font-semibold text-ink">Recent alerts</h3>
            <ul className="mt-1.5 space-y-1 text-[12.5px]">{r.alerts.slice(0, 8).map((a, i) => <li key={i}><span className="num text-faint">{a.date}</span> {a.message}</li>)}</ul>
          </section>
        )}
        <section className="text-[12.5px] text-muted">
          <h3 className="font-semibold text-ink">Methodology</h3>
          <ul className="mt-1.5 list-disc space-y-1 pl-5">{r.methodology.map((f) => <li key={f}>{f}</li>)}</ul>
          <h3 className="mt-4 font-semibold text-ink">Data limitations</h3>
          <ul className="mt-1.5 list-disc space-y-1 pl-5">{(r.limitations.length ? r.limitations : ["No limitation flagged."]).map((f) => <li key={f}>{f}</li>)}</ul>
        </section>
      </div>
    </article>
  );
}
