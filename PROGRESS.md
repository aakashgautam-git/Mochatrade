# Progress log

Three lines per phase: done / deviations / issues.

## Circuit-breaker bounds fix
- Done: DCB bounds anchored to the opposite extreme; look-back restarts on resume; fires in 5/6 scenarios; controls-on still beats off everywhere; reopen wick 413 -> 223 bps.
- Deviations: none. FRAME_SCHEMA bumped to 6 so cached runs re-warm.
- Issues: none.

## Phase 7: War room
- Done: declare against any scenario; one T+0 to T+60 clock (engine ticks, then the drill clock); three-layer triage from live state; 11-step playbook from research section 6 with owners and due times; decisions with role, rationale and guardrail confirms; public updates 1-3; incident drives the pill (new "Trading paused"); simulator never does.
- Deviations: added PROTECT_SWITCH and QUANTIFY action types (the playbook's T+2 and T+15 steps); after the market event only post-market decisions are accepted, since nothing else can change a finished run. Divergence is labelled "Mark vs clean reference": the chart's composite line is what our oracle published, the stat is against the same ladder rebuilt without our defect.
- Issues: an action racing a clock step on the threaded dev server was refused as "in the past" (intermittent 400); fixed with a per-incident lock and a test.

## Phase 8: Forensics
- Done: pure classifier (APE criteria per account on the decisive fill; A-G per account and per incident from tape signatures); POST/GET classify writes SimAccount + Claim rows with evidence and logs CLASSIFY; evidence endpoint now serves the persisted per-source PriceObservation tape; Forensics page; War Room "Run the APE test" calls the real classifier. Controls-on verdicts match every scenario's expected class.
- Deviations: a liquidation on a last-traded-price mark is class C (our market's mark methodology), so controls-off runs of the off-hours wick and the macro cascade classify C, not B/A: that is the finding, not a bug. B vs A with nobody liquidated uses "book dislocated beyond the mark band while the underlying's primary market was closed" as the thin-book test, since the research gives no depth threshold. Manipulation (G) is two or more tradeable venues beyond the NRR on the same side at once with our book following.
- Issues: none open.

## Phase 9: Remediation
- Done: pure make-whole per class and the five-step waterfall; POST/GET claims (auto-approve + provisional credit for C/D/E, G pending, A/F no remedy, B fee rebate); human decisions survive re-opening; the reserve is one ledger across incidents; Recalibrate from simulation writes a new policy version (reserve = 2x worst modelled loss) and proves its fixed point; Remediation page with the thesis line, waterfall, claims decisions, reserve and the India tax note.
- Deviations: the cap is read as the total cash paid per incident from all sources (its help text: "per-incident compensation cap"), with the waterfall ordering who funds it. D restores equity at the moment of lockout and G equity at the start of the push (the research names the window, not a formula). Worst modelled loss = the largest uncapped claims total over all 12 seeded runs, controls on and off: a failed control stack is what a reserve is for. E&O and F goodwill have no amount in the policy, so neither is invented: E&O reimburses after payout, and no goodwill is credited. The run cache key now ignores the version string and funding-only fields, which no run depends on.
- Issues: none open.

## Phase 10: Comms
- Done: guardrail rulebook (each rule cites its research line) with live server-side checking; nine data-filled templates across four audiences and five channels; draft / IC approval / publish flow with re-linting at approval; the war room's one-click update now runs the same guardrails and templates; public /status page (components from live state, incident timeline, public-audience updates only).
- Deviations: the "funds are safe" rule is unlocked by an explicit OPS solvency attestation on the draft, since solvency verification is a human act the engine cannot model. The handover template leaves "[ship date]" for a human to commit, and the guardrails block it until filled. Platform limits (X 280, Telegram 4096) are the only length rules.
- Issues: none open.

## Phase 11: Report and Playbook
- Done: Report page (handover five, verdict and evidence, run summary, timeline, waterfall, comms with the one-hour check, class-matched precedents, India obligations with this incident's dates); Playbook page (the research's published procedure with live policy values); one shared research data module; the placeholder page is gone and every nav section is real; documents default to the light palette.
- Deviations: precedents are placed per research 3 and 5 by class (C → OKX 2019 + NSE/Emkay, D → Robinhood + Oct 2025, G → JELLY + dYdX, and so on); the research's reopen gate thresholds are unnumbered ("spread < X bps, depth > Y%"), so the Playbook states the gates without inventing numbers. The report endpoint now returns aggregates instead of every claim twice.
- Issues: none open.

## Checkpoint: cloud handoff (26 Sep 2026)
- Current phase: 12 (seed data + polish), next and not started; phases 0-11 done and committed (last: b776174). Tests at that commit: backend 377 passed / 2 skipped, web 34 passed, typecheck clean.
- Half-done: nothing in code. A fresh database has no demo incident until Phase 12's seed, so Forensics, Remediation, Comms and Report start empty; the final pass (click-through, build, final docs) has not run.
- Next: Phase 12 seed_demo command wired into make seed, then polish, then the final pass. Cloud setup steps are in HANDOFF.md.

## Phase 12: Seed data and polish
- Done: `seed_demo` (wired into `make seed`) runs three drills through the real API: G long-tail (resolved, FIU-IND + venue pack, IC approves every claim), D broker outage (resolved, provisional credit then paid, staged reopen, handover), C macro cascade controls off (in flight at T+40, 319 class C claims above the cap, pro-rata 96%, reopen update awaiting the IC). Indian money everywhere via `riskengine/indian.py` (admin, margin-tier labels, engine and classifier text) and a matching web `rupees()`. Polish from the click-through: next-update times follow the template's playbook slot; class C by last-trade marking is named as such; own-it and glitch rules no longer misfire on our own templates; the number owns C/D/E; public updates counted per number, not per channel; /status shows each update once with its channels; logs label publishes "Update 2 on X"; the pill follows the live incident on every page; favicon; cascade axis floor.
- Deviations: the seed re-stamps each record at declared_at + its drill second (the war room log's own mapping) because a drill plays an hour in seconds; resolved drills are declared at their scenario's labelled IST time. The handover's ship date is committed from the research's effort for the matching change (section 8: #1, #5, #9). A comms publish during a live market is now queued to the engine too (a rebuild replays it; before, the rebuilt frame log differed). FRAME_SCHEMA 7 (Indian grouping in engine log lines).
- Issues: none open.

## Phase 13: Final pass
- Done: `make build` clean (tsc + vite); vendor split into react / charts / state / icons chunks, largest 416 kB (112 kB gzip), no size warning; `make preview` serves the build with the /api proxy. Headless click-through of all 11 routes on the production build, plus the main interaction on each (simulator plays, account select, claims filter, template fill + guardrail block, report incident switch, war-room declare, step and Protect Switch): all pass, no page or console errors.
- Deviations: ARCHITECTURE.md had no Phase 13 row; the final pass HANDOFF.md described (build, click-through, docs) is taken as Phase 13. The final docs update runs after the research review.
- Issues: none open. Google Fonts cannot load inside the cloud sandbox (proxy), which is environmental; the app falls back to system fonts there.

