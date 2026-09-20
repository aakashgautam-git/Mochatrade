"""Reference Composite: the ladder, the clamp, the staleness kill, and health."""
from __future__ import annotations

import pytest

from riskengine.oracle import (
    FaultKind,
    OracleFeed,
    OracleHealth,
    OracleSource,
    SourceFault,
    SourceKind,
    build_composite,
)
from riskengine.params import DEFAULT_PARAMS as P
from riskengine.rng import Rng

CRYPTO = (
    OracleSource("binance", SourceKind.SPOT_VENUE, 1.0, 5.0, is_major=True),
    OracleSource("okx", SourceKind.SPOT_VENUE, 1.0, 5.0, is_major=True),
    OracleSource("coinbase", SourceKind.SPOT_VENUE, 1.0, 5.0, is_major=True),
    OracleSource("hl_perp", SourceKind.PERP_VENUE, 1.0, 8.0),
    OracleSource("bybit_perp", SourceKind.PERP_VENUE, 1.0, 8.0),
)
EQUITY = (
    OracleSource("us_cash_market", SourceKind.CASH_MARKET, 2.0, 3.0),
    OracleSource("es_future", SourceKind.INDEX_FUTURE, 1.0, 8.0),
    OracleSource("etf_nav_proxy", SourceKind.ETF_NAV, 0.7, 10.0),
    OracleSource("trade_xyz_perp", SourceKind.PERP_VENUE, 1.0, 12.0),
    OracleSource("ostium_perp", SourceKind.PERP_VENUE, 0.6, 15.0),
)


def observe(sources, faults, tick=10, true_price=100.0, expected_rung=1, majors=False):
    feed = OracleFeed(sources, tuple(faults))
    rng = Rng(1)
    live = ref = ()
    for t in range(tick + 1):
        live, ref = feed.observe(tick=t, true_price=true_price, rng=rng)
    return (
        build_composite(live, P, tick=tick, majors=majors, expected_rung=expected_rung),
        build_composite(ref, P, tick=tick, majors=majors, expected_rung=expected_rung),
    )


def test_clean_feed_is_healthy_and_accurate() -> None:
    live, _ = observe(CRYPTO, [])
    assert live.rung == 1
    assert live.health is OracleHealth.HEALTHY
    assert live.price == pytest.approx(100.0, rel=2e-3)


def test_single_liar_is_clamped_and_flags_suspect() -> None:
    """Binance's outlier clamp: a source deviating beyond the clamp is capped at
    (1 +/- clamp) x median."""
    live, _ = observe(CRYPTO, [SourceFault("okx", FaultKind.DEVIATE, 0, 99, -20.0)])
    assert live.health is OracleHealth.SUSPECT
    assert any(r.clamped for r in live.readings)
    assert live.price == pytest.approx(99.0, rel=0.02)


def test_clamp_cannot_survive_a_poisoned_median() -> None:
    """Two sources lying together move the median itself, and the clamp then
    defends the wrong number. This is the 10 Oct 2025 lesson: Binance had this
    formula and still got hit, because the failure was never in the formula."""
    live, ref = observe(
        CRYPTO,
        [
            SourceFault("okx", FaultKind.DEVIATE, 0, 99, -10.0),
            SourceFault("coinbase", FaultKind.DEVIATE, 0, 99, -10.0),
        ],
    )
    assert live.price is not None and ref.price is not None
    assert live.price < ref.price * 0.94


def test_stale_source_is_believed_inside_the_window_then_killed() -> None:
    """Binance's staleness rule is five minutes. Inside it, a frozen source is
    still trusted -- that blind spot is real and hiding it would flatter us."""
    inside, _ = observe(CRYPTO, [SourceFault("binance", FaultKind.STALE, 0, 999)], tick=60)
    assert not [r for r in inside.readings if r.name == "binance"][0].stale

    outside, _ = observe(
        CRYPTO, [SourceFault("binance", FaultKind.STALE, 0, 999)], tick=400
    )
    frozen = [r for r in outside.readings if r.name == "binance"][0]
    assert frozen.stale and not frozen.used


def test_losing_quorum_steps_the_ladder_down_rather_than_trusting_a_survivor() -> None:
    """The quorum is the real defence against one surviving liar setting the
    price for everyone."""
    live, _ = observe(
        CRYPTO,
        [
            SourceFault("binance", FaultKind.DOWN, 0, 999),
            SourceFault("coinbase", FaultKind.DOWN, 0, 999),
            SourceFault("okx", FaultKind.DEVIATE, 0, 999, -30.0),
        ],
    )
    assert live.rung == 3
    assert live.price == pytest.approx(100.0, rel=0.02)


def test_equity_l1_is_the_cash_market_alone() -> None:
    """The brief defines L1 as '>=3 major spot venues (crypto) OR the US cash
    market (equities, RTH)'. One authoritative venue, not three."""
    live, _ = observe(EQUITY, [])
    assert live.rung == 1
    assert live.health is OracleHealth.HEALTHY


def test_closed_cash_market_degrades_to_l2_without_crying_wolf() -> None:
    """An equity perp at 04:00 IST is SUPPOSED to be on L2 and that is published
    in advance. Flagging it SUSPECT would latch the health monitor on for the
    whole Indian trading day and pause liquidations permanently."""
    live, _ = observe(
        EQUITY,
        [SourceFault("us_cash_market", FaultKind.CLOSED, 0, 999)],
        expected_rung=2,
    )
    assert live.rung == 2
    assert live.health is OracleHealth.SOURCES_DEGRADED

    unexpected, _ = observe(
        EQUITY,
        [SourceFault("us_cash_market", FaultKind.CLOSED, 0, 999)],
        expected_rung=1,
    )
    assert unexpected.health is OracleHealth.SUSPECT


def test_no_quorum_anywhere_forces_degraded() -> None:
    """Ladder L4: max leverage 3x, reduce-only, liquidations paused."""
    live, _ = observe(CRYPTO, [SourceFault(s.name, FaultKind.DOWN, 0, 999) for s in CRYPTO])
    assert live.rung == 4
    assert live.price is None
    assert live.health is OracleHealth.NO_COMPOSITE
    assert live.degraded


def test_reference_tape_reconstructs_the_honest_price() -> None:
    """The reference composite is what a post-incident investigation rebuilds,
    and what a class C make-whole is computed at. Our defects are excluded from
    it; a genuinely closed market is not."""
    live, ref = observe(
        CRYPTO,
        [
            SourceFault("okx", FaultKind.DEVIATE, 0, 99, -25.0),
            SourceFault("coinbase", FaultKind.DEVIATE, 0, 99, -25.0),
        ],
    )
    assert ref.price == pytest.approx(100.0, rel=2e-3)
    assert live.price is not None and live.price < ref.price


def test_majors_get_the_tighter_clamp() -> None:
    loose, _ = observe(CRYPTO, [SourceFault("okx", FaultKind.DEVIATE, 0, 99, 8.0)], majors=False)
    tight, _ = observe(CRYPTO, [SourceFault("okx", FaultKind.DEVIATE, 0, 99, 8.0)], majors=True)
    assert loose.price is not None and tight.price is not None
    assert tight.price < loose.price


def test_every_reading_is_kept_for_the_evidence_tape() -> None:
    """Point 3 of 'what would make me stay as a user': the raw tape, so I can
    check your story myself."""
    live, _ = observe(CRYPTO, [SourceFault("okx", FaultKind.DOWN, 0, 999)])
    assert len(live.readings) == len(CRYPTO)
    assert {r.name for r in live.readings} == {s.name for s in CRYPTO}
    assert sum(1 for r in live.readings if r.used) == live.n_used
