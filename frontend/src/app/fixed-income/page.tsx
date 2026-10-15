"use client";
import { useState } from "react";
import { api, useGet, usePostQuery } from "@/lib/api";
import { useCtx } from "@/lib/store";
import type { BondReport } from "@/lib/types";
import { num, pct } from "@/lib/format";
import { Badge, Button, ErrorBox, Field, inputCls, Loading, Metric, MethodButton, PageHeader, Panel, Tabs } from "@/components/ui";
import { axis, C, Chart } from "@/components/chart";
import type { PortfolioItem } from "@/components/shell";

type PBond = { id: string; name: string; issuer: string; rating: string | null; currency: string; nominal: number; clean_price: number; coupon_pct: number; frequency: number; daycount: string; maturity: string; is_sovereign: boolean; analytics?: BondReport["analytics"]; spread: BondReport["spread"]; error?: string };
type Form = { maturity: string; coupon_pct: string; frequency: string; daycount: string; settlement: string; mode: "price" | "yield"; clean_price: string; ytm_pct: string; currency: string; label: string };

const DAYCOUNTS = ["ACT/ACT ICMA", "30E/360", "30/360", "ACT/365F", "ACT/360"];

function toBody(f: Form, datasetId: string) {
  return {
    maturity: f.maturity,
    coupon_pct: Number(f.coupon_pct),
    frequency: Number(f.frequency),
    daycount: f.daycount,
    settlement: f.settlement,
    clean_price: f.mode === "price" ? Number(f.clean_price) : null,
    ytm_pct: f.mode === "yield" ? Number(f.ytm_pct) : null,
    currency: f.currency || null,
    dataset_id: f.currency ? datasetId : null,
    label: f.label || null,
  };
}

