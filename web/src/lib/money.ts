/**
 * Money for display. Pure, with type-only imports, so Node's test runner can
 * load it without a bundler.
 */
import type { MoneyString } from "./types";

/** For DISPLAY only. Do arithmetic on the string's decimal value server-side. */
export function parseMoney(value: MoneyString): number {
  return Number.parseFloat(value);
}

/**
 * Indian-scale money. A judge reads lakh and crore, not millions. Matches the
 * server's `riskengine.indian.inr_text` digit for digit, so a figure in a
 * published update and the same figure on a tile read the same.
 */
export function rupees(value: number): string {
  const abs = Math.abs(value);
  const sign = value < 0 && abs >= 0.5 ? "-" : "";
  if (abs >= 1_00_00_000) return `${sign}₹${(abs / 1_00_00_000).toFixed(2)} Cr`;
  if (abs >= 1_00_000) return `${sign}₹${(abs / 1_00_000).toFixed(2)} L`;
  return `${sign}₹${Math.round(abs).toLocaleString("en-IN")}`;
}
