import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Calculator, CheckCircle2, HandCoins, Landmark, RefreshCcw, Scale, ScanSearch } from "lucide-react";
import { useMemo, useState } from "react";

import { Link } from "../app/router";
import { IncidentSelect, useIncidentSelection } from "../components/IncidentPicker";
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
  Skeleton,
  Stat,
  toast,
} from "../components/ui";
import {
  ApiError,
  decideClaim,
  fetchActivePolicy,
  fetchClaims,
  incidentState,
  openClaims,
  parseMoney,
  recalibrateReserve,
  rupees,
} from "../lib/api";
import { CLASS_NAME, CLASS_TONE, isRemedyClass } from "../lib/forensics";
import type { Claim, ClaimsResponse, Recalibration, Remediation as RemediationDetail, RiskPolicy, Waterfall } from "../lib/types";
import { formatClock, istAt } from "../lib/warroom";

const inr = (value: number) => rupees(Math.abs(value) < 0.5 ? 0 : value);

export function Remediation() {
  const { code, incidents, loading, setCode } = useIncidentSelection();
  return (
    <div className="mx-auto max-w-[1360px] space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-xs font-medium uppercase tracking-[0.12em] text-text-dim">Remediation</p>
          <h1 className="mt-1 text-3xl font-semibold tracking-tight">Trades stand. People get made whole.</h1>
          <p className="mt-2 max-w-3xl text-sm leading-relaxed text-text-dim">
            Nothing is rolled back: fills are on-chain and non-custodial, and reversal would make a second set of victims. Every claim is sized by a
            formula published before the event, funded in a published order, and capped by a published promise. Above the cap it is pro-rata, and we say so.
          </p>
        </div>
        {code ? <IncidentSelect code={code} incidents={incidents} onChange={setCode} /> : null}
      </header>
      {loading ? (
        <Skeleton className="h-64" />
      ) : code ? (
        <IncidentRemediation key={code} code={code} />
      ) : (
        <EmptyState
          icon={<HandCoins />}
          title="No incident to remediate"
          description="Declare one in the War Room and run its clock; the claims are sized from its tape."
          action={<Link to="/war-room" className="text-sm font-medium text-accent-fg underline underline-offset-4">Open the War Room</Link>}
        />
      )}
      <ReserveCard />
      <IndiaNote />
    </div>
  );
}

