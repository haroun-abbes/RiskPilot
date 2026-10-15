"use client";
import { useState } from "react";
import { api } from "@/lib/api";
import type { Scenario } from "@/lib/types";
import { Button, ErrorBox, Field, inputCls, Panel, Tabs } from "./ui";

type Def = {
  equity?: { all?: number; by_sector?: Record<string, number>; by_country?: Record<string, number>; by_ticker?: Record<string, number> };
  rates?: Record<string, { parallel_bp?: number; tenor_bp?: Record<string, number> }>;
  spreads?: Record<string, number>;
  fx?: Record<string, number>;
  start?: string;
  end?: string;
};

const CCYS = ["EUR", "USD"];
const TENORS = ["2Y", "10Y", "30Y"];
const FXS = ["USD", "GBP", "CHF", "JPY"];

type Pair = { k: string; v: string };
const toPairs = (o?: Record<string, number>, scale = 100) => Object.entries(o ?? {}).map(([k, v]) => ({ k, v: String(+(v * scale).toFixed(6)) }));
const fromPairs = (p: Pair[], scale = 100) => Object.fromEntries(p.filter((x) => x.k.trim() && x.v !== "").map((x) => [x.k.trim(), Number(x.v) / scale]));
const n = (s: string) => (s === "" || s === "-" ? 0 : Number(s));

function Num({ label, value, onChange, unit }: { label: string; value: string; onChange: (v: string) => void; unit: string }) {
  return (
    <Field label={`${label} (${unit})`}>
      <input inputMode="decimal" className={`${inputCls} num w-[110px]`} value={value} onChange={(e) => onChange(e.target.value)} />
    </Field>
  );
}

