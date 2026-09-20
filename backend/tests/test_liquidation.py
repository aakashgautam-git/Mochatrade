"""Margin arithmetic, the two-stage path, the throttle, the grace window, ADL."""
from __future__ import annotations

import pytest

from riskengine.book import Book, BookParams
from riskengine.liquidation import (
    Account,
    AccountState,
    LiquidationEngine,
    LiquidationOutcome,
    LiquidationStage,
    Side,
)
from riskengine.params import DEFAULT_PARAMS as P

LAKH = 1_00_000.0
CRORE = 1_00_00_000.0


def account(**kw: object) -> Account:
    base = dict(
        id="MT00001",
        side=Side.LONG,
        qty=100.0,
        entry_price=1000.0,
        leverage=20.0,
        collateral=5_000.0,
    )
    base.update(kw)
    return Account(**base)  # type: ignore[arg-type]


def engine(vault: float = 1 * CRORE) -> LiquidationEngine:
    return LiquidationEngine(P, insurance_balance=vault)


def book(depth: float = 50 * LAKH) -> Book:
    return Book(BookParams(depth_1pct_notional=depth), 1000.0)


# -- margin arithmetic -----------------------------------------------------

def test_equity_and_maintenance_margin() -> None:
    a = account()
    assert a.notional(1000.0) == 1_00_000.0
    assert a.mm_required(1000.0, P) == pytest.approx(1_000.0)  # tier 1, 1%
    assert a.equity(1000.0) == 5_000.0
    assert a.equity(980.0) == 3_000.0


def test_bankruptcy_price_is_where_equity_reaches_zero() -> None:
    a = account()
    assert a.bankruptcy_price() == pytest.approx(950.0)
    assert a.equity(a.bankruptcy_price()) == pytest.approx(0.0, abs=1e-9)


def test_short_bankruptcy_is_above_entry() -> None:
    a = account(side=Side.SHORT)
    assert a.bankruptcy_price() == pytest.approx(1050.0)
    assert a.equity(1050.0) == pytest.approx(0.0, abs=1e-9)


def test_effective_leverage_blows_up_as_equity_drains() -> None:
    a = account()
    assert a.effective_leverage(1000.0) == pytest.approx(20.0)
    assert a.effective_leverage(980.0) > 30.0


# -- the grace window ------------------------------------------------------

def test_grace_window_defers_liquidation_by_the_published_period() -> None:
    a = account()
    eng = engine()
    out = LiquidationOutcome()
    due = eng.evaluate([a], mark=959.0, tick=0, grace_enabled=True,
                       upi_credit_enabled=False, outcome=out)
    assert due == []
    assert a.state is AccountState.MARGIN_CALL
    assert out.margin_calls_opened == 1

    still = eng.evaluate([a], mark=959.0, tick=P.margin_grace_ticks - 1,
                         grace_enabled=True, upi_credit_enabled=False,
                         outcome=LiquidationOutcome())
    assert still == []

    now = eng.evaluate([a], mark=959.0, tick=P.margin_grace_ticks,
                       grace_enabled=True, upi_credit_enabled=False,
                       outcome=LiquidationOutcome())
    assert now == [a]


def test_grace_is_worthless_to_a_user_who_cannot_reach_us() -> None:
    """An outage does not change the market; it changes whether the user can do
    anything about it. That is the whole class D harm."""
    a = account(reachable=False)
    due = engine().evaluate([a], mark=959.0, tick=0, grace_enabled=True,
                            upi_credit_enabled=False, outcome=LiquidationOutcome())
    assert due == [a]


def test_grace_does_not_apply_below_the_backstop_threshold() -> None:
    """Past two-thirds of maintenance margin there is no time left to give."""
    a = account()
    mark = 950.5
    assert a.equity(mark) < P.backstop_threshold(a.mm_required(mark, P))
    due = engine().evaluate([a], mark=mark, tick=0, grace_enabled=True,
                            upi_credit_enabled=False, outcome=LiquidationOutcome())
    assert due == [a]


def test_account_recovers_and_the_margin_call_clears() -> None:
    a = account()
    eng = engine()
    eng.evaluate([a], mark=959.0, tick=0, grace_enabled=True,
                 upi_credit_enabled=False, outcome=LiquidationOutcome())
    assert a.state is AccountState.MARGIN_CALL
    out = LiquidationOutcome()
    eng.evaluate([a], mark=1000.0, tick=10, grace_enabled=True,
                 upi_credit_enabled=False, outcome=out)
    assert a.state is AccountState.HEALTHY
    assert out.saved_by_grace == 1


# -- UPI ------------------------------------------------------------------

