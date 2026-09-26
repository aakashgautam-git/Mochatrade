# REVIEW — the app against the research

Every control, policy, number, precedent, India point and playbook step in
[`MOCHATRADE_PS3_RESEARCH.md`](./MOCHATRADE_PS3_RESEARCH.md), section by
section, marked against the app as it stood at `2023699` (after Phases 12
and 13). "Now" is the state at `28dd758`: fix batch 1 (everything MISSING)
shipped; the PARTIAL batches were stopped on request, with batch 2a parked
unmerged on the `wip-batch-2a` branch.

- **BUILT**: the mechanism runs, or the text is published where a user or a
  judge reads it, and the number matches the research.
- **PARTIAL**: some of it exists: a mechanism without its surface, a surface
  without its mechanism, or a piece missing.
- **MISSING**: nothing in the app does it or says it.

"Found" is the status at review time; "Now" is the status at `28dd758`.
Where a row stays PARTIAL or MISSING, the last column says why: either a
number the research does not give (never invented; see KNOWN_ISSUES.md), or
work not done yet.

Paths: `riskengine/` and `core/` are under `backend/`; pages and `lib/` are
under `web/src/`.

## §0 The insight: a broker, not an exchange

| ID | Research item | Found | Now | Where it lives |
|---|---|---|---|---|
| 0.1 | Cannot pause the matching engine: HyperCore keeps matching | BUILT | BUILT | Playbook header; L3 triage card "No control" (`core/triage.py`); Overview "How this works" |
| 0.2 | Cannot roll back or bust trades: fills are on-chain and final | BUILT | BUILT | Playbook policy section; comms `rollback-promise` block (`core/comms.py`); Remediation thesis |
| 0.3 | `haltTrading` only on our own HIP-3 market; cancels all orders, settles at current mark; the nuclear option | BUILT | BUILT | `riskengine/engine.py` `_settle_everyone_at_mark`; War Room irreversible confirm; log marks it irreversible |
| 0.4 | Mark changeable only on our HIP-3 market, where a bad oracle is slashable up to 100% of 500k HYPE | BUILT | BUILT | Playbook (`HIP3_STAKE`, `lib/research.ts`); L2 triage header |
| 0.5 | Our app, API, leverage menu, margin UI, UPI rails, INR ledger, comms, money: 100% ours | BUILT | BUILT | L1 triage signals (app/API, UPI in flight, grace window) |
| 0.6 | Three-layer triage: L3 venue, L2 market, L1 broker | BUILT | BUILT | `core/triage.py`; War Room triage cards |
| 0.7 | Minute one is "which layer broke", not "what did the market do" | BUILT | BUILT | War Room layout; classifier's layer per verdict (`riskengine/classifier.py`) |
| 0.8 | The likeliest "we caused this" failure is L1: app froze, API limited, UPI top-up late | BUILT | BUILT | Scenarios `broker_outage`, `upi_settlement_delay`; classes D and E |
| 0.9 | Builder codes; the agent wallet can execute trades but cannot move user funds | PARTIAL | BUILT | Builder-code fees fund the reserve (Playbook "The money"); the agent-wallet limit was stated nowhere user-facing. Now in the Playbook's levers table |
| 0.10 | The lever table: what the generic answer assumes vs what MochaTrade has | MISSING | BUILT | Playbook "What we can and cannot do" |

## §1 The "compare it to Binance" test breaks

