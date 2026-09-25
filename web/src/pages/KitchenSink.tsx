import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  CirclePause,
  FlaskConical,
  Inbox,
  OctagonX,
  Play,
  RotateCcw,
  ShieldAlert,
  TriangleAlert,
  X,
} from "lucide-react";
import { useEffect, useMemo, useState, type ReactNode } from "react";

import { useApp, type SystemState } from "../app/store";
import { LOOK, SystemStatePill } from "../app/SystemStatePill";
import {
  CascadeChart,
  DepthLadder,
  DeviationChart,
  PriceChart,
  type CascadePoint,
  type ControlRegion,
  type DepthLevel,
  type LiquidationBurst,
} from "../components/charts";
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
  SkeletonText,
  Slider,
  Sparkline,
  Stat,
  Timeline,
  toast,
  Toggle,
  type TimelineItem,
} from "../components/ui";
import { fetchActivePolicy, fetchCompare, parseMoney, rupees } from "../lib/api";
import type { Tick } from "../lib/types";

const SECTIONS = [
  ["state", "System state"],
  ["stats", "Stats"],
  ["buttons", "Buttons"],
  ["inputs", "Inputs"],
  ["badges", "Badges"],
  ["timeline", "Timeline"],
  ["countdown", "Countdown"],
  ["charts", "Charts"],
  ["feedback", "Feedback"],
  ["tokens", "Tokens"],
] as const;

export function KitchenSink() {
  const preview = useApp((s) => s.previewDocumentTheme);
  const setPreview = useApp((s) => s.setPreviewDocumentTheme);
  useEffect(() => () => setPreview(false), [setPreview]);

  return (
    <div className="mx-auto max-w-6xl">
      <header className="mb-8">
        <p className="text-xs font-medium uppercase tracking-[0.12em] text-text-dim">Phase 5</p>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight">Design system</h1>
        <p className="mt-2 max-w-2xl text-sm leading-relaxed text-text-dim">
          Every primitive in every state. Charts marked <em>live</em> are drawn
          from a persisted engine run of the macro cascade; charts marked{" "}
          <em>fixture</em> need per-stage or per-level data the engine does not
          emit yet.
        </p>
        <nav aria-label="Sections" className="mt-6 flex flex-wrap gap-2">
          {SECTIONS.map(([id, label]) => (
            <a
              key={id}
              href={`#${id}`}
              className="rounded-chip border border-line px-2 py-1 text-xs text-text-dim transition-colors duration-fast hover:bg-surface-2 hover:text-text"
            >
              {label}
            </a>
          ))}
        </nav>
        <div className="mt-6 max-w-xl">
          <Toggle
            checked={preview}
            onChange={setPreview}
            label="Preview the document palette"
            description="Report and Playbook can be read light. Everything else stays dark, because this is a war room."
          />
        </div>
      </header>

      <div className="space-y-12">
        <StateSection />
        <StatsSection />
        <ButtonsSection />
        <InputsSection />
        <BadgesSection />
        <TimelineSection />
        <CountdownSection />
        <ChartsSection />
        <FeedbackSection />
        <TokensSection />
      </div>
    </div>
  );
}

function Section({ id, title, description, children }: { id: string; title: string; description?: string; children: ReactNode }) {
  return (
    <section id={id} aria-labelledby={`${id}-h`} className="scroll-mt-20">
      <h2 id={`${id}-h`} className="text-lg font-semibold tracking-tight">{title}</h2>
      {description ? <p className="mt-1 max-w-2xl text-sm leading-relaxed text-text-dim">{description}</p> : null}
      <div className="mt-6">{children}</div>
    </section>
  );
}

// ---------------------------------------------------------------------------

const STATES: SystemState[] = ["NORMAL", "REDUCE_ONLY", "LIQ_PAUSED", "HALTED", "DEGRADED_ORACLE"];

