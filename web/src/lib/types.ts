/**
 * API response types, hand-written to mirror backend/core/serializers.py
 * exactly. When a serializer changes shape, this file changes in the same
 * commit.
 *
 * Money convention, matching the backend:
 * - `MoneyString` fields are decimal strings to two places ("25000.00"). JSON
 *   numbers are IEEE doubles, and a compensation figure must not shift in its
 *   last place because it crossed JavaScript. Parse with `parseMoney` for
 *   display; never do arithmetic on the parsed float and send it back.
 * - Model DecimalFields (prices, notional bounds) also arrive as strings, which
 *   is DRF's default.
 * - Tick series values are chart samples and stay numeric.
 *
 * Timestamps are ISO-8601 in IST with the +05:30 offset.
 */

export type MoneyString = string;
export type DecimalString = string;
export type IsoDateTime = string;
export type IsoTime = string;

// ---------------------------------------------------------------------------
// Policy
// ---------------------------------------------------------------------------

export interface MarginTier {
  ordering: number;
  notional_floor: DecimalString;
  notional_ceiling: DecimalString | null;
  max_leverage: number;
  mm_pct: number;
}

export interface InstrumentTier {
  tier: number;
  label: string;
  nrr_pct: number;
  nrr_offhours_pct: number;
  dcb_variant_pct: number;
}

export interface RiskPolicy {
  id: number;
  version: string;
  name: string;
  is_active: boolean;
  created_at: IsoDateTime;
  notes: string;
  outlier_clamp_pct: number;
  majors_outlier_clamp_pct: number;
  staleness_seconds: number;
  basis_ma_seconds: number;
  funding_period_seconds: number;
  mark_max_deviation_bps: number;
  composite_l1_min_sources: number;
  composite_l2_min_sources: number;
  composite_l3_min_sources: number;
  velocity_window_seconds: number;
  velocity_trigger_frac_of_dcb: number;
  velocity_cooldown_seconds: number;
  velocity_escalation_multiplier: number;
  price_band_frac_of_dcb: number;
  dcb_offhours_multiplier: number;
  dcb_lookback_seconds: number;
  dcb_pause_seconds: number;
  twap_slice_ms: number;
  twap_max_participation_pct: number;
  twap_participation_band_pct: number;
  backstop_threshold_frac: number;
  partial_liq_target_mm_multiple: number;
  clearance_fee_pct: number;
  margin_grace_seconds: number;
  upi_prefunded_credit_cap_inr: number;
  max_leverage_rth: number;
  max_leverage_offhours: number;
  max_leverage_degraded: number;
  ape_reversion_frac: number;
  ape_reversion_seconds: number;
  provisional_credit_minutes: number;
  reserve_funding_share_of_fees: number;
  reserve_target_multiple_of_worst_loss: number;
  incident_reserve_inr: MoneyString;
  per_incident_cap_inr_display: MoneyString;
  margin_tiers: MarginTier[];
  instrument_tiers: InstrumentTier[];
}

// ---------------------------------------------------------------------------
// Instruments and scenarios
// ---------------------------------------------------------------------------

export type Layer = "VENUE" | "MARKET" | "BROKER";
export type AssetClass = "EQUITY" | "CRYPTO" | "COMMODITY" | "INDEX" | "PREIPO";
export type OracleFault = "NONE" | "SINGLE_SOURCE_DEPEG" | "STALE" | "DIVERGENT";
export type BrokerFault = "NONE" | "API_DOWN" | "APP_FROZEN" | "UPI_DELAY";

export interface Instrument {
  symbol: string;
  display_name: string;
  layer: Layer;
  layer_display: string;
  tier: number;
  asset_class: AssetClass;
  asset_class_display: string;
  has_rth: boolean;
  rth_open_ist: IsoTime | null;
  rth_close_ist: IsoTime | null;
  base_price: DecimalString;
  tick_size: DecimalString;
  max_leverage: number;
  maintenance_margin_pct: number;
}

export interface ScenarioListItem {
  slug: string;
  name: string;
  description: string;
  instrument_symbol: string;
  seed: number;
  shock_pct: number;
  is_offhours: boolean;
  oracle_fault: OracleFault;
  broker_fault: BrokerFault;
  engine_key: string;
}

export interface ScenarioDetail extends ScenarioListItem {
  instrument: Instrument;
  shock_duration_s: number;
  total_duration_s: number;
  book_depth_inr: DecimalString;
  depth_collapse_pct: number;
  n_accounts: number;
  leverage_distribution: Record<string, number>;
  long_share_pct: number;
  broker_fault_window_s: number;
  assumed_scale_note: string;
}

// ---------------------------------------------------------------------------
// Runs
// ---------------------------------------------------------------------------

/**
 * One oracle source's part in one tick's composite. `price` is what the
 * composite used after the outlier clamp; `raw_price` is what the source
 * printed; the gap is the clamp. Both are null when the source printed nothing
 * -- a closed market or an unreachable venue. `weight` is zero exactly when the
 * source did not feed the composite, and `excluded_reason` says why.
 */