| ID | Research item | Found | Now | Where it lives |
|---|---|---|---|---|
| 1.1 | US cash equities open 19:00–01:30 IST; outside that there is no spot market to compare against | PARTIAL | BUILT | Was only in admin help text and scenario notes; now on the Playbook's Reference Composite section |
| 1.2 | Equity perps mark through the weekend; trade.xyz becomes the primary venue off-hours | BUILT | BUILT | `offhours_equity_wick` scenario (weekend session, trade.xyz source) |
| 1.3 | A 15% wick at 04:00 IST on a Sunday has no external reference | BUILT | BUILT | `offhours_equity_wick` ("Sunday 04:12 IST"), composite falls to L2/L3 |
| 1.4 | Some off-hours moves are real (a 20% earnings gap) | BUILT | BUILT | APE criterion 2 (reversion) separates a wick from a repricing; class A |
| 1.5 | Define "abnormal" ex ante against a published Reference Composite | BUILT | BUILT | Playbook APE section; classifier reads the published policy |
| 1.6 | The composite degrades: index futures → ADRs → ETF proxies → other perp venues | BUILT | BUILT | `riskengine/oracle.py` ladder L1–L4 |
| 1.7 | When it cannot be built: cut leverage and widen bands before the event | BUILT | BUILT | Time-of-day caps (50x RTH → 5x off-hours); off-hours DCB ×1.6 and wider off-hours NRR; L4 → 3x, reduce-only, liquidations paused |

## §2 The physics: five amplifiers

| ID | Research item | Found | Now | Where it lives |
|---|---|---|---|---|
| 2.1 | A1: the liquidation engine becomes the largest seller (BitMEX) | BUILT | BUILT | Liquidation TWAP throttle, 20% of depth within 1% per 250 ms slice; the reopening auction's intake is throttled too |
| 2.2 | A2: liquidity evaporates; Oct 2025 top-of-book depth fell >90% | BUILT | BUILT | Maker withdrawal (`riskengine/book.py`); macro cascade depth falls to 6% of calm |
| 2.3 | A3: the price feed as the weapon (venue-local dislocation) | BUILT | BUILT | Oracle-anchored mark, clamp, staleness kill; `oracle_defect_hip3` |
| 2.4 | A4: cross-margin turns one bad asset into a portfolio wipeout | PARTIAL | PARTIAL | Accounts carry cross/isolated mode, but nothing in the engine reads it: the isolated-margin control has no effect, and (bug, now fixed) switching it on skipped a random draw and reshuffled the whole population. Contagion needs a second collateral asset and a depeg path; open decision, see KNOWN_ISSUES |
| 2.5 | A5: ADL force-closes winners at the bankruptcy price | BUILT | BUILT | ADL stage in `riskengine/liquidation.py`; ADL counts on Simulator and War Room |
| 2.6 | arXiv 2512.01112: ~$653M of unnecessary haircuts on 10 Oct, ~28× overutilisation, ~50% OI loss | PARTIAL | BUILT | Was a code comment only; now in the Playbook's ADL section |
| 2.7 | The ADL trilemma: no policy delivers solvency, fairness and revenue; choose and say which | MISSING | BUILT | Playbook ADL section states the choice the engine makes |
| 2.8 | Model all five, because turning each one off is a demonstrable control | PARTIAL | BUILT | The Simulator compared whole stacks only. Now each control's leave-one-out value per scenario is measured and published (Simulator "What each control is worth", Playbook "Ten changes") |

## §3 Case file

| ID | Research item | Found | Now | Where it lives |
|---|---|---|---|---|
| 3.1 | BitMEX, Mar 2020 → throttle your own engine | BUILT | BUILT | `lib/research.ts` precedents; Playbook case file; the throttle |
| 3.2 | Binance.US, Oct 2021 → pre-trade price bands | BUILT | BUILT | Case file; pre-trade price bands |
| 3.3 | NSE/Emkay, Oct 2012 → annulment is fragile, trades stand, rule first | BUILT | BUILT | Case file; Report precedents for C and E |
| 3.4 | dYdX v3, Nov 2023 → long-tail perps are an attack surface | BUILT | BUILT | Case file; tier 3 NRR; class G (isolated default: see 2.4) |
| 3.5 | Hyperliquid JELLY, Mar 2025 → the intervention costs more than the loss; publish the procedure | BUILT | BUILT | Case file; class G; no reversal anywhere |
| 3.6 | Oct 10–11 2025 → the infrastructure failure, not the cascade | BUILT | BUILT | Case file; class D; reduce-only over halt; published cap |
| 3.7 | Robinhood → FINRA $70M, misleading statements | BUILT | BUILT | Case file; comms guardrails |
| 3.8 | OKX 2019: compensate, name the windows, set a deadline, exclude normal losses | BUILT | BUILT | "The number" names the window; provisional deadline; class A gets no remedy |
| 3.9 | CFTC/FIA 2023: all trades stand; adjust over cancel; hard review window; consistent determinations | BUILT | BUILT | Playbook policy templates; deterministic classifier |

