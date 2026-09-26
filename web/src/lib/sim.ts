/**
 * Pure derivations for the simulator. Every function here is a pure function;
 * the module uses `import type` only and contains no enum, namespace or
 * constructor parameter properties — so Node can run it with --experimental-
 * strip-types (erasable syntax only).
 */

import type {
  LiquidationStage,
  RiskPolicy,
  ScenarioDetail,
  Tick,
} from "./types.ts";

// ---------------------------------------------------------------------------
// Spans: contiguous runs where a boolean key is true
// ---------------------------------------------------------------------------

export interface Span {
  from: number;
  to: number;
}

/**
 * Contiguous tick spans where `key` is truthy. Gap = 1 tick — never merge
 * across gaps. The brief's most-cited bug: merging turned 56 short pauses into
 * one fake 11-minute band.
 */
export function spans<T extends { tick: number }>(ticks: ReadonlyArray<T>, key: keyof T): Span[] {
  const out: Span[] = [];
  for (const t of ticks) {
    if (!t[key]) continue;
    const last = out[out.length - 1];
    if (last && t.tick - last.to <= 1) {
      last.to = t.tick;
    } else {
      out.push({ from: t.tick, to: t.tick });
    }
  }
  return out;
}

// ---------------------------------------------------------------------------
// Control regions for the PriceChart lane
// ---------------------------------------------------------------------------

export interface ControlRegion {
  from: number;
  to: number;
  label: string;
  tone: "halt" | "warn";
}

const PAUSE_REASON_LABEL: Record<string, string> = {
  velocity: "Velocity pause",
  circuit_breaker: "Circuit breaker",
  halt: "Halted",
};

/**
 * Build control regions from the tick tape. Trading-paused spans carry a label
 * derived from `pause_reason`. Liquidations-paused and reduce-only each get
 * their own set.
 */
export function controlRegions(ticks: readonly Tick[]): ControlRegion[] {
  const out: ControlRegion[] = [];

  // Trading paused — split by pause_reason
  {
    let current: { from: number; to: number; reason: string } | undefined;
    for (const t of ticks) {
      if (t.trading_paused && t.pause_reason) {
        if (current && t.tick - current.to <= 1 && t.pause_reason === current.reason) {
          current.to = t.tick;
        } else {
          if (current) {
            out.push({
              from: current.from,
              to: current.to,
              label: PAUSE_REASON_LABEL[current.reason] ?? "Paused",
              tone: "halt",
            });
          }
          current = { from: t.tick, to: t.tick, reason: t.pause_reason };
        }
      } else {
        if (current) {
          out.push({
            from: current.from,
            to: current.to,
            label: PAUSE_REASON_LABEL[current.reason] ?? "Paused",
            tone: "halt",
          });
          current = undefined;
        }
      }
    }
    if (current) {
      out.push({
        from: current.from,
        to: current.to,
        label: PAUSE_REASON_LABEL[current.reason] ?? "Paused",
        tone: "halt",
      });
    }
  }

  // Liquidations paused
  for (const s of spans(ticks, "liquidations_paused")) {
    out.push({ from: s.from, to: s.to, label: "Liq paused", tone: "halt" });
  }

  // Reduce-only
  for (const s of spans(ticks, "reduce_only")) {
    out.push({ from: s.from, to: s.to, label: "Reduce-only", tone: "warn" });
  }

  return out;
}

// ---------------------------------------------------------------------------
// Depth ladder
// ---------------------------------------------------------------------------

export interface LadderLevel {
  price: number;
  size: number;
  side: "bid" | "ask";
}

export interface LadderResult {
  levels: LadderLevel[];
  mid: number;
  spreadBps: number;
  depthOfBaseline: number;
}

/**
 * Build a DepthLadder's `levels` from a tick's `depth`, `best_bid`, `best_ask`,
 * `book_mid`, `spread_bps` and `depth_pct_of_baseline`.
 */
export function ladderAt(tick: Tick): LadderResult | undefined {
  const d = tick.depth;
  if (!d) return undefined;
  const levels: LadderLevel[] = [];

  for (let i = 0; i < d.bids.length; i++) {
    const notional = d.bids[i];
    if (notional === undefined) continue;
    const price = tick.best_bid * (1 - (i + 1) * d.bucket_bps / 10_000);
    levels.push({ price, size: notional, side: "bid" });
  }

  for (let i = 0; i < d.asks.length; i++) {
    const notional = d.asks[i];
    if (notional === undefined) continue;
    const price = tick.best_ask * (1 + (i + 1) * d.bucket_bps / 10_000);
    levels.push({ price, size: notional, side: "ask" });
  }

  return {
    levels,
    mid: tick.book_mid,
    spreadBps: tick.spread_bps,
    depthOfBaseline: tick.depth_pct_of_baseline,
  };
}

// ---------------------------------------------------------------------------
// Cascade series
// ---------------------------------------------------------------------------

export interface CascadePoint {
  t: number;
  partial: number;
  market: number;
  backstop: number;
  adl: number;
}

