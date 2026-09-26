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
