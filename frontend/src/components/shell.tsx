"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState, useSyncExternalStore, type ReactNode } from "react";
import { useGet } from "@/lib/api";
import { useCtx } from "@/lib/store";
import { inputCls } from "./ui";

const NAV: { href: string; label: string; group: string }[] = [
  { href: "/overview", label: "Overview", group: "Monitor" },
  { href: "/portfolio", label: "Portfolio", group: "Monitor" },
  { href: "/risk", label: "Risk Analytics", group: "Analyse" },
  { href: "/stress", label: "Stress Lab", group: "Analyse" },
  { href: "/fixed-income", label: "Fixed Income", group: "Analyse" },
  { href: "/attribution", label: "Risk Attribution", group: "Analyse" },
  { href: "/market", label: "Market Watch", group: "Monitor" },
  { href: "/reports", label: "Reports", group: "Communicate" },
  { href: "/data", label: "Data Sources", group: "Configure" },
  { href: "/settings", label: "Settings", group: "Configure" },
];
const ORDER = ["/overview", "/portfolio", "/risk", "/stress", "/fixed-income", "/market", "/attribution", "/reports", "/data", "/settings"];

export type PortfolioItem = { id: string; name: string; as_of: string; provenance: string; n_positions: number };
export type DatasetItem = { id: string; name: string; provenance: string; provenance_label: string; end: string; start: string; source: string };

function Logo() {
  // Mark: a descending tail cut by a threshold line - the VaR picture.
  return (
    <svg width="22" height="22" viewBox="0 0 22 22" aria-hidden>
      <rect x="0.5" y="0.5" width="21" height="21" rx="3" fill="none" stroke="#7f93c4" />
      <path d="M3 17 C7 17 8 5 11 5 C14 5 15 15 19 17" fill="none" stroke="#fff" strokeWidth="1.6" />
      <line x1="15" y1="3" x2="15" y2="19" stroke="#f2b45a" strokeWidth="1.4" />
    </svg>
  );
}

function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  const path = usePathname();
  return (
    <nav aria-label="Main" className="flex h-full flex-col bg-ink text-[13.5px] text-[#c9d2e6]">
      <div className="flex items-center gap-2.5 px-5 py-5 text-white">
        <Logo />
        <span className="text-[16px] font-semibold tracking-[-0.01em]">RiskPilot</span>
      </div>
      <ul className="flex-1 px-3">
        {ORDER.map((h) => {
          const n = NAV.find((x) => x.href === h)!;
          const active = path?.startsWith(h);
          return (
            <li key={h}>
              <Link href={h} onClick={onNavigate} aria-current={active ? "page" : undefined} className={`my-[1px] block rounded-sm px-3 py-[7px] ${active ? "bg-[#26375e] text-white" : "hover:bg-[#1c2b4d] hover:text-white"}`}>
                {n.label}
              </Link>
            </li>
          );
        })}
      </ul>
      <p className="px-5 pb-5 text-[11.5px] leading-snug text-[#8796b8]">Analysis and simulation only. No order execution, no investment advice.</p>
    </nav>
  );
}

