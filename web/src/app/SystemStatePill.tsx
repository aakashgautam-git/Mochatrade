import { CircleCheck, CirclePause, OctagonX, ShieldAlert, TriangleAlert, type LucideIcon } from "lucide-react";

import { cn } from "../components/ui/cn";
import type { SystemState } from "./store";

interface Look {
  label: string;
  icon: LucideIcon;
  pill: string;
  strip: string | null;
  meaning: string;
}

/**
 * Colour, text and icon change together, always. Two states never share all
 * three, so the pill reads correctly for a colour-blind operator and on a
 * washed-out projector alike.
 *
 * --halt is reserved for halt and intervention states, so LIQ PAUSED and HALTED
 * both use it -- told apart by treatment: a pause is a tint, a halt is the one
 * solid fill in the whole interface.
 */
export const LOOK: Record<SystemState, Look> = {
  NORMAL: {
    label: "Normal",
    icon: CircleCheck,
    pill: "border-pos-edge bg-pos-soft text-pos-fg",
    strip: null,
    meaning: "All controls at rest. Continuous trading.",
  },
  REDUCE_ONLY: {
    label: "Reduce-only",
    icon: ShieldAlert,
    pill: "border-warn-edge bg-warn-soft text-warn-fg",
    strip: "bg-warn",
    meaning: "Risk-increasing orders rejected. Positions can still close.",
  },
  LIQ_PAUSED: {
    label: "Liq paused",
    icon: CirclePause,
    pill: "border-halt-edge bg-halt-soft text-halt-fg",
    strip: "bg-halt",
    meaning: "Liquidations paused because the price feed is suspect.",
  },
  HALTED: {
    label: "Halted",
    icon: OctagonX,
    pill: "border-halt-solid bg-halt-solid text-on-halt-solid",
    strip: "bg-halt-solid",
    meaning: "haltTrading called. Orders cancelled, positions settled at mark.",
  },
  DEGRADED_ORACLE: {
    label: "Degraded oracle",
    icon: TriangleAlert,
    pill: "border-neg-edge bg-neg-soft text-neg-fg",
    strip: "bg-neg",
    meaning: "No composite reached quorum. 3x max, reduce-only, liquidations paused.",
  },
};

export function SystemStatePill({ state, size = "md" }: { state: SystemState; size?: "sm" | "md" }) {
  const look = LOOK[state];
  const Icon = look.icon;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-2 whitespace-nowrap rounded-control border font-semibold uppercase tracking-[0.08em]",
        "transition-colors duration-base ease-out",
        size === "md" ? "h-8 px-3 text-xs" : "h-6 px-2 text-[11px]",
        look.pill,
      )}
      title={look.meaning}
    >
      <Icon aria-hidden className={size === "md" ? "h-4 w-4" : "h-3.5 w-3.5"} strokeWidth={2.25} />
      {look.label}
    </span>
  );
}
