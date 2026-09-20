"""Liquidation engine, the waterfall, and ADL.

Amplifier 1: the liquidation engine becomes the largest seller. BitMEX on
12-13 Mar 2020 had contracts to sell into a worsening price, which produced
more liquidations and more contracts to sell; when a DDoS took the engine
offline at 02:16 UTC the price recovered from ~$3,900 to ~$5,300 immediately.
The outage was a better circuit breaker than the circuit breaker. That is the
strongest argument available for throttling your own engine, and the throttle
here is the control that reproduces it.

The waterfall, in order:

    partial / tiered liquidation
      -> market liquidation
        -> backstop liquidator vault / insurance
          -> ADL, last

Two-stage liquidation, Hyperliquid's model:

- Below maintenance margin, the position is worked at market. The trader keeps
  any residual collateral and pays no clearance fee.
- Only below two-thirds of maintenance margin does the backstop liquidator
  vault take the position, and the maintenance margin is forfeited.

That ordering gives a trader a chance to be liquidated at market before the
punitive path, and it is worth copying for that reason alone.

ADL is modelled because it is a trust problem, not a user problem. It force-
closes *winning* positions at the bankrupt trader's bankruptcy price, ranked by
PNL% x effective leverage. A Dec 2025 arXiv analysis of 10 Oct 2025 put
Hyperliquid's queue-based ADL at roughly $653M of unnecessary haircuts on
winning traders, about 28x overutilisation versus optimal policy, likely
contributing to the subsequent ~50% loss of open interest. The same paper
proves an impossibility trilemma: no ADL policy delivers solvency, trader
fairness and long-run revenue simultaneously.

MochaTrade's stated choice, which the UI must show rather than hide: solvency
first, then trader fairness, then revenue. ADL stays in the waterfall because
removing it means the venue goes insolvent instead; what we do is push it as
far down the waterfall as the backstop vault allows, and compensate afterwards
under the published policy.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum, IntEnum

from .book import Book
from .params import RiskParams


class Side(IntEnum):
    LONG = 1
    SHORT = -1

    @property
    def label(self) -> str:
        return "long" if self is Side.LONG else "short"


class MarginMode(Enum):
    CROSS = "cross"
    """Amplifier 4: unified accounts get tied to their weakest asset. A
    depegged collateral token liquidated whole portfolios whose individual
    positions were healthy."""

    ISOLATED = "isolated"


class AccountState(Enum):
    HEALTHY = "healthy"
    MARGIN_CALL = "margin_call"
    LIQUIDATED = "liquidated"
    BACKSTOPPED = "backstopped"
    ADL_CLOSED = "adl_closed"
    CLOSED = "closed"


class LiquidationStage(Enum):
    PARTIAL = "partial"
    MARKET = "market"
    BACKSTOP = "backstop"
    ADL = "adl"


@dataclass(slots=True)
class Account:
    """One trader's position. Mutable: the engine steps it in place."""

    id: str
    side: Side
    qty: float
    entry_price: float
    leverage: float
    collateral: float
    mode: MarginMode = MarginMode.CROSS
    state: AccountState = AccountState.HEALTHY

    realised_pnl: float = 0.0
    fees_paid: float = 0.0
    margin_call_tick: int | None = None
    liquidated_tick: int | None = None
    liquidated_qty: float = 0.0
    liquidation_value: float = 0.0
    """Notional actually realised by forced sales, at the prices achieved."""

    reachable: bool = True
    """False while a broker-layer outage is active for this user. An outage does
    not change the market; it changes whether the user can do anything about it."""

    affected_by_outage: bool = False

    upi_deposit_inr: float = 0.0
    """A UPI top-up the user initiated. Whether it lands in time is the whole
    class E question."""

    upi_initiated_tick: int | None = None
    """When the user actually pressed send. The credit is an advance against an
    initiated-but-unsettled deposit, so it cannot exist before this."""

    upi_settles_tick: int | None = None
    upi_credited: bool = False
    upi_credit_advanced: float = 0.0
    """How much of the deposit was fronted before it settled. The settlement
    tops up the remainder rather than replacing it -- the credit is an advance,
    not a cheaper substitute for the user's own money."""

    upi_settled: bool = False
    deposits_credited: float = 0.0
    """Money the user paid in during the run. Not a gain: it has to be netted
    out of any loss figure, or a control that lets deposits land sooner scores
    as if it created wealth."""

    @property
    def open(self) -> bool:
        return self.qty > 1e-12 and self.state not in (
            AccountState.LIQUIDATED,
            AccountState.BACKSTOPPED,
            AccountState.ADL_CLOSED,
            AccountState.CLOSED,
        )

    @property
    def entry_notional(self) -> float:
        return self.qty * self.entry_price

    def notional(self, mark: float) -> float:
        return self.qty * mark

    def unrealised(self, mark: float) -> float:
        return int(self.side) * self.qty * (mark - self.entry_price)

    def equity(self, mark: float) -> float:
        return self.collateral + self.realised_pnl + self.unrealised(mark)

    def mm_required(self, mark: float, params: RiskParams) -> float:
        notional = self.notional(mark)
        return notional * params.mm_rate(notional)

    def bankruptcy_price(self) -> float:
        """The price at which equity reaches zero and the position is worth
        exactly the collateral behind it. ADL closes counterparties here."""
        if self.qty <= 0.0:
            return self.entry_price
        margin = self.collateral + self.realised_pnl
        return self.entry_price - int(self.side) * margin / self.qty

    def margin_ratio(self, mark: float, params: RiskParams) -> float:
        mm = self.mm_required(mark, params)
        if mm <= 0.0:
            return math.inf
        return self.equity(mark) / mm

    def pnl_pct(self, mark: float) -> float:
        basis = self.collateral + self.realised_pnl
        if basis <= 0.0:
            return 0.0
        return self.unrealised(mark) / basis

    def effective_leverage(self, mark: float) -> float:
        equity = self.equity(mark)
        if equity <= 0.0:
            return math.inf
        return self.notional(mark) / equity