export function ScenarioEditor({ initial, onSaved, onCancel }: { initial: Scenario | null; onSaved: (s: Scenario) => void; onCancel: () => void }) {
  const d = (initial?.definition ?? {}) as Def;
  const [name, setName] = useState(initial?.name ?? "");
  const [desc, setDesc] = useState(initial?.description ?? "");
  const [kind, setKind] = useState<"hypothetical" | "historical">(initial?.kind ?? "hypothetical");
  const [eqAll, setEqAll] = useState(String(+((d.equity?.all ?? 0) * 100).toFixed(4)));
  const [sectors, setSectors] = useState<Pair[]>(toPairs(d.equity?.by_sector));
  const [tickers, setTickers] = useState<Pair[]>(toPairs(d.equity?.by_ticker));
  const [rates, setRates] = useState<Record<string, { par: string; t: Record<string, string> }>>(
    Object.fromEntries(CCYS.map((c) => [c, { par: String(d.rates?.[c]?.parallel_bp ?? 0), t: Object.fromEntries(TENORS.map((t) => [t, d.rates?.[c]?.tenor_bp?.[t] !== undefined ? String(d.rates?.[c]?.tenor_bp?.[t]) : ""])) }])),
  );
  const [ig, setIg] = useState(String(d.spreads?.IG ?? 0));
  const [hy, setHy] = useState(String(d.spreads?.HY ?? 0));
  const [fx, setFx] = useState<Record<string, string>>(Object.fromEntries(FXS.map((c) => [c, String(+((d.fx?.[c] ?? 0) * 100).toFixed(4))])));
  const [start, setStart] = useState(d.start ?? "2025-03-21");
  const [end, setEnd] = useState(d.end ?? "2025-05-02");
  const [err, setErr] = useState<Error | null>(null);

  function definition(): Def {
    if (kind === "historical") return { start, end };
    const r: Def["rates"] = {};
    for (const c of CCYS) {
      const t = Object.fromEntries(Object.entries(rates[c].t).filter(([, v]) => v !== "").map(([k, v]) => [k, n(v)]));
      if (n(rates[c].par) !== 0 || Object.keys(t).length) r[c] = { parallel_bp: n(rates[c].par), tenor_bp: t };
    }
    return {
      equity: { all: n(eqAll) / 100, by_sector: fromPairs(sectors), by_ticker: fromPairs(tickers) },
      rates: r,
      spreads: { IG: n(ig), HY: n(hy) },
      fx: Object.fromEntries(FXS.filter((c) => n(fx[c]) !== 0).map((c) => [c, n(fx[c]) / 100])),
    };
  }

  async function save() {
    setErr(null);
    try {
      const body = { name, kind, description: desc, definition: definition() };
      const s = initial ? await api.put<Scenario>(`/api/scenarios/${initial.id}`, body) : await api.post<Scenario>("/api/scenarios", body);
      onSaved(s);
    } catch (e) {
      setErr(e as Error);
    }
  }

  const pairEditor = (label: string, pairs: Pair[], set: (p: Pair[]) => void, keyHint: string) => (
    <div>
      <div className="mb-1 text-[12.5px] text-muted">{label} (%)</div>
      {pairs.map((p, i) => (
        <div key={i} className="mb-1.5 flex gap-2">
          <input aria-label={keyHint} placeholder={keyHint} className={`${inputCls} w-[160px]`} value={p.k} onChange={(e) => set(pairs.map((x, j) => (j === i ? { ...x, k: e.target.value } : x)))} />
          <input aria-label="Shock in percent" inputMode="decimal" className={`${inputCls} num w-[80px]`} value={p.v} onChange={(e) => set(pairs.map((x, j) => (j === i ? { ...x, v: e.target.value } : x)))} />
          <button className="text-[12.5px] text-loss" onClick={() => set(pairs.filter((_, j) => j !== i))}>Remove</button>
        </div>
      ))}
      <button className="text-[12.5px] text-accent" onClick={() => set([...pairs, { k: "", v: "" }])}>Add override</button>
    </div>
  );

  return (
    <Panel className="mb-4 border-ink" title={initial ? `Edit scenario: ${initial.name}` : "New scenario"} aside={<Tabs value={kind} onChange={setKind} items={[{ value: "hypothetical", label: "Hypothetical" }, { value: "historical", label: "Historical replay" }]} />}>
      <div className="flex flex-wrap gap-4">
        <Field label="Name"><input className={`${inputCls} w-[320px]`} value={name} onChange={(e) => setName(e.target.value)} /></Field>
        <Field label="Description"><input className={`${inputCls} w-[420px] max-w-full`} value={desc} onChange={(e) => setDesc(e.target.value)} /></Field>
      </div>
      {kind === "historical" ? (
        <div className="mt-4 flex flex-wrap items-end gap-4">
          <Field label="Window start"><input type="date" className={inputCls} value={start} onChange={(e) => setStart(e.target.value)} /></Field>
          <Field label="Window end"><input type="date" className={inputCls} value={end} onChange={(e) => setEnd(e.target.value)} /></Field>
          <p className="max-w-lg text-[12.5px] text-muted">Applies the cumulative factor moves recorded in the selected dataset between these dates to today&apos;s positions. Its provenance is the dataset&apos;s: on synthetic data it is a synthetic episode.</p>
        </div>
      ) : (
        <div className="mt-4 grid gap-6 lg:grid-cols-2">
          <fieldset className="space-y-3">
            <legend className="mb-2 text-[13px] font-semibold text-ink">Equities and ETFs</legend>
            <Num label="All equities" unit="%" value={eqAll} onChange={setEqAll} />
            {pairEditor("Sector overrides", sectors, setSectors, "Sector, e.g. Technology")}
            {pairEditor("Ticker overrides", tickers, setTickers, "Ticker, e.g. ORBS")}
            <p className="text-[12px] text-faint">Priority: ticker, then sector, then all.</p>
          </fieldset>
          <fieldset className="space-y-3">
            <legend className="mb-2 text-[13px] font-semibold text-ink">Rates, spreads and FX</legend>
            {CCYS.map((c) => (
              <div key={c} className="flex flex-wrap items-end gap-2">
                <Num label={`${c} parallel`} unit="bp" value={rates[c].par} onChange={(v) => setRates({ ...rates, [c]: { ...rates[c], par: v } })} />
                {TENORS.map((t) => (
                  <Field key={t} label={`+ ${t} (bp)`}>
                    <input inputMode="decimal" className={`${inputCls} num w-[70px]`} value={rates[c].t[t]} onChange={(e) => setRates({ ...rates, [c]: { ...rates[c], t: { ...rates[c].t, [t]: e.target.value } } })} />
                  </Field>
                ))}
              </div>
            ))}
            <p className="text-[12px] text-faint">Tenor points are added to the parallel shift and interpolated linearly at each bond&apos;s maturity (flat beyond the end points).</p>
            <div className="flex gap-3">
              <Num label="IG spreads" unit="bp" value={ig} onChange={setIg} />
              <Num label="HY spreads" unit="bp" value={hy} onChange={setHy} />
            </div>
            <div className="flex flex-wrap gap-3">
              {FXS.map((c) => <Num key={c} label={`${c} vs EUR`} unit="%" value={fx[c]} onChange={(v) => setFx({ ...fx, [c]: v })} />)}
            </div>
            <p className="text-[12px] text-faint">FX: change of the foreign currency&apos;s value in EUR (positive = currency appreciates).</p>
          </fieldset>
        </div>
      )}
      {err && <div className="mt-4"><ErrorBox error={err} /></div>}
      <div className="mt-5 flex justify-end gap-2 border-t border-line pt-4">
        <Button onClick={onCancel}>Cancel</Button>
        <Button variant="primary" onClick={save} disabled={!name.trim()}>Save scenario</Button>
      </div>
    </Panel>
  );
}