function StateSection() {
  const state = useApp((s) => s.systemState);
  const setState = useApp((s) => s.setSystemState);
  const incident = useApp((s) => s.incidentCode);
  const setIncident = useApp((s) => s.setIncidentCode);

  return (
    <Section
      id="state"
      title="System state"
      description="The single most important element in the interface. Colour, words and icon change together, and a band across the top of the viewport appears for any state that is not normal. Pick one to drive the real top bar."
    >
      <Card>
        <CardBody className="pt-6">
          <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
            {STATES.map((s) => (
              <li key={s}>
                <button
                  type="button"
                  onClick={() => setState(s)}
                  aria-pressed={state === s}
                  className="flex h-full w-full flex-col items-start gap-3 rounded-control border border-line p-4 text-left transition-colors duration-fast hover:bg-surface-2 aria-pressed:border-accent aria-pressed:bg-surface-2"
                >
                  <SystemStatePill state={s} />
                  <span className="text-xs leading-relaxed text-text-dim">{LOOK[s].meaning}</span>
                </button>
              </li>
            ))}
          </ul>
          <div className="mt-6 max-w-xl border-t border-line pt-6">
            <Toggle
              checked={incident !== null}
              onChange={(on) => setIncident(on ? "INC-20260926-01" : null)}
              label="Open an incident"
              description="Shows the incident code in the top bar. A sample code, not a real incident."
            />
          </div>
        </CardBody>
      </Card>
    </Section>
  );
}

// ---------------------------------------------------------------------------

function useMacroCascade() {
  return useQuery({ queryKey: ["compare", "macro_cascade"], queryFn: () => fetchCompare("macro_cascade") });
}

function StatsSection() {
  const { data, isPending, isError } = useMacroCascade();
  const [showOff, setShowOff] = useState(false);
  const [replay, setReplay] = useState(0);

  const on = data?.on.summary;
  const off = data?.off.summary;
  const shown = showOff ? off : on;
  const other = showOff ? on : off;

  const change = (a: number, b: number) => (b === 0 ? 0 : ((a - b) / b) * 100);

  return (
    <Section
      id="stats"
      title="Stats"
      description="Values count, never fade. Each value sits alone on its line inside a cell as wide as the widest of its start and end, so counting cannot move anything around it."
    >
      <div className="mb-4 flex flex-wrap items-center gap-4">
        <Button icon={<RotateCcw />} onClick={() => setReplay((r) => r + 1)} disabled={!data}>
          Replay count from zero
        </Button>
        <div className="w-80">
          <Toggle
            checked={showOff}
            onChange={setShowOff}
            label="Show the unprotected run"
            description="Counts between the two real results, up and down."
            disabled={!data}
          />
        </div>
        <Badge mono icon={<Activity />}>live · macro_cascade</Badge>
      </div>
      {isError ? (
        <EmptyState icon={<TriangleAlert />} title="The API is not reachable" description="Start Django with `make dev` and run `make seed`." />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {[
            {
              label: "Accounts liquidated",
              value: shown?.accounts_liquidated ?? 0,
              base: other?.accounts_liquidated ?? 0,
              caption: `of ${(on?.accounts_total ?? 0).toLocaleString("en-IN")}`,
            },
            {
              label: "User loss",
              value: shown ? parseMoney(shown.user_loss_inr) : 0,
              base: other ? parseMoney(other.user_loss_inr) : 0,
              format: rupees,
            },
            {
              label: "Unnecessary liquidations",
              value: shown?.unnecessary_liquidations ?? 0,
              base: other?.unnecessary_liquidations ?? 0,
              caption: "solvent at the composite",
            },
            {
              label: "ADL events",
              value: shown?.adl_accounts ?? 0,
              base: other?.adl_accounts ?? 0,
              caption: "winners force-closed",
            },
          ].map((s) => (
            <Card key={s.label}>
              <CardBody className="pt-6">
                <Stat
                  key={`${s.label}-${replay}`}
                  label={s.label}
                  value={s.value}
                  startFrom={0}
                  loading={isPending}
                  format={s.format}
                  delta={data ? { pct: change(s.value, s.base), goodWhen: "down" } : undefined}
                  baseline={data ? { value: s.base, label: showOff ? "protected" : "unprotected" } : undefined}
                  caption={s.caption}
                />
              </CardBody>
            </Card>
          ))}
        </div>
      )}
      <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardBody className="pt-6">
            <Stat label="Loading state" value={0} loading />
          </CardBody>
        </Card>
        <Card>
          <CardBody className="pt-6">
            <Stat label="Large, no delta" value={1033} size="lg" caption="size lg" />
          </CardBody>
        </Card>
        <Card>
          <CardBody className="pt-6">
            <Stat label="Rising is good" value={128} delta={{ pct: 18, goodWhen: "up" }} />
          </CardBody>
        </Card>
        <Card>
          <CardBody className="pt-6">
            <Stat label="Unchanged" value={253} delta={{ pct: 0.2, goodWhen: "down" }} />
          </CardBody>
        </Card>
      </div>
    </Section>
  );
}

