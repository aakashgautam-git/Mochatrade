"""Phase 9: make-whole by the published formula, and the funding waterfall.

Trades stand. People get made whole -- by a rule published first, funded in a
published order, and capped by a published promise. Beyond the cap the payout
is pro-rata and says so.
"""
from __future__ import annotations

from functools import lru_cache

import pytest

from riskengine.classifier import classify
from riskengine.controls import ControlStack
from riskengine.engine import Engine
from riskengine.params import DEFAULT_PARAMS as P
from riskengine.remediation import Remedy, equity_at, remedies, reserve_target, waterfall
from riskengine.scenario import by_key


@lru_cache(maxsize=None)
def remedied(key: str, controls: bool):
    scenario = by_key(key)
    engine = Engine(scenario, P, ControlStack.full() if controls else ControlStack.none())
    result = engine.run()
    verdict = classify(scenario, P, result.frames, result.events, result.accounts)
    accounts = {a.id: a for a in result.accounts}
    valuations = {v.account_id: engine.valuation(accounts[v.account_id]) for v in verdict.accounts}
    return engine, result, verdict, remedies(verdict, accounts, result.events, result.frames, valuations)


def cash(amount: float, category: str = "C") -> Remedy:
    return Remedy("MT1", category, "cash", amount, 0.0, "", 0.0, amount, True)


def test_the_waterfall_draws_the_reserve_before_the_treasury() -> None:
    plan = waterfall([cash(30_00_000), cash(20_00_000)], P, reserve_available=40_00_000)
    steps = {t.step: t for t in plan.tranches}
    assert [t.step for t in plan.tranches] == [1, 2, 3, 4, 5]
    assert steps[1].drawn == 0  # nothing is assumed recovered at payout time
    assert steps[2].drawn == 40_00_000 and steps[3].drawn == 10_00_000
    assert not plan.pro_rata and plan.ratio == 1.0 and plan.shortfall == 0
    assert plan.reserve_after == 0


def test_beyond_the_cap_every_claim_is_paid_the_same_fraction() -> None:
    claims = [cash(1.2e7), cash(0.8e7)]
    plan = waterfall(claims, P, reserve_available=P.incident_reserve_opening_inr)
    assert plan.pro_rata
    assert plan.payable == pytest.approx(P.per_incident_cap_inr)
    assert plan.ratio == pytest.approx(P.per_incident_cap_inr / 2.0e7)
    assert plan.shortfall == pytest.approx(2.0e7 - P.per_incident_cap_inr)
    assert "pro-rata" in plan.tranches[4].note.lower()


def test_the_cap_is_below_the_headline_exposure() -> None:
    """The acceptance note from the parameter review: the pro-rata path must be
    reachable, and the cap is not raised to make the numbers tidy."""
    *_, items = remedied("macro_cascade", False)
    total = sum(r.make_whole for r in items if r.kind == "cash")
    assert total > P.per_incident_cap_inr
    assert waterfall(items, P, reserve_available=P.incident_reserve_opening_inr).pro_rata


def test_with_the_controls_on_the_same_crash_owes_nothing() -> None:
    *_, items = remedied("macro_cascade", True)
    assert sum(r.make_whole for r in items) == 0
    assert {r.category for r in items} == {"A"}


def test_c_and_e_restore_counterfactual_equity() -> None:
    engine, result, _, items = remedied("upi_settlement_delay", False)
    accounts = {a.id: a for a in result.accounts}
    for r in items:
        if r.category in {"C", "E"}:
            equity, counterfactual = engine.valuation(accounts[r.account_id])
            assert r.make_whole == pytest.approx(max(0.0, counterfactual - equity))
            assert r.provisional


def test_d_restores_equity_at_the_moment_of_lockout() -> None:
    engine, result, verdict, items = remedied("broker_outage", True)
    start = engine.scenario.outage.start_tick
    accounts = {a.id: a for a in result.accounts}
    fills = [e for e in result.events]
    d = [r for r in items if r.category == "D"]
    assert d
    for r in d:
        mine = [e for e in fills if e.account_id == r.account_id]
        before = equity_at(accounts[r.account_id], mine, result.frames, start)
        assert r.make_whole == pytest.approx(max(0.0, before - r.equity_now))
        assert r.reference_equity == pytest.approx(before)


def test_g_is_cash_but_waits_for_the_ic() -> None:
    *_, items = remedied("long_tail_manipulation", True)
    g = [r for r in items if r.category == "G"]
    assert g and all(r.kind == "cash" and not r.provisional for r in g)
    assert sum(r.make_whole for r in g) > 0


def test_a_b_and_f_owe_no_cash() -> None:
    *_, items = remedied("offhours_equity_wick", False)
    for r in items:
        if r.category in {"A", "B", "F"}:
            assert r.make_whole == 0 and r.kind != "cash"


def test_equity_at_the_start_is_the_account_marked_to_the_reference() -> None:
    _, result, verdict, _ = remedied("broker_outage", True)
    a = next(a for a in result.accounts if a.id == verdict.accounts[0].account_id)
    f0 = result.frames[0]
    expected = a.collateral - a.deposits_credited + int(a.side) * (a.qty + a.liquidated_qty) * (f0.reference - a.entry_price)
    assert equity_at(a, [], result.frames, 0) == pytest.approx(expected)


def test_reserve_target_is_the_published_multiple() -> None:
    assert reserve_target(1.0e7, P) == pytest.approx(P.reserve_target_multiple_of_worst_loss * 1.0e7)
