"""Reference Composite Price and oracle health.

The single most product-specific problem in this brief: MochaTrade's flagship
is US stock perps trading 24/7 in IST. US cash equities are open 19:00-01:30
IST. A 15% wick on a TSLA perp at 04:00 IST on a Sunday has no external
reference price at all, so "compare it to Binance" is not available. The
composite must therefore be defined ex ante and must degrade gracefully.

The published ladder (research brief 5.1):
  L1  >=3 major spot venues (crypto) or the US cash market (equities, RTH)
  L2  index futures (ES/NQ) + ADRs + ETF NAV proxy
  L3  median of >=2 independent perp venues
  L4  no valid composite -> the market is force-flagged DEGRADED:
      max leverage 3x, reduce-only, liquidations paused

Protections that matter more than the formula itself (Binance's published
method):
- Outlier clamp: a source deviating >3% from the median is capped at 1.03x /
  0.97x the median (1% for the majors).
- Staleness kill: a source that has not updated within the staleness window has
  its weight set to zero.

Binance had both on 10 Oct 2025 and still got hurt, because the failure was in
how *collateral* was marked, not in the formula. Model that too.

Responsibilities
----------------
- Hold per-source price series with independent health (stale, deviating, down).
- Compute the composite at the highest available ladder rung and report which
  rung produced it, because the operator's decision depends on that.
- Emit an oracle-health verdict that can auto-trigger reduce-only and a
  liquidation pause (control #2 in the ranked change list).
- Retain per-source inputs per tick: this is the evidence tape that decides a
  Class C claim, and the thing a judge can audit.

Liability note: on a HIP-3 market MochaTrade sets this oracle and is slashable
up to 100% of a 500,000 HYPE stake for a bad one. A bad oracle is not a refund
problem here, it is a slashing event.
"""
