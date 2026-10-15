"use client";
import { useMemo, useState } from "react";
import { useSWRConfig } from "swr";
import { api, useGet } from "@/lib/api";
import { useCtx } from "@/lib/store";
import type { Exposures } from "@/lib/types";
import { compactEur, eur, num, pct } from "@/lib/format";
import { Badge, Button, ErrorBox, Loading, Metric, MethodButton, Notices, PageHeader, Panel, Tabs } from "@/components/ui";
import { ImportWizard } from "@/components/import-wizard";
import type { PortfolioItem } from "@/components/shell";

const GROUPS = [
  { value: "asset_class", label: "Asset class" },
  { value: "currency", label: "Currency" },
  { value: "sector", label: "Sector" },
  { value: "issuer", label: "Issuer" },
  { value: "country", label: "Country" },
  { value: "rating", label: "Rating" },
] as const;

export default function PortfolioPage() {
  const c = useCtx();
  const [tab, setTab] = useState<"positions" | "import">("positions");
  const [group, setGroup] = useState<(typeof GROUPS)[number]["value"]>("asset_class");
  const [cls, setCls] = useState("All");
  const expo = useGet<Exposures>(`/api/portfolios/${c.portfolioId}/exposures?dataset_id=${c.datasetId}`);
  const { data: pfs } = useGet<PortfolioItem[]>("/api/portfolios");
  const { mutate } = useSWRConfig();
  const e = expo.data;
  const current = pfs?.find((p) => p.id === c.portfolioId);
  const classes = useMemo(() => ["All", ...Array.from(new Set(e?.positions.map((p) => p.asset_class) ?? []))], [e]);
  const rows = e?.positions.filter((p) => cls === "All" || p.asset_class === cls) ?? [];

  async function remove() {
    if (!current || current.id === "demo") return;
    if (!window.confirm(`Delete portfolio "${current.name}"? This cannot be undone.`)) return;
    await api.del(`/api/portfolios/${current.id}`);
    c.set({ portfolioId: "demo" });
    mutate("/api/portfolios");
  }

  return (
    <>
      <PageHeader
        title="Portfolio"
        lead="Positions, valuation in EUR and exposures. Imported positions feed every calculation in the application."
        actions={
          <>
            <Tabs value={tab} onChange={setTab} items={[{ value: "positions", label: "Positions" }, { value: "import", label: "Import a portfolio" }]} />
            {current && current.id !== "demo" && tab === "positions" && (
              <Button variant="danger" onClick={remove}>Delete portfolio</Button>
            )}
          </>
        }
      />
      {tab === "import" ? (
        <ImportWizard onDone={(id) => { c.set({ portfolioId: id }); mutate("/api/portfolios"); setTab("positions"); }} />
      ) : (
        <>
          {expo.error && <ErrorBox error={expo.error} onRetry={() => expo.mutate()} />}
          {!e && !expo.error && <Loading label="Valuing positions" />}
          {e && (
            <div className="space-y-4">
              <Panel>
                <div className="grid grid-cols-2 gap-6 md:grid-cols-4 xl:grid-cols-6">
                  <Metric label="Net market value" value={compactEur(e.totals.net)} emphasis />
                  <Metric label="Gross exposure" value={compactEur(e.totals.gross)} sub="Σ |market value|" />
                  <Metric label="Long" value={compactEur(e.totals.long)} />
                  <Metric label="Short" value={compactEur(e.totals.short)} toneClass="text-loss" />
                  <Metric label="Bond yield (MV-weighted)" value={pct(e.fixed_income?.ytm_mv_weighted)} sub={e.fixed_income ? `Accrued ${compactEur(e.fixed_income.accrued)}` : undefined} />
                  <Metric label="Positions" value={`${e.totals.n_positions}`} sub={`${e.totals.n_excluded} excluded from risk`} />
                </div>
              </Panel>
              <Notices items={e.warnings} />
              <div className="grid gap-4 xl:grid-cols-12">
                <Panel className="xl:col-span-8" title="Positions" pad={false} aside={
                  <select aria-label="Filter by asset class" className="rounded-sm border border-line-strong bg-panel px-2 py-1 text-[12.5px]" value={cls} onChange={(ev) => setCls(ev.target.value)}>
                    {classes.map((x) => <option key={x}>{x}</option>)}
                  </select>
                }>
                  <div className="max-h-[560px] overflow-auto">
                    <table className="dense w-full min-w-[820px]">
                      <thead>
                        <tr><th>Position</th><th>Class</th><th>Ccy</th><th className="r">Local value</th><th className="r">FX (EUR/ccy)</th><th className="r">Value (EUR)</th><th className="r">Yield</th><th className="r">Mod. dur.</th><th>Risk factors</th></tr>
                      </thead>
                      <tbody>
                        {rows.map((p) => (
                          <tr key={p.id}>
                            <td><div className="font-medium text-ink">{p.name}</div><div className="text-[11.5px] text-faint">{p.id}</div></td>
                            <td>{p.asset_class}</td>
                            <td>{p.currency}</td>
                            <td className="r">{num(p.mv_local, 0)}</td>
                            <td className="r">{p.fx_rate === 1 ? "1" : num(p.fx_rate, 4)}</td>
                            <td className={`r ${p.mv_base !== null && p.mv_base < 0 ? "text-loss" : ""}`}>{eur(p.mv_base)}</td>
                            <td className="r">{p.ytm !== null ? pct(p.ytm) : ""}</td>
                            <td className="r">{p.modified_duration !== null ? num(p.modified_duration) : ""}</td>
                            <td className="text-[11.5px]">
                              {p.excluded ? <Badge tone="loss">Excluded</Badge> : [p.eq_factor, p.fx_factor, ...p.ir_factors, p.cs_factor].filter(Boolean).join(", ") || <span className="text-faint">none (EUR cash)</span>}
                              {p.excluded && <div className="mt-0.5 max-w-[240px] text-loss">{p.excluded}</div>}
                              {p.warnings.length > 0 && <div className="mt-0.5 max-w-[240px] text-warn">{p.warnings.join(" ")}</div>}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </Panel>
                <div className="min-w-0 space-y-4 xl:col-span-4">
                  <Panel title="Exposure breakdown" aside={
                    <select aria-label="Group by" className="rounded-sm border border-line-strong bg-panel px-2 py-1 text-[12.5px]" value={group} onChange={(ev) => setGroup(ev.target.value as typeof group)}>
                      {GROUPS.map((g) => <option key={g.value} value={g.value}>{g.label}</option>)}
                    </select>
                  } pad={false}>
                    <table className="dense w-full">
                      <thead><tr><th>{GROUPS.find((g) => g.value === group)?.label}</th><th className="r">Net</th><th className="r">Gross</th><th className="r">Share</th></tr></thead>
                      <tbody>
                        {e.groups[group].map((g) => (
                          <tr key={g.key}>
                            <td>{g.key}</td>
                            <td className="r">{compactEur(g.net)}</td>
                            <td className="r">{compactEur(g.gross)}</td>
                            <td className="r"><div className="flex items-center justify-end gap-2"><span className="inline-block h-1.5 bg-accent" style={{ width: `${Math.round((g.pct_gross ?? 0) * 60)}px` }} />{pct(g.pct_gross, 1)}</div></td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    <p className="px-4 py-2 text-[12px] text-faint">Share of gross market value. Currency rows show the denomination of each position, i.e. the FX exposure against EUR.</p>
                  </Panel>
                  <Panel title={<span className="flex items-center gap-2">Factor sensitivities <MethodButton k="sensitivity" /></span>} pad={false}>
                    <div className="max-h-[320px] overflow-auto">
                      <table className="dense w-full">
                        <thead><tr><th>Factor</th><th className="r">Sensitivity</th><th>Unit</th></tr></thead>
                        <tbody>
                          {e.sensitivities.map((s) => (
                            <tr key={s.factor}><td>{s.factor}</td><td className={`r ${s.sensitivity < 0 ? "text-loss" : ""}`}>{eur(s.sensitivity)}</td><td className="text-[11.5px] text-faint">{s.unit.replace("EUR ", "")}</td></tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </Panel>
                </div>
              </div>
            </div>
          )}
        </>
      )}
    </>
  );
}
