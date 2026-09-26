"""Integration: the tick loop, the cascade, and the controls-off-vs-on proof."""
from __future__ import annotations

import pytest

from riskengine.controls import ActionKind, ControlStack, OperatorAction
from riskengine.engine import Engine
from riskengine.liquidation import AccountState
from riskengine.oracle import OracleHealth
from riskengine.params import DEFAULT_PARAMS as P
from riskengine.scenario import by_key, library


def run(key: str, controls: ControlStack, **kw):
    return Engine(by_key(key), P, controls, **kw).run()


# -- the loop --------------------------------------------------------------

def test_engine_emits_one_frame_per_tick() -> None:
    scenario = by_key("macro_cascade")
    result = run("macro_cascade", ControlStack.full())
    assert len(result.frames) == scenario.n_ticks
    assert [f.tick for f in result.frames] == list(range(scenario.n_ticks))


def test_stepping_past_the_end_is_a_no_op() -> None:
    engine = Engine(by_key("macro_cascade"), P, ControlStack.full())
    engine.run()
    last = engine.frames[-1]
    assert engine.step() is last
    assert len(engine.frames) == by_key("macro_cascade").n_ticks


def test_calm_period_liquidates_nobody() -> None:
    """If the pre-crash period liquidates accounts, the cascade is igniting on
    noise and every later number is meaningless."""
    result = run("macro_cascade", ControlStack.none())
    pre = by_key("macro_cascade").shock.pre_ticks
    assert all(f.cum_liquidated_accounts == 0 for f in result.frames[:pre])


def test_cascade_grinds_rather_than_detonating() -> None:
    """A real cascade works through the book over time. If it completes in two
    or three ticks, the book is being walked from scratch by every order and
    every throttle looks pointless."""
    result = run("macro_cascade", ControlStack.none())
    active = [f.tick for f in result.frames if f.liquidated_notional_this_tick > 0]
    assert len(active) > 60
    assert max(active) - min(active) > 100


# -- the proof -------------------------------------------------------------

@pytest.mark.parametrize("scenario", library(), ids=lambda s: s.key)
def test_controls_reduce_damage_in_every_scenario(scenario) -> None:
    """The whole claim of the project, asserted once per scenario."""
    off = Engine(scenario, P, ControlStack.none()).run().summary
    on = Engine(scenario, P, ControlStack.full()).run().summary
    assert on.accounts_liquidated < off.accounts_liquidated
    assert on.unnecessary_liquidations <= off.unnecessary_liquidations
    assert on.adl_accounts <= off.adl_accounts
    assert on.user_loss < off.user_loss


def test_controls_do_not_abolish_loss_in_a_genuine_crash() -> None:
    """A 14.5% move with real leverage should still hurt. A stack that makes
    everyone whole has been rigged, and a judge will say so."""
    on = run("macro_cascade", ControlStack.full()).summary
    assert on.user_loss > 0
    assert on.accounts_liquidated > 0
    assert on.user_loss / on.user_equity_start > 0.05


def test_ltp_marking_is_the_single_largest_avoidable_harm() -> None:
    """Amplifier 3. Under LTP the venue-local wick liquidates accounts that were
    solvent against the composite; under median marking it has to convince two
    of three inputs."""
    ltp = run("offhours_equity_wick", ControlStack.none()).summary
    anchored = run(
        "offhours_equity_wick", ControlStack.none().with_only("oracle_anchored_mark")
    ).summary
    assert abs(anchored.max_divergence_bps) < abs(ltp.max_divergence_bps)


def test_throttle_shrinks_the_trough() -> None:
    """BitMEX, March 2020: the engine was the largest seller, and the price
    recovered the moment it stopped."""
    off = run("macro_cascade", ControlStack.none()).summary
    throttled = run(
        "macro_cascade", ControlStack.none().with_only("liquidation_throttle")
    ).summary
    assert throttled.trough_mark_pct > off.trough_mark_pct
    assert throttled.accounts_liquidated < off.accounts_liquidated


def test_attributable_loss_is_the_harm_we_caused() -> None:
    """user_loss minus the loss the honest price would have produced anyway.
    Positive in a cascade, and smaller once the controls are on."""
    off = run("macro_cascade", ControlStack.none()).summary
    on = run("macro_cascade", ControlStack.full()).summary
    assert off.attributable_loss > 0
    assert on.attributable_loss < off.attributable_loss


# -- per-layer behaviour ---------------------------------------------------

def test_oracle_defect_is_detected_and_pauses_liquidations() -> None:
    """Control #2. The trigger is feed health, never user pain."""
    result = run("oracle_defect_hip3", ControlStack.full())
    assert any(f.oracle_health == OracleHealth.SUSPECT.value for f in result.frames)
    assert any(f.liquidations_paused for f in result.frames)
    assert any("Oracle health monitor fired" in line for line in result.log)


