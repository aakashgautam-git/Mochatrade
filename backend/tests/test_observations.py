"""Per-source oracle observations carried in every frame.

The evidence tape a class C claim is decided from. Pure engine tests: no Django.
"""
from __future__ import annotations

import pytest

from riskengine.controls import ControlStack
from riskengine.engine import Engine
from riskengine.oracle import (
    FaultKind,
    OracleFeed,
    OracleSource,
    SourceFault,
    SourceKind,
    build_composite,
    observations,
)
from riskengine.params import DEFAULT_PARAMS as P
from riskengine.rng import Rng
from riskengine.scenario import by_key

CRYPTO = (
    OracleSource("binance_spot", SourceKind.SPOT_VENUE, 1.0, 5.0),
    OracleSource("okx_spot", SourceKind.SPOT_VENUE, 1.0, 5.0),
    OracleSource("coinbase_spot", SourceKind.SPOT_VENUE, 1.0, 5.0),
    OracleSource("hyperliquid_perp", SourceKind.PERP_VENUE, 1.0, 8.0),
    OracleSource("bybit_perp", SourceKind.PERP_VENUE, 1.0, 8.0),
)


def tape(faults, tick=10, sources=CRYPTO):
    feed = OracleFeed(sources, tuple(faults))
    rng = Rng(1)
    live = ()
    for t in range(tick + 1):
        live, _ = feed.observe(tick=t, true_price=100.0, rng=rng)
    composite = build_composite(live, P, tick=tick)
    return {o.source: o for o in observations(composite, P, tick=tick)}


def frame_at(key: str, tick: int, controls=ControlStack.none()):
    engine = Engine(by_key(key), P, controls)
    for _ in range(tick + 1):
        engine.step()
    return engine.frames[tick]


def test_every_frame_carries_one_observation_per_source() -> None:
    scenario = by_key("macro_cascade")
    result = Engine(scenario, P, ControlStack.full()).run()
    names = [s.name for s in scenario.oracle_sources]
    for frame in result.frames:
        assert [o.source for o in frame.sources] == names


def test_weight_is_zero_exactly_when_a_source_did_not_feed_the_composite() -> None:
    """Binance's staleness rule, made literal on the tape."""
    frame = frame_at("oracle_defect_hip3", 160)
    for o in frame.sources:
        assert (o.weight > 0) is o.used
        assert (o.excluded_reason == "") is o.used


def test_a_closed_market_printed_nothing() -> None:
    """At 04:00 IST the US cash market has no price. A tape that showed it
    'printing' one would mislead exactly the reader it exists for."""
    cash = {o.source: o for o in frame_at("offhours_equity_wick", 10).sources}["us_cash_market"]
    assert cash.price is None and cash.raw_price is None
    assert "closed" in cash.excluded_reason
    assert cash.weight == 0.0


def test_an_unreachable_source_is_not_described_as_closed() -> None:
    obs = tape([SourceFault("okx_spot", FaultKind.DOWN, 0, 99)])
    assert obs["okx_spot"].excluded_reason == "source unreachable"
    assert obs["okx_spot"].price is None


def test_the_clamp_is_visible_as_the_gap_between_raw_and_used() -> None:
    """Class C in one row: two L2 sources lie together, the median moves, and
    the ONE honest source is the one that gets clamped -- towards the liars."""
    adr = {o.source: o for o in frame_at("oracle_defect_hip3", 160).sources}["adr_line"]
    assert adr.used and adr.clamped
    assert adr.raw_price is not None and adr.price is not None
    assert adr.price < adr.raw_price * 0.93


def test_a_stale_source_says_how_stale_and_when_it_was_killed() -> None:
    obs = tape([SourceFault("binance_spot", FaultKind.STALE, 0, 999)], tick=400)
    b = obs["binance_spot"]
    assert b.is_stale and not b.used and b.weight == 0.0
    assert "stale" in b.excluded_reason and "300s" in b.excluded_reason


def test_losing_quorum_explains_why_the_ladder_stepped_down() -> None:
    obs = tape([
        SourceFault("binance_spot", FaultKind.DOWN, 0, 999),
        SourceFault("coinbase_spot", FaultKind.DOWN, 0, 999),
    ])
    okx = obs["okx_spot"]
    assert not okx.used
    assert "L1 short of quorum (1 of 3 live)" in okx.excluded_reason
    assert "fell to L3" in okx.excluded_reason
    assert obs["hyperliquid_perp"].used


def test_no_composite_leaves_every_source_excluded() -> None:
    obs = tape([SourceFault(s.name, FaultKind.DOWN, 0, 999) for s in CRYPTO[:4]])
    assert not any(o.used for o in obs.values())
    assert "no rung formed a composite" in obs["bybit_perp"].excluded_reason


def test_observations_serialise_into_the_frame_dict() -> None:
    frame = frame_at("oracle_defect_hip3", 5).as_dict()
    assert isinstance(frame["sources"], tuple) and len(frame["sources"]) == 6
    assert set(frame["sources"][0]) == {
        "source", "kind", "rung", "price", "raw_price", "weight",
        "is_stale", "used", "clamped", "excluded_reason",
    }
