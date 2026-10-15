"use client";
import { axis, C, Chart, kfmt } from "./chart";
import type { RiskSummary } from "@/lib/types";
import { eur } from "@/lib/format";

/** Histogram of 1-day P&L scenarios with -VaR and -ES markers (1-day, same scale as the data). */
export function DistributionChart({ r, height = 260 }: { r: RiskSummary; height?: number }) {
  const { edges, counts } = r.distribution;
  if (!edges.length) return null;
  const mids = counts.map((_, i) => (edges[i] + edges[i + 1]) / 2);
  const var1 = r.historical.var_1d;
  const es1 = r.historical.es_1d;
  const data = counts.map((c, i) => ({ value: [mids[i], c], itemStyle: { color: var1 !== undefined && edges[i + 1] <= -var1 ? C.loss : "#9fb3e6" } }));
  const lines: { name: string; xAxis: number; lineStyle: object; label: object }[] = [];
  if (var1 !== undefined) lines.push({ name: "VaR", xAxis: -var1, lineStyle: { color: C.loss, type: "solid" }, label: { formatter: `−VaR ${kfmt(var1)}`, color: C.loss } });
  if (es1 !== undefined) lines.push({ name: "ES", xAxis: -es1, lineStyle: { color: C.ink, type: "dashed" }, label: { formatter: `−ES ${kfmt(es1)}`, color: C.ink, position: "insideStartTop" } });
  const w = edges[1] - edges[0];
  return (
    <Chart
      height={height}
      ariaLabel="Distribution of daily portfolio P&L scenarios with VaR and ES thresholds"
      option={{
        tooltip: { trigger: "item", formatter: (p: unknown) => { const v = (p as { value: number[] }).value; return `P&L ${eur(v[0] - w / 2)} to ${eur(v[0] + w / 2)}<br/>${v[1]} days`; } },
        xAxis: { type: "value", scale: true, axisLabel: { formatter: kfmt }, splitLine: { show: false }, name: "1-day P&L (EUR)", nameLocation: "middle", nameGap: 24, nameTextStyle: { color: C.faint } },
        yAxis: axis.value("days"),
        grid: { bottom: 24 },
        series: [{ type: "bar", data, barWidth: "96%", markLine: { symbol: "none", silent: true, data: lines } }],
      }}
    />
  );
}

export function BacktestChart({ r, height = 260 }: { r: RiskSummary; height?: number }) {
  const bt = r.backtest;
  if (!bt) return null;
  return (
    <Chart
      height={height}
      ariaLabel="Daily P&L against minus one-day VaR over the backtest period"
      option={{
        tooltip: { trigger: "axis", valueFormatter: (v) => eur(v as number) },
        legend: { top: 0, right: 0, textStyle: { fontSize: 11.5 }, itemWidth: 14 },
        xAxis: { type: "category", data: bt.series.map((s) => s.date), axisLabel: { hideOverlap: true } },
        yAxis: axis.value(undefined, kfmt),
        grid: { top: 30 },
        series: [
          { name: "Daily P&L (constant holdings)", type: "bar", data: bt.series.map((s) => ({ value: s.pnl, itemStyle: { color: -s.pnl > s.var ? C.loss : "#b6c4e8" } })), barCategoryGap: "10%" },
          { name: "−VaR (previous window)", type: "line", data: bt.series.map((s) => -s.var), symbol: "none", lineStyle: { color: C.ink, width: 1.4 } },
        ],
      }}
    />
  );
}

export function BackcastChart({ r, height = 220 }: { r: RiskSummary; height?: number }) {
  return (
    <Chart
      height={height}
      ariaLabel="Cumulative P&L of current holdings replayed over the dataset history"
      option={{
        tooltip: { trigger: "axis", valueFormatter: (v) => eur(v as number) },
        xAxis: { type: "category", data: r.backcast.map((x) => x.date), axisLabel: { hideOverlap: true } },
        yAxis: axis.value(undefined, kfmt),
        dataZoom: [{ type: "inside" }],
        series: [{ type: "line", data: r.backcast.map((x) => x.cum_pnl), symbol: "none", lineStyle: { color: C.accent, width: 1.4 }, areaStyle: { color: "rgba(44,91,217,0.07)" } }],
      }}
    />
  );
}

export function HBar({ items, height, valueFmt = kfmt, ariaLabel }: { items: { label: string; value: number }[]; height?: number; valueFmt?: (v: number) => string; ariaLabel: string }) {
  const h = height ?? Math.max(140, items.length * 26 + 40);
  const rev = [...items].reverse();
  return (
    <Chart
      height={h}
      ariaLabel={ariaLabel}
      option={{
        tooltip: { trigger: "axis", axisPointer: { type: "shadow" }, valueFormatter: (v) => eur(v as number) },
        xAxis: axis.value(undefined, valueFmt),
        yAxis: { type: "category", data: rev.map((i) => i.label), axisLabel: { width: 170, overflow: "truncate" }, axisTick: { show: false } },
        series: [{ type: "bar", data: rev.map((i) => ({ value: i.value, itemStyle: { color: i.value < 0 ? C.gain : C.accent } })), barWidth: 14 }],
      }}
    />
  );
}