@dataclass(frozen=True, slots=True)
class LiquidationEvent:
    """One forced close, or one slice of one. The tape that every later claim
    is decided from."""

    tick: int
    account_id: str
    stage: LiquidationStage
    qty: float
    notional: float
    fill_price: float
    mark: float
    reference_price: float | None
    slippage_bps: float
    equity_before: float
    mm_required: float
    shortfall: float
    fee: float
    survived_at_reference: bool
    """Criterion 3 of the APE test, evaluated at the moment of execution: did
    this account hold enough margin to survive at the Reference Composite? If
    yes, this liquidation should not have happened, and that is the number the
    whole proof page is built on."""


@dataclass(slots=True)
class LiquidationOutcome:
    """Everything that happened to the engine in one tick."""

    events: list[LiquidationEvent] = field(default_factory=list)
    forced_sell_notional: float = 0.0
    forced_buy_notional: float = 0.0
    queued_accounts: int = 0
    throttled_accounts: int = 0
    """Accounts that breached but were held back by the TWAP participation cap.
    A non-zero number here is the control doing its job."""

    margin_calls_opened: int = 0
    saved_by_grace: int = 0
    upi_credits_issued: int = 0
    insurance_drawn: float = 0.0
    adl_notional: float = 0.0
    adl_accounts: int = 0
    unfilled_notional: float = 0.0

    @property
    def net_sell_notional(self) -> float:
        return self.forced_sell_notional - self.forced_buy_notional


