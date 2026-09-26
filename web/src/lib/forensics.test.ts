import { strict as assert } from "node:assert";
import { describe, it } from "node:test";

import { claimsIn, compositeDeviation, fillsFor, firstInteresting, signedBps, tapeAt } from "./forensics.ts";
import type { Claim, PriceObservation, Tick } from "./types.ts";

function claim(handle: string, category: Claim["category"], tick: number, ape = false): Claim {
  return {
    id: tick, account_handle: handle, account_side: "LONG", account_leverage: 10, liquidated_at_tick: tick,
    category, status: "PENDING", executed_price: "1", reference_composite_price: "1", deviation_pct: 0,
    counterfactual_equity_inr: "0", claimed_inr_display: "0.00", approved_inr_display: "0.00",
    provisional_credit_inr: "0", shortfall_inr_display: "0.00", decided_by: "", decided_at: null, reason: "",
    evidence: ape ? ({ ape: true } as Claim["evidence"]) : null,
  };
}

function obs(source: string, rung: number | null, raw: number | null, extra: Partial<PriceObservation> = {}): PriceObservation {
  return {
    tick: 5, source, source_display: source, rung, price: raw, raw_price: raw, is_stale: false,
    weight: 1, used: rung !== null, clamped: false, excluded_reason: "", ...extra,
  };
}

describe("forensics helpers", () => {
  it("orders claims by when the harm began and filters by class", () => {
    const rows = [claim("MT3", "A", 30), claim("MT1", "C", 10), claim("MT2", "C", 10)];
    assert.deepEqual(claimsIn(rows, "ALL").map((c) => c.account_handle), ["MT1", "MT2", "MT3"]);
    assert.deepEqual(claimsIn(rows, "A").map((c) => c.account_handle), ["MT3"]);
  });

  it("opens on the first APE, then the first liable class", () => {
    assert.equal(firstInteresting([claim("MT1", "A", 1), claim("MT2", "B", 5, true)])?.account_handle, "MT2");
    assert.equal(firstInteresting([claim("MT1", "A", 1), claim("MT2", "D", 5)])?.account_handle, "MT2");
    assert.equal(firstInteresting([]), undefined);
  });

  it("reads each source against the Reference Composite and names what happened to it", () => {
    const rows = tapeAt(
      [
        obs("BINANCE", 1, 101),
        obs("OKX", 1, 90, { clamped: true, price: 99 }),
        obs("US_CASH", 1, null, { used: false, excluded_reason: "market closed -- outside its trading session" }),
        obs("REFERENCE", null, 100),
        { ...obs("BINANCE", 1, 50), tick: 6 },
      ],
      5,
    );
    assert.equal(rows.length, 4);
    assert.equal(Math.round(rows[0]?.deviationBps ?? 0), 100);
    assert.deepEqual(rows.map((r) => r.state), ["used", "clamped", "closed", "derived"]);
  });

  it("collects one account's fills and skips ticks without a composite", () => {
    const ticks = [
      { tick: 1, composite: 99, reference: 100, liquidations: [{ account_id: "MT1", stage: "partial" }] },
      { tick: 2, composite: null, reference: 100, liquidations: [{ account_id: "MT2", stage: "market" }] },
    ] as unknown as Tick[];
    assert.deepEqual(fillsFor(ticks, "MT1").map((f) => f.tick), [1]);
    assert.deepEqual(compositeDeviation(ticks).map((p) => Math.round(p.bps)), [-100]);
  });

  it("writes signed basis points with a real minus sign", () => {
    assert.equal(signedBps(-1234.4), "−1,234 bps");
    assert.equal(signedBps(12), "+12 bps");
    assert.equal(signedBps(0), "0 bps");
  });
});
