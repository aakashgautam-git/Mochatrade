"""Scenario definitions: the shock, the book, and the account population.

A scenario is a fully declarative, seeded description of a crisis. It must
contain no behaviour, so that the same scenario can be replayed against the
control stack off and on and the only difference is the controls.

A scenario declares:
- the instrument and its tier (which sets the Non-Reviewable Range)
- the wall-clock start in IST, which decides whether the US cash market is open
  and therefore which rung of the composite ladder is available
- the shock: shape, magnitude, duration, and whether it reverts
- which layer actually broke (VENUE / MARKET / BROKER), because the operator
  has to triage that and the classifier has to agree
- the injected faults: oracle source deviation or staleness, app/API outage
  window, UPI settlement delay, manipulation
- the book's calm baseline and its withdrawal behaviour under stress
- the account population: sizes, leverage, margin mode, entry prices

Scenarios to ship, drawn from the case file:
- Off-hours equity wick, no reference composite available (the signature
  MochaTrade risk: 04:00 IST Sunday, no cash market to compare against)
- Oracle defect on a MochaTrade-deployed HIP-3 market (Class C, full liability,
  and a slashing exposure on the 500k HYPE stake)
- Broker-layer outage during a real market move (Class D: the failure mode a
  three-person team is most likely to actually cause)
- UPI settlement delay across a liquidation (Class E)
- Self-manipulation into the backstop vault (JELLY, 26 Mar 2025)
- The macro cascade (10-11 Oct 2025: $19.3B liquidated, 1.62M accounts, 87%
  longs)
"""
