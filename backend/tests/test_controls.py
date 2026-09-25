"""Control stack, volatility layers, and operator actions."""
from __future__ import annotations

import pytest

from riskengine.controls import (
    CONTROL_KILLS,
    CONTROL_LABELS,
    ActionKind,
    CircuitBreaker,
    ControlStack,
    MarketFlags,
    OperatorAction,
    ReopenStage,
    VelocityMonitor,
    apply_action,
)
from riskengine.params import DEFAULT_PARAMS as P


def test_stack_presets() -> None:
    assert ControlStack.none().enabled == ()
    assert len(ControlStack.full().enabled) == len(CONTROL_LABELS)
    assert all(ControlStack.full().as_dict().values())


def test_every_control_is_labelled_and_attributed() -> None:
    """Each control names the amplifier it kills. A control nobody can explain
    is a control nobody will keep."""
    names = set(ControlStack.none().as_dict())
    assert names == set(CONTROL_LABELS) == set(CONTROL_KILLS)


def test_with_only_and_without_isolate_a_single_control() -> None:
    only = ControlStack.full().with_only("liquidation_throttle")
    assert only.enabled == ("liquidation_throttle",)
    missing = ControlStack.full().without("liquidation_throttle")
    assert "liquidation_throttle" not in missing.enabled
    assert len(missing.enabled) == len(CONTROL_LABELS) - 1


def test_stack_is_frozen() -> None:
    with pytest.raises(Exception):
        ControlStack.none().oracle_anchored_mark = True  # type: ignore[misc]


# -- volatility layers -----------------------------------------------------

def test_circuit_breaker_bands_track_the_rolling_lookback() -> None:
    cb = CircuitBreaker(P, tier=1, offhours=False)
    for price in (100.0, 101.0, 99.0):
        cb.push(price)
    lower, upper = cb.bounds()  # type: ignore[misc]
    assert lower == pytest.approx(99.0 * 0.975)
    assert upper == pytest.approx(101.0 * 1.025)
    assert cb.check(96.0)
    assert not cb.check(100.0)


def test_circuit_breaker_needs_history_before_it_can_fire() -> None:
    cb = CircuitBreaker(P, tier=1, offhours=False)
    assert cb.bounds() is None
    assert not cb.check(1.0)


def test_lookback_restarts_on_resume() -> None:
    """CME's rule. Without the restart, the pre-crash high holds the band open
    forever and the breaker never re-arms."""
    cb = CircuitBreaker(P, tier=1, offhours=False)
    for price in (100.0, 100.0, 90.0):
        cb.push(price)
    cb.restart()
    assert cb.bounds() is None


def test_offhours_widens_the_band() -> None:
    rth = CircuitBreaker(P, tier=2, offhours=False)
    off = CircuitBreaker(P, tier=2, offhours=True)
    assert off.variant_pct == pytest.approx(rth.variant_pct * 1.6)


def test_velocity_fires_on_a_fast_move_inside_its_window() -> None:
    vm = VelocityMonitor(P, tier=1, offhours=False)
    assert vm.trigger_pct == pytest.approx(1.25)
    assert not vm.check(100.0)
    assert not vm.check(100.0)
    assert not vm.check(99.5)
    assert vm.check(98.0)


# -- operator actions ------------------------------------------------------

def test_protect_switch_sets_reduce_only_and_drops_leverage() -> None:
    flags = MarketFlags(max_leverage=50.0)
    note = apply_action(OperatorAction(10, ActionKind.PROTECT_SWITCH), flags, P)
    assert flags.reduce_only
    assert flags.max_leverage == P.max_leverage_degraded
    assert flags.stage is ReopenStage.REDUCE_ONLY
    assert flags.protect_switch_tick == 10
    assert "Cost accepted" in note


def test_halt_trading_is_described_as_the_nuclear_option() -> None:
    """haltTrading cancels all orders and settles at the current mark -- the
    mark under dispute. It turns a pricing dispute into a settlement dispute."""
    flags = MarketFlags()
    note = apply_action(OperatorAction(5, ActionKind.HALT_TRADING), flags, P)
    assert flags.halted and flags.stage is ReopenStage.HALTED
    assert "settlement dispute" in note


def test_staged_reopen_never_jumps_to_continuous() -> None:
    """Reopen through an auction, or you print a second wick on the reopen."""
    flags = MarketFlags(stage=ReopenStage.HALTED, halted=True, reduce_only=True)
    seen = []
    for tick in range(4):
        apply_action(OperatorAction(tick, ActionKind.STAGED_REOPEN), flags, P)
        seen.append(flags.stage)
    assert seen == [
        ReopenStage.REDUCE_ONLY,
        ReopenStage.POST_ONLY,
        ReopenStage.AUCTION,
        ReopenStage.CONTINUOUS,
    ]
    assert not flags.reduce_only and not flags.halted