## §4 The control catalogue

### 4.1 Pricing

| ID | Research item | Found | Now | Where it lives |
|---|---|---|---|---|
| 4.1.1 | Price index = weighted spot across venues, weight-normalised | BUILT | BUILT | `riskengine/oracle.py` |
| 4.1.2 | Mark = median(Price1, Price2, contract price) | BUILT | BUILT | `riskengine/marking.py`; now also written out on the Playbook |
| 4.1.3 | Price1 = index × (1 + funding × time to funding / period) | BUILT | BUILT | `marking.py`; hourly funding period |
| 4.1.4 | Price2 = index + 30 s moving average of basis | BUILT | BUILT | `basis_ma_seconds` 30 |
| 4.1.5 | Outlier clamp 3%, 1% for BTC/ETH/SOL | BUILT | BUILT | Engine correct. The Playbook published it as "0.03%; 0.01%" (a fraction printed as a percent); fixed |
| 4.1.6 | Staleness kill: no update in 5 minutes → weight zero | BUILT | BUILT | `staleness_seconds` 300 |
| 4.1.7 | Liquidate on a mark that blends external prices with the book, never one instantaneous price | BUILT | BUILT | Oracle-anchored mark control |
| 4.1.8 | Collateral marked off a venue-local price (USDe $0.65, wBETH/BnSOL 5–7%); multi-venue liquidity-weighted oracles | PARTIAL | PARTIAL | The instrument's oracle is multi-venue with outlier controls; collateral is INR only, and source weights are fixed, not liquidity-weighted. Open decision (see 2.4) |

### 4.2 Volatility control mechanisms

| ID | Research item | Found | Now | Where it lives |
|---|---|---|---|---|
| 4.2.1 | Pre-trade price bands, dynamic, around the reference | PARTIAL | PARTIAL | The band (width = DCB variant, DERIVED) collars the reopening auction, but the control flag is never read, so continuous trading is not banded. Wiring it was built and measured; it fights the throttle, so it waits on a calibration decision (KNOWN_ISSUES). The attribution and the Playbook say so |
| 4.2.2 | Velocity logic, ~5 s pause | BUILT | BUILT | `riskengine/controls.py` (plus cooldown and escalation, DERIVED) |
| 4.2.3 | DCB: 60-minute rolling look-back ± variant; breach → 2-minute pre-open; look-back restarts on resume | BUILT | BUILT | `controls.py`; bounds fixed in `18681be` |
| 4.2.4 | DCB pause reduced to 5 s near the close | PARTIAL | PARTIAL | Perps trade 24/7 and have no close; "how near" has no number in the research. Not modelled |
| 4.2.5 | Daily price limits, expanded after a limit settle (the macro layer) | MISSING | MISSING | The research gives no limit. Needs a parameter decision; see KNOWN_ISSUES |
| 4.2.6 | Layers used together: "no single control can accomplish the goal" | BUILT | BUILT | Three of the four layers run together |
| 4.2.7 | Reopen through an auction with an indicative opening price and order-balance display | PARTIAL | PARTIAL | The call auction runs; nothing is published during the pre-open. Next: publish the indicative price and imbalance each paused second |
| 4.2.8 | Parameters public and replicable | BUILT | BUILT | Playbook reads the live policy; admin shows every citation |
| 4.2.9 | Market-wide notification when a control fires | BUILT | BUILT | `/status` components come from the live engine ("paused for a moment, reopens through a short auction") |