/** Group each tick's liquidation records by stage and sum notional (INR). */
export function cascadeSeries(ticks: readonly Tick[]): CascadePoint[] {
  return ticks.map((t) => {
    const sums: Record<LiquidationStage, number> = { partial: 0, market: 0, backstop: 0, adl: 0 };
    for (const liq of t.liquidations) {
      sums[liq.stage] += liq.notional;
    }
    return { t: t.tick, ...sums };
  });
}

// ---------------------------------------------------------------------------
// Prefix sum
// ---------------------------------------------------------------------------

/** Prefix sum of a numeric tick field. */
export function prefixSum(ticks: readonly Tick[], key: keyof Tick): number[] {
  const out: number[] = [];
  let acc = 0;
  for (const t of ticks) {
    const v = t[key];
    if (typeof v === "number") acc += v;
    out.push(acc);
  }
  return out;
}

// ---------------------------------------------------------------------------
// State at cursor
// ---------------------------------------------------------------------------

export interface TickState {
  label: string;
  tone: "neutral" | "halt" | "warn" | "neg";
  velocityLevel: number;
}

/** The state badge for one tick. */
export function stateAt(tick: Tick): TickState {
  if (tick.halted) return { label: "Halted", tone: "halt", velocityLevel: tick.velocity_level };
  if (tick.trading_paused) {
    if (tick.pause_reason === "velocity") {
      const suffix = tick.velocity_level > 0 ? ` L${tick.velocity_level}` : "";
      return { label: `Velocity pause${suffix}`, tone: "halt", velocityLevel: tick.velocity_level };
    }
    if (tick.pause_reason === "circuit_breaker") return { label: "Circuit breaker", tone: "halt", velocityLevel: tick.velocity_level };
    return { label: "Halted", tone: "halt", velocityLevel: tick.velocity_level };
  }
  if (tick.liquidations_paused) return { label: "Liq paused", tone: "halt", velocityLevel: tick.velocity_level };
  if (tick.reduce_only) return { label: "Reduce-only", tone: "warn", velocityLevel: tick.velocity_level };
  if (tick.composite_rung === 4) return { label: "Degraded oracle", tone: "neg", velocityLevel: tick.velocity_level };
  return { label: "Continuous", tone: "neutral", velocityLevel: tick.velocity_level };
}

// ---------------------------------------------------------------------------
// Events for the timeline
// ---------------------------------------------------------------------------

export interface SimEvent {
  id: string;
  tick: number;
  tSeconds: number;
  side: "off" | "on";
  action: string;
  detail: string;
  tone: "neutral" | "halt" | "warn" | "neg" | "accent" | "pos";
}

/**
 * Derive timeline events up to tick index `upTo` from a tick tape.
 * Captures pause starts, auctions, oracle health changes, first liquidation,
 * and first ADL.
 */
export function eventsUpTo(ticks: readonly Tick[], upTo: number, side: "off" | "on"): SimEvent[] {
  const events: SimEvent[] = [];
  let prevPaused = false;
  let prevHealth = "";
  let firstLiq = false;
  let firstAdl = false;

  const n = Math.min(upTo + 1, ticks.length);
  for (let i = 0; i < n; i++) {
    const t = ticks[i];
    if (!t) continue;

    // Pause starts
    if (t.trading_paused && !prevPaused) {
      // Find span length
      let end = i;
      while (end + 1 < ticks.length) {
        const next = ticks[end + 1];
        if (!next || !next.trading_paused || next.tick - t.tick > end - i + 2) break;
        end++;
      }
      const spanLen = end - i + 1;
      const reason = t.pause_reason === "velocity" ? "Velocity pause" :
        t.pause_reason === "circuit_breaker" ? "Circuit breaker" : "Trading halted";
      const levelStr = t.velocity_level > 0 ? `, level ${t.velocity_level}` : "";
      events.push({
        id: `pause-${side}-${t.tick}`,
        tick: t.tick,
        tSeconds: t.t_seconds,
        side,
        action: reason,
        detail: `${spanLen}s span${levelStr}`,
        tone: "halt",
      });
    }
    prevPaused = t.trading_paused;

    // Auctions
    if (t.auction) {
      const a = t.auction;
      events.push({
        id: `auction-${side}-${t.tick}`,
        tick: t.tick,
        tSeconds: t.t_seconds,
        side,
        action: "Reopening auction",
        detail: `cleared at ${a.clearing_price.toLocaleString("en-IN", { maximumFractionDigits: 0 })}, absorbed ${a.liquidations_absorbed}/${a.liquidations_queued}, carried ${a.liquidation_qty_carried}`,
        tone: "accent",
      });
    }

    // Oracle health changes
    if (t.oracle_health !== prevHealth && prevHealth !== "") {
      events.push({
        id: `oracle-${side}-${t.tick}`,
        tick: t.tick,
        tSeconds: t.t_seconds,
        side,
        action: "Oracle health change",
        detail: `${prevHealth} → ${t.oracle_health}`,
        tone: t.composite_rung >= 3 ? "neg" : "pos",
      });
    }
    prevHealth = t.oracle_health;

    // First liquidation
    if (!firstLiq && t.liquidated_this_tick > 0) {
      firstLiq = true;
      events.push({
        id: `first-liq-${side}`,
        tick: t.tick,
        tSeconds: t.t_seconds,
        side,
        action: "First liquidation",
        detail: `${t.liquidated_this_tick} account(s)`,
        tone: "neg",
      });
    }

    // First ADL
    if (!firstAdl && t.adl_accounts > 0) {
      firstAdl = true;
      events.push({
        id: `first-adl-${side}`,
        tick: t.tick,
        tSeconds: t.t_seconds,
        side,
        action: "First ADL",
        detail: `${t.adl_accounts} account(s) force-closed`,
        tone: "neg",
      });
    }
  }
  return events;
}

