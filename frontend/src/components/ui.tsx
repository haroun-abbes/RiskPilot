"use client";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { METHODS } from "@/lib/methods";
import type { ApiError } from "@/lib/api";

export function PageHeader({ title, lead, actions }: { title: string; lead?: ReactNode; actions?: ReactNode }) {
  return (
    <header className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div className="max-w-3xl">
        <h1 className="text-[22px] font-semibold tracking-[-0.01em] text-ink">{title}</h1>
        {lead && <p className="mt-1 text-[13.5px] text-muted">{lead}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </header>
  );
}

export function Panel({ title, aside, children, className = "", pad = true }: { title?: ReactNode; aside?: ReactNode; children: ReactNode; className?: string; pad?: boolean }) {
  return (
    <section className={`min-w-0 rounded-md border border-line bg-panel ${className}`}>
      {(title || aside) && (
        <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1 border-b border-line px-4 py-2.5">
          <h2 className="text-[13.5px] font-semibold text-ink">{title}</h2>
          {aside && <div className="flex flex-wrap items-center gap-2 text-[12px] text-muted">{aside}</div>}
        </div>
      )}
      <div className={pad ? "p-4" : ""}>{children}</div>
    </section>
  );
}

export function Metric({ label, value, sub, method, toneClass = "", emphasis = false }: { label: string; value: ReactNode; sub?: ReactNode; method?: string; toneClass?: string; emphasis?: boolean }) {
  return (
    <div className="min-w-0">
      <div className="flex items-center gap-1.5 text-[12.5px] text-muted">
        <span>{label}</span>
        {method && <MethodButton k={method} />}
      </div>
      <div className={`num mt-0.5 ${emphasis ? "text-[26px]" : "text-[19px]"} font-semibold leading-tight text-ink ${toneClass}`}>{value}</div>
      {sub && <div className="mt-0.5 text-[12px] text-faint">{sub}</div>}
    </div>
  );
}

export function MethodButton({ k, context }: { k: string; context?: ReactNode }) {
  const [open, setOpen] = useState(false);
  const m = METHODS[k];
  if (!m) return null;
  return (
    <>
      <button type="button" onClick={() => setOpen(true)} className="rounded-sm border border-line px-1 text-[10.5px] leading-[15px] text-muted hover:border-accent hover:text-accent" aria-label={`Method: ${m.title}`}>
        Method
      </button>
      {open && <MethodDrawer k={k} onClose={() => setOpen(false)} context={context} />}
    </>
  );
}

function MethodDrawer({ k, onClose, context }: { k: string; onClose: () => void; context?: ReactNode }) {
  const m = METHODS[k];
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    ref.current?.focus();
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-ink/25" onClick={onClose} role="presentation">
      <div ref={ref} tabIndex={-1} role="dialog" aria-modal="true" aria-label={m.title} className="h-full w-full max-w-[460px] overflow-y-auto border-l border-line bg-panel p-6 text-[13.5px] outline-none" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-start justify-between">
          <h3 className="text-[17px] font-semibold text-ink">{m.title}</h3>
          <button onClick={onClose} className="text-muted hover:text-ink" aria-label="Close">
            Close
          </button>
        </div>
        <p className="mt-3 text-text">{m.plain}</p>
        <h4 className="mt-5 text-[12.5px] font-semibold text-muted">Definition</h4>
        <pre className="mt-1 whitespace-pre-wrap rounded-sm border border-line bg-canvas p-3 text-[12.5px] leading-relaxed text-ink">{m.formula}</pre>
        {context && (
          <>
            <h4 className="mt-5 text-[12.5px] font-semibold text-muted">Data used</h4>
            <div className="mt-1 text-text">{context}</div>
          </>
        )}
        <h4 className="mt-5 text-[12.5px] font-semibold text-muted">Assumptions</h4>
        <ul className="mt-1 list-disc space-y-1 pl-5">{m.assumptions.map((a) => <li key={a}>{a}</li>)}</ul>
        <h4 className="mt-5 text-[12.5px] font-semibold text-muted">Limits of interpretation</h4>
        <ul className="mt-1 list-disc space-y-1 pl-5">{m.limits.map((a) => <li key={a}>{a}</li>)}</ul>
        <p className="mt-6 text-[12px] text-faint">Full derivations and tests: docs/METHODOLOGY.md</p>
      </div>
    </div>
  );
}

