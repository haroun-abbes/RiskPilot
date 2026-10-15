"use client";
import { useMemo, useState } from "react";
import { api, useGet } from "@/lib/api";
import { useCtx } from "@/lib/store";
import { factorChange, factorLevel, tone } from "@/lib/format";
import { Badge, Button, ErrorBox, Field, inputCls, Loading, PageHeader, Panel } from "@/components/ui";
import { axis, Chart } from "@/components/chart";

type Watchlist = { id: string; name: string; factors: string[] };
type FactorInfo = { factor: string; class: string; name?: string };
type Series = { meta: { name?: string }; class: string; last: number | null; last_date: string | null; chg_1d: number | null; chg_5d: number | null; chg_21d: number | null; chg_ytd: number | null; points: [string, number][] };
type Rule = { id: string; name: string; factor: string; rule_type: "level" | "change" | "zscore"; direction: "above" | "below" | "abs"; threshold: number; lookback: number; active: boolean };
type Event = { id: number; rule_id: string; date: string; value: number; message: string };

const RULE_HELP: Record<string, string> = {
  level: "Level of the factor (rates and spreads in %, prices as quoted)",
  change: "Change over the lookback: return for prices/FX (%), absolute for rates/spreads (bp)",
  zscore: "Daily move divided by the standard deviation of the previous 250 daily moves",
};

function thresholdToInput(r: Pick<Rule, "factor" | "rule_type" | "threshold">) {
  const rate = r.factor.startsWith("IR:") || r.factor.startsWith("CS:");
  if (r.rule_type === "zscore") return r.threshold;
  if (r.rule_type === "level") return rate ? r.threshold * 100 : r.threshold;
  return rate ? r.threshold * 1e4 : r.threshold * 100;
}
function inputToThreshold(factor: string, type: string, v: number) {
  const rate = factor.startsWith("IR:") || factor.startsWith("CS:");
  if (type === "zscore") return v;
  if (type === "level") return rate ? v / 100 : v;
  return rate ? v / 1e4 : v / 100;
}
function unitFor(factor: string, type: string) {
  const rate = factor.startsWith("IR:") || factor.startsWith("CS:");
  if (type === "zscore") return "sd";
  if (type === "level") return rate ? "%" : "price";
  return rate ? "bp" : "%";
}