### 4.3 Liquidation engine

| ID | Research item | Found | Now | Where it lives |
|---|---|---|---|---|
| 4.3.1 | Partial, tiered: close only enough to restore margin | BUILT | BUILT | `liquidation.py`; target 1.5× MM (DERIVED) |
| 4.3.2 | Two-stage: market first, residual kept, no fee; backstop below ⅔ MM, MM forfeited | BUILT | BUILT | `backstop_threshold_frac` ⅔, `clearance_fee_pct` on stage two only |
| 4.3.3 | Waterfall: partial → market → backstop → ADL last | BUILT | BUILT | `liquidation.py` |
| 4.3.4 | ADL rank = PNL% × effective leverage, at the bankruptcy price | BUILT | BUILT | `liquidation.py` ADL stage |
| 4.3.5 | Backstop liquidity providers: committed makers, quoting obligations, paid in rebates | MISSING | MISSING | No committed depth or rebate in the research. Needs a parameter decision |
| 4.3.6 | Margin-call grace window, 2–5 minutes, with a push notification | BUILT | BUILT | `margin_grace_seconds` 120; L1 triage "Margin calls in grace window" |

### 4.4 HIP-3

| ID | Research item | Found | Now | Where it lives |
|---|---|---|---|---|
| 4.4.1 | Deployer sets oracle, contract spec, max leverage, fee share; can `haltTrading` | BUILT | BUILT | Policy editable in the admin; halt action |
| 4.4.2 | 500k HYPE for ≥183 days; slashing up to 100/50/20%; burned, not paid to users | BUILT | BUILT | Playbook |
| 4.4.3 | Cross-margin enablement irreversible; barred for assets expected to move 50% daily more than monthly; a >50% daily move triggers validator review | MISSING | BUILT | Playbook HIP-3 section; L2 triage "Move vs the 50% review line" from the tape |
| 4.4.4 | Each dex has an on-chain backstop liquidator that reduces ADL | BUILT | BUILT | Backstop vault stage |

## §5 The policy: trades stand, people get made whole