function ContextBar() {
  const c = useCtx();
  const { data: pfs } = useGet<PortfolioItem[]>("/api/portfolios");
  const { data: dss, error } = useGet<DatasetItem[]>("/api/datasets");
  const ds = dss?.find((d) => d.id === c.datasetId);
  const pf = pfs?.find((p) => p.id === c.portfolioId);
  // fall back to an existing selection if the stored one was deleted
  useEffect(() => {
    if (pfs && pfs.length && !pf) c.set({ portfolioId: pfs[0].id });
    if (dss && dss.length && !ds) c.set({ datasetId: dss[0].id });
  }, [pfs, dss, pf, ds, c]);
  const synthetic = ds?.provenance === "SYNTHETIC" || pf?.provenance === "SYNTHETIC";
  return (
    <div className={`${synthetic ? "prov-synthetic" : "prov-real"} px-4 py-2.5 lg:px-6`}>
      <div className="flex flex-wrap items-end gap-x-4 gap-y-2 text-[12px] text-muted">
        <label className="flex flex-col gap-0.5">
          Portfolio
          <select className={`${inputCls} max-w-[260px]`} value={c.portfolioId} onChange={(e) => c.set({ portfolioId: e.target.value })}>
            {pfs?.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name} ({p.as_of})
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-0.5">
          Market data
          <select className={`${inputCls} max-w-[240px]`} value={c.datasetId} onChange={(e) => c.set({ datasetId: e.target.value })}>
            {dss?.map((d) => (
              <option key={d.id} value={d.id}>
                {d.name}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-0.5">
          Confidence
          <select className={inputCls} value={c.confidence} onChange={(e) => c.set({ confidence: Number(e.target.value) })}>
            {Array.from(new Set([0.95, 0.975, 0.99, c.confidence])).sort().map((x) => <option key={x} value={x}>{+(x * 100).toFixed(2)}%</option>)}
          </select>
        </label>
        <label className="flex flex-col gap-0.5">
          Horizon
          <select className={inputCls} value={c.horizon} onChange={(e) => c.set({ horizon: Number(e.target.value) })}>
            {Array.from(new Set([1, 5, 10, c.horizon])).sort((a, b) => a - b).map((x) => <option key={x} value={x}>{x} day{x > 1 ? "s" : ""}</option>)}
          </select>
        </label>
        <label className="flex flex-col gap-0.5">
          Window
          <select className={inputCls} value={c.window} onChange={(e) => c.set({ window: Number(e.target.value) })}>
            {Array.from(new Set([250, 500, 750, c.window])).sort((a, b) => a - b).map((x) => <option key={x} value={x}>{x} days</option>)}
          </select>
        </label>
        <div className="ml-auto max-w-[420px] text-right text-[12px] leading-snug">
          {error ? (
            <span className="font-medium text-loss">Backend unreachable: no figures can be computed.</span>
          ) : ds ? (
            <>
              <span className={`font-semibold ${synthetic ? "text-[#7a4504]" : "text-ink"}`}>{synthetic ? "Synthetic data, not market prices" : ds.provenance_label}</span>
              <br />
              {ds.source}, {ds.start} to {ds.end}. Valuation date {pf?.as_of ?? "n/a"}.
            </>
          ) : null}
        </div>
      </div>
    </div>
  );
}

export function Shell({ children }: { children: ReactNode }) {
  const [menu, setMenu] = useState(false);
  // render only after the persisted analysis context has been restored
  const ready = useSyncExternalStore(
    (cb) => useCtx.persist.onFinishHydration(cb),
    () => useCtx.persist.hasHydrated(),
    () => false,
  );
  return (
    <div className="flex min-h-screen">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:bg-panel focus:px-3 focus:py-2">
        Skip to content
      </a>
      <aside className="sticky top-0 hidden h-screen w-[220px] shrink-0 lg:block">
        <Sidebar />
      </aside>
      {menu && (
        <div className="fixed inset-0 z-40 flex lg:hidden" onClick={() => setMenu(false)}>
          <div className="h-full w-[240px]" onClick={(e) => e.stopPropagation()}>
            <Sidebar onNavigate={() => setMenu(false)} />
          </div>
          <div className="flex-1 bg-ink/30" />
        </div>
      )}
      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex items-center gap-3 bg-ink px-4 py-2.5 text-white lg:hidden">
          <button onClick={() => setMenu(true)} className="rounded-sm border border-[#3a4a70] px-2 py-1 text-[13px]" aria-label="Open navigation">
            Menu
          </button>
          <span className="font-semibold">RiskPilot</span>
        </div>
        <div className="z-30 lg:sticky lg:top-0">{ready && <ContextBar />}</div>
        <main id="main" className="mx-auto w-full max-w-[1440px] flex-1 px-4 py-6 lg:px-6">
          {ready ? children : null}
        </main>
      </div>
    </div>
  );
}
