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

/** A pause reopening through a call auction: one clearing price, max matched
 * volume, collared around the Reference Composite. Negative imbalance means
 * unmatched sellers carried into continuous trading. */
export interface AuctionRecord {
  tick: number;
  reason: string;
  reference: number;
  collar_lo: number;
  collar_hi: number;
  clearing_price: number;
  matched_qty: number;
  matched_notional: number;
  imbalance_qty: number;
  liquidations_queued: number;
  liquidations_absorbed: number;
  liquidation_qty_carried: number;
}

export type LiquidationStage = "partial" | "market" | "backstop" | "adl";

/** One fill. The last record for an account with `closed` set is the stage
 * that closed it; grouping a tick's records by stage is the cascade split. */
export interface LiquidationRecord {
  account_id: string;
  stage: LiquidationStage;
  qty: number;
  notional: number;
  price: number;
  via_auction: boolean;
  closed: boolean;
  survived_at_reference: boolean;
}

/** Resting depth left at the end of a tick: INR notional per bucket, nearest
 * the touch first. Bid bucket i spans i*bucket_bps..(i+1)*bucket_bps below
 * `best_bid`; asks likewise above `best_ask`. */
export interface DepthSnapshot {
  bucket_bps: number;
  bids: number[];
  asks: number[];
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
  best_bid: number;
  best_ask: number;
  auction: AuctionRecord | null;
  liquidations: LiquidationRecord[];
  depth: DepthSnapshot | null;
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
  auctions: number;
  auction_liquidations_absorbed: number;
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
  | "DECLARE" | "PROTECT_SWITCH" | "QUANTIFY" | "REDUCE_ONLY" | "PAUSE_LIQUIDATIONS" | "LIQ_THROTTLE"
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

export type TriageStatus = "ok" | "warn" | "fail";

export interface TriageSignal {
  label: string;
  value: string;
  status: TriageStatus;
}

/** One of the three layers: L3 venue, L2 our HIP-3 market, L1 our broker stack. */
export interface TriageLayer {
  layer: "venue" | "market" | "broker";
  tier: "L3" | "L2" | "L1";
  name: string;
  control: string;
  status: TriageStatus;
  headline: string;
  signals: TriageSignal[];
}

export interface IncidentScenario {
  slug: string;
  name: string;
  instrument: string;
  ist_label: string;
  layer: string;
  n_ticks: number;
}

/** GET /api/incidents/{code}/state/, POST /api/incidents/ and POST .../clock/ */
export interface IncidentState {
  incident: Incident;
  scenario: IncidentScenario;
  elapsed_seconds: number;
  /** The playbook clock in seconds, T+0 to T+3600. */
  drill_clock_s: number;
  drill_total_s: number;
  current_tick: number;
  total_ticks: number;
  finished: boolean;
  snapshot: Tick | null;
  active_controls: Record<string, boolean>;
  flags: IncidentFlags;
  triage: TriageLayer[];
  actions: IncidentAction[];
}

/** GET /api/incidents/{code}/ticks/ */
export interface TicksResponse {
  from_tick: number;
  ticks: Tick[];
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
  source_display: string;
  /** Null on the derived rows: our mark, the published composite, the Reference Composite. */
  rung: number | null;
  price: number | null;
  raw_price: number | null;
  is_stale: boolean;
  weight: number;
  used: boolean;
  clamped: boolean;
  excluded_reason: string;
}

/** GET /api/incidents/{code}/evidence/?from=&to= */
export interface EvidenceResponse {
  incident_code: string;
  ticks_recorded: number;
  from_tick: number;
  to_tick: number;
  observations: PriceObservation[];
}

export type RemedyClass = "A" | "B" | "C" | "D" | "E" | "F" | "G";

export interface EpisodeSignal {
  start_tick: number;
  end_tick: number;
  peak_bps: number;
  peak_tick: number;
  sources: string[];
  direction: number;
  fingerprint_start_tick: number | null;
  fingerprint_end_tick: number | null;
}

export interface VerdictSignals {
  nrr_bps: number;
  mark_band_bps: number;
  reversion_frac: number;
  reversion_seconds: number;
  composite_defect: EpisodeSignal | null;
  push: EpisodeSignal | null;
  closed_primary: string[];
  thin_book_wick: EpisodeSignal | null;
  outage: { start_tick: number; end_tick: number; affected_frac: number; label: string } | null;
  upi_in_flight: number;
  ltp_marked_liquidations: number;
  accounts_force_closed: number;
  ape_accounts: number;
}

/** The incident-level verdict and the working behind it. */
export interface Verdict {
  category: RemedyClass;
  label: string;
  layer: "venue" | "market" | "broker";
  fault: string;
  remedy: string;
  headline: string;
  evidence: string[];
  signals: VerdictSignals;
  provisional: boolean;
  at_tick: number;
  nrr_bps: number;
  counts: Record<RemedyClass, number>;
}

export interface CriterionResult {
  /** Null while the 60-second reversion window is still open. */
  passed: boolean | null;
  value: number | null;
  threshold: number;
  detail: string;
}

/** One account's APE test, exactly as the classifier ran it. */
export interface AccountEvidence {
  account_id: string;
  category: RemedyClass;
  reason: string;
  side: "LONG" | "SHORT";
  leverage: number;
  entry_price: number;
  collateral: number;
  entry_notional: number;
  first_tick: number;
  tick: number;
  stage: string;
  executed_price: number;
  reference_price: number;
  mark: number;
  mark_source: string;
  composite: number | null;
  book_mid: number;
  deviation_bps: number;
  deviation_basis: "fill" | "mark";
  nrr_bps: number;
  fills: number;
  liquidated_notional: number;
  fees: number;
  closed: boolean;
  ape: boolean;
  pending: boolean;
  criteria: { deviation: CriterionResult; reversion: CriterionResult; survival: CriterionResult };
  outage: { start_tick: number; end_tick: number; inside: boolean } | null;
  upi: { amount: number; initiated_tick: number; settles_tick: number | null; credit_advanced: number } | null;
  equity_inr: number;
  counterfactual_equity_inr: number;
  /** Set once claims are opened: the published formula, applied. */
  remedy?: RemedyEvidence;
}

export interface RemedyEvidence {
  account_id: string;
  category: RemedyClass;
  kind: "cash" | "fee_rebate" | "none";
  /** The full claim under the published formula, before any cap. */
  make_whole: number;
  fee_rebate: number;
  basis: string;
  equity_now: number;
  reference_equity: number | null;
  provisional: boolean;
  cash_inr: number;
  make_good_inr: number;
  pro_rata: boolean;
}

export interface Tranche {
  step: number;
  source: string;
  drawn: number;
  available: number | null;
  note: string;
}

export interface Waterfall {
  total_claims: number;
  cap: number;
  payable: number;
  pro_rata: boolean;
  /** Cash paid per rupee claimed. 1 unless the cap binds. */
  ratio: number;
  shortfall: number;
  reserve_opening: number;
  reserve_available: number;
  reserve_after: number;
  fee_rebates: number;
  tranches: Tranche[];
  formula: string;
}

export interface Remediation {
  policy_version: string;
  computed_at_tick: number;
  provisional_deadline: IsoDateTime;
  provisional_minutes: number;
  reserve: { opening: number; drawn_by_other_incidents: number; available: number };
  waterfall: Waterfall;
}

/** GET/POST /api/incidents/{code}/claims/ */
export interface ClaimsResponse {
  status: "open" | "not_opened";
  incident_code: string;
  classification: Classification;
  market_finished: boolean;
  current_tick: number;
  remediation: Remediation | null;
  claims: Claim[];
}

export interface RecalibrationRow {
  slug: string;
  name: string;
  controls_enabled: boolean;
  category: string;
  claims_total_inr: MoneyString;
  cash_accounts: number;
  above_cap: boolean;
  run_id: number;
}

/** POST /api/policies/recalibrate/ */
export interface Recalibration {
  previous_version: string;
  new_version: string | null;
  active_version: string;
  rows: RecalibrationRow[];
  worst: RecalibrationRow;
  multiple: number;
  previous_reserve_inr: MoneyString;
  target_reserve_inr: MoneyString;
  cap_inr: MoneyString;
  converged: boolean;
  same_runs: boolean;
  explanation: string;
}

export type ClaimStatus = "AUTO_APPROVED" | "PENDING" | "APPROVED" | "REJECTED" | "PAID";

export interface Claim {
  id: number;
  account_handle: string;
  account_side: "LONG" | "SHORT";
  account_leverage: number;
  liquidated_at_tick: number | null;
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
  /** The classifier's working; null for a claim entered by hand. */
  evidence: AccountEvidence | null;
}

/** GET/POST /api/incidents/{code}/classify/ */
export interface ClassificationResponse {
  status: "classified" | "unclassified";
  incident_code: string;
  market_finished: boolean;
  current_tick: number;
  verdict: Verdict | null;
  claims: Claim[];
}

export interface ClassifyRequest {
  actor?: string;
  rationale?: string;
}

export interface ClaimDecisionRequest {
  decision: "APPROVED" | "REJECTED" | "PAID";
  approved_inr?: MoneyString | null;
  reason?: string;
  decided_by?: string;
}

export type Channel = "STATUS_PAGE" | "X" | "WHATSAPP" | "TELEGRAM" | "EMAIL";

export type Audience = "PUBLIC" | "AFFECTED" | "VENUE" | "REGULATOR";
export type Approval = "DRAFT" | "PENDING" | "APPROVED" | "REJECTED";

/** One guardrail finding. A block stops approval and publishing. */
export interface Finding {
  rule: string;
  severity: "block" | "warn";
  message: string;
  source: string;
  match: string | null;
}

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
  audience: Audience;
  audience_display: string;
  template: string;
  approval: Approval;
  approval_display: string;
  drafted_by: string;
  approved_by: string;
  approved_at: IsoDateTime | null;
  approval_note: string;
  guardrails: Finding[];
  solvency_verified: boolean;
}

