"""The reopening call auction: clearing maths on hand-built books, and the
engine never reopening a pause straight into continuous trading."""
from __future__ import annotations

import pytest

from riskengine.auction import allocate, uncross
from riskengine.controls import ControlStack
from riskengine.engine import Engine
from riskengine.params import DEFAULT_PARAMS as P
from riskengine.scenario import by_key

BIDS = [(99.0, 10.0), (98.0, 10.0), (97.0, 10.0)]
ASKS = [(101.0, 10.0), (102.0, 10.0)]
WIDE = (90.0, 110.0)


def test_sells_clear_at_the_highest_price_the_bids_can_cover() -> None:
    """25 to sell into 10 at 99, 10 at 98, 10 at 97. Every price at or below 97
    matches all 25; 97 leaves the smallest surplus and is nearest the reference."""
    u = uncross(bids=BIDS, asks=ASKS, market_buy_qty=0, market_sell_qty=25, reference=100, collar=WIDE)
    assert u.price == 97.0
    assert u.matched_qty == 25.0
    assert u.imbalance_qty == 5.0  # 30 bid at 97, 25 sold: buyers left over


def test_the_collar_stops_the_price_and_carries_the_rest() -> None:
    """The collar is the published price band. At its floor only 20 can match;
    5 unmatched sellers carry into continuous trading."""
    u = uncross(bids=BIDS, asks=ASKS, market_buy_qty=0, market_sell_qty=25, reference=100, collar=(98.0, 102.0))
    assert u.price == 98.0
    assert u.matched_qty == 20.0
    assert u.imbalance_qty == -5.0


def test_opposing_liquidations_cross_each_other_at_the_reference() -> None:
    """Continuous trading cannot net a long liquidation against a short one; each
    walks its own side of the book. The auction matches them directly."""
    u = uncross(bids=BIDS, asks=ASKS, market_buy_qty=8, market_sell_qty=8, reference=100, collar=WIDE)
    assert u.price == 100.0
    assert u.matched_qty == 8.0
    assert u.imbalance_qty == 0.0


def test_volume_beats_proximity_to_the_reference() -> None:
    """Rule one is maximum matched volume, even if a nearer price exists."""
    u = uncross(bids=[(99.5, 1.0), (95.0, 50.0)], asks=[], market_buy_qty=0, market_sell_qty=40, reference=100, collar=WIDE)
    assert u.matched_qty == 40.0
    assert u.price == 95.0


def test_imbalance_breaks_a_volume_tie() -> None:
    """Both 99 and 98 match 10; 99 leaves 0 surplus, 98 leaves 10."""
    u = uncross(bids=[(99.0, 10.0), (98.0, 10.0)], asks=[], market_buy_qty=0, market_sell_qty=10, reference=95, collar=WIDE)
    assert u.price == 99.0
    assert u.imbalance_qty == 0.0


def test_nothing_to_cross_prints_no_volume() -> None:
    u = uncross(bids=BIDS, asks=ASKS, market_buy_qty=0, market_sell_qty=0, reference=100, collar=WIDE)
    assert u.matched_qty == 0.0


def test_an_inverted_collar_is_rejected() -> None:
    with pytest.raises(ValueError):
        uncross(bids=BIDS, asks=ASKS, market_buy_qty=0, market_sell_qty=1, reference=100, collar=(105.0, 95.0))


def test_market_orders_fill_in_queue_order() -> None:
    """Deepest margin deficit first, so the most endangered account is filled."""
    assert allocate([5.0, 5.0, 5.0], 12.0) == [5.0, 5.0, 2.0]
    assert allocate([5.0, 5.0], 0.0) == [0.0, 0.0]


# -- the engine ---------------------------------------------------------------

def _protected_macro():
    return Engine(by_key("macro_cascade"), P, ControlStack.full()).run()


def test_every_reopen_goes_through_an_auction() -> None:
    frames = _protected_macro().frames
    reopens = [f.tick for prev, f in zip(frames, frames[1:]) if prev.trading_paused and not f.trading_paused]
    auctions = [f.tick for f in frames if f.auction is not None]
    assert reopens and reopens == auctions


def test_auction_fills_share_one_price_inside_the_collar() -> None:
    result = _protected_macro()
    by_tick = {f.tick: f.auction for f in result.frames if f.auction}
    fills = [e for e in result.events if e.via_auction]
    assert fills
    for e in fills:
        a = by_tick[e.tick]
        assert e.fill_price == a.clearing_price
        assert a.collar_lo <= a.clearing_price <= a.collar_hi


def _auction(throttle: bool):
    """One queue of 40 underwater longs, one book, auctioned once."""
    from riskengine.book import Book, BookParams
    from riskengine.liquidation import Account, LiquidationEngine, LiquidationOutcome, Side

    accounts = [
        Account(id=f"MT{i:05d}", side=Side.LONG, qty=2000.0, entry_price=1000.0,
                leverage=20.0, collateral=1_00_000.0)
        for i in range(40)
    ]
    book = Book(BookParams(depth_1pct_notional=10_00_000.0), 940.0)
    engine = LiquidationEngine(P, insurance_balance=1e12)
    budget = engine._tick_budget(book, 940.0, True)
    record = engine.run_auction(
        list(accounts), book=book, mark=940.0, reference=940.0,
        collar_reference=940.0, collar_pct=4.0, tick=0, reason="velocity",
        two_stage_enabled=False, throttle_enabled=throttle,
        all_accounts=accounts, outcome=LiquidationOutcome(),
    )
    return record, budget


def test_the_auction_respects_the_throttle() -> None:
    """Without the cap the whole queue entered at once and max-volume uncrossing
    walked it to the collar floor -- the auction printed the wick itself."""
    capped, budget = _auction(throttle=True)
    open_, _ = _auction(throttle=False)
    assert capped.matched_notional <= budget * 1.001
    assert open_.matched_notional > capped.matched_notional
    assert capped.clearing_price > open_.clearing_price
    assert open_.clearing_price == pytest.approx(open_.collar_lo, rel=1e-3)
    assert capped.liquidations_queued < open_.liquidations_queued


def test_the_protected_run_no_longer_stutters() -> None:
    """56 pauses and 83 swings before the cooldown and the auction."""
    frames = _protected_macro().frames
    pauses = sum(1 for prev, f in zip(frames, frames[1:]) if f.trading_paused and not prev.trading_paused)
    assert pauses <= 12


def test_controls_off_never_pauses_so_never_auctions() -> None:
    result = Engine(by_key("macro_cascade"), P, ControlStack.none()).run()
    assert result.summary.auctions == 0
    assert not any(e.via_auction for e in result.events)
