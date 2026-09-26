import { ArrowDown, ArrowUp, Minus } from "lucide-react";

import { useCountUp } from "../../hooks/useCountUp";
import { Badge } from "./Badge";
import { cn } from "./cn";
import { Skeleton } from "./Skeleton";

const integer = (n: number) => Math.round(n).toLocaleString("en-IN");

export interface StatDelta {
  /** Signed percent change. */
  pct: number;
  /** Which direction is good. For liquidations and losses, down is good. */
  goodWhen: "up" | "down";
}

interface StatProps {
  label: string;
  value: number;
  format?: ((n: number) => string) | undefined;
  delta?: StatDelta | undefined;
  /** A comparison value shown struck through, e.g. the unprotected run. */
  baseline?: { value: number; label: string } | undefined;
  caption?: string | undefined;
  size?: "md" | "lg";
  loading?: boolean;
  /** Count up from this on first render instead of appearing at the value. */
  startFrom?: number | undefined;
  /** Duration of the count animation in ms. Defaults to 400. */
  duration?: number | undefined;
}

/**
 * Label, one big mono value, and an optional delta chip.
 *
 * Layout never shifts while counting: the value sits alone on its line, and it
 * is stacked in one grid cell with invisible copies of both the start and the
 * end value, so the cell is always as wide as the widest of the two. Screen
 * readers get the final value only, never the digits mid-count.
 */
export function Stat({
  label,
  value,
  format: formatProp,
  delta,
  baseline,
  caption,
  size = "md",
  loading = false,
  startFrom,
  duration,
}: StatProps) {
  const format = formatProp ?? integer;
  const { value: counted, from } = useCountUp(value, {
    ...(startFrom !== undefined && { startFrom }),
    ...(duration !== undefined && { duration }),
  });
  // Mid-count frames are floats; an integer stat must never show raw digits.
  const shown = Number.isInteger(value) ? Math.round(counted) : counted;

  return (
    <div className="min-w-0">
      <p className="text-xs font-medium uppercase tracking-[0.12em] text-text-dim">{label}</p>

      {loading ? (
        <div className="mt-3 space-y-2" aria-busy>
          <Skeleton className={size === "lg" ? "h-10 w-32" : "h-8 w-28"} />
          <span className="sr-only">Loading {label}</span>
        </div>
      ) : (
        <div
          title={format(value)}
          className={cn(
            "num mt-3 grid min-w-0 overflow-hidden whitespace-nowrap font-semibold leading-none tracking-tight text-text",
            size === "lg" ? "text-4xl" : "text-3xl",
          )}
        >
          <span aria-hidden className="invisible col-start-1 row-start-1 truncate">{format(value)}</span>
          <span aria-hidden className="invisible col-start-1 row-start-1 truncate">{format(Number.isInteger(value) ? Math.round(from) : from)}</span>
          <span aria-hidden className="col-start-1 row-start-1 truncate">{format(shown)}</span>
          <span className="sr-only">{format(value)}</span>
        </div>
      )}

      {(delta || baseline || caption) && !loading ? (
        <div className="mt-3 flex min-h-6 flex-wrap items-center gap-2">
          {delta ? <DeltaChip delta={delta} /> : null}
          {baseline ? (
            <span className="text-xs text-text-dim">
              <span className="sr-only">{baseline.label}: </span>
              <span className="num text-text-dim line-through decoration-1">{format(baseline.value)}</span>{" "}
              <span aria-hidden>{baseline.label}</span>
            </span>
          ) : null}
          {caption ? <span className="text-xs text-text-dim">{caption}</span> : null}
        </div>
      ) : null}
    </div>
  );
}

export function DeltaChip({ delta }: { delta: StatDelta }) {
  const rounded = Math.round(delta.pct);
  if (rounded === 0) {
    return <Badge tone="neutral" mono icon={<Minus />}>no change</Badge>;
  }
  const up = rounded > 0;
  const good = up === (delta.goodWhen === "up");
  return (
    <Badge tone={good ? "pos" : "neg"} mono icon={up ? <ArrowUp /> : <ArrowDown />}>
      {`${up ? "+" : "−"}${Math.abs(rounded)}%`}
    </Badge>
  );
}