// ---------------------------------------------------------------------------

function ButtonsSection() {
  const [busy, setBusy] = useState(false);
  return (
    <Section
      id="buttons"
      title="Buttons"
      description="Primary is mocha and is used once per view. Danger is for destructive actions. Halt is reserved for halt and intervention actions -- nothing else uses that colour."
    >
      <Card>
        <CardBody className="space-y-6 pt-6">
          {(["primary", "ghost", "danger", "halt"] as const).map((variant) => (
            <div key={variant} className="flex flex-wrap items-center gap-3">
              <span className="num w-20 text-xs text-text-dim">{variant}</span>
              <Button variant={variant} size="sm">Small</Button>
              <Button variant={variant}>Default</Button>
              <Button variant={variant} size="lg">Large</Button>
              <Button variant={variant} icon={variant === "halt" ? <CirclePause /> : variant === "danger" ? <X /> : <Play />}>
                {variant === "halt" ? "Pause liquidations" : variant === "danger" ? "Reject claim" : "With icon"}
              </Button>
              <Button variant={variant} disabled>Disabled</Button>
            </div>
          ))}
          <div className="flex flex-wrap items-center gap-3 border-t border-line pt-6">
            <span className="num w-20 text-xs text-text-dim">loading</span>
            <Button
              variant="primary"
              loading={busy}
              onClick={() => {
                setBusy(true);
                window.setTimeout(() => setBusy(false), 1500);
              }}
            >
              {busy ? "Running…" : "Run comparison"}
            </Button>
            <Button variant="halt" icon={<OctagonX />}>haltTrading</Button>
            <span className="text-xs text-text-dim">Default height 36px. Hover shifts the fill; nothing scales.</span>
          </div>
        </CardBody>
      </Card>
    </Section>
  );
}

// ---------------------------------------------------------------------------

function InputsSection() {
  const [throttle, setThrottle] = useState(true);
  const [grace, setGrace] = useState(false);
  const [participation, setParticipation] = useState(20);
  const [graceSeconds, setGraceSeconds] = useState(120);
  const [scenario, setScenario] = useState("oracle_defect_hip3");
  const [tier, setTier] = useState("1");

  return (
    <Section id="inputs" title="Inputs" description="Controlled, keyboard accessible, with a mono readout of the value so state never rests on a colour or a thumb position.">
      <div className="grid gap-4 lg:grid-cols-3">
        <Card>
          <CardHeader><CardEyebrow>Toggle</CardEyebrow></CardHeader>
          <CardBody className="space-y-6">
            <Toggle checked={throttle} onChange={setThrottle} label="Liquidation throttle" description="TWAP at 20% of resting depth, 250ms slices." />
            <Toggle checked={grace} onChange={setGrace} label="Margin grace window" description="120s, sized to UPI p99 settlement." />
            <Toggle checked label="Oracle-anchored mark" description="Disabled: always on in the published policy." onChange={() => undefined} disabled />
          </CardBody>
        </Card>
        <Card>
          <CardHeader><CardEyebrow>Slider</CardEyebrow></CardHeader>
          <CardBody className="space-y-8">
            <Slider label="Max participation" value={participation} onChange={setParticipation} min={5} max={100} step={5} format={(n) => `${n}%`} hint="of resting depth" />
            <Slider label="Grace window" value={graceSeconds} onChange={setGraceSeconds} min={0} max={300} step={15} format={(n) => `${n}s`} />
            <Slider label="Disabled" value={50} onChange={() => undefined} min={0} max={100} disabled format={(n) => `${n}`} />
          </CardBody>
        </Card>
        <Card>
          <CardHeader><CardEyebrow>Select</CardEyebrow></CardHeader>
          <CardBody className="space-y-6">
            <Select
              label="Scenario"
              value={scenario}
              onChange={setScenario}
              options={[
                { value: "oracle_defect_hip3", label: "Oracle defect on our own HIP-3 market" },
                { value: "macro_cascade", label: "The macro cascade" },
                { value: "broker_outage", label: "Our app and API go down mid-move" },
              ]}
            />
            <Select label="Instrument tier" mono value={tier} onChange={setTier} options={[{ value: "1", label: "Tier 1 · NRR 3%" }, { value: "2", label: "Tier 2 · NRR 5%" }, { value: "3", label: "Tier 3 · NRR 10%" }]} />
            <Select label="Disabled" value="x" onChange={() => undefined} options={[{ value: "x", label: "Locked while the incident is open" }]} disabled />
          </CardBody>
        </Card>
      </div>
    </Section>
  );
}

