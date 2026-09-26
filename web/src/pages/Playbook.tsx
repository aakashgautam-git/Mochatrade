import { useQuery } from "@tanstack/react-query";

import { Skeleton } from "../components/ui";
import { fetchActivePolicy, parseMoney, rupees } from "../lib/api";
import {
  DONTS,
  FIRST_HOUR,
  HIP3_STAKE,
  INDIA,
  JUDGMENT_CALLS,
  POLICY_TEMPLATES,
  PRECEDENTS,
  REMEDY_MATRIX,
  ROLES,
  WHAT_KEEPS_USERS,
  WHY_TRADES_STAND,
} from "../lib/research";

const SECTIONS = [
  ["policy", "The policy"],
  ["ape", "The APE test"],
  ["matrix", "Who pays"],
  ["money", "The money"],
  ["roles", "Roles"],
  ["clock", "The first 60 minutes"],
  ["calls", "Judgment calls"],
  ["donts", "What we do not do"],
  ["users", "What keeps a user"],
  ["india", "India"],
  ["cases", "Case file"],
] as const;

/**
 * The published playbook, readable before the event. The numbers in it are
 * read from the active risk policy, so the page and the engine cannot drift.
 */
export function Playbook() {
  const policy = useQuery({ queryKey: ["active-policy"], queryFn: fetchActivePolicy });
  const p = policy.data;
  return (
    <div className="mx-auto grid max-w-6xl gap-10 lg:grid-cols-[12rem_minmax(0,1fr)]">
      <nav aria-label="Playbook sections" className="hidden lg:block">
        <ol className="sticky top-20 space-y-2 text-sm">
          {SECTIONS.map(([id, label]) => (
            <li key={id}><a href={`#${id}`} className="text-text-dim hover:text-text">{label}</a></li>
          ))}
        </ol>
      </nav>
      <article className="max-w-3xl space-y-14 text-[15px] leading-relaxed">
        <header>
          <p className="text-xs font-medium uppercase tracking-[0.12em] text-text-dim">MochaTrade · published playbook{p ? ` · policy ${p.version}` : ""}</p>
          <h1 className="mt-2 text-4xl font-semibold tracking-tight">Trades stand. People get made whole.</h1>
          <p className="mt-4 text-text-dim">
            MochaTrade is a non-custodial broker built on Hyperliquid. We cannot pause the matching engine and we cannot roll back a fill. We control our own
            HIP-3 market, our app, our API, our UPI rails and our INR ledger. So the first minute of any crisis is one question: which of our three layers
            broke? Everything below was published before anything happened.
          </p>
        </header>

        <section id="policy" aria-labelledby="policy-h">
          <h2 id="policy-h" className="text-2xl font-semibold tracking-tight">Never reverse. Always compensate. Decide by a rule published first.</h2>
          <ol className="mt-5 grid gap-3 sm:grid-cols-2">
            {WHY_TRADES_STAND.map((w, i) => (
              <li key={w.title} className="rounded-control border border-line bg-surface px-4 py-3">
                <p className="font-medium"><span className="num text-text-dim">{i + 1}.</span> {w.title}</p>
                <p className="text-sm text-text-dim">{w.text}</p>
              </li>
            ))}
          </ol>
        </section>

        <section id="ape" aria-labelledby="ape-h">
          <h2 id="ape-h" className="text-2xl font-semibold tracking-tight">The Abnormal Price Event test</h2>
          <p className="mt-2">A fill or liquidation is an Abnormal Price Event only if all three hold:</p>
          <ol className="mt-3 list-decimal space-y-2 pl-5">
            <li><span className="font-medium">Deviation.</span> The execution price differs from the Reference Composite Price in the same 1-second window by more than the Non-Reviewable Range for its tier.</li>
            <li><span className="font-medium">Reversion.</span> The deviation retraces at least {p ? `${Math.round(p.ape_reversion_frac * 100)}%` : "half"} within {p ? `${p.ape_reversion_seconds} seconds` : "a minute"}: it was a wick, not a repricing.</li>
            <li><span className="font-medium">Counterfactual survival.</span> The account held enough margin to survive at the Reference Composite Price.</li>
          </ol>
          <h3 className="mt-6 font-semibold">Non-Reviewable Ranges</h3>
          {p ? (
            <table className="mt-2 w-full text-left text-sm">
              <thead className="text-xs uppercase tracking-[0.08em] text-text-dim">
                <tr><th className="py-2 font-medium">Tier</th><th className="py-2 font-medium">Instruments</th><th className="py-2 text-right font-medium">NRR</th><th className="py-2 text-right font-medium">Off-hours</th></tr>
              </thead>
              <tbody>
                {p.instrument_tiers.map((t) => (
                  <tr key={t.tier} className="border-t border-line">
                    <td className="num py-2">{t.tier}</td>
                    <td className="py-2 pr-4">{t.label}</td>
                    <td className="num py-2 text-right">{t.nrr_pct}%</td>
                    <td className="num py-2 text-right">{t.nrr_offhours_pct}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <Skeleton className="mt-2 h-32" />
          )}
          <h3 className="mt-6 font-semibold">The Reference Composite Price</h3>
          <p className="mt-1">A published, degrading ladder, so it exists at 04:00 IST on a Sunday:</p>
          <ol className="mt-2 space-y-1 text-sm">
            <li><span className="num font-medium">L1</span> — three or more major spot venues (crypto), or the US cash market (equities, regular hours).</li>
            <li><span className="num font-medium">L2</span> — index futures, ADRs and an ETF NAV proxy.</li>
            <li><span className="num font-medium">L3</span> — the median of two or more independent perp venues.</li>
            <li><span className="num font-medium">L4</span> — no valid composite: the market is force-flagged degraded — max leverage 3x, reduce-only, liquidations paused.</li>
          </ol>
          <p className="mt-2 text-sm text-text-dim">
            Our mark never follows the last trade. Sources deviating from the median are clamped{p ? ` (${p.outlier_clamp_pct}%; ${p.majors_outlier_clamp_pct}% for majors)` : ""}, and a source silent for{" "}
            {p ? `${Math.round(p.staleness_seconds / 60)} minutes` : "five minutes"} has its weight set to zero.
          </p>
        </section>

        <section id="matrix" aria-labelledby="matrix-h">
          <h2 id="matrix-h" className="text-2xl font-semibold tracking-tight">Root cause decides who pays</h2>
          <table className="mt-4 w-full text-left text-sm">
            <thead className="text-xs uppercase tracking-[0.08em] text-text-dim">
              <tr><th className="py-2 pr-3 font-medium">Class</th><th className="py-2 pr-3 font-medium">Root cause</th><th className="py-2 pr-3 font-medium">Fault</th><th className="py-2 font-medium">Remedy</th></tr>
            </thead>
            <tbody>
              {REMEDY_MATRIX.map((m) => (
                <tr key={m.cls} className="border-t border-line align-top">
                  <td className="num py-2 pr-3 font-semibold">{m.cls}</td>
                  <td className="py-2 pr-3">{m.cause}</td>
                  <td className="py-2 pr-3 text-text-dim">{m.fault}</td>
                  <td className="py-2">{m.remedy}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-4 rounded-control border border-line bg-surface px-4 py-3 text-sm">
            <span className="font-medium">The speed clause.</span> For clear-cut C, D and E signatures, provisional credit is pushed within {p ? `${p.provisional_credit_minutes} minutes` : "the hour"} as
            locked trading credit, converted to withdrawable cash after a published reconciliation. Nobody files a ticket to get their own money back.
          </p>
          <p className="mt-3 text-sm text-text-dim">{HIP3_STAKE}</p>
        </section>

        <section id="money" aria-labelledby="money-h">
          <h2 id="money-h" className="text-2xl font-semibold tracking-tight">Where the money comes from</h2>
          <ol className="mt-4 space-y-2">
            <li><span className="num font-medium">1.</span> Recovery from the at-fault party — the attacker, a vendor's SLA, the PSP.</li>
            <li><span className="num font-medium">2.</span> The Incident Reserve — ring-fenced, publicly visible, funded by {p ? `${Math.round(p.reserve_funding_share_of_fees * 100)}%` : "a share"} of builder-code fee revenue until it reaches {p ? `${p.reserve_target_multiple_of_worst_loss}x` : "a multiple of"} the worst modelled 30-day loss{p ? `. Today: ${rupees(parseMoney(p.incident_reserve_inr))}.` : "."}</li>
            <li><span className="num font-medium">3.</span> Corporate treasury, up to the published per-incident cap{p ? ` of ${rupees(parseMoney(p.per_incident_cap_inr_display))}` : ""}.</li>
            <li><span className="num font-medium">4.</span> Tech E&O insurance.</li>
            <li><span className="num font-medium">5.</span> Beyond the cap: pro-rata by a published formula, plus a non-cash make-good — announced as pro-rata, never paid silently short.</li>
          </ol>
          <p className="mt-4 text-sm text-text-dim">
            Binance spent ~$188M of insurance fund and ~$283M in total on one weekend. MochaTrade cannot. So the cap exists and is published in advance: an honest,
            finite promise beats an implied infinite one we would break.
          </p>
        </section>

        <section id="roles" aria-labelledby="roles-h">
          <h2 id="roles-h" className="text-2xl font-semibold tracking-tight">Roles, assigned in writing</h2>
          <p className="mt-1 text-text-dim">At T+0 we assume them; we do not discuss them.</p>
          <dl className="mt-4 grid gap-3 sm:grid-cols-3">
            {ROLES.map((r) => (
              <div key={r.role} className="rounded-control border border-line bg-surface px-4 py-3">
                <dt className="font-medium">{r.role}</dt>
                <dd className="text-sm text-text-dim">{r.who}. {r.duty}</dd>
              </div>
            ))}
          </dl>
        </section>

        <section id="clock" aria-labelledby="clock-h">
          <h2 id="clock-h" className="text-2xl font-semibold tracking-tight">The first 60 minutes</h2>
          <table className="mt-4 w-full text-left text-sm">
            <thead className="text-xs uppercase tracking-[0.08em] text-text-dim">
              <tr><th className="py-2 pr-3 font-medium">Minute</th><th className="py-2 pr-3 font-medium">Phase</th><th className="py-2 font-medium">What happens</th></tr>
            </thead>
            <tbody>
              {FIRST_HOUR.map((row) => (
                <tr key={row.clock + row.phase} className="border-t border-line align-top">
                  <td className="num py-2 pr-3 font-medium">{row.clock}</td>
                  <td className="py-2 pr-3 font-medium">{row.phase}</td>
                  <td className="py-2 text-text-dim">{row.actions}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>

        <section id="calls" aria-labelledby="calls-h">
          <h2 id="calls-h" className="text-2xl font-semibold tracking-tight">Three judgment calls, defended out loud</h2>
          <ol className="mt-4 space-y-3">
            {JUDGMENT_CALLS.map((c, i) => (
              <li key={c.title}>
                <p className="font-medium"><span className="num text-text-dim">{i + 1}.</span> {c.title}</p>
                <p className="text-text-dim">{c.text}</p>
              </li>
            ))}
          </ol>
        </section>

        <section id="donts" aria-labelledby="donts-h">
          <h2 id="donts-h" className="text-2xl font-semibold tracking-tight">What we explicitly do not do at 3am</h2>
          <ul className="mt-4 grid gap-2 sm:grid-cols-2">
            {DONTS.map((d) => <li key={d} className="rounded-control border border-line bg-surface px-4 py-2 text-sm">{d}</li>)}
          </ul>
          <p className="mt-3 text-sm text-text-dim">The comms desk enforces these as guardrails: a draft that breaks one cannot be approved or published.</p>
        </section>

        <section id="users" aria-labelledby="users-h">
          <h2 id="users-h" className="text-2xl font-semibold tracking-tight">What would make a user stay</h2>
          <ol className="mt-4 list-decimal space-y-1 pl-5">
            {WHAT_KEEPS_USERS.map((w) => <li key={w}>{w}</li>)}
          </ol>
        </section>

        <section id="india" aria-labelledby="india-h">
          <h2 id="india-h" className="text-2xl font-semibold tracking-tight">The India layer</h2>
          <ol className="mt-4 space-y-4">
            {INDIA.map((i, n) => (
              <li key={i.key}>
                <p className="font-medium"><span className="num text-text-dim">{n + 1}.</span> {i.title}</p>
                <p className="text-text-dim">{i.text}</p>
              </li>
            ))}
          </ol>
        </section>

        <section id="cases" aria-labelledby="cases-h">
          <h2 id="cases-h" className="text-2xl font-semibold tracking-tight">Case file: seven precedents, one lesson each</h2>
          <div className="mt-4 space-y-5">
            {PRECEDENTS.map((c, i) => (
              <div key={c.key} className="border-l-2 border-line pl-4">
                <p className="font-medium"><span className="num text-text-dim">{i + 1}.</span> {c.event} <span className="font-normal text-text-dim">· {c.when}</span></p>
                <p className="text-sm text-text-dim">{c.what}</p>
                <p className="mt-1 text-sm"><span className="font-medium">Lesson:</span> {c.lesson}</p>
                <p className="mt-1 text-sm"><span className="font-medium">Where we answer it:</span> {c.answer}</p>
              </div>
            ))}
          </div>
          <h3 className="mt-8 font-semibold">Two published policies we copy</h3>
          <div className="mt-3 space-y-4">
            {POLICY_TEMPLATES.map((t) => (
              <div key={t.key} className="text-sm">
                <p className="font-medium">{t.event} <span className="font-normal text-text-dim">· {t.when}</span></p>
                <p className="text-text-dim">{t.what}</p>
              </div>
            ))}
          </div>
        </section>
      </article>
    </div>
  );
}
