/**
 * The 60-minute playbook as data, and the pure rules the war room runs on.
 *
 * Steps, owners, windows and guidance are the research brief's section 6 table.
 * A step is done when the decision it names has been logged; the war room never
 * marks progress on its own. Pure: `import type` only, so Node's built-in test
 * runner can load it without a bundler.
 */
import type { ActionType, IncidentAction, Tick } from "./types";

export type Role = "IC" | "OPS" | "COMMS";

export interface PlaybookStep {
  id: string;
  /** Window on the drill clock, in seconds. */
  from: number;
  due: number;
  title: string;
  owner: Role;
  guidance: string;
  /** Done when any of these has been logged at least `count` times. */
  completes: { type: ActionType; count?: number }[];
}

const MIN = 60;

export const PLAYBOOK: PlaybookStep[] = [
  { id: "detect", from: 0, due: 2 * MIN, title: "Detect and declare", owner: "IC",
    guidance: "Auto-pager on mark–oracle divergence, liquidation rate, API 5xx or ticket rate. Say “SEV-1, I am IC” out loud. The record opens itself.",
    completes: [{ type: "DECLARE" }] },
  { id: "contain", from: 2 * MIN, due: 5 * MIN, title: "Contain — the Protect Switch", owner: "OPS",
    guidance: "One pre-authorised switch: reduce-only, liquidation TWAP throttle, max leverage 3x. Pause liquidations on this market only if the oracle is suspect. haltTrading stays holstered.",
    completes: [{ type: "PROTECT_SWITCH" }, { type: "REDUCE_ONLY" }] },
  { id: "preserve", from: 2 * MIN, due: 3 * MIN, title: "Preserve the evidence", owner: "OPS",
    guidance: "Write-once snapshot: L2 book, trade tape, per-source oracle inputs, mark series, liquidation events, app and API telemetry, deposit queue.",
    completes: [{ type: "SNAPSHOT_EVIDENCE" }] },
  { id: "first-word", from: 2 * MIN, due: 5 * MIN, title: "First public word", owner: "COMMS",
    guidance: "Status page, then X, then WhatsApp and Telegram. No cause. No blame. What we see, what we turned on, next update at HH:MM.",
    completes: [{ type: "PUBLISH_UPDATE", count: 1 }] },
  { id: "diagnose", from: 5 * MIN, due: 15 * MIN, title: "Diagnose all three layers", owner: "OPS",
    guidance: "Run the APE detector: our mark against the Reference Composite, per second, per source. And check our own layer: app uptime, API errors, UPI queue. Classify A–G.",
    completes: [{ type: "CLASSIFY" }] },
  { id: "update-2", from: 5 * MIN, due: 15 * MIN, title: "Update 2 and the preliminary call", owner: "COMMS",
    guidance: "If it is C, D or E, say so at T+15. Owning it early is the highest-return trust action there is, and a three-person team can do it faster than an exchange.",
    completes: [{ type: "PUBLISH_UPDATE", count: 2 }] },
  { id: "quantify", from: 15 * MIN, due: 30 * MIN, title: "Quantify", owner: "IC",
    guidance: "Build the affected set and the counterfactual equity for each account. Get the number. Check the Incident Reserve covers it.",
    completes: [{ type: "QUANTIFY" }] },
  { id: "update-3", from: 15 * MIN, due: 30 * MIN, title: "Update 3 — the number", owner: "COMMS",
    guidance: "“N users, ₹X aggregate, between HH:MM and HH:MM IST.” Cite the APE policy that already existed.",
    completes: [{ type: "PUBLISH_UPDATE", count: 3 }] },
  { id: "remediate", from: 30 * MIN, due: 45 * MIN, title: "Remediate", owner: "OPS",
    guidance: "Push provisional credit to clear cases automatically. Open the claims portal for 72 hours. Answer every open ticket with a link to that user’s own status.",
    completes: [{ type: "PROVISIONAL_CREDIT" }, { type: "OPEN_CLAIMS" }] },
  { id: "reopen", from: 45 * MIN, due: 60 * MIN, title: "Stabilise and reopen", owner: "OPS",
    guidance: "Staged: reduce-only, then post-only, then full, through a short auction. Each gate needs the oracle healthy for five minutes and spread and depth back.",
    completes: [{ type: "STAGED_REOPEN" }] },
  { id: "handover", from: 45 * MIN, due: 60 * MIN, title: "Handover", owner: "IC",
    guidance: "Publish what happened, who is affected, what we are paying, when it lands, and the date of the full root-cause analysis.",
    completes: [{ type: "RESOLVE" }] },
];

