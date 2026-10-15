"use client";
import { Fragment, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { Badge, Button, ErrorBox, Field, inputCls, Panel } from "./ui";

type Preview = { session_id: string; filename: string; header: string[]; n_rows: number; preview: (string | number | null)[][]; suggested_mapping: Record<string, string | null>; fields: Record<string, string>; required: Record<string, string[]> };
type Issue = { row: number; field: string | null; message: string; severity: "error" | "warning" };
type Validation = { valid_positions: number; rows: number; errors: number; warnings: number; issues: Issue[]; rows_status: { row: number; id: string; instrument_type: string; status: string }[]; by_type: Record<string, number>; can_commit: boolean };

const STEPS = ["Upload", "Map columns", "Review and confirm"];

export function ImportWizard({ onDone }: { onDone: (id: string) => void }) {
  const [step, setStep] = useState(0);
  const [pv, setPv] = useState<Preview | null>(null);
  const [mapping, setMapping] = useState<Record<string, string | null>>({});
  const [asOf, setAsOf] = useState("2026-10-14");
  const [name, setName] = useState("");
  const [val, setVal] = useState<Validation | null>(null);
  const [err, setErr] = useState<Error | null>(null);
  const [busy, setBusy] = useState(false);

  async function upload(f: File) {
    setErr(null);
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("file", f);
      const p = await api.upload<Preview>("/api/portfolios/import/preview", fd);
      setPv(p);
      setMapping(p.suggested_mapping);
      setName(f.name.replace(/\.(csv|xlsx|txt)$/i, ""));
      setVal(null);
      setStep(1);
    } catch (e) {
      setErr(e as Error);
    } finally {
      setBusy(false);
    }
  }

  async function validate() {
    if (!pv) return;
    setErr(null);
    setBusy(true);
    try {
      setVal(await api.post<Validation>("/api/portfolios/import/validate", { session_id: pv.session_id, mapping, as_of: asOf, name: name || pv.filename }));
      setStep(2);
    } catch (e) {
      setErr(e as Error);
    } finally {
      setBusy(false);
    }
  }

  async function commit() {
    if (!pv) return;
    setBusy(true);
    try {
      const r = await api.post<{ id: string }>("/api/portfolios/import/commit", { session_id: pv.session_id, mapping, as_of: asOf, name: name || pv.filename });
      onDone(r.id);
    } catch (e) {
      setErr(e as ApiError);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      <ol className="flex flex-wrap gap-2 text-[12.5px]" aria-label="Import steps">
        {STEPS.map((s, i) => (
          <li key={s} className={`rounded-sm border px-3 py-1 ${i === step ? "border-ink bg-ink text-white" : i < step ? "border-line-strong text-ink" : "border-line text-faint"}`}>
            {i + 1}. {s}
          </li>
        ))}
      </ol>
      {err && <ErrorBox error={err} />}

      {step === 0 && (
        <div className="grid gap-4 xl:grid-cols-12">
          <Panel className="xl:col-span-7" title="Upload a CSV or Excel file">
            <label className="flex cursor-pointer flex-col items-center justify-center rounded-md border border-dashed border-line-strong bg-canvas px-6 py-12 text-center hover:border-accent">
              <span className="font-medium text-ink">{busy ? "Reading file…" : "Choose a .csv or .xlsx file"}</span>
              <span className="mt-1 text-[12.5px] text-muted">One row per position, maximum 5,000 rows and 5 MB. Macro-enabled workbooks are refused.</span>
              <input type="file" accept=".csv,.xlsx,.txt" className="sr-only" onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} />
            </label>
          </Panel>
          <Panel className="xl:col-span-5" title="Template and demonstration file">
            <p className="text-[13px] text-text">The templates contain the synthetic demonstration book (fictitious issuers). Edit them or use them as a format reference.</p>
            <div className="mt-3 flex flex-wrap gap-2">
              <a className="rounded-sm border border-line-strong px-3 py-1.5 text-[13px] font-medium text-ink hover:border-ink" href="/api/templates/portfolio.csv">Download CSV</a>
              <a className="rounded-sm border border-line-strong px-3 py-1.5 text-[13px] font-medium text-ink hover:border-ink" href="/api/templates/portfolio.xlsx">Download Excel</a>
            </div>
            <ul className="mt-4 list-disc space-y-1 pl-5 text-[12.5px] text-muted">
              <li>Supported types: EQUITY, ETF, BOND_FIXED, FX_CASH. Floating-rate notes and derivatives are refused with an explanation.</li>
              <li>Coupons in percent (3.25 = 3.25%), bond prices clean in % of par.</li>
              <li>Negative quantity or nominal means a short position.</li>
              <li>Equities need a price history in the market dataset (EQ:ticker) or a risk proxy, otherwise they are valued but excluded from risk.</li>
            </ul>
          </Panel>
        </div>
      )}

      {step === 1 && pv && (
        <>
          <Panel title={`Preview of ${pv.filename}`} aside={<span>{pv.n_rows} rows, first {Math.min(15, pv.n_rows)} shown</span>} pad={false}>
            <div className="max-h-[300px] overflow-auto">
              <table className="dense w-full">
                <thead><tr>{pv.header.map((h) => <th key={h}>{h}</th>)}</tr></thead>
                <tbody>{pv.preview.map((r, i) => <tr key={i}>{r.map((v, j) => <td key={j} className="whitespace-nowrap">{v === null ? "" : String(v)}</td>)}</tr>)}</tbody>
              </table>
            </div>
          </Panel>
          <Panel title="Map file columns to RiskPilot fields" aside={<span>Suggested automatically from column names</span>}>
            <div className="grid gap-x-6 gap-y-3 sm:grid-cols-2 xl:grid-cols-4">
              {Object.entries(pv.fields).map(([f, desc]) => (
                <Field key={f} label={f} hint={desc}>
                  <select className={inputCls} value={mapping[f] ?? ""} onChange={(e) => setMapping({ ...mapping, [f]: e.target.value || null })}>
                    <option value="">Not mapped</option>
                    {pv.header.map((h) => <option key={h} value={h}>{h}</option>)}
                  </select>
                </Field>
              ))}
            </div>
            <div className="mt-5 flex flex-wrap items-end gap-4 border-t border-line pt-4">
              <Field label="Portfolio name"><input className={`${inputCls} w-[280px]`} value={name} onChange={(e) => setName(e.target.value)} /></Field>
              <Field label="Valuation date" hint="Prices in the file are as of this date"><input type="date" className={inputCls} value={asOf} onChange={(e) => setAsOf(e.target.value)} /></Field>
              <div className="ml-auto flex gap-2">
                <Button onClick={() => setStep(0)}>Choose another file</Button>
                <Button variant="primary" onClick={validate} disabled={busy}>{busy ? "Validating…" : "Validate"}</Button>
              </div>
            </div>
          </Panel>
        </>
      )}

      {step === 2 && val && (
        <div className="grid gap-4 xl:grid-cols-12">
          <Panel className="xl:col-span-4" title="Summary">
            <dl className="grid grid-cols-2 gap-y-2 text-[13px]">
              <dt className="text-muted">Rows read</dt><dd className="num text-right">{val.rows}</dd>
              <dt className="text-muted">Valid positions</dt><dd className="num text-right">{val.valid_positions}</dd>
              <dt className="text-muted">Blocking errors</dt><dd className={`num text-right ${val.errors ? "text-loss" : ""}`}>{val.errors}</dd>
              <dt className="text-muted">Warnings</dt><dd className={`num text-right ${val.warnings ? "text-warn" : ""}`}>{val.warnings}</dd>
              {Object.entries(val.by_type).map(([k, v]) => (<Fragment key={k}><dt className="text-muted">{k}</dt><dd className="num text-right">{v}</dd></Fragment>))}
            </dl>
            <div className="mt-4 border-t border-line pt-4">
              {val.can_commit ? (
                <p className="text-[13px] text-text">Import <b>{val.valid_positions}</b> positions as “{name}”, valued on {asOf}{val.warnings ? `, with ${val.warnings} warning(s)` : ""}?</p>
              ) : (
                <p className="text-[13px] text-loss">Fix the blocking errors in the file or the mapping before importing. Nothing has been saved.</p>
              )}
              <div className="mt-3 flex gap-2">
                <Button onClick={() => setStep(1)}>Back to mapping</Button>
                <Button variant="primary" disabled={!val.can_commit || busy} onClick={commit}>Confirm import</Button>
              </div>
            </div>
          </Panel>
          <Panel className="xl:col-span-8" title="Row-level checks" pad={false}>
            {val.issues.length === 0 ? (
              <p className="px-4 py-6 text-[13px] text-gain">All rows passed validation.</p>
            ) : (
              <div className="max-h-[460px] overflow-auto">
                <table className="dense w-full">
                  <thead><tr><th>Row</th><th>Field</th><th>Severity</th><th>Message</th></tr></thead>
                  <tbody>
                    {val.issues.map((i, k) => (
                      <tr key={k}><td className="num">{i.row}</td><td>{i.field ?? ""}</td><td><Badge tone={i.severity === "error" ? "loss" : "warn"}>{i.severity}</Badge></td><td>{i.message}</td></tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Panel>
        </div>
      )}
    </div>
  );
}