def test_prefunded_upi_credit_is_capped_and_saves_the_account() -> None:
    """The most India-specific control in the brief: without it, avoiding
    liquidation depends on an NPCI leg settling."""
    a = account(upi_deposit_inr=5_00_000.0, upi_initiated_tick=0)
    out = LiquidationOutcome()
    engine().evaluate([a], mark=959.0, tick=0, grace_enabled=False,
                      upi_credit_enabled=True, outcome=out)
    assert a.collateral == 5_000.0 + P.upi_prefunded_credit_cap_inr
    assert out.upi_credits_issued == 1


def test_late_upi_settlement_arrives_after_the_liquidation() -> None:
    """Class E, exactly: the deposit was initiated before and settled after."""
    a = account(upi_deposit_inr=20_000.0, upi_settles_tick=300)
    eng = engine()
    eng.settle_upi_deposits([a], 100)
    assert a.collateral == 5_000.0
    eng.settle_upi_deposits([a], 300)
    assert a.collateral == 25_000.0


def test_the_credit_is_an_advance_not_a_substitute() -> None:
    """The deposit still lands; settlement pays the remainder. Treating the
    capped credit as a replacement leaves a user with a large deposit WORSE off
    for having the control switched on."""
    a = account(upi_deposit_inr=2_00_000.0, upi_initiated_tick=0, upi_settles_tick=300)
    eng = engine()
    eng.evaluate([a], mark=959.0, tick=0, grace_enabled=False,
                 upi_credit_enabled=True, outcome=LiquidationOutcome())
    assert a.collateral == 5_000.0 + P.upi_prefunded_credit_cap_inr
    eng.settle_upi_deposits([a], 300)
    assert a.collateral == pytest.approx(5_000.0 + 2_00_000.0)


# -- two-stage -------------------------------------------------------------

def test_stage_one_closes_only_enough_to_restore_margin() -> None:
    a = account()
    out = LiquidationOutcome()
    eng = engine()
    due = eng.evaluate([a], mark=958.0, tick=0, grace_enabled=False,
                       upi_credit_enabled=False, outcome=out)
    eng.run(due, book=book(), mark=958.0, reference=1000.0, tick=0,
            throttle_enabled=False, two_stage_enabled=True,
            all_accounts=[a], outcome=out)
    assert out.events[0].stage is LiquidationStage.PARTIAL
    assert 0.0 < a.qty < 100.0
    assert a.state is not AccountState.LIQUIDATED
    assert out.events[0].fee == 0.0  # stage one is fee-free


def test_stage_two_hands_the_position_to_the_backstop_and_charges_a_fee() -> None:
    a = account()
    mark = 951.0
    assert a.equity(mark) < P.backstop_threshold(a.mm_required(mark, P))
    out = LiquidationOutcome()
    eng = engine()
    due = eng.evaluate([a], mark=mark, tick=0, grace_enabled=False,
                       upi_credit_enabled=False, outcome=out)
    eng.run(due, book=book(), mark=mark, reference=1000.0, tick=0,
            throttle_enabled=False, two_stage_enabled=True,
            all_accounts=[a], outcome=out)
    assert out.events[0].stage is LiquidationStage.BACKSTOP
    assert a.state is AccountState.BACKSTOPPED
    assert out.events[0].fee > 0.0


def test_without_two_stage_the_whole_position_goes_at_once() -> None:
    a = account()
    out = LiquidationOutcome()
    eng = engine()
    due = eng.evaluate([a], mark=958.0, tick=0, grace_enabled=False,
                       upi_credit_enabled=False, outcome=out)
    eng.run(due, book=book(), mark=958.0, reference=1000.0, tick=0,
            throttle_enabled=False, two_stage_enabled=False,
            all_accounts=[a], outcome=out)
    assert out.events[0].stage is LiquidationStage.MARKET
    assert a.qty == 0.0


# -- the throttle ----------------------------------------------------------

def test_throttle_caps_the_engine_at_the_published_participation_rate() -> None:
    """BitMEX, March 2020: when a DDoS took the engine offline the price
    recovered instantly, because the biggest forced seller had vanished."""
    accounts = [
        account(id=f"MT{i:05d}", qty=2000.0, collateral=1_00_000.0) for i in range(40)
    ]
    b = book(depth=10 * LAKH)
    expected = (
        b.depth_within(P.twap_participation_band_pct * 100.0)
        * P.twap_max_participation_pct
        * P.twap_slices_per_tick
    )

    out = LiquidationOutcome()
    eng = engine()
    due = eng.evaluate(accounts, mark=940.0, tick=0, grace_enabled=False,
                       upi_credit_enabled=False, outcome=out)
    eng.run(due, book=b, mark=940.0, reference=1000.0, tick=0,
            throttle_enabled=True, two_stage_enabled=True,
            all_accounts=accounts, outcome=out)
    executed = sum(e.notional for e in out.events)
    assert executed <= expected * 1.02
    assert out.throttled_accounts > 0


