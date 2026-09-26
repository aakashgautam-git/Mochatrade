import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, CircleDashed, FileSearch, Gavel, ScanSearch, XCircle } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { Link } from "../app/router";
import { ControlsBadge } from "../components/ControlsBadge";
import { useApp } from "../app/store";
import { DepthLadder, DeviationChart, PriceChart } from "../components/charts";
import {
  Badge,
  Button,
  Card,
  CardBody,
  CardDescription,
  CardEyebrow,
  CardHeader,
  CardTitle,
  EmptyState,
  Select,
  Skeleton,
  toast,
} from "../components/ui";
import { ApiError, classifyIncident, fetchClassification, fetchEvidence, incidentTicks, listIncidents, rupees } from "../lib/api";
import {
  CLASS_NAME,
  CLASS_TONE,
  CLASSES,
  claimsIn,
  compositeDeviation,
  fillsFor,
  firstInteresting,
  forensicPrices,
  price,
  signedBps,
  tapeAt,
} from "../lib/forensics";
import { ladderAt } from "../lib/sim";
import type { AccountEvidence, Claim, ClassificationResponse, CriterionResult, RemedyClass, Tick, Verdict } from "../lib/types";
import { formatClock } from "../lib/warroom";

const ROW_LIMIT = 250;

/** Rupees, with float dust below half a rupee shown as zero rather than "₹-0". */
const inr = (value: number) => rupees(Math.abs(value) < 0.5 ? 0 : value);

export function Forensics() {
  const storeCode = useApp((s) => s.incidentCode);
  const setIncidentCode = useApp((s) => s.setIncidentCode);
  const incidents = useQuery({ queryKey: ["incidents"], queryFn: listIncidents });
  const code = storeCode ?? incidents.data?.[0]?.code ?? null;

  if (incidents.isLoading) return <Skeleton className="h-64" />;
  if (!code) {
    return (
      <EmptyState
        icon={<ScanSearch />}
        title="No incident to examine"
        description="Forensics runs the published APE test on an incident's own tape. Declare one in the War Room and run its clock first."
        action={<Link to="/war-room" className="text-sm font-medium text-accent-fg underline underline-offset-4">Open the War Room</Link>}
      />
    );
  }

  return (
    <div className="mx-auto max-w-[1360px] space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-xs font-medium uppercase tracking-[0.12em] text-text-dim">Forensics</p>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight">The published APE test, run on the tape</h1>
          <p className="mt-2 max-w-3xl text-sm leading-relaxed text-text-dim">
            Deviation beyond the Non-Reviewable Range, reversion of half within 60 seconds, survival at the Reference Composite.
            All three, or the trade stands. Then the root cause decides who pays, from A to G.
          </p>
        </div>
        <Select
          label="Incident"
          mono
          value={code}
          onChange={(next) => setIncidentCode(next)}
          options={(incidents.data ?? []).map((i) => ({
            value: i.code,
            label: `${i.code} · ${i.scenario_slug ?? "no run"} · ${i.controls_enabled === false ? "controls OFF" : "controls ON"} · ${i.status.toLowerCase()}`,
          }))}
          className="min-w-[360px]"
        />
      </header>
      <IncidentForensics key={code} code={code} controls={incidents.data?.find((i) => i.code === code)?.controls_enabled} />
    </div>
  );
}