export default function MarketWatch() {
  const c = useCtx();
  const wls = useGet<Watchlist[]>("/api/watchlists");
  const facs = useGet<FactorInfo[]>(`/api/datasets/${c.datasetId}/factors`);
  const [wid, setWid] = useState<string | null>(null);
  const wl = wls.data?.find((w) => w.id === wid) ?? wls.data?.[0];
  const avail = new Set(facs.data?.map((f) => f.factor));
  const shown = (wl?.factors ?? []).filter((f) => avail.has(f));
  const missing = (wl?.factors ?? []).filter((f) => facs.data && !avail.has(f));
  const series = useGet<{ series: Record<string, Series> }>(shown.length ? `/api/datasets/${c.datasetId}/series?factors=${encodeURIComponent(shown.join(","))}` : null);
  const [plotBy, setPlotBy] = useState<Record<string, string[]>>({});
  const plotKey = `${wl?.id}|${c.datasetId}`;
  const plot = (plotBy[plotKey] ?? shown.slice(0, 3)).filter((f) => shown.includes(f));
  const setPlot = (p: string[]) => setPlotBy({ ...plotBy, [plotKey]: p });
  const [editWl, setEditWl] = useState<{ id?: string; name: string; factors: string[] } | null>(null);
  const [err, setErr] = useState<Error | null>(null);

  async function saveWl() {
    if (!editWl) return;
    try {
      const body = { name: editWl.name, factors: editWl.factors };
      const r = editWl.id ? await api.put<Watchlist>(`/api/watchlists/${editWl.id}`, body) : await api.post<Watchlist>("/api/watchlists", body);
      await wls.mutate();
      setWid(r.id);
      setEditWl(null);
    } catch (e) {
      setErr(e as Error);
    }
  }

  const last = series.data && Object.values(series.data.series)[0]?.last_date;
  return (
    <>
      <PageHeader
        title="Market watch"
        lead={<>End-of-day series from the selected dataset{last ? `, last observation ${last}` : ""}. RiskPilot does not display real-time prices.</>}
        actions={
          <>
            <select aria-label="Watchlist" className={inputCls} value={wl?.id ?? ""} onChange={(e) => setWid(e.target.value)}>
              {wls.data?.map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}
            </select>
            {wl && <Button onClick={() => setEditWl({ id: wl.id, name: wl.name, factors: [...wl.factors] })}>Edit list</Button>}
            <Button onClick={() => setEditWl({ name: "", factors: [] })}>New list</Button>
            {wl && wls.data && wls.data.length > 1 && <Button variant="danger" onClick={async () => { if (window.confirm(`Delete watchlist "${wl.name}"?`)) { await api.del(`/api/watchlists/${wl.id}`); setWid(null); wls.mutate(); } }}>Delete list</Button>}
          </>
        }
      />
      {err && <div className="mb-4"><ErrorBox error={err} /></div>}
      {editWl && (
        <Panel className="mb-4 border-ink" title={editWl.id ? "Edit watchlist" : "New watchlist"}>
          <Field label="Name"><input className={`${inputCls} w-[300px]`} value={editWl.name} onChange={(e) => setEditWl({ ...editWl, name: e.target.value })} /></Field>
          <div className="mt-3 grid max-h-[260px] grid-cols-2 gap-x-6 gap-y-1 overflow-auto sm:grid-cols-3 xl:grid-cols-5">
            {facs.data?.map((f) => (
              <label key={f.factor} className="flex items-center gap-2 text-[12.5px]" title={f.name}>
                <input type="checkbox" className="accent-[#14213d]" checked={editWl.factors.includes(f.factor)} onChange={() => setEditWl({ ...editWl, factors: editWl.factors.includes(f.factor) ? editWl.factors.filter((x) => x !== f.factor) : [...editWl.factors, f.factor] })} />
                {f.factor}
              </label>
            ))}
          </div>
          <div className="mt-4 flex justify-end gap-2"><Button onClick={() => setEditWl(null)}>Cancel</Button><Button variant="primary" disabled={!editWl.name.trim() || editWl.factors.length === 0} onClick={saveWl}>Save watchlist</Button></div>
        </Panel>
      )}
      <div className="space-y-4">
        <Panel title={wl?.name ?? "Watchlist"} pad={false} aside={<span>Tick a row to plot it</span>}>
          {series.error && <div className="p-4"><ErrorBox error={series.error} /></div>}
          {!series.data && shown.length > 0 && !series.error && <Loading label="Loading series" />}
          {series.data && (
            <div className="overflow-auto">
              <table className="dense w-full min-w-[760px]">
                <thead><tr><th /><th>Factor</th><th>Description</th><th className="r">Last</th><th className="r">1 day</th><th className="r">1 week</th><th className="r">1 month</th><th className="r">Year to date</th></tr></thead>
                <tbody>
                  {shown.map((f) => {
                    const s = series.data!.series[f];
                    return (
                      <tr key={f}>
                        <td><input type="checkbox" aria-label={`Plot ${f}`} className="accent-[#14213d]" checked={plot.includes(f)} onChange={() => setPlot(plot.includes(f) ? plot.filter((x) => x !== f) : [...plot, f].slice(-6))} /></td>
                        <td className="font-medium text-ink">{f}</td>
                        <td className="text-muted">{s.meta?.name}</td>
                        <td className="r">{factorLevel(f, s.last)}</td>
                        {[s.chg_1d, s.chg_5d, s.chg_21d, s.chg_ytd].map((x, i) => <td key={i} className={`r ${tone(x)}`}>{factorChange(f, x)}</td>)}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
          {missing.length > 0 && <p className="border-t border-line px-4 py-2 text-[12px] text-warn">Not available in this dataset: {missing.join(", ")}</p>}
        </Panel>
        {series.data && plot.length > 0 && <Comparison series={series.data.series} plot={plot} />}
        <Alerts />
      </div>
    </>
  );
}

function Comparison({ series, plot }: { series: Record<string, Series>; plot: string[] }) {
  const prices = plot.filter((f) => /^(EQ|FX):/.test(f));
  const rates = plot.filter((f) => /^(IR|CS):/.test(f));
  const dates = series[plot[0]]?.points.map((p) => p[0]) ?? [];
  const lines = [
    ...prices.map((f) => {
      const pts = series[f].points;
      const base = pts[0]?.[1] ?? 1;
      const m = new Map(pts.map(([d, v]) => [d, (v / base) * 100]));
      return { name: `${f} (rebased)`, type: "line" as const, yAxisIndex: 0, data: dates.map((d) => m.get(d) ?? null), symbol: "none", lineStyle: { width: 1.4 } };
    }),
    ...rates.map((f) => {
      const m = new Map(series[f].points);
      return { name: `${f} (%)`, type: "line" as const, yAxisIndex: rates.length && prices.length ? 1 : 0, data: dates.map((d) => (m.has(d) ? (m.get(d) as number) * 100 : null)), symbol: "none", lineStyle: { width: 1.4, type: prices.length ? ("dashed" as const) : ("solid" as const) } };
    }),
  ];
  const yAxes = prices.length && rates.length ? [axis.value("Rebased = 100"), { ...axis.value("%"), splitLine: { show: false } }] : [axis.value(prices.length ? "Rebased = 100" : "%")];
  return (
    <Panel title="Comparison" aside={<span>Prices and FX rebased to 100 at the first date; rates and spreads in %</span>}>
      <Chart
        height={320}
        ariaLabel="Time series comparison of selected market factors"
        option={{
          tooltip: { trigger: "axis", valueFormatter: (v) => (v === null || v === undefined ? "n/a" : (v as number).toFixed(3)) },
          legend: { top: 0, type: "scroll", textStyle: { fontSize: 11.5 } },
          grid: { top: 36, bottom: 40 },
          xAxis: { type: "category", data: dates, axisLabel: { hideOverlap: true } },
          yAxis: yAxes.map((y) => ({ ...y, scale: true })),
          dataZoom: [{ type: "inside" }, { type: "slider", height: 18, bottom: 6 }],
          series: lines,
        }}
      />
    </Panel>
  );
}

function Alerts() {
  const c = useCtx();
  const rules = useGet<Rule[]>("/api/alerts/rules");
  const events = useGet<Event[]>(`/api/alerts/events?dataset_id=${c.datasetId}&limit=300`);
  const facs = useGet<FactorInfo[]>(`/api/datasets/${c.datasetId}/factors`);
  const [draft, setDraft] = useState({ name: "", factor: "EQ:SXEU", rule_type: "change" as Rule["rule_type"], direction: "abs" as Rule["direction"], threshold: "3", lookback: "1" });
  const [err, setErr] = useState<Error | null>(null);
  const [evaluated, setEvaluated] = useState<string | null>(null);
  const ruleName = useMemo(() => Object.fromEntries((rules.data ?? []).map((r) => [r.id, r.name])), [rules.data]);

  async function evaluate() {
    setErr(null);
    try {
      const r = await api.post<{ evaluated_at: string; n_events: number }>(`/api/alerts/evaluate?dataset_id=${c.datasetId}`);
      setEvaluated(`${r.n_events} trigger(s) recorded, evaluated ${r.evaluated_at.replace("T", " ").replace("+00:00", " UTC")}`);
      events.mutate();
    } catch (e) {
      setErr(e as Error);
    }
  }
  async function addRule() {
    setErr(null);
    try {
      await api.post("/api/alerts/rules", { name: draft.name || `${draft.factor} ${draft.rule_type}`, factor: draft.factor, rule_type: draft.rule_type, direction: draft.direction, threshold: inputToThreshold(draft.factor, draft.rule_type, Number(draft.threshold)), lookback: Number(draft.lookback) || 1 });
      rules.mutate();
      setDraft({ ...draft, name: "" });
    } catch (e) {
      setErr(e as Error);
    }
  }
  async function toggle(r: Rule) {
    await api.put(`/api/alerts/rules/${r.id}`, { ...r, active: !r.active });
    rules.mutate();
  }

  return (
    <div className="grid gap-4 xl:grid-cols-12">
      <Panel className="xl:col-span-7" title="Alert rules" pad={false} aside={<Button variant="primary" onClick={evaluate}>Evaluate on dataset</Button>}>
        {err && <div className="p-4"><ErrorBox error={err} /></div>}
        {evaluated && <p className="border-b border-line bg-gain-soft px-4 py-2 text-[12.5px] text-gain">{evaluated}</p>}
        <div className="overflow-auto">
          <table className="dense w-full min-w-[640px]">
            <thead><tr><th>Rule</th><th>Factor</th><th>Condition</th><th>Status</th><th /></tr></thead>
            <tbody>
              {rules.data?.map((r) => (
                <tr key={r.id}>
                  <td className="font-medium text-ink">{r.name}</td>
                  <td>{r.factor}</td>
                  <td className="text-[12.5px]">{r.rule_type}{r.rule_type === "change" ? ` over ${r.lookback}d` : ""} {r.direction === "abs" ? "beyond ±" : r.direction} {thresholdToInput(r).toLocaleString("en-GB", { maximumFractionDigits: 4 })} {unitFor(r.factor, r.rule_type)}</td>
                  <td><button onClick={() => toggle(r)}>{r.active ? <Badge tone="gain">Active</Badge> : <Badge>Paused</Badge>}</button></td>
                  <td><button className="text-[12.5px] text-loss hover:underline" onClick={async () => { await api.del(`/api/alerts/rules/${r.id}`); rules.mutate(); events.mutate(); }}>Delete</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="flex flex-wrap items-end gap-3 border-t border-line px-4 py-3">
          <Field label="Name"><input className={`${inputCls} w-[180px]`} value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} placeholder="Optional" /></Field>
          <Field label="Factor"><select className={inputCls} value={draft.factor} onChange={(e) => setDraft({ ...draft, factor: e.target.value })}>{facs.data?.map((f) => <option key={f.factor}>{f.factor}</option>)}</select></Field>
          <Field label="Rule"><select className={inputCls} value={draft.rule_type} title={RULE_HELP[draft.rule_type]} onChange={(e) => setDraft({ ...draft, rule_type: e.target.value as Rule["rule_type"] })}><option value="level">Level</option><option value="change">Change</option><option value="zscore">Z-score</option></select></Field>
          <Field label="Direction"><select className={inputCls} value={draft.direction} onChange={(e) => setDraft({ ...draft, direction: e.target.value as Rule["direction"] })}><option value="above">Above</option><option value="below">Below</option><option value="abs">Either side</option></select></Field>
          <Field label={`Threshold (${unitFor(draft.factor, draft.rule_type)})`}><input inputMode="decimal" className={`${inputCls} num w-[90px]`} value={draft.threshold} onChange={(e) => setDraft({ ...draft, threshold: e.target.value })} /></Field>
          {draft.rule_type === "change" && <Field label="Lookback (days)"><input inputMode="numeric" className={`${inputCls} num w-[70px]`} value={draft.lookback} onChange={(e) => setDraft({ ...draft, lookback: e.target.value })} /></Field>}
          <Button onClick={addRule}>Add rule</Button>
        </div>
        <p className="px-4 pb-3 text-[12px] text-faint">{RULE_HELP[draft.rule_type]}. Rules are deterministic and evaluated on every date of the dataset.</p>
      </Panel>
      <Panel className="xl:col-span-5" title="Alert history" pad={false} aside={<span>{events.data?.length ?? 0} shown, newest first</span>}>
        {events.data && events.data.length === 0 && <p className="p-4 text-[13px] text-muted">No trigger recorded. Evaluate the rules on this dataset.</p>}
        <div className="max-h-[420px] overflow-auto">
          <table className="dense w-full">
            <thead><tr><th>Date</th><th>Rule</th><th>Detail</th></tr></thead>
            <tbody>
              {events.data?.map((e) => (
                <tr key={e.id}><td className="num whitespace-nowrap">{e.date}</td><td>{ruleName[e.rule_id] ?? ""}</td><td className="text-[12px] text-muted">{e.message.split(": ").slice(1).join(": ")}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
    </div>
  );
}
