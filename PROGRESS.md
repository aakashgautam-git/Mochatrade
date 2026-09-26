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
