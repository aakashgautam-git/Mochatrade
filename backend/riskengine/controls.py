"""The risk-control stack. This module is the proof.

The app's second job is to demonstrate that these controls measurably reduce
damage: run the identical seeded shock with the stack off, then on, and
quantify the delta. Each control must therefore be independently togglable and
each must map to an amplifier it kills.

Ranked by damage reduction per engineering-week (research brief section 8):
 1. Mark = oracle-anchored composite with clamp + staleness kill, never LTP
 2. Oracle health monitor -> auto reduce-only + liquidation pause
 3. Liquidation TWAP throttle + max participation rate of resting depth
 4. Time-of-day leverage caps for equity perps (50x RTH -> 5x off-hours)
 5. Margin-call grace window + one-tap top-up + pre-funded UPI buffer
 6. Two-stage partial liquidation (market first, backstop below two-thirds MM)
 7. Published APE policy + funded Incident Reserve
 8. Status page + automated incident comms + evidence snapshotter
 9. Isolated-margin default for long-tail; haircuts that scale with vol
10. Quarterly game-day: run this exact playbook against the simulator

Volatility control mechanisms, which are designed to be layered because no
single control can do the job (CFTC/FIA, Sept 2023):
    pre-trade price bands -> velocity logic (~5s pause) -> dynamic circuit
    breakers (60-minute rolling look-back, 2-minute pre-open on breach)
    -> daily price limits

Reopen discipline belongs here too: come back through an auction with an
indicative opening price and order-balance display, never straight into
continuous trading, or you print a second wick on the reopen.

The transparency rule is part of the design, not decoration: parameters must be
publicly available and replicable so a participant can compute the triggers
themselves, with market-wide notification when a control fires.

Also models the operator's Protect Switch (T+2..5): one pre-authorised switch
that sets risk-increasing orders to reduce-only, throttles the liquidation
engine, drops max leverage to 3x, and pauses liquidations on a market whose
oracle is suspect. haltTrading stays holstered, because it cancels all orders
and settles everyone at the mark that is currently in dispute.
"""