| ID | Research item | Found | Now | Where it lives |
|---|---|---|---|---|
| 5.0 | Never reverse, always compensate, decide by a rule published first; four reasons | BUILT | BUILT | Playbook; Report precedent section |
| 5.1.1 | APE 1: deviation from the Reference Composite in the same second beyond the NRR | BUILT | BUILT | `classifier.py` |
| 5.1.2 | APE 2: ≥50% reversion within 60 s | BUILT | BUILT | `ape_reversion_frac`, `ape_reversion_seconds` |
| 5.1.3 | APE 3: counterfactual survival at the reference | BUILT | BUILT | Per-fill `survived_at_reference` |
| 5.1.4 | NRR table 3/5, 5/8, 10/15 | BUILT | BUILT | `INSTRUMENT_TIERS_V1`; Playbook table |
| 5.1.5 | Ladder L1 (≥3 spot or US cash RTH) → L2 → L3 (≥2 perps) → L4 degraded: 3x, reduce-only, liquidations paused | BUILT | BUILT | `oracle.py`; oracle health monitor |
| 5.2.A | A: no remedy; publish the evidence tape | BUILT | BUILT | Remedy logic; the tape is on the Forensics page (not yet downloadable) |
| 5.2.B | B: fee rebate, and the fix ships with a date | BUILT | BUILT | Fee rebate in claims; handover commits the fix and its date |
| 5.2.C | C: full make-whole to counterfactual equity at the reference | BUILT | BUILT | `riskengine/remediation.py` |
| 5.2.D | D: make-whole for loss attributable to the outage window | BUILT | BUILT | Equity at lockout |
| 5.2.E | E: make-whole where the deposit was initiated before and settled after | BUILT | BUILT | UPI in-flight accounts |
| 5.2.F | F: no cash liability; file the evidence pack; publish the venue's response; goodwill at a published cap | PARTIAL | PARTIAL | Evidence pack template built. There is no venue response to publish in a drill, and the research gives no goodwill cap, so none is credited |
| 5.2.G | G: freeze what we can, report to FIU-IND and the venue, fund from the reserve, pursue recovery | PARTIAL | PARTIAL | FIU-IND and venue templates, reserve funding; a recovery cannot yet be recorded into waterfall step 1 |
| 5.2.S | Speed clause: provisional credit within 60 min as locked credit, withdrawable after a published reconciliation | PARTIAL | PARTIAL | Credit and deadline work; the reconciliation is not yet published |
| 5.2.T | Never make a liquidated user file a ticket | BUILT | BUILT | C/D/E auto-approved |
| 5.3.1 | Funding waterfall, five steps, in order | BUILT | BUILT | `remediation.waterfall`; Remediation page |
| 5.3.2 | Incident Reserve: ring-fenced, publicly visible balance | PARTIAL | PARTIAL | Visible on Remediation and the Playbook, not yet on the public `/status` |
| 5.3.3 | Funded by 10% of builder-code fees until 2× the worst modelled 30-day loss | BUILT | BUILT | "Recalibrate from simulation". The worst loss is the worst single seeded run (Phase 9 decision) |
| 5.3.4 | Treasury up to a published per-incident cap | BUILT | BUILT | ₹1.50 Cr cap |
| 5.3.5 | Tech E&O insurance | BUILT | BUILT | Step 4, reimburses the treasury |
| 5.3.6 | Beyond the cap: pro-rata + non-cash make-good, announced, never paid silently short | BUILT | BUILT | Waterfall; `full-when-pro-rata` block |
| 5.3.7 | The cap exists and is published in advance | BUILT | BUILT | Playbook; Remediation |

## §6 The first 60 minutes

| ID | Research item | Found | Now | Where it lives |
|---|---|---|---|---|
| 6.0 | Roles pre-assigned; IC owns decisions and the clock and does not touch a keyboard | BUILT | BUILT | Declare panel; "Acting as"; Playbook roles |
| 6.1 | 0–2 Detect: auto-pager on divergence, liquidation rate, API 5xx, ticket rate; the record opens itself | PARTIAL | PARTIAL | The 50 bps divergence line exists, but nothing pages; the operator declares. Built on `wip-batch-2a`, not merged |
| 6.2 | 2–5 Contain: Protect Switch (reduce-only, TWAP throttle, 3x); pause liquidations only if the oracle is suspect; halt holstered | BUILT | BUILT | Engine actions; guard confirms |
| 6.3 | T+3 Preserve: write-once snapshot of book, tape, per-source oracle, marks, liquidations, telemetry, deposits | PARTIAL | PARTIAL | A log line only; the tape itself is persisted every second. Digest seal built on `wip-batch-2a`, not merged |
| 6.4 | T+5 First word: status page → X → WhatsApp/Telegram; no cause, no blame; next update at HH:MM | BUILT | BUILT | `first-word` template and guardrails |
| 6.5 | 5–15 Diagnose: APE per second per venue; own layer: app uptime, API errors, order-reject rate, UPI queue; classify A–G | PARTIAL | PARTIAL | All built except the order-reject rate: the engine has no user order flow to reject |
| 6.6 | T+15 Update 2: if C/D/E, say so | BUILT | BUILT | `preliminary` template; `own-it` rule |
| 6.7 | 15–30 Quantify: affected set, counterfactual equity, the number; does the reserve cover it | PARTIAL | PARTIAL | "Log quantified" only logs; the number is computed on Remediation. Built on `wip-batch-2a`, not merged |
| 6.8 | T+30 Update 3: "N users, ₹X, between HH:MM–HH:MM IST", citing the APE policy | BUILT | BUILT | `the-number` template |
| 6.9 | 30–45 Remediate: push provisional credit; claims portal, 72-hour window; answer each ticket with a link to their own status | PARTIAL | PARTIAL | War Room claims buttons only log (claims open on Remediation); no 72-hour window; the per-user link is a merge field |
| 6.10 | 45–60 Reopen: staged, each gate needs the oracle healthy 5 minutes, spread < X, depth > Y%; through a short auction | PARTIAL | PARTIAL | Stages are log entries; gates not evaluated. Gate check built on `wip-batch-2a`, not merged |
| 6.11 | T+60 Handover: what happened, who, what we pay, when, RCA date | BUILT | BUILT | `handover` template |
| 6.12 | Three judgment calls | BUILT | BUILT | Guard confirms; Playbook |
| 6.13 | Don't: rewrite risk parameters live | PARTIAL | PARTIAL | "Recalibrate" can write a new policy mid-incident. Guard built on `wip-batch-2a`, not merged |
| 6.14 | Don't: argue on X; promise a number early; "funds are safe" before solvency; "market conditions" | BUILT | BUILT | Guardrail blocks |
| 6.15 | Don't: answer tickets individually | BUILT | BUILT | One templated message to every affected user |