export function Notices({ items, title = "Data and model notes" }: { items?: string[]; title?: string }) {
  const [open, setOpen] = useState(false);
  if (!items || items.length === 0) return null;
  const shown = open ? items : items.slice(0, 3);
  return (
    <div className="rounded-md border border-[#ecd3a6] bg-warn-soft px-4 py-3 text-[13px] text-[#6b3f05]">
      <div className="font-medium">{title} ({items.length})</div>
      <ul className="mt-1 list-disc space-y-0.5 pl-5">{shown.map((w, i) => <li key={i}>{w}</li>)}</ul>
      {items.length > 3 && (
        <button className="mt-1 text-[12.5px] underline" onClick={() => setOpen(!open)}>
          {open ? "Show fewer" : `Show all ${items.length}`}
        </button>
      )}
    </div>
  );
}

export function ErrorBox({ error, onRetry }: { error: ApiError | Error; onRetry?: () => void }) {
  return (
    <div role="alert" className="rounded-md border border-[#f1c1bc] bg-loss-soft px-4 py-3 text-[13px] text-loss">
      <div className="font-medium">The request could not be completed</div>
      <div className="mt-0.5 text-[#7a1a12]">{error.message}</div>
      {onRetry && (
        <button onClick={onRetry} className="mt-2 rounded-sm border border-loss px-2 py-0.5 text-[12.5px]">
          Retry
        </button>
      )}
    </div>
  );
}

export function Loading({ label = "Computing" }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 py-8 text-[13px] text-muted" aria-live="polite">
      <span className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-line-strong border-t-accent" />
      {label}…
    </div>
  );
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="rounded-md border border-dashed border-line-strong px-6 py-10 text-center">
      <div className="font-medium text-ink">{title}</div>
      {children && <div className="mx-auto mt-1 max-w-md text-[13px] text-muted">{children}</div>}
    </div>
  );
}

export function Button({ children, variant = "secondary", className = "", ...p }: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "danger" | "ghost" }) {
  const v = {
    primary: "bg-ink text-white hover:bg-ink-2 border-ink",
    secondary: "bg-panel text-ink border-line-strong hover:border-ink",
    danger: "bg-panel text-loss border-[#e6b4ae] hover:border-loss",
    ghost: "border-transparent text-accent hover:bg-accent-soft",
  }[variant];
  return (
    <button {...p} className={`inline-flex items-center gap-1.5 rounded-sm border px-3 py-1.5 text-[13px] font-medium disabled:cursor-not-allowed disabled:opacity-50 ${v} ${className}`}>
      {children}
    </button>
  );
}

export const inputCls = "rounded-sm border border-line-strong bg-panel px-2 py-1.5 text-[13px] text-text focus:border-accent focus:outline-none";

export function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="flex flex-col gap-1 text-[12.5px] text-muted">
      <span>{label}</span>
      {children}
      {hint && <span className="text-[11.5px] text-faint">{hint}</span>}
    </label>
  );
}

export function Tabs<T extends string>({ value, onChange, items }: { value: T; onChange: (v: T) => void; items: { value: T; label: string }[] }) {
  return (
    <div role="tablist" className="inline-flex rounded-sm border border-line-strong bg-panel p-0.5">
      {items.map((i) => (
        <button key={i.value} role="tab" aria-selected={value === i.value} onClick={() => onChange(i.value)} className={`rounded-[2px] px-3 py-1 text-[12.5px] ${value === i.value ? "bg-ink text-white" : "text-muted hover:text-ink"}`}>
          {i.label}
        </button>
      ))}
    </div>
  );
}

export function Badge({ children, tone = "neutral" }: { children: ReactNode; tone?: "neutral" | "warn" | "loss" | "gain" | "accent" }) {
  const t = {
    neutral: "bg-canvas text-muted border-line",
    warn: "bg-warn-soft text-warn border-[#ecd3a6]",
    loss: "bg-loss-soft text-loss border-[#f1c1bc]",
    gain: "bg-gain-soft text-gain border-[#b7dcc8]",
    accent: "bg-accent-soft text-accent border-[#c7d5f6]",
  }[tone];
  return <span className={`inline-flex items-center rounded-sm border px-1.5 py-[1px] text-[11.5px] font-medium ${t}`}>{children}</span>;
}

export function ProvenanceBadge({ provenance }: { provenance?: string }) {
  if (!provenance) return null;
  if (provenance === "SYNTHETIC") return <Badge tone="warn">Synthetic data</Badge>;
  if (provenance === "HISTORICAL_REAL") return <Badge tone="accent">Historical, end of day</Badge>;
  if (provenance === "DELAYED") return <Badge tone="accent">Delayed</Badge>;
  if (provenance === "USER_IMPORT") return <Badge>Imported</Badge>;
  return <Badge>{provenance}</Badge>;
}
