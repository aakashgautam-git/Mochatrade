/**
 * Pure helpers for the Forensics page. Type-only imports so node --test can
 * run them without a bundler.
 */
import type { Claim, LiquidationRecord, PriceObservation, RemedyClass, Tick } from "./types";

export const CLASSES: readonly RemedyClass[] = ["A", "B", "C", "D", "E", "F", "G"];

export type ClassTone = "neutral" | "accent" | "neg" | "warn";

/** Colour follows who pays. It is always shown next to the letter, never alone. */
export const CLASS_TONE: Record<RemedyClass, ClassTone> = {
  A: "neutral",
  B: "warn",
  C: "neg",
  D: "neg",
  E: "warn",
  F: "accent",
  G: "neg",
};

/** Research brief 5.2, the remedy matrix, one line per class. */
export const CLASS_NAME: Record<RemedyClass, string> = {
  A: "Genuine move",
  B: "Thin book wick",
  C: "Our oracle or mark",
  D: "Our outage",
  E: "UPI delay",
  F: "Venue or ADL",
  G: "Manipulation",
};

export function isRemedyClass(value: string): value is RemedyClass {
  return (CLASSES as readonly string[]).includes(value);
}

/** Claims in a class, or all of them. Ordered by when the harm began. */
export function claimsIn(claims: readonly Claim[], filter: RemedyClass | "ALL"): Claim[] {
  const rows = filter === "ALL" ? [...claims] : claims.filter((c) => c.category === filter);
  return rows.sort((a, b) => (a.liquidated_at_tick ?? 0) - (b.liquidated_at_tick ?? 0) || a.account_handle.localeCompare(b.account_handle));
}

/** The claim a reader should see first: the earliest that passed the APE test,
 * else the earliest in a liable class, else the earliest of all. */
export function firstInteresting(claims: readonly Claim[]): Claim | undefined {
  const ordered = claimsIn(claims, "ALL");
  return (
    ordered.find((c) => c.evidence?.ape) ??
    ordered.find((c) => c.category === "C" || c.category === "D" || c.category === "E" || c.category === "G") ??
    ordered[0]
  );
}

/** Every fill for one account, in tick order, from the ticks' liquidation records. */
export function fillsFor(ticks: readonly Tick[], accountId: string): Array<LiquidationRecord & { tick: number }> {
  const out: Array<LiquidationRecord & { tick: number }> = [];
  for (const t of ticks) {
    for (const f of t.liquidations) if (f.account_id === accountId) out.push({ ...f, tick: t.tick });
  }
  return out;
}

/** Our published composite against the Reference Composite, in bps: the
 * oracle-defect signature. Ticks with no composite are skipped, not zeroed. */
export function compositeDeviation(ticks: readonly Tick[]): Array<{ t: number; bps: number }> {
  const out: Array<{ t: number; bps: number }> = [];
  for (const t of ticks) {
    if (t.composite === null || !t.reference) continue;
    out.push({ t: t.tick, bps: (t.composite / t.reference - 1) * 10_000 });
  }
  return out;
}

/** Price lines for the forensics chart: the Reference Composite the APE test
 * measures against, our mark, and the book. */
export function forensicPrices(ticks: readonly Tick[]): Array<{ t: number; oracle: number | null; mark: number; ltp: number }> {
  return ticks.map((t) => ({ t: t.tick, oracle: t.reference, mark: t.mark, ltp: t.book_mid }));
}

export interface TapeRow {
  source: string;
  label: string;
  rung: number | null;
  raw: number | null;
  used: number | null;
  deviationBps: number | null;
  weight: number;
  state: "used" | "clamped" | "stale" | "closed" | "excluded" | "derived";
  reason: string;
}

/** One tick of the persisted evidence tape, as rows a user can check: each
 * source's print against the Reference Composite, and what the composite did
 * with it. */
export function tapeAt(observations: readonly PriceObservation[], tick: number): TapeRow[] {
  const rows = observations.filter((o) => o.tick === tick);
  const reference = rows.find((o) => o.source === "REFERENCE")?.price ?? null;
  return rows.map((o) => {
    const printed = o.raw_price ?? o.price;
    const state: TapeRow["state"] =
      o.rung === null ? "derived"
      : o.excluded_reason.startsWith("market closed") ? "closed"
      : o.is_stale ? "stale"
      : o.clamped ? "clamped"
      : o.used ? "used"
      : "excluded";
    return {
      source: o.source,
      label: o.source_display,
      rung: o.rung,
      raw: printed,
      used: o.price,
      deviationBps: printed !== null && reference ? (printed / reference - 1) * 10_000 : null,
      weight: o.weight,
      state,
      reason: o.excluded_reason,
    };
  });
}

export function signedBps(bps: number): string {
  const r = Math.round(bps);
  return `${r > 0 ? "+" : r < 0 ? "−" : ""}${Math.abs(r).toLocaleString("en-IN")} bps`;
}

export function price(value: number | null): string {
  if (value === null) return "—";
  return value.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}