## §7 The India layer

| ID | Research item | Found | Now | Where it lives |
|---|---|---|---|---|
| 7.1 | VDA: flat 30%, no loss set-off, 1% TDS; compensation policy is the competitive weapon | BUILT | BUILT | Remediation India note; Report; Playbook |
| 7.2a | SEBI framework: a malfunction ≥5 minutes is a reportable glitch | PARTIAL | PARTIAL | Stated on the Report, not measured from the tape |
| 7.2b | Notify within 1 hour | BUILT | BUILT | Report obligations; SEBI notice template |
| 7.2c | Preliminary report T+1; RCA within 14 days | BUILT | BUILT | Report dates; templates |
| 7.2d | Capacity ≥1.5× peak; alert at 70%; DR ≥250 km | BUILT | BUILT | Playbook India (infrastructure; not simulated) |
| 7.2e | Glitch data retained 2 years | BUILT | BUILT | Report `retain_until` |
| 7.2f | Glitch and RCA published | BUILT | BUILT | `/status`; handover RCA date |
| 7.2g | FIU-IND registration in flight | BUILT | BUILT | Playbook; FIU-IND template |
| 7.3a | UPI: 282 minutes of outage across two incidents | BUILT | BUILT | Playbook; param citation |
| 7.3b | Pre-funded instant margin credit, capped and risk-scored | PARTIAL | PARTIAL | Capped at ₹50,000 and working. No risk score: the research gives no scoring rule |
| 7.4 | Grievance redressal with published SLAs; bilingual comms on WhatsApp and Telegram | PARTIAL | PARTIAL | WhatsApp and Telegram in English only; no SLA numbers in the research |
| 7.5 | Compensation may be taxed as income; document, gross up | BUILT | BUILT | Remediation note; Report |

## §8 The ten changes, ranked by damage reduction per engineering-week

