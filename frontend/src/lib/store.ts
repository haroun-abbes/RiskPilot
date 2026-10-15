"use client";
import { create } from "zustand";
import { persist } from "zustand/middleware";

/** Analysis context shared by every screen and kept across navigation/reloads. */
export type Ctx = {
  portfolioId: string;
  datasetId: string;
  confidence: number;
  horizon: number;
  window: number;
  compareId: string | null;
  set: (p: Partial<Omit<Ctx, "set">>) => void;
};

export const useCtx = create<Ctx>()(
  persist(
    (set) => ({
      portfolioId: "demo",
      datasetId: "synthetic-demo-v1",
      confidence: 0.99,
      horizon: 1,
      window: 500,
      compareId: null,
      set: (p) => set(p),
    }),
    { name: "riskpilot-context" },
  ),
);

export function riskBody(c: Ctx) {
  return { portfolio_id: c.portfolioId, dataset_id: c.datasetId, window: c.window, confidence: c.confidence, horizon_days: c.horizon };
}
