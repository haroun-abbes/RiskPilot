"use client";
import { useMemo, useState } from "react";
import { api, useGet, usePostQuery } from "@/lib/api";
import { useCtx } from "@/lib/store";
import type { Scenario, StressResponse, StressResult } from "@/lib/types";
import { bp, compactEur, eur, pct, signedPct, tone } from "@/lib/format";
import { Badge, Button, ErrorBox, Loading, MethodButton, Notices, PageHeader, Panel } from "@/components/ui";
import { axis, C, Chart, kfmt } from "@/components/chart";
import { ScenarioEditor } from "@/components/scenario-editor";

const CLASS_LABEL: Record<string, string> = { equity: "Equity", rates: "Rates", spreads: "Spreads", fx: "FX" };

export default function StressPage() {
  const c = useCtx();
  const scs = useGet<Scenario[]>("/api/scenarios");
  const [chosen, setSelected] = useState<string[] | null>(null);
  const [focus, setFocus] = useState<number>(0);
  const [editing, setEditing] = useState<Scenario | "new" | null>(null);
  const [err, setErr] = useState<Error | null>(null);

  // default comparison until the user makes a choice
  const selected = chosen ?? (scs.data ?? []).filter((s) => s.is_builtin && (["Combined risk-off", "Rates +100bp parallel (EUR, USD)", "Credit spread widening"].includes(s.name) || s.kind === "historical")).map((s) => s.id);

  const body = { portfolio_id: c.portfolioId, dataset_id: c.datasetId, scenario_ids: selected };
  const run = usePostQuery<StressResponse>(selected.length ? "/api/stress/run" : null, body);
  const res = run.data;
  const ok = (res?.results ?? []).filter((r) => !r.error);
  const cur = ok[Math.min(focus, ok.length - 1)];

  async function act(fn: () => Promise<unknown>) {
    setErr(null);
    try {
      await fn();
      await scs.mutate();
    } catch (e) {
      setErr(e as Error);
    }
  }
  const toggle = (id: string) => setSelected(selected.includes(id) ? selected.filter((x) => x !== id) : [...selected, id]);

  return (
    <>
      <PageHeader
        title="Stress Lab"
        lead="Instantaneous revaluation of the portfolio under hypothetical shocks or replays of moves recorded in the selected dataset."
        actions={<><MethodButton k="stress" /><Button variant="primary" onClick={() => setEditing("new")}>New scenario</Button></>}
      />
      {err && <div className="mb-4"><ErrorBox error={err} /></div>}
      {editing && (
        <ScenarioEditor
          initial={editing === "new" ? null : editing}
          onCancel={() => setEditing(null)}
          onSaved={async (s) => { setEditing(null); await scs.mutate(); setSelected([...selected.filter((x) => x !== s.id), s.id]); }}
        />
      )}
      <div className="grid gap-4 xl:grid-cols-12">
        <Panel className="xl:col-span-4" title="Scenarios" aside={<span>{selected.length} selected for comparison</span>} pad={false}>
          {!scs.data && <Loading label="Loading scenarios" />}
          <ul className="divide-y divide-line">
            {scs.data?.map((s) => (
              <li key={s.id} className="flex gap-3 px-4 py-3">
                <input type="checkbox" className="mt-1 accent-[#14213d]" checked={selected.includes(s.id)} onChange={() => toggle(s.id)} aria-label={`Include ${s.name}`} />
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <span className="font-medium text-ink">{s.name}</span>
                    <Badge tone={s.kind === "historical" ? "accent" : "neutral"}>{s.kind === "historical" ? "Historical replay" : "Hypothetical"}</Badge>
                    {s.is_builtin && <Badge>Built-in</Badge>}
                  </div>
                  <p className="mt-0.5 text-[12.5px] text-muted">{s.description}</p>
                  <div className="mt-1.5 flex gap-3 text-[12.5px]">
                    <button className="text-accent hover:underline" onClick={() => act(() => api.post(`/api/scenarios/${s.id}/duplicate`))}>Duplicate</button>
                    {!s.is_builtin && <button className="text-accent hover:underline" onClick={() => setEditing(s)}>Edit</button>}
                    {!s.is_builtin && <button className="text-loss hover:underline" onClick={() => window.confirm(`Delete "${s.name}"?`) && act(() => api.del(`/api/scenarios/${s.id}`))}>Delete</button>}
                  </div>
                </div>
              </li>
            ))}
          </ul>
        </Panel>

        <div className="min-w-0 space-y-4 xl:col-span-8">
          {selected.length === 0 && <Panel><p className="text-[13px] text-muted">Select one or more scenarios to revalue the portfolio.</p></Panel>}
          {run.error && <ErrorBox error={run.error} onRetry={() => run.mutate()} />}
          {selected.length > 0 && !res && !run.error && <Loading label="Revaluing positions" />}
          {res && (
            <>
              <Panel title="Scenario comparison" pad={false} aside={<span>Base value {compactEur(res.base_value)}</span>}>
                <div className="overflow-auto">
                  <table className="dense w-full min-w-[760px]">
                    <thead><tr><th>Scenario</th><th className="r">P&L</th><th className="r">% of value</th>{Object.values(CLASS_LABEL).map((l) => <th key={l} className="r">{l}</th>)}<th className="r">Cross effect</th><th className="r">× 10d ES</th></tr></thead>
                    <tbody>
                      {res.results.map((r) =>
                        r.error ? (
                          <tr key={r.name}><td>{r.name}</td><td colSpan={8} className="text-loss">{r.error}</td></tr>
                        ) : (
                          <tr key={r.name} className={`cursor-pointer ${cur?.name === r.name ? "bg-accent-soft" : ""}`} onClick={() => setFocus(ok.indexOf(r))}>
                            <td className="font-medium text-ink">{r.name}</td>
                            <td className={`r font-semibold ${tone(r.total_pnl)}`}>{compactEur(r.total_pnl)}</td>
                            <td className={`r ${tone(r.total_pnl)}`}>{signedPct(r.total_pnl_pct)}</td>
                            {Object.keys(CLASS_LABEL).map((k) => <td key={k} className={`r ${tone(r.by_class[k])}`}>{compactEur(r.by_class[k])}</td>)}
                            <td className="r">{compactEur(r.interaction)}</td>
                            <td className="r">{res.reference && r.total_pnl < 0 ? (-r.total_pnl / res.reference.es_10d).toFixed(2) : "n/a"}</td>
                          </tr>
                        ),
                      )}
                    </tbody>
                  </table>
                </div>
                {res.reference && <p className="border-t border-line px-4 py-2 text-[12px] text-faint">Reference for scale: {res.reference.label} = {eur(res.reference.es_10d)}. Click a row for its detail.</p>}
              </Panel>
              <Notices items={res.warnings} />
              {cur && <ScenarioDetail r={cur} base={res.base_value} />}
            </>
          )}
        </div>
      </div>
    </>
  );
}