| ID | Research item | Found | Now | Where it lives |
|---|---|---|---|---|
| 8.1 | #1 Oracle-anchored mark with clamp and staleness kill (1 wk) | BUILT | BUILT | `oracle_anchored_mark` |
| 8.2 | #2 Oracle health monitor → reduce-only + liquidation pause (1 wk) | BUILT | BUILT | `oracle_health_monitor` |
| 8.3 | #3 TWAP throttle + participation cap (2 wks) | BUILT | BUILT | `liquidation_throttle` |
| 8.4 | #4 Time-of-day leverage caps, 50x → 5x (3 d) | BUILT | BUILT | `time_of_day_leverage_caps` |
| 8.5 | #5 Grace window + one-tap top-up + pre-funded UPI buffer (2 wks) | BUILT | BUILT | `margin_grace_window`, `upi_prefunded_credit` |
| 8.6 | #6 Two-stage partial liquidation (2 wks) | BUILT | BUILT | `two_stage_liquidation` |
| 8.7 | #7 Published APE policy + funded reserve (1 wk) | BUILT | BUILT | Playbook; Remediation |
| 8.8 | #8 Status page + automated comms + evidence snapshotter (3 d) | PARTIAL | PARTIAL | Status page and comms built; the snapshotter only logs (see 6.3) |
| 8.9 | #9 Isolated margin by default on long-tail; vol-scaled haircuts (1 wk) | PARTIAL | PARTIAL | See 2.4: the flag is inert; haircuts have no numbers in the research |
| 8.10 | #10 Quarterly game-day against the simulator | BUILT | BUILT | The War Room drill |
| 8.11 | The ranking itself: effort, what it kills, damage reduction per week | MISSING | BUILT | Playbook "Ten changes": the research's table plus the simulator's measured leave-one-out value per control |

## §9 What would make a user stay

| ID | Research item | Found | Now | Where it lives |
|---|---|---|---|---|
| 9.1 | A number and a deadline inside the hour | BUILT | BUILT | `the-number` at T+30 with the provisional deadline |
| 9.2 | Money before I ask | BUILT | BUILT | Auto-approved provisional credit |
| 9.3 | The raw tape, to check the story | PARTIAL | PARTIAL | The tape is on the internal Forensics page; no download, no per-account page |
| 9.4 | A named human on camera | BUILT | BUILT | `named-human` rule; signed updates |
| 9.5 | A shipped mechanism change with a date, and a follow-up when it ships | PARTIAL | PARTIAL | The handover carries the fix date; no follow-up "fix shipped" template yet |
| 9.6 | Never "your fault for using the 50x we sold you" | BUILT | BUILT | `blame-users` block |

## §10 Judge questions

| ID | Research item | Found | Now | Where it lives |
|---|---|---|---|---|
| 10.1 | Isn't compensating moral hazard? | MISSING | BUILT | Playbook "Questions we expect" |
| 10.2 | You can't afford Binance's $283M | PARTIAL | BUILT | Was in "The money"; now answered as asked |
| 10.3 | Why not just halt? | PARTIAL | BUILT | Judgment calls; now answered as asked |
| 10.4 | Why not roll back? | PARTIAL | BUILT | Policy section; now answered as asked |
| 10.5 | Your simulator's numbers are made up | MISSING | BUILT | Was in the README only; now on the Playbook |

## Broken, found during the review

| ID | What | Fix |
|---|---|---|
| X.1 | Playbook printed the outlier clamp as 0.03% / 0.01% (a fraction shown as a percent) | Rendered as 3% / 1% |
| X.2 | `isolated_margin_default` short-circuited a random draw, so the controls-on population differed from controls-off beyond leverage | The draw is always taken; FRAME_SCHEMA bumped so cached runs re-warm |
| X.3 | The UPI credit's docstring claims it is risk-scored | Not fixed yet |
| X.4 | The `pre_trade_price_bands` control is never read by the engine: switching it changes nothing | Not wired, by decision: wiring it was measured (KNOWN_ISSUES). The attribution labels it "not wired" instead of reporting a zero as a finding |
| X.5 | With X.2 fixed, the UPI credit's test (fewer in-flight liquidations last into the full stack) only held on the shuffled book | Re-based on the credit alone (264 → 110 in-flight liquidations); last in, the pauses already hold the cascade until deposits land, which the attribution shows |

## Summary

133 items reviewed.

| | Found | Now |
|---|---|---|
| BUILT | 95 | 108 |
| PARTIAL | 30 | 23 |
| MISSING | 8 | 2 |

Every MISSING item that needs no invented number was fixed in batch 1. The two
still MISSING (daily price limits, backstop liquidity providers) need a number
the research does not give. Plus five broken items found during the review
(X.1–X.5): three fixed, one labelled and left for a decision (X.4), one open
(X.3).