export interface CommsCreateRequest {
  channel?: Channel;
  headline: string;
  body: string;
  sequence?: number;
  next_update_at?: IsoDateTime | null;
  is_published?: boolean;
  audience?: Audience;
  template?: string;
  drafted_by?: string;
  solvency_verified?: boolean;
  submit?: boolean;
}

export interface CommsCheckRequest {
  headline: string;
  body: string;
  channel: Channel;
  audience: Audience;
  template?: string;
  solvency_verified?: boolean;
}

/** POST /api/incidents/{code}/comms/check/ */
export interface CommsCheckResponse {
  findings: Finding[];
  blocked: boolean;
  facts: {
    classified: boolean;
    category: string;
    affected: number;
    claims_open: boolean;
    pro_rata: boolean;
    ratio: number;
    next_update: string;
  };
}

export interface TemplateDraft {
  channel: Channel;
  headline: string;
  body: string;
  findings: Finding[];
}

/** GET /api/incidents/{code}/comms/templates/ */
export interface CommsTemplate {
  key: string;
  audience: Audience;
  audience_display: string;
  channels: Channel[];
  title: string;
  when: string;
  drafts: TemplateDraft[];
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
  classification: ClassificationResponse;
  claims: ClaimsResponse;
  claims_summary: {
    accounts_owed_cash: number;
    claimed_inr: MoneyString;
    approved_inr: MoneyString;
    provisional_credit_inr: MoneyString;
    make_good_inr: MoneyString;
    paid: number;
    pending: number;
  };
  /** SEBI's technical-glitch framework, adopted voluntarily, measured on this incident. */
  obligations: {
    first_update_minutes: number | null;
    notified_within_hour: boolean;
    preliminary_due: IsoDateTime;
    rca_due: IsoDateTime;
    retain_until: IsoDateTime;
    channels_used: Channel[];
  };
  /** The control stack the incident's run used. */
  controls: string[];
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

export type ComponentState = "operational" | "degraded" | "partial_outage" | "major_outage";

export interface PublicComponent {
  name: string;
  state: ComponentState;
  state_label: string;
  note: string;
}

export interface PublicIncident {
  code: string;
  title: string;
  severity: string;
  started_at: IsoDateTime;
  resolved_at: IsoDateTime | null;
  state: "investigating" | "identified" | "monitoring" | "resolved";
  updates: PublicStatusUpdate[];
}

/** GET /api/status/ */
export interface PublicStatusResponse {
  overall: { state: ComponentState; headline: string };
  components: PublicComponent[];
  incidents: PublicIncident[];
  updates: PublicStatusUpdate[];
  as_of: IsoDateTime;
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

// ---------------------------------------------------------------------------
// Attribution: what each control is worth
// ---------------------------------------------------------------------------

export interface AttributionMetrics {
  attributable_loss: MoneyString;
  user_loss: MoneyString;
  accounts_liquidated: number;
  unnecessary_liquidations: number;
  adl_accounts: number;
}

export interface AttributionRow {
  control: string;
  label: string;
  kills: string;
  /** Why the engine cannot show this control's effect yet; empty when it can. */
  not_modelled: string;
  /** Saved by this control on its own, against no controls. */
  alone: AttributionMetrics;
  /** Lost by removing it from the full stack. */
  last_in: AttributionMetrics;
}

/** GET /api/scenarios/{slug}/attribution/ */
export interface ScenarioAttribution {
  scenario_slug: string;
  scenario_name: string;
  policy_version: string;
  seed: number;
  full: AttributionMetrics;
  none: AttributionMetrics;
  controls: AttributionRow[];
}

export interface AttributionTotal {
  control: string;
  label: string;
  kills: string;
  not_modelled: string;
  alone: AttributionMetrics;
  last_in: AttributionMetrics;
}

/** GET /api/controls/attribution/ */
export interface AttributionOverview {
  policy_version: string;
  scenarios: ScenarioAttribution[];
  totals: AttributionTotal[];
}