@dataclass(slots=True)
class LiquidationEngine:
    """Stateless with respect to price: everything it needs arrives per tick."""

    params: RiskParams
    insurance_balance: float
    insurance_opening: float = 0.0

    def __post_init__(self) -> None:
        self.insurance_opening = self.insurance_balance

    # -- margin evaluation --------------------------------------------------

    def evaluate(
        self,
        accounts: list[Account],
        *,
        mark: float,
        tick: int,
        grace_enabled: bool,
        upi_credit_enabled: bool,
        outcome: LiquidationOutcome,
    ) -> list[Account]:
        """Return the accounts that must be liquidated this tick.

        The grace window is applied here rather than in the liquidation loop,
        because grace is a decision about *whether* an account is due, not about
        how fast the engine works through what is due.
        """
        due: list[Account] = []
        for account in accounts:
            if not account.open:
                continue

            # Both of these depend on the user being able to reach us. A grace
            # window behind a 5xx is worthless, which is the class D harm.
            if (
                upi_credit_enabled
                and account.reachable
                and not account.upi_credited
                and account.upi_initiated_tick is not None
                and tick >= account.upi_initiated_tick
            ):
                self._maybe_credit_upi(account, tick, outcome)

            equity = account.equity(mark)
            mm = account.mm_required(mark, self.params)
            if equity >= mm:
                if account.state is AccountState.MARGIN_CALL:
                    account.state = AccountState.HEALTHY
                    account.margin_call_tick = None
                    outcome.saved_by_grace += 1
                continue

            below_backstop = equity < self.params.backstop_threshold(mm)

            if grace_enabled and account.reachable and not below_backstop:
                # A margin call opens, a push notification fires, and the user
                # gets the published window to act. Sized to UPI p99, not to
                # market risk: this control exists because of the rail.
                if account.margin_call_tick is None:
                    account.margin_call_tick = tick
                    account.state = AccountState.MARGIN_CALL
                    outcome.margin_calls_opened += 1
                    continue
                if tick - account.margin_call_tick < self.params.margin_grace_ticks:
                    continue

            due.append(account)

        # Deterministic ordering: deepest deficit first, id as the tie-break.
        due.sort(key=lambda a: (-(a.mm_required(mark, self.params) - a.equity(mark)), a.id))
        outcome.queued_accounts = len(due)
        return due

    def _maybe_credit_upi(
        self, account: Account, tick: int, outcome: LiquidationOutcome
    ) -> None:
        """Pre-funded instant margin credit against an initiated-but-unsettled
        UPI deposit, capped and risk-scored. The most India-specific control in
        the brief: without it, a user's ability to avoid liquidation depends on
        an NPCI leg settling, and India saw 282 minutes of UPI outage across two
        incidents."""
        if account.upi_deposit_inr <= 0.0:
            return
        credit = min(account.upi_deposit_inr, self.params.upi_prefunded_credit_cap_inr)
        account.collateral += credit
        account.deposits_credited += credit
        account.upi_credit_advanced = credit
        account.upi_credited = True
        outcome.upi_credits_issued += 1

    def settle_upi_deposits(self, accounts: list[Account], tick: int) -> None:
        """The deposit finally lands. Runs every tick regardless of whether the
        pre-funded credit is enabled: the credit is an advance against this
        money, so settlement pays the remainder. Late money with no advance
        against it is the class E signature."""
        for account in accounts:
            if (
                account.upi_settles_tick is not None
                and not account.upi_settled
                and tick >= account.upi_settles_tick
            ):
                remainder = max(
                    0.0, account.upi_deposit_inr - account.upi_credit_advanced
                )
                account.collateral += remainder
                account.deposits_credited += remainder
                account.upi_settled = True

    # -- execution ----------------------------------------------------------

    def run(
        self,
        due: list[Account],
        *,
        book: Book,
        mark: float,
        reference: float | None,
        tick: int,
        throttle_enabled: bool,
        two_stage_enabled: bool,
        all_accounts: list[Account],
        outcome: LiquidationOutcome,
    ) -> LiquidationOutcome:
        """Work the due queue through the waterfall under the active controls."""
        budget = self._tick_budget(book, mark, throttle_enabled)

        for account in due:
            # A budget too small to fund any meaningful close is exhausted. Left
            # as an exact `<= 0`, float residue means the queue silently drains
            # through zero-size fills and nothing is ever reported as throttled.
            if budget <= 1.0:
                outcome.throttled_accounts += 1
                continue

            equity = account.equity(mark)
            mm = account.mm_required(mark, self.params)
            below_backstop = equity < self.params.backstop_threshold(mm)

            if two_stage_enabled and not below_backstop:
                stage = LiquidationStage.PARTIAL
                close_qty = self._partial_close_qty(account, mark, mm)
            elif two_stage_enabled:
                stage = LiquidationStage.BACKSTOP
                close_qty = account.qty
            else:
                # Control off: no tiering, no two-stage path. The whole position
                # goes to market the instant maintenance margin breaks.
                stage = LiquidationStage.MARKET
                close_qty = account.qty

            close_qty = min(close_qty, account.qty)
            if close_qty <= 0.0:
                continue

            selling = account.side is Side.LONG

            # The participation cap is a limit on how much of the BOOK the
            # engine consumes, so it is measured at the book's own touch price.
            # Converting the budget at the mark lets the engine overshoot the
            # published cap whenever the two have drifted apart -- which, during
            # a cascade, is exactly when the cap matters.
            if throttle_enabled:
                touch = book.best_bid if selling else book.best_ask
                affordable = budget / touch if touch > 0.0 else 0.0
                if affordable < close_qty:
                    # Held back by the cap, wholly or in part. This count is the
                    # control visibly doing its job.
                    close_qty = affordable
                    outcome.throttled_accounts += 1
                if close_qty <= 0.0:
                    continue

            fill = book.walk(sell=selling, qty=close_qty)
            if fill.filled_qty <= 0.0:
                outcome.unfilled_notional += close_qty * mark
                continue

            executed_qty = min(close_qty, fill.filled_qty)
            executed_notional = executed_qty * fill.avg_price
            budget -= executed_notional
            outcome.unfilled_notional += fill.unfilled_notional

            self._book_pnl(account, executed_qty, fill.avg_price)
            account.qty -= executed_qty
            account.liquidated_qty += executed_qty
            account.liquidation_value += executed_notional
            account.liquidated_tick = tick

            fee = 0.0
            shortfall = 0.0
            if stage is LiquidationStage.BACKSTOP:
                # The punitive path: maintenance margin is forfeited.
                fee = executed_notional * self.params.clearance_fee_pct
                account.fees_paid += fee
                account.realised_pnl -= fee
            elif stage is LiquidationStage.MARKET:
                fee = executed_notional * self.params.clearance_fee_pct
                account.fees_paid += fee
                account.realised_pnl -= fee

            residual_equity = account.equity(mark)
            if account.qty <= 1e-12:
                account.qty = 0.0
                account.state = (
                    AccountState.BACKSTOPPED
                    if stage is LiquidationStage.BACKSTOP
                    else AccountState.LIQUIDATED
                )
                if residual_equity < 0.0:
                    # The account closed underwater. Somebody funds the hole.
                    shortfall = -residual_equity
                    account.realised_pnl -= residual_equity  # zero it out
                    self.insurance_balance -= shortfall
                    outcome.insurance_drawn += shortfall

            if selling:
                outcome.forced_sell_notional += executed_notional
            else:
                outcome.forced_buy_notional += executed_notional

            outcome.events.append(
                LiquidationEvent(
                    tick=tick,
                    account_id=account.id,
                    stage=stage,
                    qty=executed_qty,
                    notional=executed_notional,
                    fill_price=fill.avg_price,
                    mark=mark,
                    reference_price=reference,
                    slippage_bps=fill.slippage_bps,
                    equity_before=equity,
                    mm_required=mm,
                    shortfall=shortfall,
                    fee=fee,
                    survived_at_reference=self._would_survive(account, reference),
                )
            )

        if self.insurance_balance < 0.0:
            self._auto_deleverage(
                deficit=-self.insurance_balance,
                accounts=all_accounts,
                mark=mark,
                tick=tick,
                reference=reference,
                outcome=outcome,
            )

        return outcome

    # -- helpers ------------------------------------------------------------

    def _tick_budget(
        self, book: Book, mark: float, throttle_enabled: bool
    ) -> float:
        """How much notional the engine may sell this tick.

        Throttled: max participation of resting depth within the published band,
        per 250ms slice, four slices to the second. Unthrottled: everything,
        immediately, which is the BitMEX spiral.
        """
        if not throttle_enabled:
            return math.inf
        depth = book.depth_within(self.params.twap_participation_band_pct * 100.0)
        per_slice = depth * self.params.twap_max_participation_pct
        return per_slice * self.params.twap_slices_per_tick

    def _partial_close_qty(self, account: Account, mark: float, mm: float) -> float:
        """Close only enough to restore margin, per the tier.

        Target is a multiple of maintenance margin rather than maintenance
        margin exactly, so the account is not re-liquidated on the next tick --
        which would reproduce the cascade this control exists to prevent.
        """
        if mark <= 0.0:
            return 0.0
        equity = account.equity(mark)
        target_ratio = self.params.mm_rate(account.notional(mark)) * (
            self.params.partial_liq_target_mm_multiple
        )
        if target_ratio <= 0.0:
            return account.qty
        # equity is roughly preserved by closing at mark, so the qty that
        # satisfies equity >= target_ratio * qty_remaining * mark is:
        target_qty = equity / (target_ratio * mark)
        close = account.qty - target_qty
        if close <= 0.0:
            return 0.0
        return min(close, account.qty)

    @staticmethod
    def _book_pnl(account: Account, qty: float, price: float) -> None:
        account.realised_pnl += int(account.side) * qty * (price - account.entry_price)

    def _would_survive(self, account: Account, reference: float | None) -> bool:
        """APE criterion 3. Evaluated against the position as it stood before
        this slice, at the Reference Composite rather than the disputed mark."""
        if reference is None or reference <= 0.0:
            return False
        restored_qty = account.qty + account.liquidated_qty
        if restored_qty <= 0.0:
            return False
        probe = Account(
            id=account.id,
            side=account.side,
            qty=restored_qty,
            entry_price=account.entry_price,
            leverage=account.leverage,
            collateral=account.collateral,
            mode=account.mode,
        )
        return probe.equity(reference) >= probe.mm_required(reference, self.params)

    # -- auto-deleveraging --------------------------------------------------

    def _auto_deleverage(
        self,
        *,
        deficit: float,
        accounts: list[Account],
        mark: float,
        tick: int,
        reference: float | None,
        outcome: LiquidationOutcome,
    ) -> None:
        """Last resort. Force-close winning positions at the bankruptcy price.

        Binance's rank: PNL% x effective leverage, so the profitable and highly
        levered go first. This is the step that converts a user problem into a
        trust problem, and the simulator counts its cost explicitly rather than
        burying it in a footnote.
        """
        winners = [
            a
            for a in accounts
            if a.open and a.unrealised(mark) > 0.0 and a.qty > 1e-12
        ]
        if not winners:
            return

        winners.sort(
            key=lambda a: (
                -(a.pnl_pct(mark) * min(a.effective_leverage(mark), 1e6)),
                a.id,
            )
        )

        remaining = deficit
        for account in winners:
            if remaining <= 1e-6:
                break
            price = account.bankruptcy_price()
            if price <= 0.0:
                price = mark
            close_qty = min(account.qty, remaining / mark if mark > 0 else account.qty)
            if close_qty <= 0.0:
                continue

            notional = close_qty * price
            self._book_pnl(account, close_qty, price)
            account.qty -= close_qty
            account.liquidated_qty += close_qty
            account.liquidation_value += notional
            account.liquidated_tick = tick
            if account.qty <= 1e-12:
                account.qty = 0.0
                account.state = AccountState.ADL_CLOSED

            remaining -= close_qty * mark
            self.insurance_balance += close_qty * mark
            outcome.adl_notional += close_qty * mark
            outcome.adl_accounts += 1
            outcome.events.append(
                LiquidationEvent(
                    tick=tick,
                    account_id=account.id,
                    stage=LiquidationStage.ADL,
                    qty=close_qty,
                    notional=notional,
                    fill_price=price,
                    mark=mark,
                    reference_price=reference,
                    slippage_bps=0.0,
                    equity_before=account.equity(mark),
                    mm_required=account.mm_required(mark, self.params),
                    shortfall=0.0,
                    fee=0.0,
                    survived_at_reference=True,
                )
            )
