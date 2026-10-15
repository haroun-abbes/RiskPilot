"use client";
import dynamic from "next/dynamic";
import type { EChartsOption } from "echarts";

const ReactECharts = dynamic(() => import("echarts-for-react"), { ssr: false, loading: () => <div className="h-full w-full animate-pulse bg-canvas" /> });

export const C = {
  ink: "#14213d",
  accent: "#2c5bd9",
  accent2: "#7a95e0",
  loss: "#b42318",
  gain: "#11734a",
  warn: "#a15c07",
  grid: "#e6e9ef",
  muted: "#5b6475",
  faint: "#8a93a3",
  series: ["#2c5bd9", "#14213d", "#0f8a8a", "#a15c07", "#7a4fc9", "#b42318", "#5b6475", "#11734a"],
};

const base: EChartsOption = {
  textStyle: { fontFamily: "IBM Plex Sans, system-ui, sans-serif", color: C.muted, fontSize: 11.5 },
  color: C.series,
  animationDuration: 250,
  grid: { left: 8, right: 16, top: 24, bottom: 8, containLabel: true },
  tooltip: { trigger: "axis", backgroundColor: "#fff", borderColor: "#c4ccd8", textStyle: { color: "#1a2233", fontSize: 12 }, confine: true },
};

export function Chart({ option, height = 260, ariaLabel }: { option: EChartsOption; height?: number; ariaLabel: string }) {
  return (
    <div style={{ height }} role="img" aria-label={ariaLabel}>
      <ReactECharts option={{ ...base, ...option, grid: { ...(base.grid as object), ...((option.grid as object) ?? {}) } }} style={{ height: "100%", width: "100%" }} notMerge lazyUpdate opts={{ renderer: "canvas" }} />
    </div>
  );
}

export const axis = {
  value: (name?: string, fmt?: (v: number) => string) => ({
    type: "value" as const,
    name,
    nameTextStyle: { color: C.faint, fontSize: 11 },
    splitLine: { lineStyle: { color: C.grid } },
    axisLabel: fmt ? { formatter: fmt } : {},
  }),
};

export const kfmt = (v: number) => (Math.abs(v) >= 1e6 ? `${(v / 1e6).toFixed(1)}M` : Math.abs(v) >= 1e3 ? `${(v / 1e3).toFixed(0)}k` : `${v.toFixed(0)}`);
