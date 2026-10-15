"use client";
import { useGet } from "@/lib/api";
import { useCtx } from "@/lib/store";
import { Button, Field, inputCls, PageHeader, Panel } from "@/components/ui";

export default function Settings() {
  const c = useCtx();
  const health = useGet<{ status: string; engine_version: string }>("/api/health");
  return (
    <>
      <PageHeader title="Settings" lead="Analysis parameters are shared by every screen and remembered in this browser." />
      <div className="grid gap-4 xl:grid-cols-2">
        <Panel title="Risk parameters">
          <div className="flex flex-wrap gap-4">
            <Field label="Confidence level" hint="Between 50% and 99.9%"><input type="number" step="0.005" min="0.5" max="0.999" className={`${inputCls} num w-[120px]`} value={c.confidence} onChange={(e) => { const v = Number(e.target.value); if (v > 0.5 && v < 1) c.set({ confidence: v }); }} /></Field>
            <Field label="Horizon (business days)" hint="Scaled by √h from 1-day figures"><input type="number" min={1} max={250} className={`${inputCls} num w-[120px]`} value={c.horizon} onChange={(e) => { const v = Math.round(Number(e.target.value)); if (v >= 1 && v <= 250) c.set({ horizon: v }); }} /></Field>
            <Field label="Historical window (days)" hint="Minimum 100 for a historical estimate"><input type="number" min={50} max={2000} step={10} className={`${inputCls} num w-[120px]`} value={c.window} onChange={(e) => { const v = Math.round(Number(e.target.value)); if (v >= 50 && v <= 2000) c.set({ window: v }); }} /></Field>
          </div>
          <Button className="mt-4" onClick={() => c.set({ confidence: 0.99, horizon: 1, window: 500, portfolioId: "demo", datasetId: "synthetic-demo-v1", compareId: null })}>Reset to defaults</Button>
        </Panel>
        <Panel title="Conventions">
          <dl className="grid grid-cols-[180px_1fr] gap-y-2 text-[13px]">
            <dt className="text-muted">Base currency</dt><dd>EUR (fixed in this version)</dd>
            <dt className="text-muted">Loss sign</dt><dd>VaR and ES are positive numbers expressing losses</dd>
            <dt className="text-muted">Returns</dt><dd>Simple daily returns for prices and FX; absolute daily changes for rates and spreads</dd>
            <dt className="text-muted">Annualisation</dt><dd>252 business days</dd>
            <dt className="text-muted">FX quotation</dt><dd>EUR per 1 unit of foreign currency</dd>
            <dt className="text-muted">Bond yields</dt><dd>Compounded at the coupon frequency (ICMA convention)</dd>
          </dl>
        </Panel>
        <Panel title="System">
          <dl className="grid grid-cols-[180px_1fr] gap-y-2 text-[13px]">
            <dt className="text-muted">Calculation service</dt><dd className={health.data ? "text-gain" : "text-loss"}>{health.data ? `Running, engine v${health.data.engine_version}` : health.error ? "Unreachable" : "Checking…"}</dd>
            <dt className="text-muted">Accounts</dt><dd>Single-user installation without accounts; deploy behind your own access control.</dd>
            <dt className="text-muted">Personal data</dt><dd>None collected. Portfolios and reports are stored in the configured database only.</dd>
          </dl>
        </Panel>
        <Panel title="Scope">
          <p className="text-[13px] text-text">RiskPilot is an analysis and simulation tool. It does not execute orders, is not connected to any trading venue and does not provide investment recommendations. Figures computed on synthetic data illustrate the methods only.</p>
        </Panel>
      </div>
    </>
  );
}