// ---------------------------------------------------------------------------

function BadgesSection() {
  return (
    <Section id="badges" title="Badges" description="Always a text label. The tone reinforces it; it never replaces it.">
      <Card>
        <CardBody className="space-y-4 pt-6">
          <div className="flex flex-wrap gap-2">
            <Badge>Neutral</Badge>
            <Badge tone="accent">Accent</Badge>
            <Badge tone="pos">Class A — no remedy</Badge>
            <Badge tone="warn">Due soon</Badge>
            <Badge tone="neg">Class C — we pay</Badge>
            <Badge tone="halt">Intervention</Badge>
          </div>
          <div className="flex flex-wrap gap-2">
            <Badge tone="pos" icon={<ShieldAlert />}>Reduce-only lifted</Badge>
            <Badge tone="warn" icon={<TriangleAlert />}>Composite on L2</Badge>
            <Badge tone="neg" icon={<OctagonX />}>Irreversible</Badge>
            <Badge tone="halt" icon={<CirclePause />}>Liquidations paused</Badge>
          </div>
          <div className="flex flex-wrap gap-2">
            <Badge mono>INC-20260926-01</Badge>
            <Badge mono tone="accent">BTC-PERP</Badge>
            <Badge mono tone="neg">−1,987 bps</Badge>
            <Badge mono tone="pos">seed 20251010</Badge>
          </div>
        </CardBody>
      </Card>
    </Section>
  );
}

// ---------------------------------------------------------------------------

const LOG: TimelineItem[] = [
  { id: 1, time: "T+0s", wall: "05:20:00", actor: "IC", action: "Declared SEV-1", rationale: "Mark-to-composite divergence past 50 bps on BTC-PERP. SEV-1, I am IC.", tone: "neg" },
  { id: 2, time: "T+120s", wall: "05:22:00", actor: "OPS", action: "Protect Switch", rationale: "Reduce-only, liquidation engine to TWAP, max leverage 3x. Cost accepted: traders who wanted to add margin are blocked too.", tone: "halt" },
  { id: 3, time: "T+180s", wall: "05:23:00", actor: "OPS", action: "Evidence snapshot", rationale: "Write-once: L2 book, trade tape, per-source oracle inputs, mark series, deposit queue.", tone: "accent" },
  { id: 4, time: "T+300s", wall: "05:25:00", actor: "COMMS", action: "First public update", rationale: "What we see, what we turned on, next update at 05:35 IST. No cause, no blame.", tone: "pos" },
  { id: 5, time: "T+412s", wall: "05:26:52", actor: "IC", action: "haltTrading", rationale: "Settles every position at the current mark — the mark under dispute. Used only because the feed could not be recovered.", irreversible: true },
];

function TimelineSection() {
  return (
    <Section id="timeline" title="Timeline" description="The action log. An irreversible decision gets a different node shape and a label, not just a colour.">
      <Card>
        <CardBody className="pt-6">
          <Timeline items={LOG} />
        </CardBody>
      </Card>
    </Section>
  );
}

// ---------------------------------------------------------------------------

function CountdownSection() {
  const [base] = useState(() => Date.now());
  return (
    <Section id="countdown" title="Countdown" description="MM:SS to a commitment. Crossing a threshold changes colour, icon and words together; past zero it counts overdue time rather than stopping.">
      <div className="grid gap-4 sm:grid-cols-3">
        <Card><CardBody className="pt-6"><Countdown label="Next public update" deadline={base + 270_000} warnAt={60} /></CardBody></Card>
        <Card><CardBody className="pt-6"><Countdown label="Preliminary call (T+15)" deadline={base + 48_000} warnAt={60} /></CardBody></Card>
        <Card><CardBody className="pt-6"><Countdown label="Provisional credit (T+60)" deadline={base - 23_000} warnAt={300} /></CardBody></Card>
      </div>
    </Section>
  );
}

// ---------------------------------------------------------------------------

/** Contiguous spans where a control was active, exactly as the engine recorded
 * them. Not merged: merging across short gaps turned 56 five-second pauses into
 * one eleven-minute band. `trading_paused` covers both the velocity pause and
 * the circuit breaker; frames do not yet say which. */