function IncidentForensics({ code, controls }: { code: string; controls: boolean | null | undefined }) {
  const queryClient = useQueryClient();
  const classification = useQuery({ queryKey: ["classification", code], queryFn: () => fetchClassification(code) });
  const ticks = useQuery({ queryKey: ["forensic-ticks", code], queryFn: () => incidentTicks(code, 0) });
  const [running, setRunning] = useState(false);

  const run = async () => {
    setRunning(true);
    try {
      const result = await classifyIncident(code);
      queryClient.setQueryData(["classification", code], result);
      await queryClient.invalidateQueries({ queryKey: ["incidents"] });
      const v = result.verdict;
      if (v) toast(`Class ${v.category}: ${v.label}`, { tone: CLASS_TONE[v.category] === "neg" ? "neg" : "pos", description: v.headline });
    } catch (e) {
      toast("The test did not run", { tone: "neg", description: e instanceof ApiError ? e.message : String(e) });
    } finally {
      setRunning(false);
    }
  };

  if (classification.isLoading || ticks.isLoading) return <Skeleton className="h-96" />;
  const data = classification.data;
  if (!data) return <EmptyState icon={<FileSearch />} title="Could not load this incident" />;
  const tape = ticks.data?.ticks ?? [];

  return (
    <div className="space-y-6">
      <RunBar data={data} running={running} onRun={run} controls={controls} />
      {data.verdict ? (
        <Classified data={data} verdict={data.verdict} ticks={tape} code={code} />
      ) : (
        <EmptyState
          icon={<Gavel />}
          title={data.current_tick === 0 ? "The market has not started" : "Not classified yet"}
          description={
            data.current_tick === 0
              ? "There is no tape to test. Run the incident's clock in the War Room."
              : `The tape holds ${data.current_tick} seconds. Run the test to classify every force-closed account against the published rules.`
          }
        />
      )}
    </div>
  );
}

function RunBar({ data, running, onRun, controls }: { data: ClassificationResponse; running: boolean; onRun: () => void; controls: boolean | null | undefined }) {
  const v = data.verdict;
  return (
    <Card>
      <CardBody className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex flex-wrap items-center gap-3 text-sm text-text-dim">
          <Badge mono tone="neutral">{data.incident_code}</Badge>
          <ControlsBadge on={controls} />
          <span className="num">Tape: {formatClock(data.current_tick)} recorded</span>
          <Badge tone={data.market_finished ? "pos" : "warn"}>{data.market_finished ? "Market event complete" : "Market still moving"}</Badge>
          {v ? (
            <span>
              Last run at <span className="num text-text">{formatClock(v.at_tick)}</span>
              {v.provisional ? " — provisional: fills in the last 60 s could not finish the reversion test" : ""}
            </span>
          ) : null}
        </div>
        <Button variant="primary" icon={<Gavel />} loading={running} disabled={data.current_tick === 0} onClick={onRun}>
          {v ? "Re-run the APE test" : "Run the APE test"}
        </Button>
      </CardBody>
    </Card>
  );
}

function Classified({ data, verdict, ticks, code }: { data: ClassificationResponse; verdict: Verdict; ticks: Tick[]; code: string }) {
  const [filter, setFilter] = useState<RemedyClass | "ALL">("ALL");
  const [selected, setSelected] = useState<string | null>(() => firstInteresting(data.claims)?.account_handle ?? null);
  useEffect(() => {
    if (selected && !data.claims.some((c) => c.account_handle === selected)) setSelected(firstInteresting(data.claims)?.account_handle ?? null);
  }, [data.claims, selected]);
  const claim = data.claims.find((c) => c.account_handle === selected) ?? null;
  const cursor = claim?.evidence?.tick;

  return (
    <>
      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
        <VerdictCard verdict={verdict} />
        <TestCard verdict={verdict} />
      </div>
      <TapeCharts verdict={verdict} ticks={ticks} cursor={cursor} />
      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.25fr)_minmax(0,1fr)]">
        <AccountsCard claims={data.claims} verdict={verdict} filter={filter} onFilter={setFilter} selected={selected} onSelect={setSelected} />
        {claim && claim.evidence ? (
          <AccountDetail code={code} claim={claim} evidence={claim.evidence} ticks={ticks} />
        ) : (
          <Card>
            <CardBody>
              <EmptyState icon={<CheckCircle2 />} title="No account was force-closed" description="The verdict above stands on the tape signatures alone. There is nobody to compensate and nothing to rebate." />
            </CardBody>
          </Card>
        )}
      </div>
    </>
  );
}