def test_unthrottled_engine_sells_far_more_in_the_same_tick() -> None:
    def run(throttled: bool) -> float:
        accounts = [
            account(id=f"MT{i:05d}", qty=2000.0, collateral=1_00_000.0) for i in range(40)
        ]
        out = LiquidationOutcome()
        eng = engine()
        due = eng.evaluate(accounts, mark=940.0, tick=0, grace_enabled=False,
                           upi_credit_enabled=False, outcome=out)
        eng.run(due, book=book(depth=10 * LAKH), mark=940.0, reference=1000.0, tick=0,
                throttle_enabled=throttled, two_stage_enabled=True,
                all_accounts=accounts, outcome=out)
        return sum(e.notional for e in out.events)

    assert run(throttled=False) > run(throttled=True) * 3


# -- queue order and the APE counterfactual --------------------------------

def test_queue_order_is_deterministic() -> None:
    accounts = [account(id=f"MT{i:05d}", qty=100.0 + i) for i in range(10)]
    eng = engine()
    first = [a.id for a in eng.evaluate(list(accounts), mark=940.0, tick=0,
                                        grace_enabled=False, upi_credit_enabled=False,
                                        outcome=LiquidationOutcome())]
    second = [a.id for a in eng.evaluate(list(reversed(accounts)), mark=940.0, tick=0,
                                         grace_enabled=False, upi_credit_enabled=False,
                                         outcome=LiquidationOutcome())]
    assert first == second


def test_survived_at_reference_is_the_ape_counterfactual() -> None:
    """APE criterion 3: did this account hold enough margin to survive at the
    Reference Composite? If yes, the liquidation should not have happened."""
    a = account()
    out = LiquidationOutcome()
    eng = engine()
    due = eng.evaluate([a], mark=940.0, tick=0, grace_enabled=False,
                       upi_credit_enabled=False, outcome=out)
    eng.run(due, book=book(), mark=940.0, reference=1000.0, tick=0,
            throttle_enabled=False, two_stage_enabled=True,
            all_accounts=[a], outcome=out)
    assert out.events[0].survived_at_reference is True

    b = account(id="MT00002")
    out2 = LiquidationOutcome()
    eng2 = engine()
    due2 = eng2.evaluate([b], mark=940.0, tick=0, grace_enabled=False,
                         upi_credit_enabled=False, outcome=out2)
    eng2.run(due2, book=book(), mark=940.0, reference=941.0, tick=0,
             throttle_enabled=False, two_stage_enabled=True,
             all_accounts=[b], outcome=out2)
    assert out2.events[0].survived_at_reference is False


# -- ADL -------------------------------------------------------------------

def test_adl_closes_winners_when_the_vault_goes_underwater() -> None:
    """ADL converts a user problem into a trust problem: it force-closes
    *winning* positions at the bankrupt trader's bankruptcy price."""
    loser = account(id="MT00001", qty=20_000.0, collateral=2_00_000.0)
    winner = account(id="MT00002", side=Side.SHORT, qty=5_000.0, collateral=5_00_000.0)
    accounts = [loser, winner]

    out = LiquidationOutcome()
    eng = engine(vault=1_000.0)
    due = eng.evaluate(accounts, mark=880.0, tick=0, grace_enabled=False,
                       upi_credit_enabled=False, outcome=out)
    eng.run(due, book=book(depth=200 * LAKH), mark=880.0, reference=880.0, tick=0,
            throttle_enabled=False, two_stage_enabled=True,
            all_accounts=accounts, outcome=out)

    assert out.insurance_drawn > 0.0
    assert out.adl_accounts >= 1
    assert winner.qty < 5_000.0
    adl = [e for e in out.events if e.stage is LiquidationStage.ADL]
    assert adl and all(e.survived_at_reference for e in adl)


def test_adl_ranks_by_pnl_times_effective_leverage() -> None:
    """Binance's rank: the profitable and highly levered go first."""
    loser = account(id="MT00001", qty=30_000.0, collateral=3_00_000.0)
    modest = account(id="MT00002", side=Side.SHORT, qty=4_000.0, collateral=20_00_000.0)
    levered = account(id="MT00003", side=Side.SHORT, qty=4_000.0, collateral=2_00_000.0)
    accounts = [loser, modest, levered]

    out = LiquidationOutcome()
    eng = engine(vault=500.0)
    due = eng.evaluate(accounts, mark=880.0, tick=0, grace_enabled=False,
                       upi_credit_enabled=False, outcome=out)
    eng.run(due, book=book(depth=200 * LAKH), mark=880.0, reference=880.0, tick=0,
            throttle_enabled=False, two_stage_enabled=True,
            all_accounts=accounts, outcome=out)

    adl_ids = [e.account_id for e in out.events if e.stage is LiquidationStage.ADL]
    assert adl_ids and adl_ids[0] == "MT00003"