function controlRegions(ticks: Tick[]): ControlRegion[] {
  const kinds: Array<{ key: keyof Tick; label: string; tone: ControlRegion["tone"] }> = [
    { key: "trading_paused", label: "Trading paused", tone: "halt" },
    { key: "liquidations_paused", label: "Liq paused", tone: "halt" },
    { key: "reduce_only", label: "Reduce-only", tone: "warn" },
  ];
  const out: ControlRegion[] = [];
  for (const kind of kinds) {
    const spans: Array<[number, number]> = [];
    for (const t of ticks) {
      if (!t[kind.key]) continue;
      const last = spans[spans.length - 1];
      if (last && t.tick - last[1] <= 1) last[1] = t.tick;
      else spans.push([t.tick, t.tick]);
    }
    spans.forEach(([from, to]) => out.push({ from, to, label: kind.label, tone: kind.tone }));
  }
  return out;
}

function liquidationBursts(ticks: Tick[], n = 8): LiquidationBurst[] {
  return ticks
    .filter((t) => t.liquidated_this_tick > 0)
    .sort((a, b) => b.liquidated_this_tick - a.liquidated_this_tick)
    .slice(0, n)
    .map((t) => ({ t: t.tick, price: t.mark, count: t.liquidated_this_tick }));
}

function every<T>(list: T[], n: number): T[] {
  const step = Math.max(1, Math.floor(list.length / n));
  return list.filter((_, i) => i % step === 0);
}

/** Fixture: a cascade that starts in the market, spills into the backstop and
 * ends in ADL. Smooth and deterministic -- jitter here made the chart look
 * broken rather than busy, and the fixture is for judging the chart, not the
 * engine. */
const CASCADE: CascadePoint[] = Array.from({ length: 240 }, (_, t) => {
  const bump = (centre: number, width: number, height: number) =>
    Math.round(height * Math.exp(-(((t - centre) / width) ** 2)));
  return { t, market: bump(70, 24, 14), backstop: bump(108, 20, 7), adl: bump(132, 12, 4) };
});

const LIQUIDITY = [1, 0.78, 0.55, 0.34, 0.18, 0.09, 0.06, 0.12, 0.3, 0.55, 0.8];

function ladder(liquidity: number): { levels: DepthLevel[]; mid: number; spreadBps: number } {
  const mid = 92_00_000 * (1 - (1 - liquidity) * 0.04);
  const spreadBps = Math.min(250, 4 / Math.max(liquidity, 0.02));
  const step = mid * 0.0005;
  const levels: DepthLevel[] = [];
  for (let i = 0; i < 7; i += 1) {
    const size = 7_00_000 * Math.exp(-0.28 * i) * liquidity;
    levels.push({ side: "ask", price: Math.round(mid + (i + 1) * step), size: size * (1 + 0.15 * Math.sin(i * 1.7)) });
    levels.push({ side: "bid", price: Math.round(mid - (i + 1) * step), size: size * (1 + 0.15 * Math.cos(i * 1.3)) });
  }
  return { levels, mid, spreadBps };
}