export interface SourceObservation {
  source: string;
  kind: string;
  rung: number;
  price: number | null;
  raw_price: number | null;
  weight: number;
  is_stale: boolean;
  used: boolean;
  clamped: boolean;
  excluded_reason: string;
}

export interface Tick {
  tick: number;
  t_seconds: number;
  true_price: number;
  composite: number | null;
  composite_rung: number;
  oracle_health: string;
  reference: number | null;
  book_mid: number;
  spread_bps: number;
  depth_pct_of_baseline: number;
  mark: number;
  mark_source: string;
  divergence_bps: number;
  reduce_only: boolean;
  liquidations_paused: boolean;
  trading_paused: boolean;
  /** Which layer holds trading paused. Tells a 5s velocity pause from a 2-minute breaker. */
  pause_reason: "circuit_breaker" | "velocity" | "halt" | null;
  velocity_level: number;
  halted: boolean;
  max_leverage: number;
  stage: string;
  liquidated_this_tick: number;
  cum_liquidated_accounts: number;
  cum_liquidated_notional: number;
  adl_accounts: number;
  insurance_balance: number;
  unnecessary_liquidations: number;
  accounts_open: number;
  aggregate_equity: number;
  sources: SourceObservation[];
}

export interface RunSummary {
  scenario_key: string;
  seed: number;
  policy_version: string;
  ticks: number;
  accounts_total: number;
  accounts_liquidated: number;
  unnecessary_liquidations: number;
  adl_accounts: number;
  trough_mark_pct: number;
  peak_mark_pct: number;
  max_divergence_bps: number;
  min_depth_pct_of_baseline: number;
  saved_by_grace: number;
  upi_credits_issued: number;
  open_interest_inr: MoneyString;
  liquidated_notional_inr: MoneyString;
  unnecessary_notional_inr: MoneyString;
  adl_notional_inr: MoneyString;
  user_loss_inr: MoneyString;
  attributable_loss_inr: MoneyString;
  insurance_drawn_inr: MoneyString;
}

export type CacheState = "hit" | "miss";

export interface RunPayload {
  run_id: number;
  controls_enabled: boolean;
  seed: number;
  policy_version: string;
  summary: RunSummary;
  ticks: Tick[];
}

/** POST /api/runs/ */
export interface RunCreateResponse extends RunPayload {
  cache: CacheState;
}

export interface RunCreateRequest {
  scenario_slug: string;
  controls_enabled?: boolean;
  seed?: number | null;
  policy_id?: number | null;
}

/** POST /api/runs/compare/. Positive delta = the controls REDUCED the quantity. */
export interface CompareResponse {
  scenario_slug: string;
  seed: number;
  policy_version: string;
  cache: CacheState;
  off: RunPayload;
  on: RunPayload;
  delta: {
    liquidations_pct: number;
    notional_pct: number;
    wick_pct: number;
    adl_pct: number;
  };
}

export interface CompareRequest {
  scenario_slug: string;
  seed?: number | null;
}

// ---------------------------------------------------------------------------
// Incidents
// ---------------------------------------------------------------------------

export type Classification = "UNCLASSIFIED" | "A" | "B" | "C" | "D" | "E" | "F" | "G";

export type ActionType =
  | "DECLARE" | "REDUCE_ONLY" | "PAUSE_LIQUIDATIONS" | "LIQ_THROTTLE"
  | "LEVERAGE_CAP" | "WIDEN_BANDS" | "HALT_MARKET" | "SNAPSHOT_EVIDENCE"
  | "PUBLISH_UPDATE" | "CLASSIFY" | "OPEN_CLAIMS" | "PROVISIONAL_CREDIT"
  | "STAGED_REOPEN" | "RESOLVE";

export interface IncidentAction {
  id: number;
  tick: number;
  wall_clock: IsoDateTime;
  actor: string;
  action_type: ActionType;
  action_type_display: string;
  params: Record<string, unknown>;
  rationale: string;
  reversible: boolean;
}

export interface Incident {
  code: string;
  scenario_slug: string | null;
  severity: string;
  status: string;
  declared_at: IsoDateTime;
  resolved_at: IsoDateTime | null;
  minutes_open: number;
  incident_commander: string;
  ops_lead: string;
  comms_lead: string;
  classification: Classification;
  classification_display: string;
  root_cause_layer: Layer | "";
  owes_cash_remedy: boolean;
  affected_accounts_count: number;
  aggregate_exposure_inr_display: MoneyString;
}

export interface IncidentFlags {
  reduce_only: boolean;
  liquidations_paused: boolean;
  halted: boolean;
  max_leverage: number;
  stage: string;
  operator_throttle: boolean;
}

