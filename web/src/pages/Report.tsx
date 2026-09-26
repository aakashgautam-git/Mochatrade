import { useQuery } from "@tanstack/react-query";
import { FileText, Printer } from "lucide-react";

import { Link } from "../app/router";
import { ControlsBadge } from "../components/ControlsBadge";
import { IncidentSelect, useIncidentSelection } from "../components/IncidentPicker";
import { Badge, Button, EmptyState, Skeleton } from "../components/ui";
import { fetchReport, parseMoney, rupees } from "../lib/api";
import { CLASS_NAME, isRemedyClass } from "../lib/forensics";
import { INDIA, POLICY_TEMPLATES, PRECEDENTS, PRECEDENTS_FOR, REMEDY_MATRIX, WHY_TRADES_STAND } from "../lib/research";
import type { IncidentReport, RemedyClass } from "../lib/types";
import { actionLabel, formatClock, istAt } from "../lib/warroom";

const inr = (value: number) => rupees(Math.abs(value) < 0.5 ? 0 : value);
const day = (iso: string) => new Date(iso).toLocaleDateString("en-IN", { timeZone: "Asia/Kolkata", day: "numeric", month: "long", year: "numeric" });
const wall = (iso: string) => new Date(iso).toLocaleString("en-IN", { timeZone: "Asia/Kolkata", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", hour12: false });

/**
 * The incident report: the research's T+60 handover, built from the
 * incident's own record. What happened, who is affected, what we are paying,
 * when it lands, and the date of the full RCA -- then the working behind each.
 */
export function Report() {
  const { code, incidents, loading, setCode } = useIncidentSelection();
  if (loading) return <Skeleton className="mx-auto h-96 max-w-4xl" />;
  if (!code) {
    return (
      <EmptyState
        icon={<FileText />}
        title="No incident to report on"
        description="A report is built from an incident's own record. Declare one in the War Room."
        action={<Link to="/war-room" className="text-sm font-medium text-accent-fg underline underline-offset-4">Open the War Room</Link>}
      />
    );
  }
  return (
    <div className="mx-auto max-w-4xl">
      <div className="mb-8 flex flex-wrap items-end justify-between gap-4 print:hidden">
        <IncidentSelect code={code} incidents={incidents} onChange={setCode} />
        <Button icon={<Printer />} onClick={() => window.print()}>Print or save as PDF</Button>
      </div>
      <ReportBody key={code} code={code} />
    </div>
  );
}

function ReportBody({ code }: { code: string }) {
  const report = useQuery({ queryKey: ["report", code], queryFn: () => fetchReport(code) });
  if (report.isLoading) return <Skeleton className="h-96" />;
  if (!report.data) return <EmptyState icon={<FileText />} title="Could not load the report" />;
  return <Document r={report.data} />;
}

function Document({ r }: { r: IncidentReport }) {
  const inc = r.incident;
  const verdict = r.classification.verdict;
  const plan = r.claims.remediation?.waterfall;
  const summary = r.run.summary;
  const cls = verdict && isRemedyClass(verdict.category) ? verdict.category : null;
  const matrix = cls ? REMEDY_MATRIX.find((m) => m.cls === cls) : undefined;
  const lockout = (verdict?.signals.outage?.end_tick ?? 0) - (verdict?.signals.outage?.start_tick ?? 0);

  return (
    <article className="space-y-12 text-[15px] leading-relaxed">
      <header className="border-b border-line pb-8">
        <p className="text-xs font-medium uppercase tracking-[0.12em] text-text-dim">Incident report · {inc.severity === "SEV1" ? "SEV-1" : inc.severity}</p>
        <h1 className="mt-2 flex items-center gap-3 text-3xl font-semibold tracking-tight">{inc.code} <ControlsBadge on={inc.controls_enabled} /></h1>
        <p className="mt-2 text-text-dim">
          {r.run.scenario_slug ?? "No run"} · declared {wall(inc.declared_at)} IST · policy {r.run.policy_version ?? "—"} · {inc.status.toLowerCase()}
        </p>
        <dl className="mt-6 grid grid-cols-3 gap-4 text-sm">
          <Person role="Incident commander" name={inc.incident_commander} />
          <Person role="Operations" name={inc.ops_lead} />
          <Person role="Comms" name={inc.comms_lead} />
        </dl>
      </header>

      <section aria-labelledby="five">
        <h2 id="five" className="text-xl font-semibold tracking-tight">The handover, in five lines</h2>
        <p className="mt-1 text-sm text-text-dim">Research 6, T+60: what happened, who is affected, what we are paying, when it lands, and the date of the full RCA.</p>
        <dl className="mt-5 divide-y divide-line border-y border-line">
          <Line label="What happened">
            {verdict ? (
              <>
                <span className="font-medium">Class {verdict.category}: {verdict.label}.</span> {verdict.headline}
                {verdict.provisional ? <span className="text-warn-fg"> Provisional: classified while the market was still moving.</span> : null}
              </>
            ) : (
              "Not classified yet. The Forensics page runs the published APE test on the tape."
            )}
          </Line>
          <Line label="Who is affected">
            {verdict ? `${inc.affected_accounts_count} accounts owed a remedy, of ${verdict.signals.accounts_force_closed} force-closed.` : "The affected set is built by the classification."}
          </Line>
          <Line label="What we are paying">
            {plan ? (
              <>
                {inr(plan.payable)} in cash on {inr(plan.total_claims)} claimed
                {plan.pro_rata
                  ? `: the claims exceed our published per-incident cap of ${inr(plan.cap)}, so every claim is paid ${(plan.ratio * 100).toFixed(1)}% in cash and ${inr(plan.shortfall)} as a non-cash make-good. Announced as pro-rata.`
                  : ", every claim in full."}
              </>
            ) : (
              "Claims are not open yet. No number is published before it is computed."
            )}
          </Line>
          <Line label="When it lands">
            {r.claims.remediation
              ? `Provisional credit, as locked trading credit, by ${wall(r.claims.remediation.provisional_deadline)} IST for clear-cut C, D and E claims (${inr(parseMoney(r.claims_summary.provisional_credit_inr))} credited). Withdrawable cash after the reconciliation we publish.`
              : "Set when claims are opened: provisional credit within 60 minutes of the incident, for clear-cut cases."}
          </Line>
          <Line label="Full RCA">By {day(r.obligations.rca_due)}, under the SEBI technical-glitch framework we adopt voluntarily. Preliminary report by {day(r.obligations.preliminary_due)}.</Line>
        </dl>
      </section>

      {verdict ? (
        <section aria-labelledby="why">
          <h2 id="why" className="text-xl font-semibold tracking-tight">Why this class</h2>
          <p className="mt-1 text-sm text-text-dim">From the tape alone, by the Abnormal Price Event policy published before the event. Every account's working is on the Forensics page.</p>
          <ul className="mt-4 list-disc space-y-2 pl-5">
            {verdict.evidence.map((e) => <li key={e}>{e}</li>)}
          </ul>
          {matrix ? (
            <p className="mt-4 rounded-control border border-line bg-surface px-4 py-3 text-sm">
              <span className="font-medium">Remedy matrix, class {matrix.cls}.</span> Fault: {matrix.fault}. {matrix.remedy}
            </p>
          ) : null}
          <dl className="mt-6 grid grid-cols-2 gap-x-8 gap-y-2 text-sm sm:grid-cols-4">
            {(["A", "B", "C", "D", "E", "F", "G"] as RemedyClass[]).map((c) => (
              <div key={c} className="flex justify-between border-b border-line py-1">
                <dt className="text-text-dim">{c} · {CLASS_NAME[c]}</dt>
                <dd className="num">{verdict.counts[c]}</dd>
              </div>
            ))}
          </dl>
        </section>
      ) : null}

      {summary ? (
        <section aria-labelledby="market">
          <h2 id="market" className="text-xl font-semibold tracking-tight">What the market did, and what held</h2>
          <dl className="mt-4 grid grid-cols-2 gap-x-8 gap-y-2 text-sm sm:grid-cols-3">
            <Stat label="Accounts force-closed" value={String(summary.accounts_liquidated)} />
            <Stat label="Would have survived at the reference" value={String(summary.unnecessary_liquidations)} />
            <Stat label="Auto-deleveraged" value={String(summary.adl_accounts)} />
            <Stat label="Mark trough" value={`${summary.trough_mark_pct.toFixed(1)}%`} />
            <Stat label="Largest mark vs reference" value={`${Math.round(summary.max_divergence_bps).toLocaleString("en-IN")} bps`} />
            <Stat label="Pauses reopened by auction" value={String(summary.auctions)} />
            <Stat label="User loss" value={inr(parseMoney(summary.user_loss_inr))} />
            <Stat label="Of which attributable to pricing and processing" value={inr(parseMoney(summary.attributable_loss_inr))} />
            <Stat label="Saved by the grace window" value={String(summary.saved_by_grace)} />
          </dl>
          <p className="mt-3 text-sm text-text-dim">
            Controls on this run: {r.controls.length ? r.controls.map((c) => c.replaceAll("_", " ")).join(", ") : "none — the uncontrolled counterfactual"}.
            {lockout > 0 ? ` Our app and API were down for ${Math.round(lockout / 60)} minutes of it.` : ""}
          </p>
        </section>
      ) : null}

      <section aria-labelledby="timeline">
        <h2 id="timeline" className="text-xl font-semibold tracking-tight">Timeline</h2>
        <p className="mt-1 text-sm text-text-dim">The append-only action log: who decided what, when, and why.</p>
        <ol className="mt-4 space-y-3">
          {r.timeline.map((a) => (
            <li key={a.id} className="grid grid-cols-[5.5rem_minmax(0,1fr)] gap-4 text-sm">
              <span className="num text-text-dim">{formatClock(a.tick)}<br />{istAt(inc.declared_at, a.tick)} IST</span>
              <span>
                <span className="font-medium">{actionLabel(a)}</span> <span className="text-text-dim">· {a.actor}</span>
                {a.rationale ? <span className="block text-text-dim">{a.rationale}</span> : null}
              </span>
            </li>
          ))}
        </ol>
      </section>

      {plan ? (
        <section aria-labelledby="money">
          <h2 id="money" className="text-xl font-semibold tracking-tight">Where the money comes from</h2>
          <p className="mt-1 text-sm text-text-dim">The published funding waterfall, research 5.3, drawn in order.</p>
          <table className="mt-4 w-full text-left text-sm">
            <thead className="text-xs uppercase tracking-[0.08em] text-text-dim">
              <tr><th className="py-2 font-medium">Step</th><th className="py-2 font-medium">Source</th><th className="py-2 text-right font-medium">Amount</th></tr>
            </thead>
            <tbody>
              {plan.tranches.map((t) => (
                <tr key={t.step} className="border-t border-line align-top">
                  <td className="num py-2 pr-4 text-text-dim">{t.step}</td>
                  <td className="py-2 pr-4">{t.source}<span className="block text-xs text-text-dim">{t.note}</span></td>
                  <td className="num py-2 text-right">{inr(t.drawn)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-3 text-sm text-text-dim">
            {r.claims_summary.accounts_owed_cash} accounts owed cash · {inr(parseMoney(r.claims_summary.approved_inr))} approved · {r.claims_summary.paid} paid · {r.claims_summary.pending} awaiting the IC.
          </p>
        </section>
      ) : null}

      <section aria-labelledby="said">
        <h2 id="said" className="text-xl font-semibold tracking-tight">What we said, and when</h2>
        <p className="mt-1 text-sm text-text-dim">
          {r.obligations.first_update_minutes === null
            ? "Nothing has been published yet. The framework we hold ourselves to asks for notice within one hour."
            : `First update at T+${Math.round(r.obligations.first_update_minutes)} minutes${r.obligations.notified_within_hour ? ", inside the one hour the framework allows" : ", later than the one hour the framework allows"}. Channels: ${r.obligations.channels_used.map((c) => c.replace("_", " ").toLowerCase()).join(", ")}.`}
        </p>
        <ol className="mt-4 space-y-4">
          {r.comms.filter((u) => u.is_published).map((u) => (
            <li key={u.id} className="border-l-2 border-line pl-4 text-sm">
              <p className="num text-xs text-text-dim">{u.published_at ? `${wall(u.published_at)} IST` : ""} · {u.audience_display} · {u.channel_display}{u.approved_by ? ` · approved by ${u.approved_by}` : ""}</p>
              <p className="font-medium">{u.headline}</p>
              <p className="whitespace-pre-line text-text-dim">{u.body}</p>
            </li>
          ))}
        </ol>
      </section>

      <section aria-labelledby="precedent">
        <h2 id="precedent" className="text-xl font-semibold tracking-tight">Precedent</h2>
        <p className="mt-1 text-sm text-text-dim">Why trades stand, and the cases this incident's class answers to (research 3 and 5).</p>
        <ul className="mt-4 grid gap-3 sm:grid-cols-2">
          {WHY_TRADES_STAND.map((w) => (
            <li key={w.title} className="rounded-control border border-line bg-surface px-4 py-3 text-sm">
              <p className="font-medium">{w.title}</p>
              <p className="text-text-dim">{w.text}</p>
            </li>
          ))}
        </ul>
        {cls ? (
          <div className="mt-6 space-y-4">
            {PRECEDENTS_FOR[cls].map((key) => {
              const p = PRECEDENTS.find((x) => x.key === key);
              const t = POLICY_TEMPLATES.find((x) => x.key === key);
              if (p) {
                return (
                  <div key={key} className="text-sm">
                    <p className="font-medium">{p.event} <span className="font-normal text-text-dim">· {p.when}</span></p>
                    <p className="text-text-dim">{p.what}</p>
                    <p className="mt-1"><span className="font-medium">Lesson:</span> {p.lesson}</p>
                    <p className="mt-1"><span className="font-medium">Our answer:</span> {p.answer}</p>
                  </div>
                );
              }
              if (t) {
                return (
                  <div key={key} className="text-sm">
                    <p className="font-medium">{t.event} <span className="font-normal text-text-dim">· {t.when} · the template we follow</span></p>
                    <p className="text-text-dim">{t.what}</p>
                  </div>
                );
              }
              return null;
            })}
          </div>
        ) : null}
      </section>

      <section aria-labelledby="india">
        <h2 id="india" className="text-xl font-semibold tracking-tight">India</h2>
        <p className="mt-1 text-sm text-text-dim">What the India layer (research 7) asks of this incident.</p>
        <ul className="mt-4 space-y-3 text-sm">
          <IndiaLine k="sebi" note={`Notice ${r.obligations.notified_within_hour ? "given inside the hour" : "not yet given"}; preliminary report by ${day(r.obligations.preliminary_due)}; RCA by ${day(r.obligations.rca_due)}; glitch data kept until ${day(r.obligations.retain_until)}.`} />
          <IndiaLine k="tax" note={plan && plan.total_claims > 0 ? "This is why the claims above are paid without a ticket." : "No cash claims on this incident."} />
          {plan && plan.payable > 0 ? <IndiaLine k="characterisation" note="Each credit's tax treatment is documented in the published reconciliation." /> : null}
          {cls === "E" || (verdict && verdict.signals.upi_in_flight > 0) ? (
            <IndiaLine k="upi" note={r.controls.includes("upi_prefunded_credit") ? "The pre-funded credit was on for this run." : "The pre-funded credit was off for this run."} />
          ) : null}
          <IndiaLine
            k="grievance"
            note={r.obligations.channels_used.some((c) => c === "WHATSAPP" || c === "TELEGRAM") ? "Updates went out on WhatsApp or Telegram." : "No WhatsApp or Telegram update has gone out yet."}
          />
          {cls === "G" ? (
            <li className="rounded-control border border-line bg-surface px-4 py-3">
              <p className="font-medium">FIU-IND</p>
              <p className="text-text-dim">Identifiable manipulation is reported to FIU-IND and the venue (research 5.2, class G). The template is on the Comms page.</p>
            </li>
          ) : null}
        </ul>
      </section>

      <footer className="border-t border-line pt-6 text-sm text-text-dim">
        <p className="font-medium text-text">Trades stand. People get made whole.</p>
        <p className="mt-1">The raw tape for every account is on the Forensics page, so anyone can check this report against it.</p>
      </footer>
    </article>
  );
}

function Person({ role, name }: { role: string; name: string }) {
  return (
    <div>
      <dt className="text-xs text-text-dim">{role}</dt>
      <dd className="font-medium">{name || "—"}</dd>
    </div>
  );
}

function Line({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[9rem_minmax(0,1fr)] gap-4 py-3">
      <dt className="text-sm font-medium text-text-dim">{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3 border-b border-line py-1">
      <dt className="text-text-dim">{label}</dt>
      <dd className="num">{value}</dd>
    </div>
  );
}

function IndiaLine({ k, note }: { k: string; note: string }) {
  const item = INDIA.find((i) => i.key === k);
  if (!item) return null;
  return (
    <li className="rounded-control border border-line bg-surface px-4 py-3">
      <p className="font-medium">{item.title}</p>
      <p className="text-text-dim">{item.text}</p>
      <p className="mt-1"><Badge tone="neutral">This incident</Badge> {note}</p>
    </li>
  );
}