function ClassTile({ letter, size = "lg" }: { letter: RemedyClass; size?: "lg" | "sm" }) {
  const tone = CLASS_TONE[letter];
  const tint = {
    neutral: "border-line bg-surface-2 text-text",
    accent: "border-accent-edge bg-accent-soft text-accent-fg",
    neg: "border-neg-edge bg-neg-soft text-neg-fg",
    warn: "border-warn-edge bg-warn-soft text-warn-fg",
  }[tone];
  return (
    <span
      aria-label={`Class ${letter}`}
      className={`num inline-flex shrink-0 items-center justify-center rounded-control border font-semibold ${tint} ${size === "lg" ? "h-16 w-16 text-4xl" : "h-7 w-7 text-sm"}`}
    >
      {letter}
    </span>
  );
}

function VerdictCard({ verdict }: { verdict: Verdict }) {
  const layer = { venue: "L3 Venue", market: "L2 Market", broker: "L1 Broker" }[verdict.layer];
  return (
    <Card>
      <CardHeader>
        <CardEyebrow>Verdict</CardEyebrow>
        <div className="mt-2 flex items-start gap-4">
          <ClassTile letter={verdict.category} />
          <div className="min-w-0">
            <CardTitle>{verdict.label}</CardTitle>
            <CardDescription>{verdict.headline}</CardDescription>
            <div className="mt-3 flex flex-wrap gap-2">
              <Badge tone="neutral">{layer}</Badge>
              <Badge tone={CLASS_TONE[verdict.category] === "neg" ? "neg" : "neutral"}>Fault: {verdict.fault}</Badge>
              {verdict.provisional ? <Badge tone="warn">Provisional</Badge> : null}
            </div>
          </div>
        </div>
      </CardHeader>
      <CardBody className="space-y-5">
        <div className="rounded-control border border-line bg-surface-2 px-4 py-3">
          <p className="text-xs font-medium uppercase tracking-[0.12em] text-text-dim">Remedy, as published</p>
          <p className="mt-1 text-sm text-text">{verdict.remedy}</p>
        </div>
        <ul className="space-y-2">
          {verdict.evidence.map((line) => (
            <li key={line} className="flex gap-2 text-sm leading-relaxed text-text-dim">
              <span aria-hidden className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-text-dim" />
              <span>{line}</span>
            </li>
          ))}
        </ul>
        <div>
          <p className="text-xs font-medium uppercase tracking-[0.12em] text-text-dim">Force-closed accounts by class</p>
          <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-4">
            {CLASSES.map((c) => (
              <div key={c} className={`flex items-center justify-between gap-2 rounded-control border border-line px-3 py-2 ${verdict.counts[c] ? "" : "opacity-60"}`}>
                <p className="text-xs text-text-dim"><span className="num font-semibold text-text">{c}</span> {CLASS_NAME[c]}</p>
                <p className="num text-lg font-semibold">{verdict.counts[c]}</p>
              </div>
            ))}
          </div>
        </div>
      </CardBody>
    </Card>
  );
}

