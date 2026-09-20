"""The determinism contract.

Same seed + same params + same control stack + same action sequence produces a
byte-identical frame sequence. The credibility of the whole demo rests on this:
a judge should be able to change one parameter, re-run, and know that every
difference they see was caused by that parameter and nothing else.

These tests hash the serialised output rather than spot-checking fields,
because "byte-identical" is the actual claim being made.
"""
from __future__ import annotations

import hashlib
import json

import pytest

from riskengine.controls import ActionKind, ControlStack, OperatorAction
from riskengine.engine import Engine
from riskengine.params import DEFAULT_PARAMS as P
from riskengine.scenario import by_key, library


def digest(engine: Engine) -> str:
    """A stable fingerprint of an entire run."""
    result = engine.run()
    payload = {
        "summary": result.summary.as_dict(),
        "frames": [f.as_dict() for f in result.frames],
        "events": [
            {
                "tick": e.tick,
                "account": e.account_id,
                "stage": e.stage.value,
                "qty": e.qty,
                "notional": e.notional,
                "fill": e.fill_price,
                "survived": e.survived_at_reference,
            }
            for e in result.events
        ],
        "accounts": [
            (a.id, a.qty, a.collateral, a.realised_pnl, a.state.value)
            for a in result.accounts
        ],
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


@pytest.mark.parametrize("scenario", library(), ids=lambda s: s.key)
def test_every_scenario_replays_byte_identically(scenario) -> None:
    a = digest(Engine(scenario, P, ControlStack.full()))
    b = digest(Engine(scenario, P, ControlStack.full()))
    assert a == b


def test_controls_off_also_replays_byte_identically() -> None:
    scenario = by_key("macro_cascade")
    assert digest(Engine(scenario, P, ControlStack.none())) == digest(
        Engine(scenario, P, ControlStack.none())
    )


def test_operator_actions_are_part_of_the_contract() -> None:
    scenario = by_key("macro_cascade")
    actions = (
        OperatorAction(90, ActionKind.PROTECT_SWITCH),
        OperatorAction(120, ActionKind.SNAPSHOT_EVIDENCE),
        OperatorAction(300, ActionKind.STAGED_REOPEN),
    )
    a = digest(Engine(scenario, P, ControlStack.full(), actions=actions))
    b = digest(Engine(scenario, P, ControlStack.full(), actions=actions))
    assert a == b
    assert a != digest(Engine(scenario, P, ControlStack.full()))


def test_a_different_seed_produces_a_different_run() -> None:
    scenario = by_key("macro_cascade")
    assert digest(Engine(scenario, P, ControlStack.none())) != digest(
        Engine(scenario, P, ControlStack.none(), seed=scenario.seed + 1)
    )


def test_changing_one_parameter_moves_the_result() -> None:
    """The promise made on stage: change a parameter, watch the number move.

    Measured with the throttle as the ONLY active control. With the full stack
    on, loosening the throttle can lower the liquidation count rather than raise
    it -- a faster cascade trips the circuit breaker sooner and the pause stops
    the rest -- so the full stack is the wrong place to read a single
    parameter's sign off.
    """
    scenario = by_key("macro_cascade")
    throttle_only = ControlStack.none().with_only("liquidation_throttle")
    baseline = Engine(scenario, P, throttle_only).run().summary
    loosened = (
        Engine(scenario, P.evolve(version="v-test", twap_max_participation_pct=1.0),
               throttle_only)
        .run()
        .summary
    )
    assert loosened.accounts_liquidated > baseline.accounts_liquidated
    assert loosened.trough_mark_pct < baseline.trough_mark_pct


def test_stepping_and_running_agree() -> None:
    """The REST surface steps the engine one tick at a time; the proof page runs
    it to completion. They must be the same simulation."""
    scenario = by_key("upi_settlement_delay")
    stepped = Engine(scenario, P, ControlStack.full())
    while not stepped.finished:
        stepped.step()
    whole = Engine(scenario, P, ControlStack.full())
    whole.run()
    assert [f.as_dict() for f in stepped.frames] == [f.as_dict() for f in whole.frames]


def test_sub_streams_isolate_subsystems() -> None:
    """Population draws must not shift when oracle draws change, which is what
    named sub-streams buy us."""
    scenario = by_key("macro_cascade")
    a = Engine(scenario, P, ControlStack.none())
    b = Engine(scenario, P, ControlStack.none())
    for _ in range(50):
        b.step()
    assert [(x.id, x.entry_price, x.leverage) for x in a.accounts] == [
        (y.id, y.entry_price, y.leverage) for y in b.accounts
    ]
