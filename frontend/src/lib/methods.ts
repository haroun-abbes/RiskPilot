/** Methodology notes shown next to each indicator. Mirrors docs/METHODOLOGY.md. */
export type Method = { title: string; formula: string; plain: string; assumptions: string[]; limits: string[] };

export const METHODS: Record<string, Method> = {
  hist_var: {
    title: "Historical VaR",
    formula: "L_t = −P&L_t ;  VaR_α = L₍⌊k⌋+1₎ with losses sorted decreasingly, k = n(1−α)\n= inf{ l : F̂_n(l) ≥ α }",
    plain: "The loss that was not exceeded on α of the historical days, when today's positions are revalued under each observed daily market move.",
    assumptions: ["Today's positions are held constant over the horizon.", "Each historical day is an equally likely scenario.", "Full revaluation: bonds are repriced at the shocked yield.", "Losses are positive numbers (sign convention)."],
    limits: ["VaR is not a maximum loss: losses beyond VaR occur on (1−α) of days.", "Blind to events absent from the window.", "Multi-day VaR uses √h scaling, valid only for i.i.d. zero-mean P&L."],
  },
  hist_es: {
    title: "Historical Expected Shortfall",
    formula: "ES_α = (1/k) [ Σ_{i≤⌊k⌋} L₍ᵢ₎ + (k−⌊k⌋) L₍⌊k⌋+1₎ ],  k = n(1−α)",
    plain: "The average loss over the worst (1−α) of historical scenarios. It answers: when things go badly, how badly on average?",
    assumptions: ["Same scenarios and sign convention as historical VaR.", "Acerbi–Tasche estimator (handles non-integer k); ES ≥ VaR always."],
    limits: ["At 99% with 500 days the tail holds only 5 scenarios: estimate is noisy.", "Same window dependence as VaR."],
  },
  param_var: {
    title: "Delta-normal VaR",
    formula: "σ² = 1ᵀ Σ 1 (Σ = covariance of linearised position P&L) ;  VaR_α = z_α σ ;  ES_α = σ φ(z_α)/(1−α)",
    plain: "VaR assuming daily P&L is normally distributed with zero mean, using first-order (delta / duration) sensitivities.",
    assumptions: ["P&L is linear in factor moves (no convexity).", "Normal distribution, zero mean.", "Sample covariance over the window, equal weights."],
    limits: ["Understates tail risk when P&L has fat tails (compare kurtosis).", "Ignores bond convexity and FX × asset cross terms."],
  },
  component_es: {
    title: "ES contribution (historical)",
    formula: "CES_i = −Σ_t w_t P&L_{t,i}, w_t = tail weights (1/k on worst ⌊k⌋ days) ;  Σ_i CES_i = ES",
    plain: "Each position's average P&L on the portfolio's worst days. Contributions add up exactly to ES; a negative value means the position hedged the portfolio on those days.",
    assumptions: ["Tail scenarios are those of the total portfolio."],
    limits: ["Based on few tail days: individual contributions can be unstable.", "Not the same as market-value weight."],
  },
  component_var: {
    title: "Euler VaR contribution (delta-normal)",
    formula: "CVaR_i = z_α (Σ 1)_i / σ_p ;  Σ_i CVaR_i = VaR",
    plain: "Marginal effect of each position on parametric VaR times its size; the allocation adds up to total VaR (Euler theorem for homogeneous risk measures).",
    assumptions: ["Delta-normal model assumptions."],
    limits: ["Linear approximation; inherits normality limits."],
  },
  volatility: {
    title: "Volatility",
    formula: "σ_ann = sd(r_t, ddof=1) · √252 ;  EWMA: s²_t = λ s²_{t−1} + (1−λ) r²_{t−1}, λ = 0.94",
    plain: "Annualised standard deviation of daily returns (prices, FX) or of daily changes (rates, spreads, in bp).",
    assumptions: ["252 business days per year.", "Simple returns for prices, absolute changes for rates."],
    limits: ["√252 annualisation assumes independent daily moves."],
  },
  backtest: {
    title: "VaR backtest (Kupiec POF)",
    formula: "LR = −2 ln[(1−p)^{n−x} p^x] + 2 ln[(1−x/n)^{n−x} (x/n)^x] ~ χ²(1), p = 1−α",
    plain: "Rolling 1-day historical VaR estimated on the previous window, compared with the next day's P&L of today's holdings over the last 250 days.",
    assumptions: ["Hypothetical P&L of constant holdings (not actual P&L)."],
    limits: ["Low power with 250 observations.", "Basel traffic light defined only for 250 obs at 99%."],
  },
  ytm: {
    title: "Yield to maturity",
    formula: "Solve  P_clean + AI = Σ_k CF_k (1 + y/f)^{−(k−1+w)}  for y (Brent)",
    plain: "The single rate that discounts the bond's cash flows to its dirty price, compounded at the coupon frequency.",
    assumptions: ["Regular coupons, unadjusted dates, redemption at par, no default."],
    limits: ["Not a risk-free rate; includes the credit spread.", "Assumes reinvestment at y."],
  },
  duration: {
    title: "Duration and convexity",
    formula: "D_mac = Σ t_k PV_k / P ;  D_mod = D_mac/(1+y/f) ;  C = Σ PV_k t_k (t_k+1/f) / (P (1+y/f)²)\nΔP/P ≈ −D_mod Δy + ½ C Δy²",
    plain: "Macaulay: average timing of cash flows (years). Modified: % price change per unit yield change. Convexity: curvature correcting the duration approximation.",
    assumptions: ["Parallel change of the bond's own yield."],
    limits: ["Approximation degrades for large moves (see sensitivity chart)."],
  },
  gspread: {
    title: "G-spread",
    formula: "G = y_bond − y_govt(T), y_govt interpolated linearly on the curve at maturity T",
    plain: "Extra yield over the government curve at the same maturity. A rough measure of credit and liquidity premium.",
    assumptions: ["Curve from the selected dataset at the settlement date."],
    limits: ["Not a Z-spread or OAS; curve compounding may differ from the bond's."],
  },
  stress: {
    title: "Stress revaluation",
    formula: "Equity: V₁ = V₀(1+r_e)(1+r_x) ;  Bond: V₁ = N/100 · P_dirty(y₀+Δr(T)+Δs) · X(1+r_x)",
    plain: "Instantaneous full revaluation of every position under the scenario's shocks. Factor columns shock one class at a time; the remainder is the cross effect.",
    assumptions: ["No time passes: no carry, roll-down or rebalancing.", "Sovereign bonds receive no spread shock."],
    limits: ["Hypothetical scenarios are not reconstructions of historical crises.", "Historical replays inherit the dataset's provenance."],
  },
  sensitivity: {
    title: "Factor sensitivities",
    formula: "EQ/FX: Δ = 1% · V₀ ;  IR key-rate DV01_j = −w_j(T) · DV01 ;  CS01 = −DV01",
    plain: "First-order P&L for a small move in each risk factor: +1% for prices and FX, +1bp for rates and spreads.",
    assumptions: ["Linear; key-rate weights from linear interpolation of the curve at maturity."],
    limits: ["Ignores convexity and cross effects."],
  },
};
