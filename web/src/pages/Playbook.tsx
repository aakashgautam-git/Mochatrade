import { useQuery } from "@tanstack/react-query";

import { Skeleton } from "../components/ui";
import { fetchActivePolicy, fetchAttributionOverview, parseMoney, rupees } from "../lib/api";
import type { RiskPolicy } from "../lib/types";
import {
  ADL_FINDINGS,
  AMPLIFIERS,
  BUILDER_CODES,
  DONTS,
  FIRST_HOUR,
  HIP3_RULES,
  HIP3_STAKE,
  INDIA,
  JUDGE_QUESTIONS,
  JUDGMENT_CALLS,
  LEVERS,
  OFF_HOURS,
  POLICY_TEMPLATES,
  PRECEDENTS,
  RANKED_CHANGES,
  RANKED_NOTE,
  REMEDY_MATRIX,
  ROLES,
  WHAT_KEEPS_USERS,
  WHY_TRADES_STAND,
} from "../lib/research";

const SECTIONS = [
  ["levers", "What we can do"],
  ["policy", "The policy"],
  ["ape", "The APE test"],
  ["matrix", "Who pays"],
  ["money", "The money"],
  ["physics", "Five amplifiers"],
  ["controls", "The controls"],
  ["changes", "Ten changes"],
  ["roles", "Roles"],
  ["clock", "The first 60 minutes"],
  ["calls", "Judgment calls"],
  ["donts", "What we do not do"],
  ["users", "What keeps a user"],
  ["india", "India"],
  ["cases", "Case file"],
  ["questions", "Questions we expect"],
] as const;