function TestCard({ verdict }: { verdict: Verdict }) {
  const s = verdict.signals;
  const signals: Array<{ label: string; value: string; on: boolean }> = [
    {
      label: "Our composite vs the Reference Composite",
      value: s.composite_defect ? `${signedBps(s.composite_defect.peak_bps)} at ${formatClock(s.composite_defect.peak_tick)}` : "within the NRR",
      on: s.composite_defect !== null,
    },
    {
      label: "Coordinated push across venues",
      value: s.push ? `${s.push.sources.join(", ")} · book ${signedBps(s.push.peak_bps)}` : "none",
      on: s.push !== null,
    },
    {
      label: "Our app and API",
      value: s.outage ? `down ${formatClock(s.outage.start_tick)}–${formatClock(s.outage.end_tick)}, ${Math.round(s.outage.affected_frac * 100)}% cut off` : "up throughout",
      on: s.outage !== null,
    },
    { label: "UPI deposits in flight", value: String(s.upi_in_flight), on: s.upi_in_flight > 0 },
    { label: "Liquidations on a last-trade mark", value: String(s.ltp_marked_liquidations), on: s.ltp_marked_liquidations > 0 },
    {
      label: "Book wick while the primary market was shut",
      value: s.thin_book_wick ? `${signedBps(s.thin_book_wick.peak_bps)} · ${s.closed_primary.join(", ")} closed` : "none",
      on: s.thin_book_wick !== null,
    },
  ];
  return (
    <Card>
      <CardHeader>
        <CardEyebrow>The test</CardEyebrow>
        <CardTitle>Published before the event</CardTitle>
        <CardDescription>A fill is an Abnormal Price Event only if all three hold. Every threshold comes from the active risk policy.</CardDescription>
      </CardHeader>
      <CardBody className="space-y-5">
        <ol className="space-y-3 text-sm">
          <li className="flex gap-3">
            <span className="num text-text-dim">1</span>
            <span><span className="font-medium text-text">Deviation.</span> <span className="text-text-dim">Execution more than </span><span className="num text-text">{Math.round(s.nrr_bps).toLocaleString("en-IN")} bps</span><span className="text-text-dim"> from the Reference Composite in the same second.</span></span>
          </li>
          <li className="flex gap-3">
            <span className="num text-text-dim">2</span>
            <span><span className="font-medium text-text">Reversion.</span> <span className="text-text-dim">It comes back at least </span><span className="num text-text">{Math.round(s.reversion_frac * 100)}%</span><span className="text-text-dim"> within </span><span className="num text-text">{s.reversion_seconds}s</span><span className="text-text-dim">: a wick, not a repricing.</span></span>
          </li>
          <li className="flex gap-3">
            <span className="num text-text-dim">3</span>
            <span><span className="font-medium text-text">Survival.</span> <span className="text-text-dim">The account held enough margin to survive at the Reference Composite.</span></span>
          </li>
        </ol>
        <div>
          <p className="text-xs font-medium uppercase tracking-[0.12em] text-text-dim">What the tape shows, layer by layer</p>
          <dl className="mt-2 divide-y divide-line">
            {signals.map((row) => (
              <div key={row.label} className="flex items-baseline justify-between gap-4 py-2 text-sm">
                <dt className="flex items-center gap-2 text-text-dim">
                  {row.on ? <XCircle aria-hidden className="h-4 w-4 text-neg-fg" /> : <CheckCircle2 aria-hidden className="h-4 w-4 text-pos-fg" />}
                  <span>{row.label}</span>
                  <span className="sr-only">{row.on ? "(present)" : "(clear)"}</span>
                </dt>
                <dd className="num text-right text-text">{row.value}</dd>
              </div>
            ))}
          </dl>
        </div>
      </CardBody>
    </Card>
  );
}

function TapeCharts({ verdict, ticks, cursor }: { verdict: Verdict; ticks: Tick[]; cursor: number | undefined }) {
  const prices = useMemo(() => forensicPrices(ticks), [ticks]);
  const markDev = useMemo(() => ticks.map((t) => ({ t: t.tick, bps: t.divergence_bps })), [ticks]);
  const compositeDev = useMemo(() => compositeDeviation(ticks), [ticks]);
  const nrrLabel = `NRR ±${(verdict.nrr_bps / 100).toFixed(1)}%`;
  if (ticks.length < 2) return null;
  return (
    <Card>
      <CardHeader>
        <CardEyebrow>The tape</CardEyebrow>
        <CardTitle>Reference Composite, our mark, and the book</CardTitle>
        <CardDescription>
          The green line is the Reference Composite the test measures against: the published ladder rebuilt from the per-source tape with our own defects taken out.
          {cursor !== undefined ? ` The dashed rule marks the selected account's decisive fill at ${formatClock(cursor)}.` : ""}
        </CardDescription>
      </CardHeader>
      <CardBody className="space-y-6">
        <PriceChart data={prices} cursor={cursor} height={260} />
        <div className="grid gap-6 lg:grid-cols-2">
          <DeviationChart data={markDev} nrrBps={verdict.nrr_bps} nrrLabel={nrrLabel} cursor={cursor} height={200} />
          <DeviationChart data={compositeDev} nrrBps={verdict.nrr_bps} nrrLabel={nrrLabel} cursor={cursor} height={200} seriesLabel="Our published composite − Reference Composite" />
        </div>
      </CardBody>
    </Card>
  );
}

