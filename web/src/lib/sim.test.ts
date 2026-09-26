import assert from "node:assert/strict";
import { test, describe } from "node:test";

import {
  spans,
  controlRegions,
  ladderAt,
  cascadeSeries,
  prefixSum,
  nrrFor,
  stateAt,
  eventsUpTo,
  sharedPriceDomain,
} from "./sim.ts";

import type { Tick, LiquidationRecord, DepthSnapshot, RiskPolicy } from "./types.ts";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

type TickOverrides = Partial<Tick>;

function makeTick(overrides: TickOverrides = {}): Tick {
  return {
    tick: 0,
    t_seconds: 0,
    true_price: 100_000,
    composite: 100_000,
    composite_rung: 1,
    oracle_health: "HEALTHY",
    reference: 100_000,
    book_mid: 100_000,
    spread_bps: 5,
    depth_pct_of_baseline: 1.0,
    mark: 100_000,
    mark_source: "composite",
    divergence_bps: 0,
    reduce_only: false,
    liquidations_paused: false,
    trading_paused: false,
    pause_reason: null,
    velocity_level: 0,
    halted: false,
    max_leverage: 50,
    stage: "normal",
    liquidated_this_tick: 0,
    cum_liquidated_accounts: 0,
    cum_liquidated_notional: 0,
    adl_accounts: 0,
    insurance_balance: 10_000_000,
    unnecessary_liquidations: 0,
    accounts_open: 1000,
    aggregate_equity: 50_000_000,
    best_bid: 99_950,
    best_ask: 100_050,
    auction: null,
    liquidations: [],
    depth: null,
    sources: [],
    ...overrides,
  };
}