def test_healthy_oracle_never_pauses_liquidations() -> None:
    """Pausing liquidations on a healthy feed does not save users; it converts
    their losses into our insolvency."""
    result = run("macro_cascade", ControlStack.full())
    assert not any(f.liquidations_paused for f in result.frames)


def test_outage_makes_the_grace_window_worthless() -> None:
    """Class D. The market did not break; we did."""
    reachable = run("broker_outage", ControlStack.full()).summary
    scenario = by_key("broker_outage")
    assert scenario.outage is not None
    assert scenario.outage.duration_ticks >= 300  # a reportable glitch
    assert reachable.accounts_liquidated > 0


def test_upi_prefunded_credit_saves_accounts_the_late_settlement_would_not() -> None:
    """Class E. The most India-specific control in the brief.

    Measured on what the control is FOR: accounts liquidated while their UPI
    deposit was still in flight, and measured alone. Last into the full stack
    it adds nothing on this seed: the velocity and breaker pauses already hold
    the cascade until the deposits land. That used to look otherwise only
    because switching the isolated-margin default reshuffled the population,
    so the two runs compared different books. The Simulator shows both views.
    The total must not get worse.
    """
    scenario = by_key("upi_settlement_delay")

    def in_flight_losses(controls: ControlStack):
        result = Engine(scenario, P, controls).run()
        hit = [
            a for a in result.accounts
            if a.upi_deposit_inr > 0 and not a.open
            and a.liquidated_tick is not None and a.liquidated_tick < (a.upi_settles_tick or 0)
        ]
        return result.summary, len(hit)

    with_credit, e_with = in_flight_losses(ControlStack.none().with_only("upi_prefunded_credit"))
    without, e_without = in_flight_losses(ControlStack.none())
    assert with_credit.upi_credits_issued > 0
    assert without.upi_credits_issued == 0
    assert e_with < e_without
    assert with_credit.accounts_liquidated <= without.accounts_liquidated
    _, e_full = in_flight_losses(ControlStack.full())
    assert e_full <= e_with


def test_time_of_day_cap_applies_to_equity_perps_only() -> None:
    """Crypto trades 24/7 and has no off-hours, so the cap must not be credited
    with damage reduction there."""
    crypto_on = Engine(by_key("macro_cascade"), P,
                       ControlStack.none().with_only("time_of_day_leverage_caps"))
    crypto_off = Engine(by_key("macro_cascade"), P, ControlStack.none())
    assert crypto_on.open_interest_start == pytest.approx(
        crypto_off.open_interest_start, rel=1e-9
    )

    equity_on = Engine(by_key("offhours_equity_wick"), P,
                       ControlStack.none().with_only("time_of_day_leverage_caps"))
    equity_off = Engine(by_key("offhours_equity_wick"), P, ControlStack.none())
    assert equity_on.open_interest_start < equity_off.open_interest_start * 0.8


# -- operator actions ------------------------------------------------------

def test_protect_switch_changes_the_outcome() -> None:
    """The war room has to matter: an operator decision must move the number."""
    base = run("macro_cascade", ControlStack.none()).summary
    protected = run(
        "macro_cascade",
        ControlStack.none(),
        actions=(OperatorAction(70, ActionKind.PROTECT_SWITCH),),
    ).summary
    assert protected.accounts_liquidated < base.accounts_liquidated


def test_halt_trading_settles_the_whole_book_at_the_disputed_mark() -> None:
    """The nuclear option, behaving nuclearly. It cancels all orders and settles
    every position at the current mark -- turning a pricing dispute into a
    settlement dispute for everyone at once."""
    result = run(
        "oracle_defect_hip3",
        ControlStack.full(),
        actions=(OperatorAction(200, ActionKind.HALT_TRADING),),
    )
    assert all(not a.open for a in result.accounts)
    assert any(a.state is AccountState.CLOSED for a in result.accounts)
    assert any("Nobody chose that price" in line for line in result.log)


def test_evidence_snapshot_is_captured_on_command() -> None:
    result = run(
        "macro_cascade",
        ControlStack.full(),
        actions=(OperatorAction(100, ActionKind.SNAPSHOT_EVIDENCE),),
    )
    assert any("Write-once snapshot" in line for line in result.log)


# -- output shape ----------------------------------------------------------

def test_frames_and_summary_are_json_ready() -> None:
    """Phase 2 serialises these straight through DRF."""
    import json

    result = run("upi_settlement_delay", ControlStack.full())
    json.dumps([f.as_dict() for f in result.frames])
    json.dumps(result.summary.as_dict())


def test_summary_reports_the_book_it_started_with() -> None:
    result = run("macro_cascade", ControlStack.full())
    assert result.summary.accounts_total == 1200
    assert result.summary.open_interest_start > 0
    assert result.summary.user_equity_start > 0
