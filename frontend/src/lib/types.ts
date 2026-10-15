export type Meta = {
  computed_at: string;
  engine_version: string;
  params: Record<string, unknown>;
  portfolio: { id: string; name: string; as_of: string; provenance: string; hash: string };
  dataset: { id: string; name: string; provenance: string; provenance_label: string; source: string; hash: string; end: string };
};

export type RiskSummary = {
  meta: Meta;
  portfolio_value: number;
  coverage_gross: number | null;
  window: { start: string | null; end: string | null; n_obs: number; dropped: number };
  historical: { available: boolean; reason?: string; var_1d?: number; es_1d?: number; var?: number; es?: number; n_obs?: number; tail_obs?: number };
  parametric: { available: boolean; sigma_1d?: number; var_1d?: number; es_1d?: number; var?: number; es?: number; diversification_1d?: number; skew?: number | null; excess_kurtosis?: number | null; delta_approx_corr?: number | null };
  distribution: { edges: number[]; counts: number[] };
  pnl_series: { date: string; pnl: number }[];
  backcast: { date: string; cum_pnl: number }[];
  backtest: null | { n: number; exceptions: number; expected: number; kupiec_lr: number; kupiec_pvalue: number; traffic_light: string | null; series: { date: string; var: number; pnl: number }[] };
  positions: { id: string; name: string; asset_class: string; currency: string; mv_base: number; vol_annual: number | null; component_es: number | null; component_es_pct: number | null; component_var_param: number | null; standalone_var_param: number | null }[];
  excluded: { id: string; reason: string }[];
  warnings: string[];
};

export type Group = { key: string; net: number; gross: number; long: number; short: number; count: number; pct_gross: number | null };

export type PositionVal = {
  id: string;
  instrument_type: string;
  asset_class: string;
  name: string;
  currency: string;
  fx_rate: number | null;
  mv_local: number | null;
  mv_base: number | null;
  attributes: Record<string, string | number | null>;
  ytm: number | null;
  accrued_base: number | null;
  modified_duration: number | null;
  convexity: number | null;
  dv01_base: number | null;
  eq_factor: string | null;
  fx_factor: string | null;
  ir_factors: string[];
  ir_weights: number[];
  cs_factor: string | null;
  excluded: string | null;
  warnings: string[];
  included_in_risk: boolean;
};

export type Exposures = {
  meta: Meta;
  positions: PositionVal[];
  totals: { net: number; gross: number; long: number; short: number; n_positions: number; n_excluded: number };
  groups: Record<string, Group[]>;
  fixed_income: null | { market_value: number; modified_duration: number; dv01: number; cs01: number; accrued: number; ytm_mv_weighted: number };
  sensitivities: { factor: string; factor_class: string; sensitivity: number; unit: string }[];
  warnings: string[];
};

export type Scenario = { id: string; name: string; kind: "hypothetical" | "historical"; description: string; definition: Record<string, unknown>; is_builtin: boolean; updated_at: string };

export type StressPos = { id: string; name: string; asset_class: string; currency: string; mv_base: number; pnl: number; pnl_pct: number | null; pnl_duration_convexity: number | null; moves: Record<string, number>; by_class: Record<string, number>; interaction: number };
export type StressResult = { scenario_id: string | null; name: string; description?: string; kind: string; total_pnl: number; total_pnl_pct: number | null; portfolio_value: number; by_class: Record<string, number>; interaction: number; positions: StressPos[]; issues: string[]; excluded: { id: string; reason: string }[]; provenance_note?: string; error?: string };
export type StressResponse = { meta: Meta; base_value: number; results: StressResult[]; reference: null | { label: string; es_10d: number; var_10d: number }; warnings: string[] };

export type Attribution = {
  meta: Meta;
  available: boolean;
  reason?: string;
  totals: { es: number; var_param: number; sum_standalone_es_by_class: number; diversification_es: number };
  positions: { id: string; name: string; asset_class: string; currency: string; sector: string | null; issuer: string | null; country: string | null; mv_base: number; es: number; var_param: number; standalone_var_param: number }[];
  groups: Record<string, { key: string; es: number; var_param: number; mv: number; gross: number; es_pct: number | null; weight_gross: number | null }[]>;
  factors: { factor: string; class: string; var_param: number; standalone_var_param: number }[];
  factor_classes: { class: string; var_param: number; standalone_es_hist: number | null }[];
  sensitivities: Exposures["sensitivities"];
  warnings: string[];
};

export type BondReport = {
  label: string;
  inputs: { maturity: string; coupon_pct: number; frequency: number; daycount: string; settlement: string };
  analytics: { yield_to_maturity: number; dirty_price: number; clean_price: number; accrued_interest: number; macaulay_duration: number; modified_duration: number; convexity: number; dv01: number; effective_duration: number; effective_convexity: number };
  previous_coupon: string;
  next_coupon: string;
  cash_flows: { date: string; amount: number; time_years: number; discount_factor: number; present_value: number; type: string }[];
  sensitivity_curve: { dy_bp: number; exact: number; duration: number; duration_convexity: number }[];
  spread: null | { kind: string; benchmark_yield: number; spread_bp: number; curve_date: string; curve: { factor: string; tenor_years: number; yield: number }[]; note: string };
};