function IncidentRemediation({ code }: { code: string }) {
  const queryClient = useQueryClient();
  const claims = useQuery({ queryKey: ["claims", code], queryFn: () => fetchClaims(code) });
  const state = useQuery({ queryKey: ["incident-state-lite", code], queryFn: () => incidentState(code) });
  const [busy, setBusy] = useState(false);

  const open = async () => {
    setBusy(true);
    try {
      const result = await openClaims(code);
      queryClient.setQueryData(["claims", code], result);
      await queryClient.invalidateQueries({ queryKey: ["incidents"] });
      await queryClient.invalidateQueries({ queryKey: ["classification", code] });
      const w = result.remediation?.waterfall;
      if (w) {
        toast(w.pro_rata ? `Pro-rata at ${(w.ratio * 100).toFixed(1)}%` : "Every claim paid in full", {
          tone: w.pro_rata ? "warn" : "pos",
          description: `${inr(w.total_claims)} claimed, ${inr(w.payable)} payable in cash.`,
        });
      }
    } catch (e) {
      toast("Claims were not opened", { tone: "neg", description: e instanceof ApiError ? e.message : String(e) });
    } finally {
      setBusy(false);
    }
  };

  if (claims.isLoading) return <Skeleton className="h-96" />;
  const data = claims.data;
  if (!data) return <EmptyState icon={<HandCoins />} title="Could not load this incident's claims" />;
  const detail = data.remediation;
  const drill = state.data?.drill_clock_s ?? 0;
  const declared = state.data?.incident.declared_at;

  return (
    <div className="space-y-6">
      <Card>
        <CardBody className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex flex-wrap items-center gap-3 text-sm text-text-dim">
            <Badge mono tone="neutral">{data.incident_code}</Badge>
            {isRemedyClass(data.classification) ? (
              <Badge tone={CLASS_TONE[data.classification] === "neg" ? "neg" : "neutral"}>
                Class {data.classification} · {CLASS_NAME[data.classification]}
              </Badge>
            ) : (
              <Badge tone="warn">Not classified yet</Badge>
            )}
            <Badge tone={data.market_finished ? "pos" : "warn"}>{data.market_finished ? "Market event complete" : "Market still moving"}</Badge>
            {detail ? <span>Governed by policy <span className="num text-text">{detail.policy_version}</span>, in force when the incident was declared</span> : null}
          </div>
          <div className="flex items-center gap-4">
            {detail ? (
              <Countdown
                label={`Provisional credit due T+${String(detail.provisional_minutes).padStart(2, "0")}:00${declared ? ` · ${istAt(declared, detail.provisional_minutes * 60)} IST` : ""}`}
                remaining={detail.provisional_minutes * 60 - drill}
                warnAt={600}
                size="sm"
              />
            ) : null}
            <Button variant="primary" icon={<Calculator />} loading={busy} disabled={data.current_tick === 0} onClick={open}>
              {detail ? "Re-open claims" : "Open claims"}
            </Button>
          </div>
        </CardBody>
      </Card>

      {detail ? (
        <Opened data={data} detail={detail} code={code} onChanged={() => queryClient.invalidateQueries({ queryKey: ["claims", code] })} />
      ) : (
        <EmptyState
          icon={<Scale />}
          title={data.current_tick === 0 ? "The market has not started" : "Claims are not open yet"}
          description={
            data.current_tick === 0
              ? "There is nothing to size. Run the incident's clock in the War Room."
              : "Opening claims classifies every force-closed account on the full tape (if it has not been), sizes each claim by its class's formula, and funds the total through the waterfall."
          }
          action={
            <Link to="/forensics" className="inline-flex items-center gap-2 text-sm font-medium text-accent-fg underline underline-offset-4">
              <ScanSearch className="h-4 w-4" aria-hidden /> See the classification first
            </Link>
          }
        />
      )}
    </div>
  );
}

function Opened({ data, detail, code, onChanged }: { data: ClaimsResponse; detail: RemediationDetail; code: string; onChanged: () => void }) {
  const w = detail.waterfall;
  const cashClaims = data.claims.filter((c) => c.evidence?.remedy?.kind === "cash");
  const provisional = data.claims.reduce((sum, c) => sum + parseMoney(c.provisional_credit_inr), 0);
  return (
    <>
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-3">
        <Card><CardBody><Stat label="Claimed" value={w.total_claims} format={inr} caption="Uncapped, by formula" /></CardBody></Card>
        <Card><CardBody><Stat label="Paid in cash" value={w.payable} format={inr} caption={w.pro_rata ? `${(w.ratio * 100).toFixed(1)}% of every claim` : "Every claim in full"} /></CardBody></Card>
        <Card><CardBody><Stat label="Non-cash make-good" value={w.shortfall} format={inr} caption={w.pro_rata ? "Above the cap, announced" : "Not needed"} /></CardBody></Card>
        <Card><CardBody><Stat label="Provisional credit" value={provisional} format={inr} caption="C, D and E, no ticket needed" /></CardBody></Card>
        <Card><CardBody><Stat label="Accounts owed cash" value={cashClaims.length} format={(n) => String(Math.round(n))} caption="C, D, E and G" /></CardBody></Card>
        <Card><CardBody><Stat label="Fee rebates" value={w.fee_rebates} format={inr} caption="Class B, no cash remedy" /></CardBody></Card>
      </div>
      <WaterfallCard w={w} reserve={detail.reserve} />
      <ClaimsTable claims={data.claims} code={code} onChanged={onChanged} />
    </>
  );
}