function ChartsSection() {
  const { data, isError } = useMacroCascade();
  const policy = useQuery({ queryKey: ["policy", "active"], queryFn: fetchActivePolicy });
  const [step, setStep] = useState(0);
  const [live, setLive] = useState(true);

  useEffect(() => {
    if (!live) return;
    const id = window.setInterval(() => setStep((s) => (s + 1) % LIQUIDITY.length), 1200);
    return () => window.clearInterval(id);
  }, [live]);

  const derived = useMemo(() => {
    if (!data) return null;
    const on = data.on.ticks;
    const off = data.off.ticks;
    return {
      price: on.map((t) => ({ t: t.tick, oracle: t.composite, mark: t.mark, ltp: t.book_mid })),
      regions: controlRegions(on),
      bursts: liquidationBursts(on),
      deviation: off.map((t) => ({ t: t.tick, bps: t.divergence_bps })),
      liqOn: every(on, 60).map((t) => t.cum_liquidated_accounts),
      liqOff: every(off, 60).map((t) => t.cum_liquidated_accounts),
      depthOff: every(off, 60).map((t) => t.depth_pct_of_baseline),
    };
  }, [data]);

  const tier1 = policy.data?.instrument_tiers.find((t) => t.tier === 1);
  const book = ladder(LIQUIDITY[step] ?? 1);

  return (
    <Section id="charts" title="Charts" description="Themed from the tokens, never Recharts' defaults. Every series is told apart by line weight, dash, fill or marker shape as well as by colour.">
      <div className="space-y-4">
        <Card>
          <CardHeader actions={<Badge mono icon={<Activity />}>live · controls on</Badge>}>
            <CardEyebrow>PriceChart</CardEyebrow>
            <CardTitle>Oracle, mark and last traded</CardTitle>
            <CardDescription>The lane across the top marks every span a control was active. Markers are the largest liquidation bursts, sized by accounts closed.</CardDescription>
          </CardHeader>
          <CardBody>
            {isError ? <ChartError /> : derived ? <PriceChart data={derived.price} regions={derived.regions} bursts={derived.bursts} /> : <Skeleton className="h-72 w-full" />}
          </CardBody>
        </Card>

        <div className="grid gap-4 lg:grid-cols-2">
          <Card>
            <CardHeader actions={<Badge mono icon={<Activity />}>live · controls off</Badge>}>
              <CardEyebrow>DeviationChart</CardEyebrow>
              <CardTitle>Mark − Reference Composite</CardTitle>
              <CardDescription>Unprotected run, marking on last traded price.</CardDescription>
            </CardHeader>
            <CardBody>
              {isError ? <ChartError /> : derived && tier1 ? (
                <DeviationChart data={derived.deviation} nrrBps={tier1.nrr_pct * 100} nrrLabel={`Tier 1 NRR ±${tier1.nrr_pct.toFixed(1)}%`} />
              ) : (
                <Skeleton className="h-56 w-full" />
              )}
            </CardBody>
          </Card>
          <Card>
            <CardHeader actions={<Badge mono icon={<FlaskConical />}>fixture</Badge>}>
              <CardEyebrow>CascadeChart</CardEyebrow>
              <CardTitle>Liquidations per tick, by stage</CardTitle>
              <CardDescription>Frames record accounts closed per tick but not which stage closed them; Phase 6 adds the split.</CardDescription>
            </CardHeader>
            <CardBody>
              <CascadeChart data={CASCADE} />
            </CardBody>
          </Card>
        </div>

        <div className="grid gap-4 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
          <Card>
            <CardHeader
              actions={
                <>
                  <Badge mono icon={<FlaskConical />}>fixture</Badge>
                  <Button size="sm" onClick={() => setLive((l) => !l)} aria-pressed={live}>
                    {live ? "Pause" : "Animate"}
                  </Button>
                </>
              }
            >
              <CardEyebrow>DepthLadder</CardEyebrow>
              <CardTitle>Resting depth, thinning under stress</CardTitle>
              <CardDescription>Steps through a liquidity collapse and recovery. Frames carry total depth, not levels; Phase 6 adds levels.</CardDescription>
            </CardHeader>
            <CardBody>
              <DepthLadder levels={book.levels} mid={book.mid} spreadBps={book.spreadBps} depthOfBaseline={LIQUIDITY[step]} />
            </CardBody>
          </Card>
          <Card>
            <CardHeader actions={<Badge mono icon={<Activity />}>live</Badge>}>
              <CardEyebrow>Sparkline</CardEyebrow>
              <CardTitle>Inline trends</CardTitle>
            </CardHeader>
            <CardBody className="space-y-4">
              {derived ? (
                <>
                  <SparkRow label="Accounts liquidated, controls off" value={derived.liqOff[derived.liqOff.length - 1] ?? 0}>
                    <Sparkline data={derived.liqOff} tone="neg" label="Cumulative liquidations with controls off, rising steeply" />
                  </SparkRow>
                  <SparkRow label="Accounts liquidated, controls on" value={derived.liqOn[derived.liqOn.length - 1] ?? 0}>
                    <Sparkline data={derived.liqOn} tone="accent" label="Cumulative liquidations with controls on, rising gradually" />
                  </SparkRow>
                  <SparkRow label="Depth of baseline, controls off" value={Math.round((derived.depthOff[derived.depthOff.length - 1] ?? 0) * 100)} suffix="%">
                    <Sparkline data={derived.depthOff} tone="warn" label="Resting depth collapsing and partially recovering" />
                  </SparkRow>
                </>
              ) : (
                <SkeletonText lines={3} />
              )}
            </CardBody>
          </Card>
        </div>
      </div>
    </Section>
  );
}