function Waterfall({ r, base }: { r: StressResult; base: number }) {
  const steps = [...Object.keys(CLASS_LABEL).map((k) => ({ label: CLASS_LABEL[k], v: r.by_class[k] })), { label: "Cross", v: r.interaction }];
  let run = base;
  const cats = ["Base", ...steps.map((s) => s.label), "Stressed"];
  const invisible: number[] = [base * 0];
  const up: (number | string)[] = ["-"];
  const down: (number | string)[] = ["-"];
  const totals: (number | string)[] = [base];
  for (const s of steps) {
    const next = run + s.v;
    invisible.push(Math.min(run, next));
    if (s.v >= 0) { up.push(s.v); down.push("-"); } else { up.push("-"); down.push(-s.v); }
    totals.push("-");
    run = next;
  }
  invisible.push(0); up.push("-"); down.push("-"); totals.push(run);
  const lo = Math.min(base, run, ...invisible.slice(1, -1)) * 0.97;
  return (
    <Chart
      height={280}
      ariaLabel="Waterfall from base portfolio value to stressed value by risk factor class"
      option={{
        tooltip: { trigger: "axis", axisPointer: { type: "shadow" }, formatter: (ps: unknown) => { const arr = ps as { seriesName: string; value: number | string; name: string }[]; const v = arr.filter((p) => p.seriesName !== "base" && p.value !== "-"); return v.map((p) => `${p.name}: ${eur(p.seriesName === "Loss" ? -(p.value as number) : (p.value as number))}`).join("<br/>"); } },
        xAxis: { type: "category", data: cats, axisLabel: { interval: 0 } },
        yAxis: { ...axis.value(undefined, kfmt), min: lo },
        series: [
          { name: "base", type: "bar", stack: "w", data: invisible.map((v, i) => (i === 0 || i === invisible.length - 1 ? "-" : v)), itemStyle: { color: "transparent" }, silent: true },
          { name: "Value", type: "bar", stack: "w", data: totals, itemStyle: { color: C.ink }, barWidth: "46%" },
          { name: "Gain", type: "bar", stack: "w", data: up, itemStyle: { color: C.gain } },
          { name: "Loss", type: "bar", stack: "w", data: down, itemStyle: { color: C.loss } },
        ],
      }}
    />
  );
}

