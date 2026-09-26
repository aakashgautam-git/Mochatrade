import { useQuery } from "@tanstack/react-query";
import {
  Camera,
  CircleCheck,
  CirclePause,
  FastForward,
  Gavel,
  Megaphone,
  OctagonX,
  Pause,
  Play,
  Radar,
  ShieldCheck,
  SkipForward,
  TriangleAlert,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { useApp } from "../app/store";
import { PriceChart } from "../components/charts";
import { PauseNote } from "../components/PauseNote";
import {
  Badge,
  Button,
  Card,
  CardBody,
  CardDescription,
  CardEyebrow,
  CardHeader,
  CardTitle,
  Countdown,
  EmptyState,
  Select,
  Skeleton,
  Stat,
  TextField,
  Timeline,
  toast,
  type TimelineItem,
  type Tone,
} from "../components/ui";
import {
  classifyIncident,
  advanceClock,
  ApiError,
  declareIncident,
  fetchScenarios,
  incidentAction,
  incidentState,
  incidentTicks,
  listIncidents,
  publishUpdate,
  stepIncident,
} from "../lib/api";
import { auctionMarkers, controlRegions, liquidationBursts, priceSeries } from "../lib/sim";
import type { ActionType, IncidentState, Tick, TriageLayer, TriageStatus } from "../lib/types";
import { formatClock, istAt, phaseAt, pillFor, playbookStatus, type Role, type StepState } from "../lib/warroom";

const ROLE_BLURB: Record<Role, string> = {
  IC: "Incident Commander. Owns the decisions and the clock. Does not touch a keyboard.",
  OPS: "Engineering. System state, kill switches, evidence capture.",
  COMMS: "Support and comms. Status page, social, macros, then the claims queue.",
};

export function WarRoom() {
  const code = useApp((s) => s.incidentCode);
  const setCode = useApp((s) => s.setIncidentCode);
  const setSystemState = useApp((s) => s.setSystemState);

  const close = useCallback(() => {
    setCode(null);
    setSystemState("NORMAL");
  }, [setCode, setSystemState]);

  return code ? <IncidentRoom code={code} onClose={close} /> : <DeclarePanel onOpen={setCode} />;
}

// ---------------------------------------------------------------------------
// Declare
// ---------------------------------------------------------------------------

function DeclarePanel({ onOpen }: { onOpen: (code: string) => void }) {
  const scenarios = useQuery({ queryKey: ["scenarios"], queryFn: fetchScenarios });
  const recent = useQuery({ queryKey: ["incidents"], queryFn: listIncidents, staleTime: 0 });
  const [slug, setSlug] = useState("oracle_defect_hip3");
  const [ic, setIc] = useState("CEO");
  const [ops, setOps] = useState("CTO");
  const [comms, setComms] = useState("Support lead");
  const [busy, setBusy] = useState(false);

  const declare = async () => {
    setBusy(true);
    try {
      const state = await declareIncident({
        scenario_slug: slug,
        controls_enabled: true,
        incident_commander: ic,
        ops_lead: ops,
        comms_lead: comms,
      });
      toast(`${state.incident.code} declared`, { tone: "warn", description: "SEV-1. Roles assumed as pre-assigned. The clock is at T+0." });
      onOpen(state.incident.code);
    } catch (e) {
      toast("Could not declare", { tone: "neg", description: e instanceof Error ? e.message : String(e) });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <header>
        <p className="text-xs font-medium uppercase tracking-[0.12em] text-text-dim">War room</p>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight">The first 60 minutes, drilled live</h1>
        <p className="mt-2 max-w-3xl text-sm leading-relaxed text-text-dim">
          Declare an incident on a scenario. The market plays out on the engine, one tick a second,
          with the published controls running. You make the playbook's decisions on one clock from
          T+0 to T+60, and every decision lands in an append-only log. Minute one is not “what did
          the market do” — it is “which of our three layers broke”.
        </p>
      </header>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <Card>
          <CardHeader>
            <CardEyebrow>Declare</CardEyebrow>
            <CardTitle>SEV-1, I am IC</CardTitle>
            <CardDescription>Roles are pre-assigned in writing. At T+0 you assume them; you do not discuss them.</CardDescription>
          </CardHeader>
          <CardBody className="space-y-4">
            <Select
              label="Scenario"
              value={slug}
              onChange={setSlug}
              options={(scenarios.data ?? []).map((s) => ({ value: s.slug, label: s.name }))}
              disabled={!scenarios.data}
            />
            <div className="grid gap-4 sm:grid-cols-3">
              <TextField label="IC" value={ic} onChange={setIc} hint={ROLE_BLURB.IC} />
              <TextField label="OPS" value={ops} onChange={setOps} hint={ROLE_BLURB.OPS} />
              <TextField label="COMMS" value={comms} onChange={setComms} hint={ROLE_BLURB.COMMS} />
            </div>
            <Button variant="primary" icon={<Radar />} loading={busy} onClick={declare} disabled={!scenarios.data}>
              Declare SEV-1
            </Button>
          </CardBody>
        </Card>

        <Card>
          <CardHeader>
            <CardEyebrow>Resume</CardEyebrow>
            <CardTitle>Recent incidents</CardTitle>
          </CardHeader>
          <CardBody>
            {recent.isPending ? (
              <Skeleton className="h-24 w-full" />
            ) : !recent.data?.length ? (
              <p className="text-sm text-text-dim">No incidents yet.</p>
            ) : (
              <ul className="divide-y divide-line">
                {recent.data.slice(0, 6).map((inc) => (
                  <li key={inc.code} className="flex items-center justify-between gap-3 py-3">
                    <div className="min-w-0">
                      <p className="num text-sm text-text">{inc.code}</p>
                      <p className="truncate text-xs text-text-dim">{inc.scenario_slug ?? "—"} · {inc.status.toLowerCase()}</p>
                    </div>
                    <Button size="sm" onClick={() => onOpen(inc.code)}>Open</Button>
                  </li>
                ))}
              </ul>
            )}
          </CardBody>
        </Card>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// The room
// ---------------------------------------------------------------------------

const SPEEDS = [1, 5, 10, 30, 60];

const DEFAULT_RATIONALE: Partial<Record<ActionType, string>> = {
  PROTECT_SWITCH: "Contain: reduce-only, liquidation TWAP throttle, 3x max leverage. haltTrading stays holstered.",
  REDUCE_ONLY: "Reduce-only: people can leave; nobody can add risk. Cost accepted: adding margin is blocked too.",
  PAUSE_LIQUIDATIONS: "The price feed is suspect; liquidations pause on this market only.",
  LIQ_THROTTLE: "Our engine is the largest seller in the book; throttle to the published cap.",
  LEVERAGE_CAP: "Cut max leverage to 3x while the market is disorderly.",
  SNAPSHOT_EVIDENCE: "Write-once snapshot of book, tape, per-source oracle inputs, marks, liquidations and deposits.",
  HALT_MARKET: "The oracle cannot be recovered; halting despite settling at the disputed mark.",
  CLASSIFY: "Classified against the published APE policy.",
  QUANTIFY: "Affected set and counterfactual equity computed.",
  OPEN_CLAIMS: "Claims portal open for 72 hours; every ticket linked to its own status.",
  PROVISIONAL_CREDIT: "Provisional credit pushed to clear C/D/E cases as locked trading credit.",
  STAGED_REOPEN: "Oracle healthy five minutes, spread and depth back: advance the reopen one gate.",
  RESOLVE: "Handover: what happened, who is affected, what we pay, when it lands, and the RCA date.",
};

interface Confirmation {
  type: ActionType;
  title: string;
  message: string;
  variant: "danger" | "halt";
}

function IncidentRoom({ code, onClose }: { code: string; onClose: () => void }) {
  const setSystemState = useApp((s) => s.setSystemState);
  const setInstrument = useApp((s) => s.setInstrument);

  const [state, setState] = useState<IncidentState | null>(null);
  const [ticks, setTicks] = useState<Tick[]>([]);
  const [missing, setMissing] = useState(false);
  const [running, setRunning] = useState(false);
  const [speed, setSpeed] = useState(10);
  const [actor, setActor] = useState<Role>("IC");
  const [rationale, setRationale] = useState("");
  const [confirm, setConfirm] = useState<Confirmation | null>(null);
  const [headline, setHeadline] = useState("");
  const [body, setBody] = useState("");
  const stateRef = useRef<IncidentState | null>(null);
  stateRef.current = state;

  // Load, and reload after a restart: the server rebuilds the engine silently.
  useEffect(() => {
    let live = true;
    Promise.all([incidentState(code), incidentTicks(code)])
      .then(([s, t]) => {
        if (!live) return;
        setState(s);
        setTicks(t.ticks);
      })
      .catch(() => live && setMissing(true));
    return () => {
      live = false;
    };
  }, [code]);

  // The pill is the live market. This page is the only place that drives it.
  useEffect(() => {
    if (!state) return;
    setInstrument(state.scenario.instrument);
    setSystemState(state.incident.status === "RESOLVED" ? "NORMAL" : pillFor(state.snapshot));
  }, [state, setInstrument, setSystemState]);

  const refresh = useCallback(async () => {
    setState(await incidentState(code));
  }, [code]);

  const advance = useCallback(
    async (seconds: number) => {
      const s = stateRef.current;
      if (!s) return;
      if (!s.finished) {
        const r = await stepIncident(code, Math.min(seconds, 600));
        setTicks((prev) => [...prev, ...r.snapshots]);
        await refresh();
      } else if (s.drill_clock_s < s.drill_total_s) {
        setState(await advanceClock(code, Math.min(s.drill_total_s, s.drill_clock_s + seconds)));
      }
    },
    [code, refresh],
  );

  // Run the clock: one request per second, never overlapping.
  useEffect(() => {
    if (!running) return;
    let cancelled = false;
    const loop = async () => {
      while (!cancelled) {
        const began = performance.now();
        try {
          await advance(speed);
        } catch (e) {
          toast("The clock stopped", { tone: "neg", description: e instanceof Error ? e.message : String(e) });
          setRunning(false);
          return;
        }
        const s = stateRef.current;
        if (s && s.finished && s.drill_clock_s >= s.drill_total_s) {
          setRunning(false);
          return;
        }
        await new Promise((r) => setTimeout(r, Math.max(0, 1000 - (performance.now() - began))));
      }
    };
    void loop();
    return () => {
      cancelled = true;
    };
  }, [running, speed, advance]);

  const series = useMemo(
    () => ({
      price: priceSeries(ticks),
      regions: controlRegions(ticks),
      bursts: liquidationBursts(ticks),
      auctions: auctionMarkers(ticks),
    }),
    [ticks],
  );

  if (missing) {
    return (
      <div className="mx-auto max-w-3xl">
        <EmptyState
          icon={<TriangleAlert />}
          title={`No incident ${code}`}
          description="It may belong to a database that was reset. Declare a new one."
          action={<Button onClick={onClose}>Back to declare</Button>}
        />
      </div>
    );
  }
  if (!state) {
    return (
      <div className="mx-auto max-w-6xl space-y-4">
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  const clock = state.drill_clock_s;
  const phase = phaseAt(clock);
  const steps = playbookStatus(state.actions, clock);
  const resolved = state.incident.status === "RESOLVED";
  const snap = state.snapshot;
  // Overdue first, then due, then the earliest step not yet open: between T+0
  // and T+2 every remaining step is still upcoming, not finished.
  const nextDue =
    steps.find((s) => s.state === "overdue") ??
    steps.find((s) => s.state === "due") ??
    steps.find((s) => s.state === "upcoming");
  const updates = state.actions.filter((a) => a.action_type === "PUBLISH_UPDATE").length;

  const act = async (type: ActionType, params: Record<string, unknown> = {}) => {
    setConfirm(null);
    const who = actor === "IC" ? state.incident.incident_commander || "IC" : actor === "OPS" ? state.incident.ops_lead || "OPS" : state.incident.comms_lead || "COMMS";
    if (type === "CLASSIFY") {
      // Diagnose runs the published APE test on the tape, not a free-text note.
      try {
        const r = await classifyIncident(code, { actor: who, rationale: rationale.trim() });
        const v = r.verdict;
        toast(v ? `Class ${v.category}: ${v.label}` : "Classified", {
          tone: "pos",
          description: v ? `${v.headline}${v.provisional ? " Provisional: the market is still moving." : ""} The working is on the Forensics page.` : "",
        });
        setRationale("");
        await refresh();
      } catch (e) {
        toast("Refused", { tone: "neg", description: e instanceof ApiError ? e.message : String(e) });
      }
      return;
    }
    try {
      const r = await incidentAction(code, {
        action_type: type,
        actor: who,
        rationale: rationale.trim() || DEFAULT_RATIONALE[type] || "",
        params,
      });
      toast(r.action.action_type_display, { tone: r.affects_engine ? "warn" : "pos", description: r.note });
      setRationale("");
      await refresh();
      if (type === "RESOLVE") onClose();
    } catch (e) {
      toast("Refused", { tone: "neg", description: e instanceof ApiError ? e.message : String(e) });
    }
  };

  const guarded = (type: ActionType) => {
    if (type === "PAUSE_LIQUIDATIONS" && snap && snap.oracle_health === "healthy") {
      setConfirm({
        type,
        variant: "halt",
        title: "The price feed is healthy",
        message:
          "Pause liquidations only if the price is suspect. Pausing while the feed is healthy does not save users; it converts their losses into our insolvency.",
      });
      return;
    }
    if (type === "HALT_MARKET") {
      setConfirm({
        type,
        variant: "danger",
        title: "haltTrading is irreversible",
        message:
          "It cancels every order and settles every position at the current mark — the mark under dispute. A pricing dispute becomes a settlement dispute for the whole book.",
      });
      return;
    }
    if (type === "RESOLVE") {
      const open = steps.filter((s) => s.state !== "done" && s.step.id !== "handover").length;
      if (open > 0) {
        setConfirm({
          type,
          variant: "danger",
          title: `${open} playbook step${open === 1 ? " is" : "s are"} still open`,
          message: "Handover closes the log. Publish what happened, who is affected, what we are paying, when it lands, and the RCA date.",
        });
        return;
      }
    }
    void act(type);
  };

  const draftUpdate = () => {
    const n = updates + 1;
    const since = istAt(state.incident.declared_at, 0);
    const next = istAt(state.incident.declared_at, clock + 600);
    const contained = state.actions.some((a) => a.action_type === "PROTECT_SWITCH");
    const turnedOn = contained
      ? "reduce-only, a liquidation throttle and a 3x leverage cap"
      : "our automatic volatility controls";
    const cls = state.incident.classification;
    if (n === 1) {
      setHeadline(`Abnormal price moves on ${state.scenario.instrument}`);
      setBody(`We are seeing abnormal price moves on ${state.scenario.instrument} since ${since} IST. What we have turned on: ${turnedOn}. We have not confirmed a cause and we will not guess. Next update at ${next} IST.`);
    } else if (n === 2) {
      const ours = cls === "C" || cls === "D" || cls === "E";
      setHeadline(ours ? "Preliminary finding: the fault is ours" : `Update on ${state.scenario.instrument}`);
      setBody(
        ours
          ? `Our preliminary finding is that this was a fault on our side (class ${cls} under our published Abnormal Price Event policy). Affected users will be made whole under that policy. Trades stand; people get made whole. Next update at ${next} IST with the number.`
          : `We are still diagnosing across our market, our app and the venue. What we have turned on: ${turnedOn}. Next update at ${next} IST.`,
      );
    } else {
      const n3 = state.incident.affected_accounts_count;
      setHeadline(n3 ? `${n3} users affected` : `Update on ${state.scenario.instrument}`);
      setBody(
        n3
          ? `${n3} users are affected, ${state.incident.aggregate_exposure_inr_display} in aggregate, between ${since} and ${istAt(state.incident.declared_at, state.total_ticks)} IST. Compensation follows our published Abnormal Price Event policy. Next update at ${next} IST.`
          : `We are computing the affected set and will publish the number once it is computed — not an estimate. Next update at ${next} IST.`,
      );
    }
  };

  const publish = async () => {
    if (!headline.trim() || !body.trim()) {
      toast("Write the update first", { tone: "warn" });
      return;
    }
    try {
      await publishUpdate(code, { channel: "STATUS_PAGE", headline, body, is_published: true });
      toast(`Update ${updates + 1} published`, { tone: "pos", description: "Status page. Full channel templates and guardrails are on the Comms page." });
      setHeadline("");
      setBody("");
      await refresh();
    } catch (e) {
      toast("Not published", { tone: "neg", description: e instanceof Error ? e.message : String(e) });
    }
  };

  const log: TimelineItem[] = state.actions.map((a) => ({
    id: a.id,
    time: formatClock(a.tick),
    wall: `${istAt(state.incident.declared_at, a.tick)} IST`,
    actor: a.actor,
    action: a.action_type_display,
    rationale: a.rationale,
    irreversible: !a.reversible,
    tone: a.action_type === "DECLARE" ? "neg" : a.action_type === "PUBLISH_UPDATE" ? "pos" : "accent",
  }));

  const live = !state.finished && !resolved;

  return (
    <div className="space-y-4">
      {/* Clock and controls */}
      <Card>
        <CardBody className="flex flex-wrap items-center justify-between gap-6 pt-6">
          <div className="flex items-center gap-6">
            <div>
              <p className="text-xs font-medium uppercase tracking-[0.12em] text-text-dim">Playbook clock</p>
              <p className="num mt-1 text-4xl font-semibold tracking-tight">{formatClock(clock)}</p>
            </div>
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <Badge tone="neg" mono>{state.incident.code}</Badge>
                <Badge mono>{state.scenario.instrument}</Badge>
                <Badge>{state.scenario.ist_label}</Badge>
                {resolved ? <Badge tone="pos" icon={<CircleCheck />}>Resolved</Badge> : null}
              </div>
              <p className="mt-2 text-sm text-text">{state.scenario.name}</p>
              <p className="text-xs text-text-dim">
                Now: <span className="text-text">{phase.title}</span> ·{" "}
                {state.finished
                  ? "market event over; the response continues to T+60"
                  : `market tick ${state.current_tick} of ${state.total_ticks}`}
              </p>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <Button
              variant="primary"
              icon={running ? <Pause /> : <Play />}
              onClick={() => setRunning((r) => !r)}
              disabled={resolved || (state.finished && clock >= state.drill_total_s)}
            >
              {running ? "Pause clock" : "Run clock"}
            </Button>
            <Select
              label="Speed"
              hideLabel
              mono
              value={String(speed)}
              onChange={(v) => setSpeed(Number(v))}
              options={SPEEDS.map((s) => ({ value: String(s), label: `${s}× — ${s}s per second` }))}
            />
            <Button icon={<SkipForward />} onClick={() => void advance(10)} disabled={running || resolved}>+10s</Button>
            <Button icon={<FastForward />} onClick={() => void advance(state.finished ? 300 : 60)} disabled={running || resolved}>
              {state.finished ? "+5 min" : "+60s"}
            </Button>
          </div>
        </CardBody>
      </Card>

      {/* Three-layer triage */}
      <section aria-label="Three-layer triage" className="grid gap-4 lg:grid-cols-3">
        {state.triage.map((layer) => (
          <TriageCard key={layer.layer} layer={layer} />
        ))}
      </section>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        {/* Market */}
        <Card>
          <CardHeader actions={<Badge mono>{snap ? `${snap.oracle_health.replace("_", " ")} · L${snap.composite_rung}` : "no ticks yet"}</Badge>}>
            <CardEyebrow>Market</CardEyebrow>
            <CardTitle>What the book and the oracle are doing</CardTitle>
          </CardHeader>
          <CardBody className="space-y-6">
            <div className="grid grid-cols-2 gap-6 sm:grid-cols-4">
              <Stat label="Liquidated" value={snap?.cum_liquidated_accounts ?? 0} duration={300} />
              <Stat label="ADL events" value={snap?.adl_accounts ?? 0} duration={300} />
              <Stat label="Depth vs calm" value={(snap?.depth_pct_of_baseline ?? 1) * 100} format={(n) => `${Math.round(n)}%`} duration={300} />
              <Stat label="Mark vs clean ref." value={snap?.divergence_bps ?? 0} format={(n) => `${n >= 0 ? "+" : ""}${Math.round(n)} bps`} duration={300} />
            </div>
            {ticks.length > 1 ? (
              <PriceChart data={series.price} regions={series.regions} bursts={series.bursts} auctions={series.auctions} height={260} />
            ) : (
              <EmptyState icon={<Play />} title="The market has not started" description="Run the clock. One engine tick is one second." />
            )}
            <PauseNote />
          </CardBody>
        </Card>

        {/* Playbook */}
        <Card>
          <CardHeader>
            <CardEyebrow>Playbook</CardEyebrow>
            <CardTitle>{nextDue ? nextDue.step.title : "Every step is done"}</CardTitle>
            <CardDescription>{nextDue ? nextDue.step.guidance : "Hand over when you are ready."}</CardDescription>
          </CardHeader>
          <CardBody className="space-y-4">
            {nextDue ? <Countdown label={`${nextDue.step.owner} · due at ${formatClock(nextDue.step.due)}`} remaining={nextDue.remaining} warnAt={60} size="sm" /> : null}
            <ol className="divide-y divide-line">
              {steps.map((s) => (
                <li key={s.step.id} className="flex items-center justify-between gap-3 py-2">
                  <div className="min-w-0">
                    <p className="truncate text-sm text-text">{s.step.title}</p>
                    <p className="num text-xs text-text-dim">
                      {s.step.owner} · {formatClock(s.step.from)}–{formatClock(s.step.due).slice(2)}
                    </p>
                  </div>
                  <StepBadge state={s.state} doneAt={s.doneAt} />
                </li>
              ))}
            </ol>
          </CardBody>
        </Card>
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        {/* Decisions */}
        <Card>
          <CardHeader>
            <CardEyebrow>Decisions</CardEyebrow>
            <CardTitle>Decide, execute, publish</CardTitle>
            <CardDescription>The IC decides and does not type. OPS executes. COMMS publishes. Every decision needs a reason, written now.</CardDescription>
          </CardHeader>
          <CardBody className="space-y-6">
            <div className="grid gap-4 sm:grid-cols-[12rem_minmax(0,1fr)]">
              <Select
                label="Acting as"
                value={actor}
                onChange={(v) => setActor(v as Role)}
                options={[
                  { value: "IC", label: `IC — ${state.incident.incident_commander || "IC"}` },
                  { value: "OPS", label: `OPS — ${state.incident.ops_lead || "OPS"}` },
                  { value: "COMMS", label: `COMMS — ${state.incident.comms_lead || "COMMS"}` },
                ]}
              />
              <TextField label="Rationale" value={rationale} onChange={setRationale} placeholder="Why, in your own words. Left blank, the playbook's reason is logged." />
            </div>

            {confirm ? (
              <div role="alertdialog" aria-labelledby="confirm-title" className="rounded-control border border-neg-edge bg-neg-soft p-4">
                <p id="confirm-title" className="text-sm font-medium text-neg-fg">{confirm.title}</p>
                <p className="mt-1 text-sm leading-relaxed text-text">{confirm.message}</p>
                <div className="mt-3 flex gap-2">
                  <Button size="sm" variant={confirm.variant} onClick={() => void act(confirm.type)}>Do it anyway</Button>
                  <Button size="sm" onClick={() => setConfirm(null)}>Cancel</Button>
                </div>
              </div>
            ) : null}

            <ActionGroup title="Live market" note={live ? "Changes the next tick." : "The market event has ended; these no longer change anything."}>
              <Button variant="halt" icon={<ShieldCheck />} disabled={!live} onClick={() => guarded("PROTECT_SWITCH")}>Protect Switch</Button>
              <Button disabled={!live} onClick={() => guarded("LIQ_THROTTLE")}>Throttle liquidations</Button>
              <Button disabled={!live} onClick={() => guarded("LEVERAGE_CAP")}>Cap leverage 3x</Button>
              <Button variant="halt" icon={<CirclePause />} disabled={!live} onClick={() => guarded("PAUSE_LIQUIDATIONS")}>Pause liquidations</Button>
              <Button variant="danger" icon={<OctagonX />} disabled={!live} onClick={() => guarded("HALT_MARKET")}>haltTrading</Button>
            </ActionGroup>

            <ActionGroup title="Evidence and diagnosis">
              <Button icon={<Camera />} disabled={resolved} onClick={() => guarded("SNAPSHOT_EVIDENCE")}>Snapshot evidence</Button>
              <Button icon={<Gavel />} disabled={resolved} onClick={() => guarded("CLASSIFY")}>Run the APE test</Button>
              <Button disabled={resolved} onClick={() => guarded("QUANTIFY")}>Log quantified</Button>
            </ActionGroup>

            <ActionGroup title="Remediate, reopen, hand over">
              <Button disabled={resolved} onClick={() => guarded("PROVISIONAL_CREDIT")}>Provisional credit</Button>
              <Button disabled={resolved} onClick={() => guarded("OPEN_CLAIMS")}>Open claims portal</Button>
              <Button disabled={resolved} onClick={() => guarded("STAGED_REOPEN")}>Advance reopen</Button>
              <Button variant="danger" disabled={resolved} onClick={() => guarded("RESOLVE")}>Hand over</Button>
            </ActionGroup>

            <div className="space-y-3 border-t border-line pt-6">
              <div className="flex items-center justify-between gap-3">
                <p className="text-xs font-medium uppercase tracking-[0.12em] text-text-dim">Public update {updates + 1}</p>
                <Button size="sm" icon={<Megaphone />} onClick={draftUpdate} disabled={resolved}>Draft from the playbook</Button>
              </div>
              <TextField label="Headline" value={headline} onChange={setHeadline} />
              <TextField label="Body" value={body} onChange={setBody} multiline rows={4} hint="No cause, no blame, a committed next-update time. Guardrails and every channel are on the Comms page." />
              <Button icon={<Megaphone />} onClick={() => void publish()} disabled={resolved}>Publish to status page</Button>
            </div>
          </CardBody>
        </Card>

        {/* Log */}
        <Card>
          <CardHeader actions={<Badge mono>{`${state.actions.length} entries`}</Badge>}>
            <CardEyebrow>Action log</CardEyebrow>
            <CardTitle>Append-only</CardTitle>
            <CardDescription>What was decided, by whom, when and why. It cannot be edited after the fact.</CardDescription>
          </CardHeader>
          <CardBody>
            <Timeline items={log} />
          </CardBody>
        </Card>
      </div>
    </div>
  );
}

function ActionGroup({ title, note, children }: { title: string; note?: string; children: ReactNode }) {
  return (
    <div>
      <p className="text-xs font-medium uppercase tracking-[0.12em] text-text-dim">{title}</p>
      {note ? <p className="mt-1 text-xs text-text-dim">{note}</p> : null}
      <div className="mt-3 flex flex-wrap gap-2">{children}</div>
    </div>
  );
}

const STATUS_LOOK: Record<TriageStatus, { tone: Tone; label: string; Icon: typeof CircleCheck }> = {
  ok: { tone: "pos", label: "No fault", Icon: CircleCheck },
  warn: { tone: "warn", label: "Degraded", Icon: TriangleAlert },
  fail: { tone: "neg", label: "Failing", Icon: OctagonX },
};

function TriageCard({ layer }: { layer: TriageLayer }) {
  const look = STATUS_LOOK[layer.status];
  return (
    <Card>
      <CardHeader actions={<Badge tone={look.tone} icon={<look.Icon />}>{look.label}</Badge>}>
        <CardEyebrow>{layer.tier} · {layer.control}</CardEyebrow>
        <CardTitle>{layer.name}</CardTitle>
        <CardDescription>{layer.headline}</CardDescription>
      </CardHeader>
      <CardBody>
        <ul className="space-y-2">
          {layer.signals.map((s) => {
            const sig = STATUS_LOOK[s.status as TriageStatus];
            return (
              <li key={s.label} className="flex items-center justify-between gap-3 text-sm">
                <span className="flex min-w-0 items-center gap-2 text-text-dim">
                  <sig.Icon aria-label={sig.label} className={`h-3.5 w-3.5 shrink-0 ${s.status === "ok" ? "text-pos-fg" : s.status === "warn" ? "text-warn-fg" : "text-neg-fg"}`} />
                  <span className="truncate">{s.label}</span>
                </span>
                <span className="num shrink-0 text-text">{s.value}</span>
              </li>
            );
          })}
        </ul>
      </CardBody>
    </Card>
  );
}

function StepBadge({ state, doneAt }: { state: StepState; doneAt: number | null }) {
  if (state === "done") return <Badge tone="pos" mono icon={<CircleCheck />}>{`done ${formatClock(doneAt ?? 0)}`}</Badge>;
  if (state === "overdue") return <Badge tone="neg" icon={<OctagonX />}>Overdue</Badge>;
  if (state === "due") return <Badge tone="warn" icon={<TriangleAlert />}>Due</Badge>;
  return <Badge>Upcoming</Badge>;
}