/** A policy fraction as the percent people read: 0.03 → "3%". */
const pct = (frac: number) => `${+(frac * 100).toFixed(2)}%`;

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

        <section id="levers" aria-labelledby="levers-h">
          <h2 id="levers-h" className="text-2xl font-semibold tracking-tight">What we can and cannot do</h2>
          <p className="mt-2 text-sm text-text-dim">{BUILDER_CODES}</p>
          <table className="mt-4 w-full text-left text-sm">
            <thead className="text-xs uppercase tracking-[0.08em] text-text-dim">
              <tr><th className="py-2 pr-3 font-medium">The lever a generic answer assumes</th><th className="py-2 font-medium">Do we have it?</th></tr>
            </thead>
            <tbody>
              {LEVERS.map((l) => (
                <tr key={l.lever} className="border-t border-line align-top">
                  <td className="py-2 pr-3">{l.lever}</td>
                  <td className="py-2"><span className="font-medium">{l.ours ? "Yes." : "No."}</span> {l.answer.replace(/^(Yes|No)[.,] ?/, "")}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-3 text-sm">
            So the first sixty minutes are a three-layer triage — the venue (Hyperliquid), our HIP-3 market, our own app and rails — and for a
            three-person team the likeliest "we caused this" failure is our own layer: the app froze, the API rate-limited, or a UPI top-up did
            not settle before the liquidation fired.
          </p>
        </section>

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
          <p className="mt-1 text-sm text-text-dim">{OFF_HOURS}</p>
          <p className="mt-3">A published, degrading ladder, so it exists at 04:00 IST on a Sunday:</p>
          <ol className="mt-2 space-y-1 text-sm">
            <li><span className="num font-medium">L1</span> — three or more major spot venues (crypto), or the US cash market (equities, regular hours).</li>
            <li><span className="num font-medium">L2</span> — index futures, ADRs and an ETF NAV proxy.</li>
            <li><span className="num font-medium">L3</span> — the median of two or more independent perp venues.</li>
            <li><span className="num font-medium">L4</span> — no valid composite: the market is force-flagged degraded — max leverage 3x, reduce-only, liquidations paused.</li>
          </ol>
          <p className="mt-2 text-sm text-text-dim">
            Our mark never follows the last trade. Sources deviating from the median are clamped{p ? ` (${pct(p.outlier_clamp_pct)}; ${pct(p.majors_outlier_clamp_pct)} for BTC, ETH and SOL)` : ""}, and a source silent for{" "}
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

        <Physics />

        {p ? <Controls p={p} pct={pct} /> : <Skeleton className="h-64" />}

        <Changes />

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
        <section id="questions" aria-labelledby="questions-h">
          <h2 id="questions-h" className="text-2xl font-semibold tracking-tight">Questions we expect, and our answers</h2>
          <dl className="mt-4 space-y-4">
            {JUDGE_QUESTIONS.map((j) => (
              <div key={j.q}>
                <dt className="font-medium">{j.q}</dt>
                <dd className="mt-1 text-sm text-text-dim">{j.a}</dd>
              </div>
            ))}
          </dl>
        </section>
      </article>
    </div>
  );
}

function useAttribution() {
  return useQuery({ queryKey: ["attribution-overview"], queryFn: fetchAttributionOverview, staleTime: Infinity });
}

/** Research 2: the five amplifiers, the controls that act on each, and ADL. */
function Physics() {
  const a = useAttribution();
  const label = (key: string) => a.data?.totals.find((t) => t.control === key)?.label ?? key.replace(/_/g, " ");
  const scenarios = a.data?.scenarios ?? [];
  const adl = (side: "full" | "none") => ({
    runs: scenarios.filter((s) => s[side].adl_accounts > 0).length,
    accounts: scenarios.reduce((n, s) => n + s[side].adl_accounts, 0),
  });
  const on = adl("full");
  const off = adl("none");
  return (
    <section id="physics" aria-labelledby="physics-h">
      <h2 id="physics-h" className="text-2xl font-semibold tracking-tight">Why flash crashes amplify: five amplifiers</h2>
      <p className="mt-2 text-sm text-text-dim">All five were observed in real events. The simulator models each one, and each has a control that can be switched off to show what it does.</p>
      <ol className="mt-4 space-y-3">
        {AMPLIFIERS.map((amp) => (
          <li key={amp.n} className="rounded-control border border-line bg-surface px-4 py-3">
            <p className="font-medium"><span className="num text-text-dim">{amp.n}.</span> {amp.title}</p>
            <p className="mt-1 text-sm text-text-dim">{amp.evidence}</p>
            <p className="mt-1 text-sm">Acted on by: {amp.controls.map(label).join("; ")}.</p>
          </li>
        ))}
      </ol>
      <h3 className="mt-8 font-semibold">ADL: the trilemma, and what we chose</h3>
      <p className="mt-1 text-sm text-text-dim">{ADL_FINDINGS}</p>
      <p className="mt-3 text-sm">
        <span className="font-medium">We chose solvency and a published fairness rule, and we pay for it in revenue.</span> ADL stays in the
        waterfall, so the market can never go insolvent, but it runs last: after partial liquidation, market liquidation and the backstop vault.
        When it runs it ranks by Binance's published PNL% × effective leverage and closes at the bankruptcy price, so anyone can compute their own
        place in the queue. Every ADL event costs open interest, which is why the rest of the stack exists to keep the queue empty.
      </p>
      {a.data ? (
        <p className="mt-2 text-sm text-text-dim">
          On the seeded scenarios: without controls, ADL fired in {off.runs} of {scenarios.length} ({off.accounts.toLocaleString("en-IN")} winning
          accounts force-closed); with the full stack, in {on.runs} of {scenarios.length} ({on.accounts.toLocaleString("en-IN")}).
        </p>
      ) : null}
    </section>
  );
}

/** Research 4: every control's trigger, with the live numbers, so anyone can replicate it. */
function Controls({ p, pct }: { p: RiskPolicy; pct: (frac: number) => string }) {
  const variants = p.instrument_tiers.map((t) => `tier ${t.tier} ${+(t.dcb_variant_pct * p.price_band_frac_of_dcb).toFixed(2)}%`).join(", ");
  return (
    <section id="controls" aria-labelledby="controls-h">
      <h2 id="controls-h" className="text-2xl font-semibold tracking-tight">The controls, with every trigger published</h2>
      <p className="mt-2 text-sm text-text-dim">
        Parameters must be publicly available and replicable, so a participant can compute the triggers themselves (CFTC/FIA). These are the
        live values of policy {p.version}. The mechanisms are Binance's, CME's and Hyperliquid's published specifications; the values are ours.
      </p>

      <h3 className="mt-6 font-semibold">Pricing: never liquidate on the last trade</h3>
      <ul className="mt-2 space-y-1 text-sm">
        <li><span className="num">Index = Σ weightᵢ × priceᵢ</span>, across the ladder's sources, weight-normalised. A source more than {pct(p.outlier_clamp_pct)} from the median is clamped to it ({pct(p.majors_outlier_clamp_pct)} for BTC, ETH and SOL); a source silent for {Math.round(p.staleness_seconds / 60)} minutes gets weight zero.</li>
        <li><span className="num">Mark = median(Price1, Price2, last traded)</span>, where <span className="num">Price1 = Index × (1 + funding rate × time to funding ÷ {Math.round(p.funding_period_seconds / 60)} min)</span> and <span className="num">Price2 = Index + the {p.basis_ma_seconds}-second moving average of the basis</span>.</li>
        <li>Mark more than {p.mark_max_deviation_bps} bps from the Reference Composite pages the team.</li>
      </ul>

      <h3 className="mt-6 font-semibold">Volatility controls, in four layers</h3>
      <table className="mt-2 w-full text-left text-sm">
        <thead className="text-xs uppercase tracking-[0.08em] text-text-dim">
          <tr><th className="py-2 pr-3 font-medium">Layer</th><th className="py-2 pr-3 font-medium">Mechanism</th><th className="py-2 font-medium">Our trigger</th></tr>
        </thead>
        <tbody>
          <tr className="border-t border-line align-top">
            <td className="py-2 pr-3">Pre-trade</td><td className="py-2 pr-3">Price bands</td>
            <td className="py-2">The band is the Reference Composite ± {variants}, ×{p.dcb_offhours_multiplier} off-hours. Today it collars the reopening auction only. Applying it to every order was measured and waits on a calibration decision: stacked on the throttle, it holds closes past bankruptcy and brings ADL back.</td>
          </tr>
          <tr className="border-t border-line align-top">
            <td className="py-2 pr-3">Micro</td><td className="py-2 pr-3">Velocity logic</td>
            <td className="py-2">A move of {pct(p.velocity_trigger_frac_of_dcb)} of the breaker's variant inside {p.velocity_window_seconds} s pauses trading for {p.velocity_window_seconds} s. It re-arms after {p.velocity_cooldown_seconds} s; if the price is still running, the next pause is {p.velocity_escalation_multiplier}× longer, up to the breaker's.</td>
          </tr>
          <tr className="border-t border-line align-top">
            <td className="py-2 pr-3">Meso</td><td className="py-2 pr-3">Dynamic circuit breaker</td>
            <td className="py-2">The {Math.round(p.dcb_lookback_seconds / 60)}-minute rolling high and low, ± the variant ({p.instrument_tiers.map((t) => `${t.dcb_variant_pct}%`).join(" / ")} by tier). A breach is a {Math.round(p.dcb_pause_seconds / 60)}-minute pre-open; the look-back restarts on resume.</td>
          </tr>
          <tr className="border-t border-line align-top">
            <td className="py-2 pr-3">Macro</td><td className="py-2 pr-3">Daily price limits</td>
            <td className="py-2 text-text-dim">Not in our stack yet. The research names the layer but publishes no limit, and we do not invent one.</td>
          </tr>
        </tbody>
      </table>
      <p className="mt-2 text-sm">
        Every pause reopens through a call auction inside the band, never straight into continuous trading: one clearing price (most volume,
        then least imbalance, then nearest the reference), with the throttle applied to what the auction takes in.
      </p>

      <h3 className="mt-6 font-semibold">Liquidation</h3>
      <ul className="mt-2 space-y-1 text-sm">
        <li>Partial first: close only enough to restore {p.partial_liq_target_mm_multiple}× maintenance margin.</li>
        <li>Two-stage: market orders to the book, no fee, the trader keeps any residue. Below {pct(p.backstop_threshold_frac)} of maintenance margin the backstop vault takes the position and the margin is forfeited ({pct(p.clearance_fee_pct)} clearance fee).</li>
        <li>Throttle: at most {pct(p.twap_max_participation_pct)} of resting depth within {pct(p.twap_participation_band_pct)} of the mark, per {p.twap_slice_ms} ms slice.</li>
        <li>A {Math.round(p.margin_grace_seconds / 60)}-minute margin-call grace window with a push notification, and up to {rupees(p.upi_prefunded_credit_cap_inr)} of pre-funded credit against a UPI deposit already initiated.</li>
        <li>Leverage: {p.max_leverage_rth}x in US regular hours, {p.max_leverage_offhours}x off-hours, {p.max_leverage_degraded}x when the composite is degraded or the Protect Switch is thrown.</li>
        <li>ADL last, ranked by PNL% × effective leverage, at the bankruptcy price.</li>
      </ul>

      <h3 className="mt-6 font-semibold">Our own HIP-3 market</h3>
      <ul className="mt-2 space-y-1 text-sm">
        <li>{HIP3_STAKE}</li>
        {HIP3_RULES.map((r) => <li key={r}>{r}</li>)}
      </ul>
    </section>
  );
}

/** Research 8: the ranked changes, beside what the simulator measures for each. */
function Changes() {
  const a = useAttribution();
  const totals = a.data?.totals ?? [];
  const measured = RANKED_CHANGES.map((c) => {
    const rows = totals.filter((t) => c.controls.includes(t.control));
    const modelled = rows.length > 0 && rows.every((t) => !t.not_modelled);
    const loss = rows.reduce((n, t) => n + parseMoney(t.alone.attributable_loss), 0);
    const liq = rows.reduce((n, t) => n + t.alone.accounts_liquidated, 0);
    const lastIn = rows.reduce((n, t) => n + parseMoney(t.last_in.attributable_loss), 0);
    return { c, rows, modelled, loss, liq, lastIn, perWeek: modelled && c.weeks ? loss / c.weeks : null };
  });
  const order = measured.filter((m) => m.perWeek !== null).sort((x, y) => (y.perWeek ?? 0) - (x.perWeek ?? 0)).map((m) => m.c.rank);
  const signed = (v: number) => (Math.abs(v) < 0.5 ? "—" : v > 0 ? rupees(v) : `costs ${rupees(-v)}`);
  return (
    <section id="changes" aria-labelledby="changes-h">
      <h2 id="changes-h" className="text-2xl font-semibold tracking-tight">Ten changes, ranked by damage reduction per engineering-week</h2>
      <p className="mt-2 text-sm text-text-dim">
        The research's ranking, beside what our own engine measures for each change across the six seeded scenarios
        {a.data ? ` (policy ${a.data.policy_version})` : ""}: the attributable loss the change's controls save on their own, that saving per
        engineering-week, and what they add last into the full stack. Policy and product changes are not engine controls, so there is nothing to
        measure; the Simulator shows the same measurement per scenario.
      </p>
      <div className="mt-4 overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="text-xs uppercase tracking-[0.08em] text-text-dim">
            <tr>
              <th className="py-2 pr-3 font-medium">#</th>
              <th className="py-2 pr-3 font-medium">Change · effort · kills</th>
              <th className="py-2 pr-3 text-right font-medium">Saves alone</th>
              <th className="py-2 pr-3 text-right font-medium">Per week</th>
              <th className="py-2 text-right font-medium">Last in</th>
            </tr>
          </thead>
          <tbody>
            {measured.map(({ c, rows, modelled, loss, liq, lastIn, perWeek }) => (
              <tr key={c.rank} className="border-t border-line align-top">
                <td className="num py-2 pr-3 font-semibold">{c.rank}</td>
                <td className="py-2 pr-3">
                  {c.change}
                  <span className="block text-xs text-text-dim"><span className="num">{c.effort}</span> · {c.kills}</span>
                </td>
                {c.controls.length === 0 ? (
                  <td colSpan={3} className="py-2 text-right text-xs text-text-dim">Policy or product, not an engine control</td>
                ) : !a.data ? (
                  <td colSpan={3} className="py-2"><Skeleton className="h-4 w-full" /></td>
                ) : !modelled ? (
                  <td colSpan={3} className="py-2 text-right text-xs text-text-dim" title={rows.find((t) => t.not_modelled)?.not_modelled}>Not modelled yet; the Simulator says why</td>
                ) : (
                  <>
                    <td className="num py-2 pr-3 text-right whitespace-nowrap">{signed(loss)}<span className="block text-xs text-text-dim">{liq.toLocaleString("en-IN")} liquidations</span></td>
                    <td className="num py-2 pr-3 text-right whitespace-nowrap">{perWeek !== null ? signed(perWeek) : "—"}<span className="block text-xs text-text-dim">{perWeek !== null ? `our #${order.indexOf(c.rank) + 1}` : ""}</span></td>
                    <td className="num py-2 text-right whitespace-nowrap">{signed(lastIn)}</td>
                  </>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-3 text-sm text-text-dim">{RANKED_NOTE} Price bands, velocity logic and the circuit breaker come from the CFTC/FIA layers in section 4 of the research, which gives no effort for them; the Simulator measures them too.</p>
    </section>
  );
}
