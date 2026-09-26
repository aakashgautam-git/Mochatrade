import { Clock, OctagonX, TriangleAlert } from "lucide-react";

import { useNow } from "../../hooks/useNow";
import { cn } from "./cn";

interface CountdownProps {
  /** Epoch milliseconds. Ignored when `remaining` is given. */
  deadline?: number;
  /** Seconds left on a clock other than the wall clock -- e.g. the war room's
   * simulated drill clock. When set, the wall clock is not read at all. */
  remaining?: number | undefined;
  /** Seconds remaining at which it turns warn. */
  warnAt: number;
  /** Seconds remaining at which it turns neg. Defaults to the deadline itself. */
  negAt?: number;
  label: string;
  size?: "sm" | "md";
}

function clock(totalSeconds: number): string {
  const s = Math.abs(totalSeconds);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  const mmss = `${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}`;
  return h > 0 ? `${String(h).padStart(2, "0")}:${mmss}` : mmss;
}

const STATE = {
  ok: { text: "text-text", note: "on track", Icon: Clock, noteTone: "text-text-dim" },
  warn: { text: "text-warn-fg", note: "due soon", Icon: TriangleAlert, noteTone: "text-warn-fg" },
  neg: { text: "text-neg-fg", note: "overdue", Icon: OctagonX, noteTone: "text-neg-fg" },
} as const;

/**
 * MM:SS to a deadline. Crossing a threshold changes the colour, the icon and
 * the words together. Past zero it keeps counting, as overdue time.
 */
export function Countdown({ deadline = 0, remaining: given, warnAt, negAt = 0, label, size = "md" }: CountdownProps) {
  const now = useNow(1000);
  const remaining = given ?? Math.ceil((deadline - now) / 1000);
  const phase = remaining <= negAt ? "neg" : remaining <= warnAt ? "warn" : "ok";
  const s = STATE[phase];
  const overdue = remaining < 0;
  const note = overdue ? "overdue by" : s.note;

  return (
    <div role="timer" aria-label={`${label}: ${overdue ? "overdue by" : ""} ${clock(remaining)}`}>
      <p className="text-xs font-medium uppercase tracking-[0.12em] text-text-dim">{label}</p>
      <p className={cn("num mt-2 font-semibold leading-none tracking-tight transition-colors duration-base", s.text, size === "md" ? "text-3xl" : "text-xl")}>
        {overdue ? "+" : ""}{clock(remaining)}
      </p>
      <p className={cn("mt-2 flex items-center gap-1.5 text-xs", s.noteTone)}>
        <s.Icon aria-hidden className="h-3.5 w-3.5" />
        {note}
      </p>
    </div>
  );
}