def test_pause_and_resume_liquidations() -> None:
    flags = MarketFlags()
    note = apply_action(OperatorAction(1, ActionKind.PAUSE_LIQUIDATIONS), flags, P)
    assert flags.liquidations_paused
    assert "suspect" in note
    apply_action(OperatorAction(2, ActionKind.RESUME_LIQUIDATIONS), flags, P)
    assert not flags.liquidations_paused


def test_evidence_snapshot_is_recorded() -> None:
    flags = MarketFlags()
    note = apply_action(OperatorAction(3, ActionKind.SNAPSHOT_EVIDENCE), flags, P)
    assert flags.evidence_snapshot_ticks == (3,)
    assert "two years" in note


def test_timed_pauses_expire() -> None:
    flags = MarketFlags(dcb_paused_until=10, velocity_paused_until=5)
    assert flags.trading_paused
    flags.tick_expiries(6)
    assert flags.velocity_paused_until is None
    assert flags.trading_paused
    flags.tick_expiries(10)
    assert not flags.trading_paused


# -- velocity cooldown and escalation (Phase 5.5 A) ---------------------------

def _falling(start: float = 100.0, step_pct: float = 2.0):
    """A price that drops step_pct every tick: fast enough to breach any window."""
    price = start
    while True:
        yield price
        price *= 1 - step_pct / 100


def _drive(vm, prices, ticks):
    fired = []
    for tick in ticks:
        pause = vm.step(next(prices), tick)
        if pause is not None:
            fired.append(pause)
    return fired


def test_cooldown_blocks_a_refire_while_the_market_is_still_falling() -> None:
    """The stutter this fixes: 56 five-second pauses in one run, because the
    layer re-fired three seconds after every reopen."""
    params = P.evolve(velocity_cooldown_seconds=10)
    vm = VelocityMonitor(params, tier=1, offhours=False)
    fired = _drive(vm, _falling(), range(0, 17))
    assert len(fired) == 1
    first = fired[0]
    assert first.level == 0 and not first.escalated
    assert first.ticks == params.velocity_window_ticks  # the base 5s pause
    # The pause ends at first.until; no second pause before cooldown expires.
    assert vm.cooldown_until == first.until + 10


def test_still_moving_when_the_cooldown_ends_escalates_to_a_longer_pause() -> None:
    params = P.evolve(velocity_cooldown_seconds=10)
    vm = VelocityMonitor(params, tier=1, offhours=False)
    fired = _drive(vm, _falling(), range(0, 400))
    assert [p.ticks for p in fired[:4]] == [5, 20, 80, 120]  # capped at the DCB pause
    assert [p.level for p in fired[:4]] == [0, 1, 2, 3]
    assert all(p.escalated for p in fired[1:])
    # Every re-fire happens only after the previous pause AND its cooldown.
    for prev, nxt in zip(fired, fired[1:]):
        assert nxt.tick >= prev.until + 10


def test_escalation_never_outlasts_the_circuit_breaker() -> None:
    assert P.velocity_pause_ticks(0) == 5
    assert P.velocity_pause_ticks(1) == 20
    assert P.velocity_pause_ticks(2) == 80
    assert P.velocity_pause_ticks(9) == P.dcb_pause_ticks == 120


def test_a_calm_window_after_cooldown_resets_the_ladder() -> None:
    params = P.evolve(velocity_cooldown_seconds=10)
    vm = VelocityMonitor(params, tier=1, offhours=False)
    first = _drive(vm, _falling(), range(0, 3))[0]
    calm_until = first.until + 10 + params.velocity_window_ticks + 2
    flat = iter([50.0] * 1000)
    assert _drive(vm, flat, range(3, calm_until)) == []
    assert vm.level == 0
    again = _drive(vm, _falling(start=50.0), range(calm_until, calm_until + 3))
    assert again and again[0].level == 0 and again[0].ticks == 5


def test_the_window_keeps_measuring_through_a_pause() -> None:
    """A check at cooldown end must see the real recent move, not a window that
    froze when the pause began."""
    vm = VelocityMonitor(P.evolve(velocity_cooldown_seconds=0), tier=1, offhours=False)
    prices = _falling()
    fired = _drive(vm, prices, range(0, 3))
    assert fired and fired[0].until == 7
    last = None
    for tick in range(3, 7):  # inside the pause
        last = next(prices)
        assert vm.step(last, tick) is None
    assert len(vm._window) == P.velocity_window_ticks
    assert vm._window[-1] == last


def test_zero_cooldown_reproduces_the_old_behaviour_of_refiring_immediately() -> None:
    vm = VelocityMonitor(P.evolve(velocity_cooldown_seconds=0, velocity_escalation_multiplier=1.0), tier=1, offhours=False)
    fired = _drive(vm, _falling(), range(0, 40))
    assert len(fired) >= 6
    assert {p.ticks for p in fired} == {5}