function SparkRow({ label, value, suffix = "", children }: { label: string; value: number; suffix?: string; children: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4 border-b border-line pb-4 last:border-0 last:pb-0">
      <div className="min-w-0">
        <p className="text-sm text-text">{label}</p>
        <p className="num mt-1 text-xs text-text-dim">{value.toLocaleString("en-IN")}{suffix}</p>
      </div>
      {children}
    </div>
  );
}

function ChartError() {
  return <EmptyState icon={<TriangleAlert />} title="No run to draw" description="The API is not reachable. Start Django and run `make seed`." />;
}

// ---------------------------------------------------------------------------

function FeedbackSection() {
  return (
    <Section id="feedback" title="Feedback" description="Empty, loading and transient states. Skeletons are static: a pulsing skeleton is continuous motion, which the motion rule does not allow.">
      <div className="grid gap-4 lg:grid-cols-3">
        <Card>
          <CardHeader><CardEyebrow>EmptyState</CardEyebrow></CardHeader>
          <CardBody>
            <EmptyState icon={<Inbox />} title="No claims yet" description="Claims appear once the incident is classified C, D or E." action={<Button size="sm">Classify incident</Button>} />
          </CardBody>
        </Card>
        <Card>
          <CardHeader><CardEyebrow>Skeleton</CardEyebrow></CardHeader>
          <CardBody className="space-y-6">
            <Stat label="Loading a stat" value={0} loading />
            <SkeletonText lines={4} />
            <Skeleton className="h-24 w-full" />
          </CardBody>
        </Card>
        <Card>
          <CardHeader><CardEyebrow>Toast</CardEyebrow><CardDescription>Bottom right. Errors stay until dismissed.</CardDescription></CardHeader>
          <CardBody className="flex flex-col items-start gap-3">
            <Button size="sm" onClick={() => toast("Evidence snapshot written", { tone: "pos", description: "L2 book, trade tape and per-source oracle inputs, write-once." })}>Success</Button>
            <Button size="sm" onClick={() => toast("Update 2 due in 60 seconds", { tone: "warn", description: "The preliminary call is committed for T+15." })}>Warning</Button>
            <Button size="sm" variant="danger" onClick={() => toast("Claims exceed the per-incident cap", { tone: "neg", description: "₹2.47 Cr claimed against a ₹1.50 Cr cap. The pro-rata path applies." })}>Error</Button>
            <Button size="sm" onClick={() => toast("Run served from cache")}>Neutral</Button>
          </CardBody>
        </Card>
      </div>
    </Section>
  );
}

// ---------------------------------------------------------------------------

type RGBA = [number, number, number, number];

function parse(color: string): RGBA | null {
  const srgb = color.match(/color\(srgb\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)(?:\s*\/\s*([\d.]+))?\)/);
  if (srgb) return [Number(srgb[1]) * 255, Number(srgb[2]) * 255, Number(srgb[3]) * 255, srgb[4] ? Number(srgb[4]) : 1];
  const rgb = color.match(/rgba?\(([\d.]+),\s*([\d.]+),\s*([\d.]+)(?:,\s*([\d.]+))?\)/);
  if (rgb) return [Number(rgb[1]), Number(rgb[2]), Number(rgb[3]), rgb[4] ? Number(rgb[4]) : 1];
  return null;
}

function over(top: RGBA, under: RGBA): RGBA {
  const a = top[3];
  return [top[0] * a + under[0] * (1 - a), top[1] * a + under[1] * (1 - a), top[2] * a + under[2] * (1 - a), 1];
}

function luminance([r, g, b]: RGBA): number {
  const lin = (c: number) => {
    const s = c / 255;
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
}

function ratio(a: RGBA, b: RGBA): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x) as [number, number];
  return (hi + 0.05) / (lo + 0.05);
}