function AccountsCard({
  claims,
  verdict,
  filter,
  onFilter,
  selected,
  onSelect,
}: {
  claims: Claim[];
  verdict: Verdict;
  filter: RemedyClass | "ALL";
  onFilter: (next: RemedyClass | "ALL") => void;
  selected: string | null;
  onSelect: (handle: string) => void;
}) {
  const [showAll, setShowAll] = useState(false);
  const rows = useMemo(() => claimsIn(claims, filter), [claims, filter]);
  const visible = showAll ? rows : rows.slice(0, ROW_LIMIT);
  return (
    <Card>
      <CardHeader>
        <CardEyebrow>Accounts</CardEyebrow>
        <CardTitle>Every force-closed account, its class and why</CardTitle>
        <CardDescription>Select a row to see its three criteria, the oracle tape and the book at its decisive fill.</CardDescription>
      </CardHeader>
      <CardBody className="space-y-4">
        <div role="group" aria-label="Filter by class" className="flex flex-wrap gap-2">
          {(["ALL", ...CLASSES] as const).map((c) => {
            const n = c === "ALL" ? claims.length : verdict.counts[c];
            const active = filter === c;
            return (
              <button
                key={c}
                type="button"
                aria-pressed={active}
                disabled={n === 0}
                onClick={() => onFilter(c)}
                className={`num rounded-control border px-3 py-1 text-xs transition-colors duration-150 disabled:opacity-40 ${active ? "border-accent-edge bg-accent-soft text-accent-fg" : "border-line text-text-dim hover:bg-surface-2"}`}
              >
                {c === "ALL" ? "All" : c} · {n}
              </button>
            );
          })}
        </div>
        {rows.length === 0 ? (
          <p className="text-sm text-text-dim">No account was force-closed.</p>
        ) : (
          <div className="max-h-[560px] overflow-auto rounded-control border border-line">
            <table className="w-full text-left text-sm">
              <caption className="sr-only">Force-closed accounts with class, decisive fill and reason</caption>
              <thead className="sticky top-0 bg-surface text-xs uppercase tracking-[0.08em] text-text-dim">
                <tr>
                  <th scope="col" className="px-3 py-2 font-medium">Account</th>
                  <th scope="col" className="px-3 py-2 font-medium">Class</th>
                  <th scope="col" className="px-3 py-2 font-medium">Closed</th>
                  <th scope="col" className="px-3 py-2 text-right font-medium">vs ref.</th>
                  <th scope="col" className="px-3 py-2 font-medium">APE</th>
                  <th scope="col" className="px-3 py-2 font-medium">Why</th>
                </tr>
              </thead>
              <tbody>
                {visible.map((c) => {
                  const e = c.evidence;
                  const active = c.account_handle === selected;
                  return (
                    <tr
                      key={c.id}
                      aria-selected={active}
                      className={`cursor-pointer border-t border-line align-top transition-colors duration-150 ${active ? "bg-accent-soft" : "hover:bg-surface-2"}`}
                      onClick={() => onSelect(c.account_handle)}
                    >
                      <td className="px-3 py-2">
                        <button type="button" className="num text-left text-text focus-visible:underline" onClick={() => onSelect(c.account_handle)}>
                          {c.account_handle}
                        </button>
                        <p className="num text-xs text-text-dim">{c.account_side === "LONG" ? "Long" : "Short"} {Math.round(c.account_leverage)}x</p>
                      </td>
                      <td className="px-3 py-2"><ClassTile letter={c.category as RemedyClass} size="sm" /></td>
                      <td className="num whitespace-nowrap px-3 py-2 text-text-dim">{c.liquidated_at_tick === null ? "—" : formatClock(c.liquidated_at_tick)}</td>
                      <td className="num whitespace-nowrap px-3 py-2 text-right">{e ? signedBps(e.deviation_bps) : "—"}</td>
                      <td className="px-3 py-2">{e ? <ApeMark evidence={e} /> : "—"}</td>
                      <td className="max-w-[340px] px-3 py-2 text-xs leading-relaxed text-text-dim"><span className="line-clamp-2">{c.reason}</span></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
        {rows.length > ROW_LIMIT && !showAll ? (
          <Button size="sm" onClick={() => setShowAll(true)}>Show all {rows.length}</Button>
        ) : null}
      </CardBody>
    </Card>
  );
}

function ApeMark({ evidence }: { evidence: AccountEvidence }) {
  if (evidence.ape) return <Badge tone="neg">APE</Badge>;
  if (evidence.pending) return <Badge tone="warn">Pending</Badge>;
  return <Badge tone="neutral">No</Badge>;
}

function CriterionRow({ n, title, c }: { n: number; title: string; c: CriterionResult }) {
  const icon = c.passed === null ? <CircleDashed className="h-4 w-4 text-warn-fg" /> : c.passed ? <CheckCircle2 className="h-4 w-4 text-neg-fg" /> : <XCircle className="h-4 w-4 text-text-dim" />;
  const verdict = c.passed === null ? "Pending" : c.passed ? "Met" : "Not met";
  return (
    <li className="flex gap-3 rounded-control border border-line px-3 py-2">
      <span aria-hidden className="mt-0.5">{icon}</span>
      <div className="min-w-0">
        <p className="text-sm font-medium text-text">
          {n}. {title} <span className="text-xs font-normal text-text-dim">— {verdict}</span>
        </p>
        <p className="mt-0.5 text-xs leading-relaxed text-text-dim">{c.detail}</p>
      </div>
    </li>
  );
}

function AccountDetail({ code, claim, evidence, ticks }: { code: string; claim: Claim; evidence: AccountEvidence; ticks: Tick[] }) {
  const tape = useQuery({
    queryKey: ["evidence", code, evidence.tick],
    queryFn: () => fetchEvidence(code, evidence.tick, evidence.tick),
  });
  const rows = useMemo(() => tapeAt(tape.data?.observations ?? [], evidence.tick), [tape.data, evidence.tick]);
  const tick = ticks.find((t) => t.tick === evidence.tick);
  const ladder = tick ? ladderAt(tick) : undefined;
  const fills = useMemo(() => fillsFor(ticks, claim.account_handle), [ticks, claim.account_handle]);
  const gap = evidence.counterfactual_equity_inr - evidence.equity_inr;

  return (
    <Card>
      <CardHeader>
        <CardEyebrow>Account {claim.account_handle}</CardEyebrow>
        <div className="mt-2 flex items-start gap-3">
          <ClassTile letter={evidence.category} size="sm" />
          <div>
            <CardTitle>{evidence.side === "LONG" ? "Long" : "Short"} {Math.round(evidence.leverage)}x · {inr(evidence.entry_notional)} notional</CardTitle>
            <CardDescription>{claim.reason}</CardDescription>
          </div>
        </div>
      </CardHeader>
      <CardBody className="space-y-5">
        <ol className="space-y-2" aria-label="APE criteria">
          <CriterionRow n={1} title="Deviation" c={evidence.criteria.deviation} />
          <CriterionRow n={2} title="Reversion" c={evidence.criteria.reversion} />
          <CriterionRow n={3} title="Survival at the Reference Composite" c={evidence.criteria.survival} />
        </ol>

        <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
          <Fact label="Decisive fill" value={`${formatClock(evidence.tick)} · ${evidence.stage}`} />
          <Fact label="Executed" value={price(evidence.executed_price)} />
          <Fact label="Reference Composite" value={price(evidence.reference_price)} />
          <Fact label={`Mark (${evidence.mark_source})`} value={price(evidence.mark)} />
          <Fact label="Published composite" value={price(evidence.composite)} />
          <Fact label="Book mid" value={price(evidence.book_mid)} />
          <Fact label="Equity now, at reference" value={inr(evidence.equity_inr)} />
          <Fact label="Counterfactual equity" value={inr(evidence.counterfactual_equity_inr)} />
        </dl>
        <p className="text-xs leading-relaxed text-text-dim">
          The counterfactual is what the account would hold had it been processed at the Reference Composite; the gap, {inr(Math.max(0, gap))}, is the most any make-whole could restore. An account that breaches even at the honest price is valued where that price would have closed it.
        </p>

        <div>
          <p className="text-xs font-medium uppercase tracking-[0.12em] text-text-dim">Oracle tape at {formatClock(evidence.tick)}</p>
          {tape.isLoading ? (
            <Skeleton className="mt-2 h-40" />
          ) : (
            <div className="mt-2 overflow-x-auto rounded-control border border-line">
              <table className="w-full text-left text-xs">
                <caption className="sr-only">Every oracle source at the decisive fill, from the persisted evidence tape</caption>
                <thead className="text-text-dim">
                  <tr>
                    <th scope="col" className="px-2 py-1.5 font-medium">Source</th>
                    <th scope="col" className="px-2 py-1.5 font-medium">Rung</th>
                    <th scope="col" className="px-2 py-1.5 text-right font-medium">Printed</th>
                    <th scope="col" className="px-2 py-1.5 text-right font-medium">vs ref.</th>
                    <th scope="col" className="px-2 py-1.5 font-medium">In the composite</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={r.source} className="border-t border-line align-top">
                      <td className="px-2 py-1.5 text-text">{r.label}</td>
                      <td className="num px-2 py-1.5 text-text-dim">{r.rung === null ? "—" : `L${r.rung}`}</td>
                      <td className="num px-2 py-1.5 text-right">{price(r.raw)}</td>
                      <td className="num px-2 py-1.5 text-right">{r.deviationBps === null || r.source === "REFERENCE" ? "—" : signedBps(r.deviationBps)}</td>
                      <td className="px-2 py-1.5 text-text-dim" title={r.reason}>
                        {r.state === "derived" ? "derived" : r.state === "used" ? `used · w ${r.weight.toFixed(2)}` : r.state === "clamped" ? `clamped to ${price(r.used)}` : r.state}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {ladder ? (
          <div>
            <p className="text-xs font-medium uppercase tracking-[0.12em] text-text-dim">The book at {formatClock(evidence.tick)}</p>
            <div className="mt-2">
              <DepthLadder levels={ladder.levels} mid={ladder.mid} spreadBps={ladder.spreadBps} depthOfBaseline={ladder.depthOfBaseline} />
            </div>
          </div>
        ) : null}

        {fills.length ? (
          <div>
            <p className="text-xs font-medium uppercase tracking-[0.12em] text-text-dim">Every fill</p>
            <ul className="mt-2 space-y-1 text-xs">
              {fills.map((f, i) => (
                <li key={`${f.tick}-${i}`} className="num flex justify-between gap-3 text-text-dim">
                  <span>{formatClock(f.tick)} · {f.stage}{f.via_auction ? " · auction" : ""}{f.closed ? " · closed" : ""}</span>
                  <span className="text-text">{f.qty.toFixed(4)} @ {price(f.price)}</span>
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </CardBody>
    </Card>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3 border-b border-line py-1">
      <dt className="text-text-dim">{label}</dt>
      <dd className="num text-text">{value}</dd>
    </div>
  );
}
