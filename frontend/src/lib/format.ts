const nf0 = new Intl.NumberFormat("en-GB", { maximumFractionDigits: 0 });
const nf2 = new Intl.NumberFormat("en-GB", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export const isNum = (x: unknown): x is number => typeof x === "number" && Number.isFinite(x);

export function eur(x: number | null | undefined, digits = 0) {
  if (!isNum(x)) return "n/a";
  if (Math.abs(x) < (digits ? 0.005 : 0.5)) x = 0; // avoid "-0 €"
  return (digits ? nf2 : nf0).format(x) + " €";
}

export function compactEur(x: number | null | undefined) {
  if (!isNum(x)) return "n/a";
  const a = Math.abs(x);
  if (a >= 1e6) return `${(x / 1e6).toFixed(2)} M€`;
  if (a >= 1e3) return `${(x / 1e3).toFixed(1)} k€`;
  return `${x.toFixed(0)} €`;
}

export function pct(x: number | null | undefined, d = 2) {
  if (!isNum(x)) return "n/a";
  return `${(x * 100).toFixed(d)}%`;
}

export function signedPct(x: number | null | undefined, d = 2) {
  if (!isNum(x)) return "n/a";
  return `${x > 0 ? "+" : ""}${(x * 100).toFixed(d)}%`;
}

export function bp(x: number | null | undefined, d = 1) {
  if (!isNum(x)) return "n/a";
  return `${x > 0 ? "+" : ""}${(x * 1e4).toFixed(d)} bp`;
}

export function num(x: number | null | undefined, d = 2) {
  if (!isNum(x)) return "n/a";
  return x.toLocaleString("en-GB", { minimumFractionDigits: d, maximumFractionDigits: d });
}

export const tone = (x: number | null | undefined) => (!isNum(x) || x === 0 ? "" : x < 0 ? "text-loss" : "text-gain");

/** Level formatting by factor class (EQ/FX prices, IR/CS decimal rates). */
export function factorLevel(factor: string, x: number | null | undefined) {
  if (!isNum(x)) return "n/a";
  const c = factor.split(":")[0];
  if (c === "IR" || c === "CS") return `${(x * 100).toFixed(3)}%`;
  if (c === "FX") return x.toFixed(x < 0.1 ? 6 : 4);
  return x.toFixed(2);
}

export function factorChange(factor: string, x: number | null | undefined) {
  const c = factor.split(":")[0];
  return c === "IR" || c === "CS" ? bp(x) : signedPct(x);
}

export const confLabel = (c: number) => `${(c * 100).toFixed(c * 100 % 1 ? 1 : 0)}%`;
