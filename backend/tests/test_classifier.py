"""Phase 8: the Abnormal Price Event test and the A-G root-cause classes.

The scenario library states the class each crisis is built to produce. The
classifier never reads that field; it reads the tape. These tests hold the two
to agreement, and hold every per-account verdict to the published rules.
"""
from __future__ import annotations

from functools import lru_cache

import pytest

from riskengine.classifier import CATEGORIES, classify
from riskengine.controls import ControlStack
from riskengine.engine import Engine
from riskengine.liquidation import LiquidationStage
from riskengine.params import DEFAULT_PARAMS as P
from riskengine.scenario import by_key, library


@lru_cache(maxsize=None)
def run(key: str, controls: bool):
    scenario = by_key(key)
    engine = Engine(scenario, P, ControlStack.full() if controls else ControlStack.none())
    result = engine.run()
    return scenario, result, classify(scenario, P, result.frames, result.events, result.accounts)


@pytest.mark.parametrize("scenario", library(), ids=lambda s: s.key)
def test_the_tape_agrees_with_the_class_each_scenario_is_built_to_produce(scenario) -> None:
    """With MochaTrade's controls on -- the proposal -- every crisis in the
    library classifies as designed, from the tape alone."""
    _, _, verdict = run(scenario.key, True)
    assert verdict.category == scenario.expected_class, verdict.headline
    assert verdict.evidence and verdict.headline
    assert not verdict.provisional


def test_the_oracle_anchored_mark_moves_the_liability() -> None:
    """The same off-hours wick is market structure (B) when the mark tracks the
    composite, and our liability (C) when the market marks on the last trade."""
    _, _, on = run("offhours_equity_wick", True)
    _, _, off = run("offhours_equity_wick", False)
    assert on.category == "B" and on.counts["C"] == 0
    assert off.category == "C"
    assert all(v.mark_source == "ltp" for v in off.accounts if v.category == "C")


def test_every_account_carries_its_working() -> None:
    _, _, verdict = run("oracle_defect_hip3", False)
    assert verdict.accounts
    for v in verdict.accounts:
        assert v.category in CATEGORIES
        assert v.reason
        assert set(v.criteria) == {"deviation", "reversion", "survival"}
        assert v.nrr_bps == verdict.nrr_bps
    assert sum(verdict.counts.values()) == len(verdict.accounts)


def test_ape_means_all_three_criteria_and_nothing_less() -> None:
    _, _, verdict = run("macro_cascade", False)
    for v in verdict.accounts:
        passed = [v.criteria[k]["passed"] for k in ("deviation", "reversion", "survival")]
        assert v.ape == all(p is True for p in passed)
        if v.category == "A":
            assert not v.ape
        if v.category in {"B", "C"}:
            assert v.ape


def test_a_class_a_reason_names_the_criterion_that_failed() -> None:
    _, _, verdict = run("macro_cascade", True)
    reasons = {v.reason.split(":")[0] for v in verdict.accounts if v.category == "A"}
    assert reasons <= {
        "Inside the Non-Reviewable Range", "Not a wick", "Pending",
        "The move itself closed this account",
    }


def test_adl_is_the_venue_class() -> None:
    _, result, verdict = run("offhours_equity_wick", False)
    adl = {e.account_id for e in result.events if e.stage is LiquidationStage.ADL}
    assert adl
    assert {v.account_id for v in verdict.accounts if v.category == "F"} == adl


def test_class_d_is_a_locked_out_user_closed_inside_our_outage() -> None:
    scenario, result, verdict = run("broker_outage", True)
    accounts = {a.id: a for a in result.accounts}
    d = [v for v in verdict.accounts if v.category == "D"]
    assert d
    for v in d:
        assert accounts[v.account_id].affected_by_outage
        assert scenario.outage.active(v.first_tick)
    # Somebody closed before the outage began is not the outage's fault.
    early = [v for v in verdict.accounts if v.first_tick < scenario.outage.start_tick]
    assert early and all(v.category != "D" for v in early)


def test_class_e_is_a_deposit_sent_before_the_close_and_settled_after() -> None:
    _, result, verdict = run("upi_settlement_delay", False)
    accounts = {a.id: a for a in result.accounts}
    e = [v for v in verdict.accounts if v.category == "E"]
    assert e
    for v in e:
        a = accounts[v.account_id]
        assert a.upi_initiated_tick <= v.first_tick < a.upi_settles_tick


def test_class_g_is_the_side_the_push_hurt() -> None:
    _, _, verdict = run("long_tail_manipulation", True)
    push = verdict.signals["push"]
    assert push and push["direction"] == 1 and len(push["sources"]) >= 2
    g = [v for v in verdict.accounts if v.category == "G"]
    assert g and all(v.side == "SHORT" for v in g)
    assert verdict.signals["composite_defect"] is None


def test_an_oracle_defect_is_ours_even_when_the_monitor_saved_everyone() -> None:
    _, _, verdict = run("oracle_defect_hip3", True)
    assert verdict.category == "C" and not verdict.accounts
    defect = verdict.signals["composite_defect"]
    assert defect and set(defect["sources"]) >= {"es_future", "etf_nav_proxy"}


def test_a_verdict_mid_event_is_provisional() -> None:
    scenario = by_key("macro_cascade")
    engine = Engine(scenario, P, ControlStack.none())
    for _ in range(200):
        engine.step()
    verdict = classify(scenario, P, engine.frames, engine.events, engine.accounts, finished=False)
    assert verdict.provisional and verdict.at_tick == 199
    recent = [v for v in verdict.accounts if v.tick > 199 - P.ape_reversion_ticks]
    assert any(v.criteria["reversion"]["passed"] is None for v in recent)


def test_classification_is_deterministic() -> None:
    scenario = by_key("upi_settlement_delay")
    a = Engine(scenario, P, ControlStack.none()).run()
    b = Engine(scenario, P, ControlStack.none()).run()
    first = classify(scenario, P, a.frames, a.events, a.accounts).as_dict()
    second = classify(scenario, P, b.frames, b.events, b.accounts).as_dict()
    assert first == second