function ScenarioDetail({ r, base }: { r: StressResult; base: number }) {
  const worst = useMemo(() => r.positions.slice(0, 5), [r]);
  const losers = r.positions.filter((p) => p.pnl < 0).length;
  return (
    <>
      <div className="grid gap-4 lg:grid-cols-12">
        <Panel className="lg:col-span-7" title={`${r.name}: from base to stressed value`} aside={<Badge tone={r.kind === "historical" ? "accent" : "neutral"}>{r.kind === "historical" ? "Historical replay" : "Hypothetical"}</Badge>}>
          <Waterfall r={r} base={base} />
          <p className="mt-1 text-[12.5px] text-muted">{r.provenance_note ?? "Hypothetical shocks chosen by the user. They do not reproduce any specific historical crisis."} Each class is shocked alone; the cross effect is the remainder (for example equity × FX).</p>
        </Panel>
        <Panel className="lg:col-span-5" title="Most affected positions">
          <ul className="space-y-2.5">
            {worst.map((p) => (
              <li key={p.id} className="flex items-baseline justify-between gap-3 text-[13px]">
                <div className="min-w-0"><div className="truncate font-medium text-ink">{p.name}</div><div className="text-[12px] text-faint">{p.asset_class}, {p.currency}</div></div>
                <div className="text-right"><div className={`num font-semibold ${tone(p.pnl)}`}>{compactEur(p.pnl)}</div><div className={`num text-[12px] ${tone(p.pnl)}`}>{signedPct(p.pnl_pct)}</div></div>
              </li>
            ))}
          </ul>
          <p className="mt-3 border-t border-line pt-2 text-[12.5px] text-muted">{losers} of {r.positions.length} positions lose value in this scenario.</p>
        </Panel>
      </div>
      {r.issues.length > 0 && <Notices items={r.issues} title="Scenario data issues" />}
      <Panel title="Position detail" pad={false}>
        <div className="max-h-[480px] overflow-auto">
          <table className="dense w-full min-w-[900px]">
            <thead><tr><th>Position</th><th className="r">Value</th><th className="r">Equity move</th><th className="r">FX move</th><th className="r">Rate Δ</th><th className="r">Spread Δ</th><th className="r">P&L (full reval.)</th><th className="r">Duration-convexity</th><th className="r">P&L %</th></tr></thead>
            <tbody>
              {r.positions.map((p) => (
                <tr key={p.id}>
                  <td className="font-medium text-ink">{p.name}</td>
                  <td className="r">{compactEur(p.mv_base)}</td>
                  <td className="r">{p.moves.r_eq ? signedPct(p.moves.r_eq, 1) : ""}</td>
                  <td className="r">{p.moves.r_fx ? signedPct(p.moves.r_fx, 1) : ""}</td>
                  <td className="r">{p.moves.dy_rates ? bp(p.moves.dy_rates) : ""}</td>
                  <td className="r">{p.moves.dy_spread ? bp(p.moves.dy_spread) : ""}</td>
                  <td className={`r font-medium ${tone(p.pnl)}`}>{eur(p.pnl)}</td>
                  <td className="r text-muted">{p.pnl_duration_convexity !== null ? eur(p.pnl_duration_convexity) : ""}</td>
                  <td className={`r ${tone(p.pnl)}`}>{pct(p.pnl_pct)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {r.excluded.length > 0 && <p className="border-t border-line px-4 py-2 text-[12px] text-loss">Not revalued: {r.excluded.map((x) => `${x.id} (${x.reason})`).join("; ")}</p>}
      </Panel>
    </>
  );
}