function WaterfallCard({ w, reserve }: { w: Waterfall; reserve: RemediationDetail["reserve"] }) {
  const max = Math.max(w.total_claims, w.cap, 1);
  const capPct = (w.cap / max) * 100;
  const totalPct = (w.total_claims / max) * 100;
  return (
    <Card>
      <CardHeader>
        <CardEyebrow>The funding waterfall</CardEyebrow>
        <CardTitle>{w.pro_rata ? "The cap binds: pro-rata, announced as pro-rata" : "Funded in full, in the published order"}</CardTitle>
        <CardDescription>
          Research 5.3, drawn in order. The per-incident cap of {inr(w.cap)} is the most MochaTrade pays in cash on one incident, from every source
          together. An honest finite promise beats an implied infinite one we would break.
        </CardDescription>
      </CardHeader>
      <CardBody className="space-y-6">
        <div>
          <div className="relative h-8 rounded-control border border-line bg-surface-2" role="img" aria-label={`Claims ${inr(w.total_claims)} against a cap of ${inr(w.cap)}`}>
            <div className={`absolute inset-y-0 left-0 rounded-control ${w.pro_rata ? "bg-warn-soft" : "bg-pos-soft"}`} style={{ width: `${totalPct}%` }} />
            <div className="absolute inset-y-0 w-0.5 bg-neg" style={{ left: `${capPct}%` }} aria-hidden />
          </div>
          <div className="mt-2 flex flex-wrap justify-between gap-2 text-xs text-text-dim">
            <span>Claims <span className="num text-text">{inr(w.total_claims)}</span></span>
            <span>Cap <span className="num text-neg-fg">{inr(w.cap)}</span> (red rule)</span>
            <span>Cash per rupee claimed <span className="num text-text">{(w.ratio * 100).toFixed(1)}%</span></span>
          </div>
        </div>
        <ol className="space-y-3">
          {w.tranches.map((t) => (
            <li key={t.step} className="grid grid-cols-[2rem_minmax(0,1fr)_auto] items-start gap-3 rounded-control border border-line px-4 py-3">
              <span className="num text-lg font-semibold text-text-dim">{t.step}</span>
              <div className="min-w-0">
                <p className="text-sm font-medium text-text">{t.source}</p>
                <p className="mt-0.5 text-xs leading-relaxed text-text-dim">{t.note}</p>
                {t.step === 2 ? (
                  <p className="num mt-1 text-xs text-text-dim">
                    Opening {inr(reserve.opening)} · drawn by earlier incidents {inr(reserve.drawn_by_other_incidents)} · available {inr(reserve.available)} · after this one {inr(w.reserve_after)}
                  </p>
                ) : null}
              </div>
              <div className="text-right">
                <p className={`num text-sm font-semibold ${t.step === 5 && t.drawn > 0 ? "text-warn-fg" : "text-text"}`}>{inr(t.drawn)}</p>
                <p className="text-xs text-text-dim">{t.step === 5 ? "make-good" : "drawn"}</p>
              </div>
            </li>
          ))}
        </ol>
        <p className="num rounded-control border border-line bg-surface-2 px-4 py-3 text-xs text-text-dim">{w.formula}</p>
      </CardBody>
    </Card>
  );
}

const STATUS_TONE: Record<string, "neutral" | "pos" | "neg" | "warn" | "accent"> = {
  AUTO_APPROVED: "pos",
  APPROVED: "pos",
  PAID: "accent",
  PENDING: "warn",
  REJECTED: "neutral",
};

