"""Persistence.

Planned tables:

RiskPolicy   A versioned, immutable set of risk parameters seeded from
             MOCHATRADE_PS3_RESEARCH.md: Non-Reviewable Ranges per tier and
             per session, mark-price weights, outlier clamp, staleness window,
             maintenance-margin tiers, two-stage threshold, TWAP throttle and
             participation rate, grace window, leverage caps by time of day,
             composite ladder definition, reserve size and per-incident cap.
             Nothing in a view or a serializer may hard-code any of these.

Scenario     A stored, seeded scenario definition (see riskengine.scenario).

Run          One simulation: scenario + policy version + seed + control stack
             on/off. Holds the engine state needed to resume stepping.

Frame        One tick of output, appended as the run steps. The evidence tape.

OperatorAction  A decision taken in the war room at a given tick, which is
             replayed as part of the determinism contract.

Incident     The classification, the affected set, the remedy and the report.
"""
