"""Order book: depth shape, slippage, liquidity withdrawal, intra-tick supply."""
from __future__ import annotations

import pytest

from riskengine.book import Book, BookParams, VolatilityTracker

LAKH = 1_00_000.0


def make_book(**kw: object) -> Book:
    params = BookParams(depth_1pct_notional=20 * LAKH, **kw)  # type: ignore[arg-type]
    return Book(params, 100.0)


def test_depth_is_normalised_to_the_one_percent_band() -> None:
    assert make_book().depth_within(1.0) == pytest.approx(20 * LAKH, rel=1e-9)


def test_depth_curve_has_a_realistic_tail() -> None:
    """Cumulative depth within 5% should be several times the 1% band. An
    over-aggressive decay makes the whole book thinner than its own top, and a
    single large sale then 'exhausts' a market that should have absorbed it."""
    book = make_book()
    one = book.depth_within(1.0)
    assert 3.5 < book.depth_within(5.0) / one < 4.5
    assert 7.0 < book.depth_within(20.0) / one < 9.0


def test_slippage_grows_with_order_size() -> None:
    book = make_book()
    small = book.walk(sell=True, notional=2 * LAKH)
    book.settle(100.0, 0.0)
    large = book.walk(sell=True, notional=20 * LAKH)
    assert small.slippage_bps < large.slippage_bps
    assert small.avg_price > large.avg_price


def test_liquidity_withdraws_under_volatility_and_heals_slowly() -> None:
    """10 Oct 2025: BTC top-of-book depth shrank by more than 90%."""
    book = make_book()
    for _ in range(60):
        book.update_liquidity(1000.0)  # a 10% move
    assert book.liquidity_frac == pytest.approx(book.params.min_liquidity_frac, abs=0.01)
    assert book.depth_pct_of_baseline() < 0.10

    stressed = book.liquidity_frac
    for _ in range(5):
        book.update_liquidity(0.0)
    healed = book.liquidity_frac
    assert healed > stressed

    fast = make_book()
    fast.liquidity_frac = 1.0
    fast.update_liquidity(1000.0)
    withdrawn_in_one_tick = 1.0 - fast.liquidity_frac
    assert withdrawn_in_one_tick > (healed - stressed)


def test_spread_widens_as_makers_step_away() -> None:
    book = make_book()
    calm = book.spread_bps
    for _ in range(60):
        book.update_liquidity(1000.0)
    assert book.spread_bps > calm * 5


def test_book_is_consumed_within_a_tick_and_replenished_on_settle() -> None:
    """Without intra-tick depletion, 800 liquidations in one tick each walk a
    pristine copy of the same book and execute many multiples of the liquidity
    that exists."""
    book = make_book()
    reachable = book.reachable_depth
    first = book.walk(sell=True, notional=reachable * 0.6)
    second = book.walk(sell=True, notional=reachable * 0.6)
    assert first.filled_notional > second.filled_notional
    assert second.exhausted
    assert first.filled_notional + second.filled_notional == pytest.approx(
        reachable, rel=1e-6
    )

    book.settle(100.0, 0.0)
    assert book.reachable_depth == pytest.approx(reachable, rel=1e-9)


def test_a_tick_cannot_reach_beyond_the_published_limit() -> None:
    book = make_book()
    assert book.reachable_depth == pytest.approx(
        book.depth_within(book.params.max_reach_pct), rel=1e-9
    )
    assert book.reachable_depth < book.depth_within(20.0)


def test_forced_flow_pushes_price_down_and_decays() -> None:
    book = make_book()
    book.apply_flow(10 * LAKH)
    book.settle(100.0, 0.0)
    pushed = book.mid
    assert pushed < 100.0
    for _ in range(40):
        book.settle(100.0, 0.0)
    assert book.mid > pushed
    assert book.mid == pytest.approx(100.0, rel=2e-3)


def test_deeper_dislocation_decays_faster() -> None:
    """Dip-buying. Without a restoring force that scales with dislocation, every
    cascade pins against the pressure ceiling and all control stacks look the
    same."""
    shallow, deep = make_book(), make_book()
    shallow.pressure_bps = 200.0
    deep.pressure_bps = 4000.0
    shallow.settle(100.0, 0.0)
    deep.settle(100.0, 0.0)
    assert (4000.0 - deep.pressure_bps) / 4000.0 > (200.0 - shallow.pressure_bps) / 200.0


def test_pressure_is_capped() -> None:
    book = make_book()
    for _ in range(50):
        book.apply_flow(500 * LAKH)
    assert book.pressure_bps <= book.params.max_pressure_bps


def test_venue_dislocation_moves_the_book_not_the_world() -> None:
    book = make_book()
    book.settle(100.0, -0.15)
    assert book.mid == pytest.approx(85.0, rel=1e-6)
    assert book.fair_value == 100.0


def test_price_bands_reject_outside_the_variant() -> None:
    """A pre-trade band is what would have stopped Binance.US printing BTC at
    $8,200 on 21 Oct 2021 from one client's algo bug."""
    book = make_book()
    assert book.check_band(98.0, reference=100.0, band_pct=2.5).accepted
    assert not book.check_band(8_200 / 66_000 * 100, reference=100.0, band_pct=2.5).accepted


def test_volatility_tracker_measures_the_move_not_its_shape() -> None:
    tracker = VolatilityTracker(window_ticks=10)
    assert tracker.realised_bps == 0.0
    for price in (100.0, 100.0, 95.0, 100.0):
        tracker.push(price)
    assert tracker.realised_bps == pytest.approx(500.0, rel=1e-6)