export default function FixedIncome() {
  const c = useCtx();
  const [tab, setTab] = useState<"calc" | "book" | "compare">("calc");
  const [form, setForm] = useState<Form>({ maturity: "2036-06-15", coupon_pct: "5", frequency: "1", daycount: "30E/360", settlement: "2026-10-14", mode: "yield", clean_price: "100", ytm_pct: "6", currency: "EUR", label: "" });
  const [submitted, setSubmitted] = useState(toBody(form, c.datasetId));
  const calc = usePostQuery<BondReport>(tab === "calc" ? "/api/bonds/analytics" : null, submitted);
  const book = useGet<{ bonds: PBond[] }>(`/api/portfolios/${c.portfolioId}/bonds?dataset_id=${c.datasetId}`);
  const { data: pfs } = useGet<PortfolioItem[]>("/api/portfolios");
  const asOf = pfs?.find((p) => p.id === c.portfolioId)?.as_of ?? form.settlement;
  const [cmpIds, setCmpIds] = useState<string[]>([]);
  const [cmp, setCmp] = useState<BondReport[] | null>(null);
  const [cmpErr, setCmpErr] = useState<Error | null>(null);

  const set = (k: keyof Form, v: string) => setForm({ ...form, [k]: v });
  const analyse = (b: PBond) => {
    const f: Form = { maturity: b.maturity, coupon_pct: String(b.coupon_pct), frequency: String(b.frequency), daycount: b.daycount, settlement: asOf, mode: "price", clean_price: String(b.clean_price), ytm_pct: "", currency: b.currency, label: b.name };
    setForm(f);
    setSubmitted(toBody(f, c.datasetId));
    setTab("calc");
  };
  async function runCompare() {
    setCmpErr(null);
    const bonds = (book.data?.bonds ?? []).filter((b) => cmpIds.includes(b.id)).map((b) => ({ maturity: b.maturity, coupon_pct: b.coupon_pct, frequency: b.frequency, daycount: b.daycount, settlement: asOf, clean_price: b.clean_price, currency: b.currency, dataset_id: c.datasetId, label: b.name }));
    try {
      setCmp(await api.post<BondReport[]>("/api/bonds/compare", { bonds }));
    } catch (e) {
      setCmpErr(e as Error);
    }
  }

  return (
    <>
      <PageHeader
        title="Fixed income"
        lead="Fixed-rate bullet bonds: price, yield, accrued interest, duration, convexity and spread to the government curve."
        actions={<Tabs value={tab} onChange={setTab} items={[{ value: "calc", label: "Bond calculator" }, { value: "book", label: "Bonds in portfolio" }, { value: "compare", label: "Compare" }]} />}
      />
      {tab === "calc" && (
        <div className="space-y-4">
          <Panel title="Bond terms">
            <form className="flex flex-wrap items-end gap-4" onSubmit={(e) => { e.preventDefault(); setSubmitted(toBody(form, c.datasetId)); }}>
              <Field label="Settlement"><input type="date" className={inputCls} value={form.settlement} onChange={(e) => set("settlement", e.target.value)} /></Field>
              <Field label="Maturity"><input type="date" className={inputCls} value={form.maturity} onChange={(e) => set("maturity", e.target.value)} /></Field>
              <Field label="Coupon (% p.a.)"><input inputMode="decimal" className={`${inputCls} num w-[90px]`} value={form.coupon_pct} onChange={(e) => set("coupon_pct", e.target.value)} /></Field>
              <Field label="Frequency"><select className={inputCls} value={form.frequency} onChange={(e) => set("frequency", e.target.value)}>{[["1", "Annual"], ["2", "Semi-annual"], ["4", "Quarterly"], ["12", "Monthly"]].map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></Field>
              <Field label="Day count"><select className={inputCls} value={form.daycount} onChange={(e) => set("daycount", e.target.value)}>{DAYCOUNTS.map((d) => <option key={d}>{d}</option>)}</select></Field>
              <Field label="Solve from"><Tabs value={form.mode} onChange={(v) => set("mode", v)} items={[{ value: "yield", label: "Yield" }, { value: "price", label: "Clean price" }]} /></Field>
              {form.mode === "yield" ? (
                <Field label="Yield (%)"><input inputMode="decimal" className={`${inputCls} num w-[90px]`} value={form.ytm_pct} onChange={(e) => set("ytm_pct", e.target.value)} /></Field>
              ) : (
                <Field label="Clean price (% of par)"><input inputMode="decimal" className={`${inputCls} num w-[100px]`} value={form.clean_price} onChange={(e) => set("clean_price", e.target.value)} /></Field>
              )}
              <Field label="Curve for spread"><select className={inputCls} value={form.currency} onChange={(e) => set("currency", e.target.value)}><option value="">None</option><option>EUR</option><option>USD</option></select></Field>
              <Button variant="primary" type="submit">Calculate</Button>
            </form>
          </Panel>
          {calc.error && <ErrorBox error={calc.error} />}
          {!calc.data && !calc.error && <Loading />}
          {calc.data && <BondResult b={calc.data} />}
        </div>
      )}

      {tab === "book" && (
        <Panel title="Fixed-rate bonds in the selected portfolio" pad={false} aside={<MethodButton k="gspread" />}>
          {book.error && <div className="p-4"><ErrorBox error={book.error} /></div>}
          {!book.data && !book.error && <Loading />}
          {book.data && book.data.bonds.length === 0 && <p className="p-4 text-[13px] text-muted">This portfolio holds no fixed-rate bond.</p>}
          {book.data && book.data.bonds.length > 0 && (
            <div className="overflow-auto">
              <table className="dense w-full min-w-[1000px]">
                <thead><tr><th>Bond</th><th>Rating</th><th className="r">Nominal</th><th className="r">Clean</th><th className="r">Accrued</th><th className="r">Yield</th><th className="r">G-spread</th><th className="r">Mod. dur.</th><th className="r">Convexity</th><th className="r">DV01 / 100</th><th /></tr></thead>
                <tbody>
                  {book.data.bonds.map((b) => (
                    <tr key={b.id}>
                      <td><div className="font-medium text-ink">{b.name}</div><div className="text-[11.5px] text-faint">{b.currency}, {b.daycount}, {b.frequency === 1 ? "annual" : b.frequency === 2 ? "semi-annual" : `${b.frequency}/yr`}, matures {b.maturity}</div></td>
                      <td>{b.is_sovereign ? <Badge>Sovereign</Badge> : b.rating ?? "n/a"}</td>
                      <td className="r">{num(b.nominal, 0)}</td>
                      <td className="r">{num(b.clean_price, 3)}</td>
                      <td className="r">{num(b.analytics?.accrued_interest, 4)}</td>
                      <td className="r">{pct(b.analytics?.yield_to_maturity, 3)}</td>
                      <td className="r">{b.spread ? `${b.spread.spread_bp.toFixed(1)} bp` : "n/a"}</td>
                      <td className="r">{num(b.analytics?.modified_duration)}</td>
                      <td className="r">{num(b.analytics?.convexity, 1)}</td>
                      <td className="r">{num(b.analytics?.dv01, 4)}</td>
                      <td><button className="text-[12.5px] text-accent hover:underline" onClick={() => analyse(b)}>Analyse</button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Panel>
      )}

      {tab === "compare" && (
        <div className="space-y-4">
          <Panel title="Select bonds to compare" aside={<Button variant="primary" disabled={cmpIds.length === 0} onClick={runCompare}>Compare {cmpIds.length || ""}</Button>}>
            <div className="flex flex-wrap gap-x-6 gap-y-2">
              {book.data?.bonds.map((b) => (
                <label key={b.id} className="flex items-center gap-2 text-[13px]">
                  <input type="checkbox" className="accent-[#14213d]" checked={cmpIds.includes(b.id)} onChange={() => setCmpIds(cmpIds.includes(b.id) ? cmpIds.filter((x) => x !== b.id) : [...cmpIds, b.id].slice(0, 8))} />
                  {b.name}
                </label>
              ))}
            </div>
          </Panel>
          {cmpErr && <ErrorBox error={cmpErr} />}
          {cmp && <Compare items={cmp} />}
        </div>
      )}
    </>
  );
}

function BondResult({ b }: { b: BondReport }) {
  const a = b.analytics;
  return (
    <>
      <Panel title={b.label} aside={<span>Previous coupon {b.previous_coupon}, next {b.next_coupon}</span>}>
        <div className="grid grid-cols-2 gap-6 md:grid-cols-4 xl:grid-cols-8">
          <Metric label="Yield to maturity" method="ytm" value={pct(a.yield_to_maturity, 4)} emphasis />
          <Metric label="Clean price" value={num(a.clean_price, 4)} sub="% of par" />
          <Metric label="Accrued interest" value={num(a.accrued_interest, 4)} sub="% of par" />
          <Metric label="Dirty price" value={num(a.dirty_price, 4)} sub="Clean + accrued" />
          <Metric label="Macaulay duration" method="duration" value={num(a.macaulay_duration, 4)} sub="years" />
          <Metric label="Modified duration" value={num(a.modified_duration, 4)} sub={`Check (±1bp): ${num(a.effective_duration, 4)}`} />
          <Metric label="Convexity" value={num(a.convexity, 2)} sub={`Check: ${num(a.effective_convexity, 2)}`} />
          <Metric label="DV01 per 100" value={num(a.dv01, 5)} sub="Price change for 1bp" />
        </div>
        <p className="mt-4 max-w-4xl border-t border-line pt-3 text-[12.5px] text-muted">
          The buyer pays the dirty price: the clean (quoted) price plus the coupon accrued since {b.previous_coupon} under {b.inputs.daycount}. Quoting clean removes the saw-tooth caused by coupon payments, so price changes reflect yield changes only.
          {b.spread && <> The yield of {pct(a.yield_to_maturity, 3)} splits into a government benchmark of {pct(b.spread.benchmark_yield, 3)} (curve of {b.spread.curve_date}) and a G-spread of {b.spread.spread_bp.toFixed(1)} bp; the benchmark is not a risk-free rate in the strict sense and the spread is not a pure credit spread.</>}
        </p>
      </Panel>
      <div className="grid gap-4 xl:grid-cols-2">
        <Panel title="Price sensitivity to a yield change" aside={<span>Dirty price, % of par</span>}>
          <Chart
            height={290}
            ariaLabel="Exact bond price versus duration and duration-convexity approximations across yield shifts"
            option={{
              tooltip: { trigger: "axis", valueFormatter: (v) => num(v as number, 3) },
              legend: { top: 0, right: 0, textStyle: { fontSize: 11.5 } },
              grid: { top: 32, bottom: 30 },
              xAxis: { type: "category", data: b.sensitivity_curve.map((s) => s.dy_bp), name: "Δy (bp)", nameLocation: "middle", nameGap: 26, axisLabel: { interval: 9 } },
              yAxis: { ...axis.value(), scale: true },
              series: [
                { name: "Exact repricing", type: "line", data: b.sensitivity_curve.map((s) => s.exact), symbol: "none", lineStyle: { color: C.ink, width: 2 } },
                { name: "Duration only", type: "line", data: b.sensitivity_curve.map((s) => s.duration), symbol: "none", lineStyle: { color: C.loss, type: "dashed", width: 1.4 } },
                { name: "Duration + convexity", type: "line", data: b.sensitivity_curve.map((s) => s.duration_convexity), symbol: "none", lineStyle: { color: C.accent, type: "dotted", width: 1.8 } },
              ],
            }}
          />
          <p className="mt-1 text-[12.5px] text-muted">Error of the approximations at ±200bp: duration {num(b.sensitivity_curve[10].duration - b.sensitivity_curve[10].exact, 3)} / {num(b.sensitivity_curve[50].duration - b.sensitivity_curve[50].exact, 3)}, with convexity {num(b.sensitivity_curve[10].duration_convexity - b.sensitivity_curve[10].exact, 3)} / {num(b.sensitivity_curve[50].duration_convexity - b.sensitivity_curve[50].exact, 3)} points of par.</p>
        </Panel>
        {b.spread ? (
          <Panel title={<span className="flex items-center gap-2">Yield against the government curve <MethodButton k="gspread" /></span>} aside={<span>Curve of {b.spread.curve_date}</span>}>
            <Chart
              height={290}
              ariaLabel="Government curve with the bond's yield plotted at its maturity"
              option={{
                tooltip: { trigger: "item", formatter: (p: unknown) => { const v = (p as { value: number[]; seriesName: string }).value; return `${(p as { seriesName: string }).seriesName}: ${v[0].toFixed(2)}y, ${(v[1] * 100).toFixed(3)}%`; } },
                legend: { top: 0, right: 0, textStyle: { fontSize: 11.5 } },
                grid: { top: 32, bottom: 30 },
                xAxis: { type: "value", name: "Maturity (years)", nameLocation: "middle", nameGap: 26, splitLine: { show: false } },
                yAxis: axis.value(undefined, (v) => `${(v * 100).toFixed(2)}%`),
                series: [
                  { name: "Government curve", type: "line", data: b.spread.curve.map((p) => [p.tenor_years, p.yield]), symbolSize: 6, lineStyle: { color: C.ink } },
                  { name: "This bond", type: "scatter", data: [[b.cash_flows[b.cash_flows.length - 1].time_years, a.yield_to_maturity]], symbolSize: 11, itemStyle: { color: C.loss } },
                ],
              }}
            />
            <p className="mt-1 text-[12.5px] text-muted">{b.spread.note}</p>
          </Panel>
        ) : (
          <Panel title="Spread"><p className="text-[13px] text-muted">Choose a curve currency to compute the spread against the dataset&apos;s government curve.</p></Panel>
        )}
      </div>
      <Panel title="Cash flows" pad={false} aside={<span>Per 100 of nominal</span>}>
        <div className="max-h-[360px] overflow-auto">
          <table className="dense w-full">
            <thead><tr><th>Payment date</th><th>Type</th><th className="r">Time (years)</th><th className="r">Amount</th><th className="r">Discount factor</th><th className="r">Present value</th></tr></thead>
            <tbody>
              {b.cash_flows.map((f) => (
                <tr key={f.date}><td className="num">{f.date}</td><td>{f.type === "coupon" ? "Coupon" : "Coupon + redemption"}</td><td className="r">{num(f.time_years, 4)}</td><td className="r">{num(f.amount, 4)}</td><td className="r">{num(f.discount_factor, 6)}</td><td className="r">{num(f.present_value, 4)}</td></tr>
              ))}
              <tr className="font-semibold"><td colSpan={5}>Sum = dirty price</td><td className="r">{num(b.cash_flows.reduce((s, f) => s + f.present_value, 0), 4)}</td></tr>
            </tbody>
          </table>
        </div>
      </Panel>
    </>
  );
}

function Compare({ items }: { items: BondReport[] }) {
  return (
    <>
      <Panel title="Side by side" pad={false}>
        <div className="overflow-auto">
          <table className="dense w-full min-w-[820px]">
            <thead><tr><th>Bond</th><th className="r">Yield</th><th className="r">G-spread</th><th className="r">Clean</th><th className="r">Mod. dur.</th><th className="r">Convexity</th><th className="r">DV01 / 100</th><th className="r">Price change −100bp</th><th className="r">+100bp</th></tr></thead>
            <tbody>
              {items.map((b) => {
                const at = (bpv: number) => b.sensitivity_curve.find((s) => s.dy_bp === bpv)!.exact / b.analytics.dirty_price - 1;
                return (
                  <tr key={b.label}><td className="font-medium text-ink">{b.label}</td><td className="r">{pct(b.analytics.yield_to_maturity, 3)}</td><td className="r">{b.spread ? `${b.spread.spread_bp.toFixed(1)} bp` : "n/a"}</td><td className="r">{num(b.analytics.clean_price, 3)}</td><td className="r">{num(b.analytics.modified_duration)}</td><td className="r">{num(b.analytics.convexity, 1)}</td><td className="r">{num(b.analytics.dv01, 4)}</td><td className="r text-gain">{pct(at(-100))}</td><td className="r text-loss">{pct(at(100))}</td></tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Panel>
      <Panel title="Relative price change against a parallel yield shift" aside={<span>Exact repricing</span>}>
        <Chart
          height={320}
          ariaLabel="Relative price change of each selected bond across yield shifts"
          option={{
            tooltip: { trigger: "axis", valueFormatter: (v) => `${(v as number).toFixed(2)}%` },
            legend: { top: 0, type: "scroll", textStyle: { fontSize: 11.5 } },
            grid: { top: 36, bottom: 30 },
            xAxis: { type: "category", data: items[0].sensitivity_curve.map((s) => s.dy_bp), name: "Δy (bp)", nameLocation: "middle", nameGap: 26, axisLabel: { interval: 9 } },
            yAxis: axis.value("%", (v) => `${v.toFixed(0)}%`),
            series: items.map((b) => ({ name: b.label, type: "line", symbol: "none", data: b.sensitivity_curve.map((s) => (s.exact / b.analytics.dirty_price - 1) * 100) })),
          }}
        />
      </Panel>
      <p className="text-[12px] text-faint">Each bond is shifted by its own yield; this ignores curve shape and spread differences between issuers.</p>
    </>
  );
}
