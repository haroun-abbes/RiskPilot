"use client";
import { useState } from "react";
import { useSWRConfig } from "swr";
import { api, useGet } from "@/lib/api";
import { useCtx } from "@/lib/store";
import { factorLevel } from "@/lib/format";
import { Badge, Button, ErrorBox, Field, inputCls, Loading, PageHeader, Panel, ProvenanceBadge } from "@/components/ui";
import type { DatasetItem } from "@/components/shell";

type Provider = { id: string; name: string; status: string; kind: string; detail: string; last_update?: string | null; realtime: boolean };
type Quality = {
  dataset: DatasetItem & { license_note: string; frequency: string; description: string; updated_at: string; hash: string };
  n_factors: number; n_dates: number; start: string; end: string; stale_factors: string[];
  issue_counts: { error: number; warning: number; info: number };
  factors: { factor: string; count: number; missing: number; first: string; last: string; last_value: number; issues: { severity: string; check: string; message: string }[]; meta: { name?: string } }[];
};

export default function DataPage() {
  const c = useCtx();
  const { mutate } = useSWRConfig();
  const dss = useGet<(DatasetItem & { n_dates: number; n_factors: number; license_note: string; updated_at: string })[]>("/api/datasets");
  const provs = useGet<Provider[]>("/api/providers");
  const [view, setView] = useState<string | null>(null);
  const qid = view ?? c.datasetId;
  const q = useGet<Quality>(`/api/datasets/${qid}/quality`);
  const [test, setTest] = useState<{ ok: boolean; detail: string; checked_at: string } | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<Error | null>(null);
  const [onlyIssues, setOnlyIssues] = useState(false);

  async function run(label: string, fn: () => Promise<unknown>) {
    setBusy(label);
    setErr(null);
    try {
      await fn();
    } catch (e) {
      setErr(e as Error);
    } finally {
      setBusy(null);
    }
  }

  return (
    <>
      <PageHeader title="Data sources and quality" lead="Where every number comes from. Synthetic, historical and delayed data are kept in separate datasets, each with its provenance; nothing is filled in when an observation is missing." />
      {err && <div className="mb-4"><ErrorBox error={err} /></div>}
      <div className="grid gap-4 xl:grid-cols-12">
        <Panel className="xl:col-span-7" title="Datasets" pad={false}>
          {!dss.data && <Loading />}
          <table className="dense w-full">
            <thead><tr><th>Dataset</th><th>Provenance</th><th>Coverage</th><th>Updated</th><th /></tr></thead>
            <tbody>
              {dss.data?.map((d) => (
                <tr key={d.id} className={qid === d.id ? "bg-accent-soft" : ""}>
                  <td><button className="text-left font-medium text-ink hover:text-accent" onClick={() => setView(d.id)}>{d.name}</button><div className="text-[11.5px] text-faint">{d.source}</div></td>
                  <td><ProvenanceBadge provenance={d.provenance} /></td>
                  <td className="num text-[12.5px]">{d.n_factors} series, {d.n_dates} dates<br />{d.start} to {d.end}</td>
                  <td className="num text-[12.5px]">{d.updated_at.slice(0, 10)}</td>
                  <td className="text-right">
                    {c.datasetId === d.id ? <Badge tone="accent">In use</Badge> : <button className="text-[12.5px] text-accent hover:underline" onClick={() => c.set({ datasetId: d.id })}>Use</button>}
                    {d.id !== "synthetic-demo-v1" && <button className="ml-3 text-[12.5px] text-loss hover:underline" onClick={() => window.confirm(`Delete dataset "${d.name}"?`) && run("del", async () => { await api.del(`/api/datasets/${d.id}`); if (c.datasetId === d.id) c.set({ datasetId: "synthetic-demo-v1" }); setView(null); dss.mutate(); mutate("/api/datasets"); })}>Delete</button>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>
        <Panel className="xl:col-span-5" title="Connections" pad={false}>
          <ul className="divide-y divide-line">
            {provs.data?.map((p) => (
              <li key={p.id} className="px-4 py-3 text-[13px]">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-medium text-ink">{p.name}</span>
                  <Badge tone={p.status === "available" || p.status === "loaded" ? "gain" : p.status === "disabled" ? "neutral" : "warn"}>{{ available: "Available", loaded: "Loaded", not_loaded: "Not loaded", disabled: "Disabled" }[p.status] ?? p.status}</Badge>
                </div>
                <p className="mt-0.5 text-[12.5px] text-muted">{p.detail}</p>
                <p className="text-[12px] text-faint">Real-time: no.{p.last_update ? ` Last fetch ${p.last_update.slice(0, 16).replace("T", " ")} UTC.` : ""}</p>
                {p.id === "ecb" && p.status !== "disabled" && (
                  <div className="mt-2 flex flex-wrap gap-2">
                    <Button disabled={!!busy} onClick={() => run("test", async () => setTest(await api.post("/api/providers/ecb/test")))}>{busy === "test" ? "Testing…" : "Test connection"}</Button>
                    <Button disabled={!!busy} onClick={() => run("fetch", async () => { await api.post("/api/providers/ecb/fetch"); provs.mutate(); dss.mutate(); mutate("/api/datasets"); })}>{busy === "fetch" ? "Fetching…" : "Fetch history since 2021"}</Button>
                  </div>
                )}
                {p.id === "ecb" && test && (
                  <p className={`mt-2 text-[12.5px] ${test.ok ? "text-gain" : "text-loss"}`}>{test.ok ? "Connected. " : "Connection failed. "}{test.detail} (checked {test.checked_at.slice(11, 19)} UTC)</p>
                )}
              </li>
            ))}
          </ul>
          <UploadMarket onDone={() => { dss.mutate(); mutate("/api/datasets"); }} />
        </Panel>
      </div>

      <div className="mt-4">
        {q.error && <ErrorBox error={q.error} />}
        {q.data && (
          <Panel title={`Quality report: ${q.data.dataset.name}`} pad={false} aside={
            <label className="flex items-center gap-1.5"><input type="checkbox" className="accent-[#14213d]" checked={onlyIssues} onChange={(e) => setOnlyIssues(e.target.checked)} />Only series with issues</label>
          }>
            <div className="grid gap-4 border-b border-line px-4 py-3 text-[12.5px] md:grid-cols-2">
              <div>
                <div className="flex items-center gap-2"><ProvenanceBadge provenance={q.data.dataset.provenance} /><span className="text-muted">{q.data.dataset.frequency}</span></div>
                <p className="mt-1 text-text">{q.data.dataset.description}</p>
                <p className="mt-1 text-faint">Terms of use: {q.data.dataset.license_note || "not specified"}</p>
              </div>
              <div className="num grid grid-cols-2 gap-y-1">
                <span className="text-muted">Series / dates</span><span className="text-right">{q.data.n_factors} / {q.data.n_dates}</span>
                <span className="text-muted">Range</span><span className="text-right">{q.data.start} to {q.data.end}</span>
                <span className="text-muted">Errors / warnings / info</span><span className="text-right">{q.data.issue_counts.error} / {q.data.issue_counts.warning} / {q.data.issue_counts.info}</span>
                <span className="text-muted">Series ending early</span><span className="text-right">{q.data.stale_factors.length ? q.data.stale_factors.join(", ") : "none"}</span>
                <span className="text-muted">Content hash</span><span className="text-right">#{q.data.dataset.hash}</span>
              </div>
            </div>
            <div className="max-h-[520px] overflow-auto">
              <table className="dense w-full min-w-[820px]">
                <thead><tr><th>Series</th><th>Description</th><th className="r">Obs.</th><th className="r">Missing</th><th>First</th><th>Last</th><th className="r">Last value</th><th>Checks</th></tr></thead>
                <tbody>
                  {q.data.factors.filter((f) => !onlyIssues || f.issues.length).map((f) => (
                    <tr key={f.factor}>
                      <td className="font-medium text-ink">{f.factor}</td>
                      <td className="text-muted">{f.meta?.name}</td>
                      <td className="r">{f.count}</td>
                      <td className={`r ${f.missing ? "text-warn" : ""}`}>{f.missing}</td>
                      <td className="num">{f.first}</td><td className="num">{f.last}</td>
                      <td className="r">{factorLevel(f.factor, f.last_value)}</td>
                      <td className="text-[12px]">{f.issues.length === 0 ? <span className="text-gain">Passed</span> : f.issues.map((i, k) => <div key={k} className={i.severity === "error" ? "text-loss" : i.severity === "warning" ? "text-warn" : "text-muted"}>{i.message}</div>)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="px-4 py-2 text-[12px] text-faint">Checks: missing values, gaps over 5 days, 5+ identical consecutive values, non-positive prices, rates above 50% (likely percent units), daily moves beyond 8 robust standard deviations.</p>
          </Panel>
        )}
      </div>
    </>
  );
}

function UploadMarket({ onDone }: { onDone: () => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [name, setName] = useState("");
  const [prov, setProv] = useState("HISTORICAL_REAL");
  const [source, setSource] = useState("");
  const [lic, setLic] = useState("");
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  async function submit() {
    if (!file) return;
    const fd = new FormData();
    fd.append("file", file);
    fd.append("name", name || file.name);
    fd.append("provenance", prov);
    fd.append("source", source);
    fd.append("license_note", lic);
    try {
      await api.upload("/api/datasets/upload", fd);
      setMsg({ ok: true, text: "Dataset imported. Select it in the context bar to use it." });
      onDone();
    } catch (e) {
      setMsg({ ok: false, text: (e as Error).message });
    }
  }
  return (
    <div className="border-t border-line px-4 py-3">
      <div className="text-[13px] font-medium text-ink">Import market history (CSV)</div>
      <p className="text-[12px] text-muted">Columns: date, then one column per series (EQ:TICKER, FX:CCY as EUR per unit, IR:CCY:10Y and CS:CCY:IG|HY in decimal).</p>
      <div className="mt-2 grid gap-2 sm:grid-cols-2">
        <input type="file" accept=".csv" aria-label="Market data file" className="text-[12.5px]" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        <Field label="Name"><input className={inputCls} value={name} onChange={(e) => setName(e.target.value)} /></Field>
        <Field label="Provenance"><select className={inputCls} value={prov} onChange={(e) => setProv(e.target.value)}><option value="HISTORICAL_REAL">Historical market data</option><option value="DELAYED">Delayed market data</option><option value="SYNTHETIC">Synthetic</option></select></Field>
        <Field label="Source (required)"><input className={inputCls} value={source} onChange={(e) => setSource(e.target.value)} placeholder="e.g. ECB Data Portal export" /></Field>
        <Field label="Terms of use"><input className={inputCls} value={lic} onChange={(e) => setLic(e.target.value)} /></Field>
      </div>
      <Button className="mt-2" disabled={!file || !source.trim()} onClick={submit}>Import dataset</Button>
      {msg && <p className={`mt-2 text-[12.5px] ${msg.ok ? "text-gain" : "text-loss"}`}>{msg.text}</p>}
    </div>
  );
}