function ClaimsTable({ claims, code, onChanged }: { claims: Claim[]; code: string; onChanged: () => void }) {
  const [scope, setScope] = useState<"cash" | "all">("cash");
  const [pending, setPending] = useState<number | null>(null);
  const rows = useMemo(
    () => (scope === "cash" ? claims.filter((c) => c.evidence?.remedy?.kind === "cash" || c.evidence?.remedy?.kind === "fee_rebate") : claims),
    [claims, scope],
  );
  const decide = async (claim: Claim, decision: "APPROVED" | "REJECTED" | "PAID") => {
    setPending(claim.id);
    try {
      await decideClaim(code, claim.id, { decision, decided_by: "IC", reason: "" });
      toast(`${claim.account_handle}: ${decision.toLowerCase()}`, { tone: decision === "REJECTED" ? "warn" : "pos", description: decision === "REJECTED" ? "Re-open claims to re-fund the waterfall without it." : "" });
      onChanged();
    } catch (e) {
      toast("Refused", { tone: "neg", description: e instanceof ApiError ? e.message : String(e) });
    } finally {
      setPending(null);
    }
  };
  return (
    <Card>
      <CardHeader>
        <CardEyebrow>Claims</CardEyebrow>
        <CardTitle>Per account: the formula, the cash, the make-good</CardTitle>
        <CardDescription>
          Clear-cut C, D and E claims are approved automatically and credited provisionally as locked trading credit, converted to cash after a published
          reconciliation. G waits for the IC. A and F owe no cash; B gets its fees back.
        </CardDescription>
      </CardHeader>
      <CardBody className="space-y-4">
        <div role="group" aria-label="Which claims" className="flex gap-2">
          {(["cash", "all"] as const).map((s) => (
            <button
              key={s}
              type="button"
              aria-pressed={scope === s}
              onClick={() => setScope(s)}
              className={`rounded-control border px-3 py-1 text-xs transition-colors duration-150 ${scope === s ? "border-accent-edge bg-accent-soft text-accent-fg" : "border-line text-text-dim hover:bg-surface-2"}`}
            >
              {s === "cash" ? "Owed something" : `Every classified account · ${claims.length}`}
            </button>
          ))}
        </div>
        {rows.length === 0 ? (
          <p className="text-sm text-text-dim">Nobody is owed anything on this incident. The evidence tape is published instead.</p>
        ) : (
          <div className="max-h-[560px] overflow-auto rounded-control border border-line">
            <table className="w-full text-left text-sm">
              <caption className="sr-only">Claims with formula, cash, make-good, provisional credit and status</caption>
              <thead className="sticky top-0 bg-surface text-xs uppercase tracking-[0.08em] text-text-dim">
                <tr>
                  <th scope="col" className="px-3 py-2 font-medium">Account</th>
                  <th scope="col" className="px-3 py-2 font-medium">Class</th>
                  <th scope="col" className="px-3 py-2 font-medium">Formula</th>
                  <th scope="col" className="px-3 py-2 text-right font-medium">Claim</th>
                  <th scope="col" className="px-3 py-2 text-right font-medium">Cash</th>
                  <th scope="col" className="px-3 py-2 text-right font-medium">Make-good</th>
                  <th scope="col" className="px-3 py-2 font-medium">Status</th>
                  <th scope="col" className="px-3 py-2 font-medium"><span className="sr-only">Decide</span></th>
                </tr>
              </thead>
              <tbody>
                {rows.map((c) => {
                  const r = c.evidence?.remedy;
                  return (
                    <tr key={c.id} className="border-t border-line align-top">
                      <td className="px-3 py-2">
                        <p className="num text-text">{c.account_handle}</p>
                        <p className="num text-xs text-text-dim">{c.account_side === "LONG" ? "Long" : "Short"} {Math.round(c.account_leverage)}x{c.liquidated_at_tick !== null ? ` · ${formatClock(c.liquidated_at_tick)}` : ""}</p>
                      </td>
                      <td className="px-3 py-2"><Badge mono tone={isRemedyClass(c.category) && CLASS_TONE[c.category] === "neg" ? "neg" : "neutral"}>{c.category}</Badge></td>
                      <td className="max-w-[360px] px-3 py-2 text-xs leading-relaxed text-text-dim"><span className="line-clamp-3">{r?.basis ?? c.reason}</span></td>
                      <td className="num whitespace-nowrap px-3 py-2 text-right">{r?.kind === "fee_rebate" ? `${inr(r.fee_rebate)} fees` : inr(r?.make_whole ?? 0)}</td>
                      <td className="num whitespace-nowrap px-3 py-2 text-right">{inr(parseMoney(c.approved_inr_display))}</td>
                      <td className={`num whitespace-nowrap px-3 py-2 text-right ${r && r.make_good_inr > 0.5 ? "text-warn-fg" : ""}`}>{inr(r?.make_good_inr ?? 0)}</td>
                      <td className="px-3 py-2"><Badge tone={STATUS_TONE[c.status] ?? "neutral"}>{c.status.replace("_", " ").toLowerCase()}</Badge></td>
                      <td className="whitespace-nowrap px-3 py-2">
                        {c.status === "PENDING" ? (
                          <span className="flex gap-2">
                            <Button size="sm" loading={pending === c.id} onClick={() => decide(c, "APPROVED")}>Approve</Button>
                            <Button size="sm" variant="danger" disabled={pending === c.id} onClick={() => decide(c, "REJECTED")}>Reject</Button>
                          </span>
                        ) : (c.status === "AUTO_APPROVED" || c.status === "APPROVED") && parseMoney(c.approved_inr_display) > 0 ? (
                          <Button size="sm" icon={<CheckCircle2 />} loading={pending === c.id} onClick={() => decide(c, "PAID")}>Mark paid</Button>
                        ) : null}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </CardBody>
    </Card>
  );
}

function ReserveCard() {
  const queryClient = useQueryClient();
  const policy = useQuery({ queryKey: ["active-policy"], queryFn: fetchActivePolicy });
  const [result, setResult] = useState<Recalibration | null>(null);
  const [busy, setBusy] = useState(false);
  const run = async () => {
    setBusy(true);
    try {
      const r = await recalibrateReserve("Risk");
      setResult(r);
      await queryClient.invalidateQueries({ queryKey: ["active-policy"] });
      toast(r.new_version ? `Policy ${r.new_version} written` : "Already at the fixed point", {
        tone: "pos",
        description: `Reserve ${inr(parseMoney(r.target_reserve_inr))}: ${r.multiple}x the worst modelled loss.`,
      });
    } catch (e) {
      toast("Recalibration failed", { tone: "neg", description: e instanceof ApiError ? e.message : String(e) });
    } finally {
      setBusy(false);
    }
  };
  const p: RiskPolicy | undefined = policy.data;
  return (
    <Card>
      <CardHeader>
        <CardEyebrow>Incident Reserve</CardEyebrow>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="max-w-3xl">
            <CardTitle>Sized by the simulator, not by hope</CardTitle>
            <CardDescription>
              Ring-fenced and publicly visible, funded by {p ? `${Math.round(p.reserve_funding_share_of_fees * 100)}%` : "a share"} of builder-code fee revenue
              until it reaches {p ? `${p.reserve_target_multiple_of_worst_loss}x` : "a multiple of"} the worst modelled 30-day loss. That target needs a
              simulation run under a policy that already has a reserve. Recalibrating resolves the loop: run every seeded scenario both ways, take the worst
              cash liability under the published formulas, and write a new policy version with the reserve at the target. The cap is never touched.
            </CardDescription>
          </div>
          <Button variant="primary" icon={<RefreshCcw />} loading={busy} onClick={run}>Recalibrate from simulation</Button>
        </div>
      </CardHeader>
      <CardBody className="space-y-5">
        {p ? (
          <dl className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <Fact label="Active policy" value={p.version} />
            <Fact label="Reserve" value={inr(parseMoney(p.incident_reserve_inr))} />
            <Fact label="Per-incident cap" value={inr(parseMoney(p.per_incident_cap_inr_display))} />
            <Fact label="Provisional credit within" value={`${p.provisional_credit_minutes} min`} />
          </dl>
        ) : (
          <Skeleton className="h-12" />
        )}
        {result ? <RecalibrationResult r={result} /> : null}
      </CardBody>
    </Card>
  );
}

function RecalibrationResult({ r }: { r: Recalibration }) {
  return (
    <div className="space-y-4">
      <div className="grid gap-4 lg:grid-cols-3">
        <div className="rounded-control border border-line px-4 py-3">
          <p className="text-xs text-text-dim">Worst modelled loss</p>
          <p className="num mt-1 text-xl font-semibold">{inr(parseMoney(r.worst.claims_total_inr))}</p>
          <p className="mt-1 text-xs text-text-dim">{r.worst.name}, controls {r.worst.controls_enabled ? "on" : "off"}</p>
        </div>
        <div className="rounded-control border border-line px-4 py-3">
          <p className="text-xs text-text-dim">Reserve: {r.multiple}x that</p>
          <p className="num mt-1 text-xl font-semibold">{inr(parseMoney(r.target_reserve_inr))}</p>
          <p className="mt-1 text-xs text-text-dim">was {inr(parseMoney(r.previous_reserve_inr))} under {r.previous_version}</p>
        </div>
        <div className="rounded-control border border-line px-4 py-3">
          <p className="text-xs text-text-dim">Policy</p>
          <p className="num mt-1 text-xl font-semibold">{r.new_version ? `${r.previous_version} → ${r.new_version}` : `${r.active_version}, unchanged`}</p>
          <p className="mt-1 text-xs text-text-dim">Cap still {inr(parseMoney(r.cap_inr))}</p>
        </div>
      </div>
      <p className="flex gap-2 rounded-control border border-pos-edge bg-pos-soft px-4 py-3 text-sm text-pos-fg">
        <Landmark className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
        <span>{r.explanation}</span>
      </p>
      <div className="overflow-x-auto rounded-control border border-line">
        <table className="w-full text-left text-sm">
          <caption className="sr-only">Modelled cash liability per seeded scenario and control state</caption>
          <thead className="text-xs uppercase tracking-[0.08em] text-text-dim">
            <tr>
              <th scope="col" className="px-3 py-2 font-medium">Scenario</th>
              <th scope="col" className="px-3 py-2 font-medium">Controls</th>
              <th scope="col" className="px-3 py-2 font-medium">Class</th>
              <th scope="col" className="px-3 py-2 text-right font-medium">Accounts owed cash</th>
              <th scope="col" className="px-3 py-2 text-right font-medium">Claims</th>
              <th scope="col" className="px-3 py-2 font-medium">Against the cap</th>
            </tr>
          </thead>
          <tbody>
            {r.rows.map((row) => {
              const worst = row.run_id === r.worst.run_id;
              return (
                <tr key={row.run_id} className={`border-t border-line ${worst ? "bg-warn-soft" : ""}`}>
                  <td className="px-3 py-2 text-text">{row.name}{worst ? <span className="ml-2 text-xs text-warn-fg">worst</span> : null}</td>
                  <td className="px-3 py-2 text-text-dim">{row.controls_enabled ? "on" : "off"}</td>
                  <td className="num px-3 py-2">{row.category}</td>
                  <td className="num px-3 py-2 text-right">{row.cash_accounts}</td>
                  <td className="num px-3 py-2 text-right">{inr(parseMoney(row.claims_total_inr))}</td>
                  <td className="px-3 py-2">{row.above_cap ? <Badge tone="warn">above: pro-rata</Badge> : <span className="text-xs text-text-dim">within</span>}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function IndiaNote() {
  return (
    <Card>
      <CardHeader>
        <CardEyebrow>Why compensation policy matters more in India</CardEyebrow>
        <CardTitle>A liquidated Indian trader has no tax relief</CardTitle>
        <CardDescription>
          VDA gains are taxed at a flat 30% with no loss set-off, plus 1% TDS on transfers. A user wiped out by a wick eats all of it with zero
          deductibility, so the trust damage from an identical event is strictly worse here than anywhere else. That is why the compensation rule, not only
          the risk rule, is the competitive weapon. Compensation credits themselves carry characterisation risk and may need grossing up; the reconciliation
          we publish says how each credit was treated.
        </CardDescription>
      </CardHeader>
    </Card>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-control border border-line px-4 py-3">
      <dt className="text-xs text-text-dim">{label}</dt>
      <dd className="num mt-1 text-lg font-semibold text-text">{value}</dd>
    </div>
  );
}