function makeLiq(overrides: Partial<LiquidationRecord> = {}): LiquidationRecord {
  return {
    account_id: "acc-1",
    stage: "market",
    qty: 1,
    notional: 50_000,
    price: 99_000,
    via_auction: false,
    closed: false,
    survived_at_reference: false,
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("spans", () => {
  test("basic span creation", () => {
    const ticks = [
      { tick: 0, trading_paused: true },
      { tick: 1, trading_paused: true },
      { tick: 2, trading_paused: false },
      { tick: 3, trading_paused: true },
    ];
    const result = spans(ticks, "trading_paused");
    assert.equal(result.length, 2);
    assert.deepEqual(result[0], { from: 0, to: 1 });
    assert.deepEqual(result[1], { from: 3, to: 3 });
  });

  test("does not merge across a gap", () => {
    // Tick 1 is missing — there is a gap between tick 0 and tick 2
    const ticks = [
      { tick: 0, x: true },
      { tick: 2, x: true },
    ];
    const result = spans(ticks, "x");
    assert.equal(result.length, 2, "must NOT merge: gap > 1 tick");
    assert.deepEqual(result[0], { from: 0, to: 0 });
    assert.deepEqual(result[1], { from: 2, to: 2 });
  });

  test("does merge when gap is exactly 1 tick", () => {
    const ticks = [
      { tick: 10, x: true },
      { tick: 11, x: true },
      { tick: 12, x: true },
    ];
    const result = spans(ticks, "x");
    assert.equal(result.length, 1);
    assert.deepEqual(result[0], { from: 10, to: 12 });
  });
});

describe("controlRegions", () => {
  test("labels velocity pauses correctly", () => {
    const ticks = [
      makeTick({ tick: 0, trading_paused: true, pause_reason: "velocity" }),
      makeTick({ tick: 1, trading_paused: true, pause_reason: "velocity" }),
      makeTick({ tick: 2, trading_paused: false, pause_reason: null }),
    ];
    const regions = controlRegions(ticks);
    const pauses = regions.filter((r) => r.label === "Velocity pause");
    assert.equal(pauses.length, 1);
    assert.equal(pauses[0]!.from, 0);
    assert.equal(pauses[0]!.to, 1);
    assert.equal(pauses[0]!.tone, "halt");
  });

  test("separates different pause reasons even if adjacent", () => {
    const ticks = [
      makeTick({ tick: 0, trading_paused: true, pause_reason: "velocity" }),
      makeTick({ tick: 1, trading_paused: true, pause_reason: "circuit_breaker" }),
    ];
    const regions = controlRegions(ticks);
    const pauses = regions.filter((r) => r.label.startsWith("Velocity") || r.label.startsWith("Circuit"));
    assert.equal(pauses.length, 2);
  });
});

describe("ladderAt", () => {
  test("builds correct prices from the formula", () => {
    const depth: DepthSnapshot = {
      bucket_bps: 10,
      bids: [500_000, 400_000, 300_000],
      asks: [480_000, 350_000, 250_000],
    };
    const tick = makeTick({
      best_bid: 100_000,
      best_ask: 100_100,
      book_mid: 100_050,
      spread_bps: 10,
      depth_pct_of_baseline: 0.8,
      depth,
    });
    const result = ladderAt(tick);
    assert.ok(result);
    assert.equal(result.levels.length, 6);

    // Bid price formula: best_bid * (1 - (i+1) * bucket_bps / 10_000)
    // i=0: 100_000 * (1 - 1 * 10 / 10_000) = 100_000 * 0.999 = 99_900
    const bid0 = result.levels.find((l) => l.side === "bid" && l.size === 500_000);
    assert.ok(bid0);
    assert.equal(bid0.price, 100_000 * (1 - 1 * 10 / 10_000));

    // i=1: 100_000 * (1 - 2 * 10 / 10_000) = 100_000 * 0.998 = 99_800
    const bid1 = result.levels.find((l) => l.side === "bid" && l.size === 400_000);
    assert.ok(bid1);
    assert.equal(bid1.price, 100_000 * (1 - 2 * 10 / 10_000));

    // Ask price formula: best_ask * (1 + (i+1) * bucket_bps / 10_000)
    // i=0: 100_100 * (1 + 1 * 10 / 10_000) = 100_100 * 1.001 = 100_200.1
    const ask0 = result.levels.find((l) => l.side === "ask" && l.size === 480_000);
    assert.ok(ask0);
    assert.equal(ask0.price, 100_100 * (1 + 1 * 10 / 10_000));

    assert.equal(result.mid, 100_050);
    assert.equal(result.spreadBps, 10);
    assert.equal(result.depthOfBaseline, 0.8);
  });

  test("returns undefined when depth is null", () => {
    const tick = makeTick({ depth: null });
    assert.equal(ladderAt(tick), undefined);
  });
});

describe("cascadeSeries", () => {
  test("groups liquidation records by stage and sums notional", () => {
    const ticks = [
      makeTick({
        tick: 0,
        liquidations: [
          makeLiq({ stage: "partial", notional: 10_000 }),
          makeLiq({ stage: "market", notional: 20_000 }),
          makeLiq({ stage: "partial", notional: 15_000 }),
        ],
      }),
      makeTick({
        tick: 1,
        liquidations: [
          makeLiq({ stage: "backstop", notional: 30_000 }),
          makeLiq({ stage: "adl", notional: 5_000 }),
        ],
      }),
    ];

    const result = cascadeSeries(ticks);
    assert.equal(result.length, 2);

    assert.equal(result[0]!.partial, 25_000);
    assert.equal(result[0]!.market, 20_000);
    assert.equal(result[0]!.backstop, 0);
    assert.equal(result[0]!.adl, 0);

    assert.equal(result[1]!.partial, 0);
    assert.equal(result[1]!.market, 0);
    assert.equal(result[1]!.backstop, 30_000);
    assert.equal(result[1]!.adl, 5_000);
  });

  test("handles ticks with no liquidations", () => {
    const ticks = [makeTick({ tick: 0, liquidations: [] })];
    const result = cascadeSeries(ticks);
    assert.equal(result.length, 1);
    assert.equal(result[0]!.partial, 0);
    assert.equal(result[0]!.market, 0);
    assert.equal(result[0]!.backstop, 0);
    assert.equal(result[0]!.adl, 0);
  });
});

describe("prefixSum", () => {
  test("accumulates correctly", () => {
    const ticks = [
      makeTick({ tick: 0, unnecessary_liquidations: 3 }),
      makeTick({ tick: 1, unnecessary_liquidations: 0 }),
      makeTick({ tick: 2, unnecessary_liquidations: 5 }),
      makeTick({ tick: 3, unnecessary_liquidations: 2 }),
    ];
    const result = prefixSum(ticks, "unnecessary_liquidations");
    assert.deepEqual(result, [3, 3, 8, 10]);
  });

  test("returns zeros for non-numeric key", () => {
    const ticks = [makeTick({ tick: 0 }), makeTick({ tick: 1 })];
    // oracle_health is a string — should not add to accumulator
    const result = prefixSum(ticks, "oracle_health");
    assert.deepEqual(result, [0, 0]);
  });
});

describe("stateAt", () => {
  test("halted wins over everything", () => {
    const t = makeTick({ halted: true, trading_paused: true, reduce_only: true });
    assert.equal(stateAt(t).label, "Halted");
    assert.equal(stateAt(t).tone, "halt");
  });

  test("velocity pause shows level", () => {
    const t = makeTick({ trading_paused: true, pause_reason: "velocity", velocity_level: 2 });
    const s = stateAt(t);
    assert.equal(s.label, "Velocity pause L2");
    assert.equal(s.tone, "halt");
  });

  test("degraded oracle", () => {
    const t = makeTick({ composite_rung: 4 });
    assert.equal(stateAt(t).label, "Degraded oracle");
    assert.equal(stateAt(t).tone, "neg");
  });

  test("normal is Continuous", () => {
    const t = makeTick({});
    assert.equal(stateAt(t).label, "Continuous");
    assert.equal(stateAt(t).tone, "neutral");
  });
});

describe("nrrFor", () => {
  const policy: Pick<RiskPolicy, "instrument_tiers"> = {
    instrument_tiers: [
      { tier: 1, label: "Tier 1", nrr_pct: 3, nrr_offhours_pct: 5, dcb_variant_pct: 5 },
      { tier: 2, label: "Tier 2", nrr_pct: 5, nrr_offhours_pct: 8, dcb_variant_pct: 8 },
    ],
  };

  test("on-hours with RTH uses nrr_pct", () => {
    const result = nrrFor(policy, {
      is_offhours: false,
      instrument: { tier: 2, has_rth: true },
    });
    assert.equal(result.bps, 500);
    assert.ok(result.label.includes("5.0%"));
    assert.ok(!result.label.includes("off-hours"));
  });

  test("off-hours with RTH uses nrr_offhours_pct", () => {
    const result = nrrFor(policy, {
      is_offhours: true,
      instrument: { tier: 2, has_rth: true },
    });
    assert.equal(result.bps, 800);
    assert.ok(result.label.includes("8.0%"));
    assert.ok(result.label.includes("off-hours"));
  });

  test("off-hours without RTH still uses nrr_pct", () => {
    // A crypto asset is off-hours but has no RTH, so off-hours NRR does not apply
    const result = nrrFor(policy, {
      is_offhours: true,
      instrument: { tier: 1, has_rth: false },
    });
    assert.equal(result.bps, 300);
    assert.ok(!result.label.includes("off-hours"));
  });

  test("unknown tier returns 0", () => {
    const result = nrrFor(policy, {
      is_offhours: false,
      instrument: { tier: 99, has_rth: false },
    });
    assert.equal(result.bps, 0);
  });
});

describe("sharedPriceDomain", () => {
  test("covers both runs with padding", () => {
    const offTicks = [
      makeTick({ composite: 95_000, mark: 94_000, book_mid: 93_000 }),
      makeTick({ composite: 100_000, mark: 101_000, book_mid: 102_000 }),
    ];
    const onTicks = [
      makeTick({ composite: 96_000, mark: 97_000, book_mid: 98_000 }),
    ];
    const [lo, hi] = sharedPriceDomain(offTicks, onTicks);
    assert.ok(lo < 93_000, "lo should be below the minimum");
    assert.ok(hi > 102_000, "hi should be above the maximum");
  });
});

describe("eventsUpTo", () => {
  test("captures first liquidation event", () => {
    const ticks = [
      makeTick({ tick: 0, t_seconds: 0 }),
      makeTick({ tick: 1, t_seconds: 1, liquidated_this_tick: 3 }),
      makeTick({ tick: 2, t_seconds: 2, liquidated_this_tick: 5 }),
    ];
    const events = eventsUpTo(ticks, 2, "off");
    const firstLiqs = events.filter((e) => e.action === "First liquidation");
    assert.equal(firstLiqs.length, 1, "should only have one 'First liquidation'");
    assert.equal(firstLiqs[0]!.tick, 1);
  });

  test("respects upTo limit", () => {
    const ticks = [
      makeTick({ tick: 0, t_seconds: 0 }),
      makeTick({ tick: 1, t_seconds: 1 }),
      makeTick({ tick: 2, t_seconds: 2, liquidated_this_tick: 3 }),
    ];
    const events = eventsUpTo(ticks, 0, "on");
    assert.equal(events.filter((e) => e.action === "First liquidation").length, 0);
  });
});
