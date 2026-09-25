"""The reopening call auction.

A pause must not reopen straight into continuous trading. The protected macro
cascade showed why: every 5-second velocity pause ended with the whole queue of
liquidations hitting the book at once, the price dropped, the layer fired again,
and the mark zig-zagged 83 times. The CFTC/FIA reopen discipline in the research
brief is explicit: come back through an auction with an indicative price and an
order-balance display, "otherwise you print a second wick on the reopen".

So at the end of every trading pause, the queued liquidations (as market orders)
and the book's resting orders are uncrossed at ONE price:

  1. Maximise matched volume.
  2. Then minimise the imbalance left over.
  3. Then stay closest to the reference price.
  4. Then, for a unique answer, the lower price.

That is the standard exchange uncrossing rule. The price may not leave the
collar -- the published pre-trade price band around the Reference Composite --
because an auction that could print anywhere would just move the wick from
continuous trading into the auction. Whatever cannot match inside the collar
carries into continuous trading, which opens at the clearing price.

Pure functions only. The engine decides WHEN to call this and applies the fills.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True, slots=True)
class Uncross:
    price: float
    matched_qty: float
    demand_qty: float
    """Buy quantity willing to trade at `price`: market buys plus bids at or above it."""

    supply_qty: float
    """Sell quantity willing to trade at `price`: market sells plus asks at or below it."""

    @property
    def imbalance_qty(self) -> float:
        """Signed: positive means buyers left over, negative means sellers."""
        return self.demand_qty - self.supply_qty


def uncross(
    *,
    bids: Sequence[tuple[float, float]],
    asks: Sequence[tuple[float, float]],
    market_buy_qty: float,
    market_sell_qty: float,
    reference: float,
    collar: tuple[float, float],
) -> Uncross:
    """Find the single clearing price.

    `bids` and `asks` are resting limit orders as (price, quantity). Market
    orders carry no limit and are willing to trade at any price in the collar.
    """
    lo, hi = collar
    if lo > hi:
        raise ValueError("collar lower bound is above its upper bound")
    ref = min(max(reference, lo), hi)

    candidates = {lo, hi, ref}
    candidates.update(p for p, _ in bids if lo <= p <= hi)
    candidates.update(p for p, _ in asks if lo <= p <= hi)

    best: tuple[float, float, float, float] | None = None
    best_key: tuple[float, float, float, float] | None = None
    for price in sorted(candidates):
        demand = market_buy_qty + sum(q for p, q in bids if p >= price)
        supply = market_sell_qty + sum(q for p, q in asks if p <= price)
        matched = min(demand, supply)
        # Larger volume first, then smaller imbalance, then nearer the
        # reference, then lower price. Negated where "more" is better.
        key = (-matched, abs(demand - supply), abs(price - ref), price)
        if best_key is None or key < best_key:
            best_key = key
            best = (price, matched, demand, supply)

    assert best is not None  # the collar always contributes candidates
    price, matched, demand, supply = best
    return Uncross(price=price, matched_qty=matched, demand_qty=demand, supply_qty=supply)


def allocate(requests: Sequence[float], available: float) -> list[float]:
    """Fill market orders in queue order until `available` runs out.

    Market orders take priority over resting orders at the clearing price, and
    among themselves they fill in the engine's queue order -- deepest margin
    deficit first -- so the most endangered account is filled first and the
    allocation is deterministic.
    """
    fills: list[float] = []
    left = max(0.0, available)
    for want in requests:
        take = min(want, left)
        fills.append(take)
        left -= take
    return fills


@dataclass(frozen=True, slots=True)
class AuctionRecord:
    """One reopening auction, as the tape records it."""

    tick: int
    reason: str
    """Which pause it reopened: "velocity" or "circuit_breaker"."""

    reference: float
    collar_lo: float
    collar_hi: float
    clearing_price: float
    matched_qty: float
    matched_notional: float
    imbalance_qty: float
    """Signed at the clearing price: negative means unmatched sellers carried
    into continuous trading."""

    liquidations_queued: int
    liquidations_absorbed: int
    """Queued liquidation orders that received any fill in the auction."""

    liquidation_qty_carried: float
    """Liquidation quantity the auction could not fill inside the collar."""
