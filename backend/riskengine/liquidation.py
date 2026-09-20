"""Liquidation engine, waterfall and ADL.

Amplifier 1: the liquidation engine becomes the largest seller. BitMEX on
12-13 Mar 2020 had contracts to sell into a worsening price, which produced
more liquidations and more contracts to sell; when a DDoS took the engine
offline at 02:16 UTC the price recovered from ~$3,900 to ~$5,300 immediately.
The outage was a better circuit breaker than the circuit breaker. That is the
strongest possible argument for throttling your own engine.

The waterfall to model:
    partial/tiered liquidation -> market liquidation -> backstop/insurance
    -> ADL (last)

Two-stage liquidation (Hyperliquid's model, worth copying):
- Below maintenance margin: market orders into the book, the trader keeps any
  residual collateral, no clearance fee.
- Only below two-thirds of maintenance margin does the backstop liquidator
  vault take the position and the maintenance margin is forfeited.

ADL, and why it is a trust problem rather than a user problem: it force-closes
*winning* positions at the bankrupt trader's bankruptcy price, ranked by
PNL% x effective leverage. A Dec 2025 arXiv analysis of 10 Oct 2025 put
Hyperliquid's queue-based ADL at roughly $653M of unnecessary haircuts on
winning traders, about 28x overutilisation versus optimal policy, likely
contributing to the subsequent ~50% loss of open interest. The same paper
proves an impossibility trilemma: no ADL policy delivers solvency, trader
fairness and long-run revenue at once. The app must state which it chose.

Responsibilities
----------------
- Evaluate accounts against maintenance margin each tick, at the mark.
- Size partial liquidations to restore margin, not to flatten the account.
- Route through the waterfall, obeying the TWAP throttle and max participation
  rate of resting depth when that control is enabled.
- Honour the margin-call grace window (2-5 minutes plus a push notification)
  and the pre-funded UPI margin credit, which is the India-specific control.
- Produce a per-account, per-tick liquidation tape: this is both the cascade
  chart and the evidence for every later claim.
"""