const PAIRS: Array<{ fg: string; bg: string; tint?: string; use: string; large?: boolean }> = [
  { fg: "--text", bg: "--surface", use: "Primary text" },
  { fg: "--text-dim", bg: "--surface", use: "Secondary text, labels" },
  { fg: "--text-faint", bg: "--surface", use: "Tertiary — not for text below 18px" },
  { fg: "--text-faint", bg: "--bg", use: "Tertiary on page" },
  { fg: "--on-accent-solid", bg: "--accent-solid", use: "Primary button" },
  { fg: "--on-halt-solid", bg: "--halt-solid", use: "HALTED pill" },
  { fg: "--pos", bg: "--surface", use: "Raw token as text" },
  { fg: "--neg", bg: "--surface", use: "Raw token as text" },
  { fg: "--halt", bg: "--surface", use: "Raw token as text" },
  { fg: "--accent-fg", bg: "--surface", tint: "--accent-soft", use: "Accent badge" },
  { fg: "--pos-fg", bg: "--surface", tint: "--pos-soft", use: "Positive badge" },
  { fg: "--neg-fg", bg: "--surface", tint: "--neg-soft", use: "Negative badge" },
  { fg: "--warn-fg", bg: "--surface", tint: "--warn-soft", use: "Warning badge" },
  { fg: "--halt-fg", bg: "--surface", tint: "--halt-soft", use: "Intervention badge" },
];

function TokensSection() {
  const [version, setVersion] = useState(0);
  const [rows, setRows] = useState<Array<(typeof PAIRS)[number] & { value: number | null }>>([]);

  useEffect(() => {
    const observer = new MutationObserver(() => setVersion((v) => v + 1));
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const probe = document.createElement("div");
    probe.style.position = "absolute";
    probe.style.visibility = "hidden";
    document.body.appendChild(probe);
    const resolve = (token: string): RGBA | null => {
      probe.style.color = `var(${token})`;
      return parse(getComputedStyle(probe).color);
    };
    setRows(
      PAIRS.map((pair) => {
        const fg = resolve(pair.fg);
        let bg = resolve(pair.bg);
        if (bg && pair.tint) {
          const tint = resolve(pair.tint);
          if (tint) bg = over(tint, bg);
        }
        return { ...pair, value: fg && bg ? ratio(fg[3] < 1 ? over(fg, bg) : fg, bg) : null };
      }),
    );
    probe.remove();
  }, [version]);

  return (
    <Section id="tokens" title="Tokens and contrast" description="Measured live from the computed styles, in whichever palette is showing -- not asserted. The bar is 4.5:1 for text.">
      <Card>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-line text-xs font-medium uppercase tracking-[0.12em] text-text-dim">
                <th scope="col" className="px-6 py-3 font-medium">Sample</th>
                <th scope="col" className="px-6 py-3 font-medium">Foreground on background</th>
                <th scope="col" className="px-6 py-3 font-medium">Use</th>
                <th scope="col" className="px-6 py-3 text-right font-medium">Ratio</th>
                <th scope="col" className="px-6 py-3 font-medium">AA text</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => {
                const pass = r.value !== null && r.value >= 4.5;
                return (
                  <tr key={`${r.fg}-${r.bg}-${r.tint ?? ""}`} className="border-b border-line last:border-0">
                    <td className="px-6 py-3">
                      <span
                        className="inline-flex h-7 items-center rounded-chip border border-line px-2 text-sm"
                        style={{ color: `var(${r.fg})`, background: r.tint ? `var(${r.tint})` : `var(${r.bg})` }}
                      >
                        Liquidated
                      </span>
                    </td>
                    <td className="num px-6 py-3 text-xs text-text-dim">
                      {r.fg} on {r.tint ? `${r.tint} over ` : ""}{r.bg}
                    </td>
                    <td className="px-6 py-3 text-sm text-text-dim">{r.use}</td>
                    <td className="num px-6 py-3 text-right text-text">{r.value ? `${r.value.toFixed(2)}:1` : "—"}</td>
                    <td className="px-6 py-3">
                      {r.value === null ? null : pass ? <Badge tone="pos">Pass</Badge> : <Badge tone="neg">Fail</Badge>}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Card>

      <Card className="mt-4">
        <CardHeader><CardEyebrow>Type</CardEyebrow></CardHeader>
        <CardBody className="space-y-4">
          <p className="text-2xl font-semibold tracking-tight">Trades stand. People get made whole.</p>
          <p className="text-base text-text">Inter for the interface. MochaTrade is a broker on Hyperliquid, not an exchange.</p>
          <p className="text-sm text-text-dim">Secondary text carries labels and explanations, never the headline figure.</p>
          <p className="num text-3xl font-semibold tracking-tight">₹1.46 Cr · 1,033 → 253 · 05:26:52</p>
          <p className="num text-sm text-text-dim">JetBrains Mono, tabular figures: 1,111,111 and 8,888,888 occupy the same width.</p>
        </CardBody>
      </Card>
    </Section>
  );
}