/** GET /api/incidents/{code}/state/ and POST /api/incidents/ */
export interface IncidentState {
  incident: Incident;
  elapsed_seconds: number;
  current_tick: number;
  total_ticks: number;
  finished: boolean;
  snapshot: Tick | null;
  active_controls: Record<string, boolean>;
  flags: IncidentFlags;
}

export interface DeclareIncidentRequest {
  scenario_slug: string;
  controls_enabled?: boolean;
  seed?: number | null;
  severity?: string;
  incident_commander?: string;
  ops_lead?: string;
  comms_lead?: string;
}

/** POST /api/incidents/{code}/step/ */
export interface StepResponse {
  from_tick: number;
  to_tick: number;
  finished: boolean;
  snapshots: Tick[];
}

export interface ActionRequest {
  action_type: ActionType;
  params?: Record<string, unknown>;
  rationale?: string;
  actor?: string;
}

/** POST /api/incidents/{code}/action/ */
export interface ActionResponse {
  action: IncidentAction;
  affects_engine: boolean;
  applies_at_tick: number;
  note: string;
}

export interface PriceObservation {
  tick: number;
  source: string;
  price: number | null;
  is_stale: boolean;
  weight: number;
  excluded_reason: string;
}

/** GET /api/incidents/{code}/evidence/ */
export interface EvidenceResponse {
  incident_code: string;
  ticks_recorded: number;
  observations: PriceObservation[];
}

export type ClaimStatus = "AUTO_APPROVED" | "PENDING" | "APPROVED" | "REJECTED" | "PAID";

export interface Claim {
  id: number;
  account_handle: string;
  category: Classification;
  status: ClaimStatus;
  executed_price: DecimalString;
  reference_composite_price: DecimalString;
  deviation_pct: number;
  counterfactual_equity_inr: DecimalString;
  claimed_inr_display: MoneyString;
  approved_inr_display: MoneyString;
  provisional_credit_inr: DecimalString;
  shortfall_inr_display: MoneyString;
  decided_by: string;
  decided_at: IsoDateTime | null;
  reason: string;
}

export interface ClaimDecisionRequest {
  decision: "APPROVED" | "REJECTED" | "PAID";
  approved_inr?: MoneyString | null;
  reason?: string;
  decided_by?: string;
}

export type Channel = "STATUS_PAGE" | "X" | "WHATSAPP" | "TELEGRAM" | "EMAIL";

export interface CommsUpdate {
  id: number;
  sequence: number;
  channel: Channel;
  channel_display: string;
  headline: string;
  body: string;
  published_at: IsoDateTime | null;
  next_update_at: IsoDateTime | null;
  is_published: boolean;
}

export interface CommsCreateRequest {
  channel?: Channel;
  headline: string;
  body: string;
  sequence?: number;
  next_update_at?: IsoDateTime | null;
  is_published?: boolean;
}

export interface PendingSection {
  status: "pending";
  phase: number;
}

/** GET /api/incidents/{code}/report/ */
export interface IncidentReport {
  incident: Incident;
  run: {
    scenario_slug: string | null;
    policy_version: string | null;
    seed: number | null;
    current_tick: number;
    summary: RunSummary | null;
  };
  timeline: IncidentAction[];
  comms: CommsUpdate[];
  classification: PendingSection;
  claims: PendingSection;
}

/** 501 from a route whose phase has not landed. */
export interface NotImplementedResponse {
  detail: string;
  phase: number;
}

/** Any 4xx/5xx carries a human-readable detail. */
export interface ApiError {
  detail: string;
}

// ---------------------------------------------------------------------------
// Public status page -- a deliberately narrow shape
// ---------------------------------------------------------------------------

export interface PublicStatusUpdate {
  incident_code: string;
  severity: string;
  sequence: number;
  channel: Channel;
  channel_display: string;
  headline: string;
  body: string;
  published_at: IsoDateTime | null;
  next_update_at: IsoDateTime | null;
}

/** GET /api/status/ */
export interface PublicStatusResponse {
  updates: PublicStatusUpdate[];
}

// ---------------------------------------------------------------------------
// Legacy: GET /api/compare/<slug>/ -- the screening-round demo's shape.
// Money is numeric here ONLY, because the shipped page parses it as a number.
// ---------------------------------------------------------------------------

export interface SeriesPoint {
  t: number;
  oracle: number | null;
  mark: number;
  ltp: number;
  liquidations: number;
}

export interface RunSide {
  liquidated: number;
  unnecessary: number;
  adl: number;
  user_loss_inr: number;
  accounts_total: number;
  trough_pct: number;
  series: SeriesPoint[];
}

export interface Comparison {
  scenario: {
    slug: string;
    name: string;
    summary: string;
    instrument: string;
    ist_label: string;
    layer: string;
    liable_layer_note: string;
    seed: number;
  };
  assumed_scale_note: string;
  off: RunSide;
  on: RunSide;
  delta: {
    liquidated_pct: number;
    loss_pct: number;
    unnecessary_pct: number;
    adl_pct: number;
  };
}