export type StepState = "done" | "due" | "overdue" | "upcoming";

export interface StepStatus {
  step: PlaybookStep;
  state: StepState;
  /** Seconds to the due time; negative once overdue. */
  remaining: number;
  /** Drill-clock tick at which it was completed. */
  doneAt: number | null;
}

/**
 * Public updates, one per number: the same update sent to the status page, X
 * and WhatsApp is one update on three channels, not three updates. A message
 * to a regulator, the venue or affected users is not a public update.
 */
export function publicUpdates(actions: readonly IncidentAction[]): IncidentAction[] {
  const seen = new Set<string>();
  const out: IncidentAction[] = [];
  for (const a of actions) {
    if (a.action_type !== "PUBLISH_UPDATE" || (a.params["audience"] ?? "PUBLIC") !== "PUBLIC") continue;
    const sequence = a.params["sequence"];
    const key = typeof sequence === "number" ? `seq-${sequence}` : `id-${a.id}`;
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(a);
  }
  return out;
}

export function stepStatus(step: PlaybookStep, actions: readonly IncidentAction[], clock: number): StepStatus {
  let doneAt: number | null = null;
  const updates = publicUpdates(actions);
  for (const rule of step.completes) {
    const hits = rule.type === "PUBLISH_UPDATE" ? updates : actions.filter((a) => a.action_type === rule.type);
    const needed = rule.count ?? 1;
    const hit = hits[needed - 1];
    if (hit && (doneAt === null || hit.tick < doneAt)) doneAt = hit.tick;
  }
  const remaining = step.due - clock;
  const state: StepState = doneAt !== null ? "done" : clock < step.from ? "upcoming" : remaining >= 0 ? "due" : "overdue";
  return { step, state, remaining, doneAt };
}

export function playbookStatus(actions: readonly IncidentAction[], clock: number): StepStatus[] {
  return PLAYBOOK.map((s) => stepStatus(s, actions, clock));
}

/** The phase the clock is in: the last step whose window has opened. */
export function phaseAt(clock: number): PlaybookStep {
  let current = PLAYBOOK[0] as PlaybookStep;
  for (const s of PLAYBOOK) if (s.from <= clock) current = s;
  return current;
}

export type PillState = "NORMAL" | "REDUCE_ONLY" | "TRADING_PAUSED" | "LIQ_PAUSED" | "HALTED" | "DEGRADED_ORACLE";

/** The top-bar pill from the live incident's latest tick. Most severe first. */
export function pillFor(tick: Tick | null | undefined): PillState {
  if (!tick) return "NORMAL";
  if (tick.halted) return "HALTED";
  if (tick.composite_rung === 4) return "DEGRADED_ORACLE";
  if (tick.trading_paused) return "TRADING_PAUSED";
  if (tick.liquidations_paused) return "LIQ_PAUSED";
  if (tick.reduce_only) return "REDUCE_ONLY";
  return "NORMAL";
}

const CHANNEL: Record<string, string> = {
  STATUS_PAGE: "status page", X: "X", WHATSAPP: "WhatsApp", TELEGRAM: "Telegram", EMAIL: "email",
};
const AUDIENCE: Record<string, string> = { AFFECTED: "Affected users", VENUE: "The venue", REGULATOR: "Regulators" };

/**
 * A log entry's label. A publish is named by what went out -- "Update 2 on X",
 * "Regulators by email" -- rather than by its type's playbook slot, which
 * reads "T+5" on an update sent at T+30.
 */
export function actionLabel(a: IncidentAction): string {
  if (a.action_type !== "PUBLISH_UPDATE") return a.action_type_display;
  const channel = CHANNEL[String(a.params["channel"] ?? "")];
  const audience = String(a.params["audience"] ?? "PUBLIC");
  const sequence = a.params["sequence"];
  if (audience !== "PUBLIC") return `${AUDIENCE[audience] ?? audience}${channel ? ` by ${channel}` : ""}`;
  if (typeof sequence !== "number") return "Public update";
  return `Update ${sequence}${channel ? ` on ${channel}` : ""}`;
}

/** "T+04:12" on the drill clock. */
export function formatClock(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  return `T+${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}

/** Wall-clock IST time for a drill offset from the declaration time. */
export function istAt(declaredAtIso: string, offsetSeconds: number): string {
  const t = new Date(new Date(declaredAtIso).getTime() + offsetSeconds * 1000);
  return new Intl.DateTimeFormat("en-GB", { timeZone: "Asia/Kolkata", hour: "2-digit", minute: "2-digit", hour12: false }).format(t);
}