// ---------------------------------------------------------------------------
// Shared price domain
// ---------------------------------------------------------------------------

/** Compute a shared y-domain for both columns' price charts. */
export function sharedPriceDomain(offTicks: readonly Tick[], onTicks: readonly Tick[]): [number, number] {
  let lo = Infinity;
  let hi = -Infinity;
  for (const t of offTicks) {
    if (t.composite !== null && t.composite < lo) lo = t.composite;
    if (t.composite !== null && t.composite > hi) hi = t.composite;
    if (t.mark < lo) lo = t.mark;
    if (t.mark > hi) hi = t.mark;
    if (t.book_mid < lo) lo = t.book_mid;
    if (t.book_mid > hi) hi = t.book_mid;
  }
  for (const t of onTicks) {
    if (t.composite !== null && t.composite < lo) lo = t.composite;
    if (t.composite !== null && t.composite > hi) hi = t.composite;
    if (t.mark < lo) lo = t.mark;
    if (t.mark > hi) hi = t.mark;
    if (t.book_mid < lo) lo = t.book_mid;
    if (t.book_mid > hi) hi = t.book_mid;
  }
  const pad = (hi - lo) * 0.04 || hi * 0.01;
  return [lo - pad, hi + pad];
}

// ---------------------------------------------------------------------------
// NRR derivation
// ---------------------------------------------------------------------------

export interface NrrResult {
  bps: number;
  label: string;
}

/**
 * Determine the NRR in basis points for a scenario, from the active policy.
 * Uses `nrr_offhours_pct` only if the instrument has regular trading hours
 * AND the scenario is off-hours.
 */
export function nrrFor(
  policy: Pick<RiskPolicy, "instrument_tiers">,
  scenario: Pick<ScenarioDetail, "is_offhours"> & { instrument: Pick<ScenarioDetail["instrument"], "tier" | "has_rth"> },
): NrrResult {
  const tier = policy.instrument_tiers.find((t) => t.tier === scenario.instrument.tier);
  if (!tier) return { bps: 0, label: "Unknown tier" };

  const offhours = scenario.instrument.has_rth && scenario.is_offhours;
  const pct = offhours ? tier.nrr_offhours_pct : tier.nrr_pct;
  const bps = pct * 100;
  const session = offhours ? " (off-hours)" : "";
  return { bps, label: `Tier ${tier.tier} NRR ±${pct.toFixed(1)}%${session}` };
}

// ---------------------------------------------------------------------------
// Liquidation bursts (top N by accounts liquidated)
// ---------------------------------------------------------------------------

export interface LiquidationBurst {
  t: number;
  price: number;
  count: number;
}

export function liquidationBursts(ticks: readonly Tick[], n = 8): LiquidationBurst[] {
  return ticks
    .filter((t) => t.liquidated_this_tick > 0)
    .sort((a, b) => b.liquidated_this_tick - a.liquidated_this_tick)
    .slice(0, n)
    .map((t) => ({ t: t.tick, price: t.mark, count: t.liquidated_this_tick }));
}

// ---------------------------------------------------------------------------
// Auction markers for the price chart
// ---------------------------------------------------------------------------

export interface AuctionMarker {
  t: number;
  price: number;
}

export function auctionMarkers(ticks: readonly Tick[]): AuctionMarker[] {
  const out: AuctionMarker[] = [];
  for (const t of ticks) {
    if (t.auction) {
      out.push({ t: t.tick, price: t.auction.clearing_price });
    }
  }
  return out;
}

// ---------------------------------------------------------------------------
// Price series for the PriceChart
// ---------------------------------------------------------------------------

export interface PricePoint {
  t: number;
  oracle: number | null;
  mark: number;
  ltp: number;
}

export function priceSeries(ticks: readonly Tick[]): PricePoint[] {
  return ticks.map((t) => ({
    t: t.tick,
    oracle: t.composite,
    mark: t.mark,
    ltp: t.book_mid,
  }));
}

// ---------------------------------------------------------------------------
// Deviation series for the DeviationChart
// ---------------------------------------------------------------------------

export interface DeviationPoint {
  t: number;
  bps: number;
}

export function deviationSeries(ticks: readonly Tick[]): DeviationPoint[] {
  return ticks.map((t) => ({ t: t.tick, bps: t.divergence_bps }));
}
