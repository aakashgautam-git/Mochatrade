"""Per-fill liquidation records and per-tick depth snapshots: the data Phase 6
draws the cascade split and the depth ladder from. Pure engine tests."""
from __future__ import annotations

from collections import Counter

import pytest

from riskengine.controls import ControlStack
from riskengine.engine import DEPTH_BUCKET_BPS, DEPTH_BUCKETS, Engine
from riskengine.params import DEFAULT_PARAMS as P
from riskengine.scenario import by_key, library

STAGES = {"partial", "market", "backstop", "adl"}


@pytest.fixture(scope="module")
def macro_off():
    return Engine(by_key("macro_cascade"), P, ControlStack.none()).run()


def test_every_frame_carries_a_full_depth_snapshot(macro_off) -> None:
    for f in macro_off.frames:
        assert f.depth is not None
        assert f.depth.bucket_bps == DEPTH_BUCKET_BPS
        assert len(f.depth.bids) == len(f.depth.asks) == DEPTH_BUCKETS
        assert min(f.depth.bids) >= 0 and min(f.depth.asks) >= 0


def test_a_calm_book_is_symmetric(macro_off) -> None:
    calm = macro_off.frames[10]
    assert calm.depth.bids == calm.depth.asks
    assert calm.depth.bids[0] > calm.depth.bids[-1]  # thins away from the touch


def test_forced_selling_empties_the_bid_side_not_the_ask_side(macro_off) -> None:
    """Visible only because consumption is tracked per side."""
    busiest = max(macro_off.frames, key=lambda f: len(f.liquidations))
    sells = [x for x in busiest.liquidations if x.stage != "adl"]
    assert sells
    assert sum(busiest.depth.bids) < 0.5 * sum(busiest.depth.asks)


def test_frames_record_every_fill(macro_off) -> None:
    recorded = sum(len(f.liquidations) for f in macro_off.frames)
    assert recorded == len(macro_off.events)
    assert {x.stage for f in macro_off.frames for x in f.liquidations} <= STAGES


@pytest.mark.parametrize("scenario", library(), ids=lambda s: s.key)
@pytest.mark.parametrize("controls", [ControlStack.none(), ControlStack.full()], ids=["off", "on"])
def test_the_closing_stage_is_known_for_every_liquidated_account(scenario, controls) -> None:
    """The last record with `closed` set names the stage that closed the account,
    and those accounts are exactly the ones the summary counts."""
    result = Engine(scenario, P, controls).run()
    closing: dict[str, str] = {}
    for f in result.frames:
        for x in f.liquidations:
            if x.closed:
                closing[x.account_id] = x.stage
    assert len(closing) == result.summary.accounts_liquidated
    assert set(closing.values()) <= STAGES


def test_the_cascade_split_is_derivable_per_tick(macro_off) -> None:
    by_stage = Counter()
    for f in macro_off.frames:
        for x in f.liquidations:
            by_stage[x.stage] += 1
    assert by_stage["market"] > 0 and by_stage["adl"] > 0


def test_auction_fills_are_marked_in_the_records() -> None:
    result = Engine(by_key("macro_cascade"), P, ControlStack.full()).run()
    via = [x for f in result.frames for x in f.liquidations if x.via_auction]
    auction_ticks = {f.tick for f in result.frames if f.auction}
    assert via
    assert {f.tick for f in result.frames for x in f.liquidations if x.via_auction} <= auction_ticks
