"""The deterministic tick loop. Holds all simulation state.

One `step()` advances the world by one tick and returns a frame. The client
polls or steps over plain REST and animates between frames; there is no
websocket, no Channels and no background worker anywhere in this project.

Order of operations inside a tick is fixed, because it is the thing that has to
be byte-identical across runs:

    1. expire timed flags (DCB pause, velocity pause)
    2. advance the exogenous shock and the per-source oracle inputs
    3. rebuild the live and reference composites, evaluate oracle health
    4. reprice the book (decayed impact, dislocation, liquidity withdrawal)
    5. run the volatility-control layers (velocity, DCB)
    6. compute the mark
    7. apply operator actions queued for this tick
    8. evaluate accounts and run the liquidation waterfall under active controls
    9. feed forced flow back into book pressure for the next tick
   10. emit the frame

Determinism contract: same seed, same params, same control stack and same
action sequence produce a byte-identical frame sequence. No wall-clock reads,
no unseeded randomness, no iteration over unordered containers, and every
sub-system draws from its own named RNG sub-stream so adding a draw in one
place cannot shift the numbers somewhere else. `tests/test_determinism.py`
asserts it against a hash of the serialised output.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass

from .book import Book, VolatilityTracker
from .controls import (
    ActionKind,
    CircuitBreaker,
    ControlStack,
    MarketFlags,
    OperatorAction,
    ReopenStage,
    VelocityMonitor,
    apply_action,
)
from .liquidation import (
    Account,
    AccountState,
    LiquidationEngine,
    LiquidationEvent,
    LiquidationOutcome,
)
from .marking import MarkCalculator, MarkResult
from .oracle import (
    Composite,
    OracleFeed,
    OracleHealth,
    SourceObservation,
    build_composite,
    observations,
)
from .params import TICK_SECONDS, RiskParams
from .rng import Rng
from .scenario import Scenario

#: Version of the Frame's shape. Anything that persists frames must include it
#: in its cache key: a run stored before a field existed must not be served as
#: if it had that field. 2 = per-source oracle observations. 3 = pause reason
#: and velocity escalation level.
FRAME_SCHEMA = 3


@dataclass(frozen=True, slots=True)
class Frame:
    """One tick of output. Everything the war room renders, and enough state to
    reconstruct the incident report without re-running the simulation."""

    tick: int
    t_seconds: float

    true_price: float
    composite: float | None
    composite_rung: int
    oracle_health: str
    oracle_reason: str
    reference: float | None
    book_mid: float
    best_bid: float
    best_ask: float
    spread_bps: float
    depth_pct_of_baseline: float
    mark: float
    mark_source: str
    divergence_bps: float

    reduce_only: bool
    liquidations_paused: bool
    trading_paused: bool
    pause_reason: str | None
    """Which layer is holding trading paused: "circuit_breaker", "velocity",
    "halt", or None. Before this, a chart could not tell a 5-second velocity
    pause from a 2-minute breaker."""

    velocity_level: int
    halted: bool
    max_leverage: float
    stage: str

    liquidated_this_tick: int
    liquidated_notional_this_tick: float
    cum_liquidated_accounts: int
    cum_liquidated_notional: float
    throttled_accounts: int
    margin_calls_open: int
    saved_by_grace: int
    upi_credits_issued: int
    adl_accounts: int
    adl_notional: float
    insurance_balance: float
    unnecessary_liquidations: int
    """Accounts liquidated this tick that held enough margin to survive at the
    Reference Composite. APE criterion 3, measured live."""

    accounts_open: int
    aggregate_equity: float
    log: tuple[str, ...] = ()
    sources: tuple[SourceObservation, ...] = ()
    """Every oracle source's part in this tick's composite: the price it
    printed, the price the composite used, its effective weight, and why it was
    excluded if it was. The evidence tape a class C claim is decided from."""

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class RunSummary:
    """The comparison surface. Every field here exists to be shown twice, once
    with the control stack off and once on, with the delta between them."""

    scenario_key: str
    seed: int
    policy_version: str
    controls: dict[str, bool]
    ticks: int

    accounts_total: int
    open_interest_start: float
    aggregate_collateral_start: float

    accounts_liquidated: int
    liquidated_notional: float
    unnecessary_liquidations: int
    unnecessary_notional: float
    adl_accounts: int
    adl_notional: float

    insurance_opening: float
    insurance_final: float
    insurance_drawn: float

    margin_calls_opened: int
    saved_by_grace: int
    upi_credits_issued: int
    throttled_ticks: int
    peak_unfilled_notional: float
    """Largest notional the book could not absorb in a single tick. Reported as
    a peak rather than a running total because an unfilled position is
    re-requested every tick until it closes, so a cumulative figure counts the
    same position many times over and reads as an absurd number."""

    max_divergence_bps: float
    peak_mark_pct: float
    trough_mark_pct: float
    trough_reference_pct: float
    trough_book_pct: float
    min_depth_pct_of_baseline: float

    user_equity_start: float
    deposits_credited: float
    """Money users paid in mid-run. Netted out of user_loss: a deposit is the
    user's own money arriving, not a gain the simulation produced."""

    user_equity_end: float
    user_loss: float
    counterfactual_equity_end: float
    counterfactual_loss: float
    attributable_loss: float
    """user_loss minus counterfactual_loss: the part of the damage that exists
    only because of how the event was priced and processed, rather than because
    the market moved. This is the number the controls are graded on and the
    number a make-whole is sized from."""

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class RunResult:
    summary: RunSummary
    frames: list[Frame]
    events: list[LiquidationEvent]
    accounts: list[Account]
    log: list[str]


class Engine:
    """One simulation run. Construct, then `step()` or `run()`."""

    def __init__(
        self,
        scenario: Scenario,
        params: RiskParams,
        controls: ControlStack,
        *,
        seed: int | None = None,
        actions: tuple[OperatorAction, ...] = (),
    ) -> None:
        self.scenario = scenario
        self.params = params
        self.controls = controls
        self.seed = scenario.seed if seed is None else int(seed)

        root = Rng(self.seed)
        self._rng_path = root.spawn("shock-path")
        self._rng_oracle = root.spawn("oracle-noise")
        rng_population = root.spawn("population")
        rng_faults = root.spawn("fault-assignment")

        self.path = scenario.shock.path(scenario.n_ticks, self._rng_path)

        # Control #4 works before the crash, not during it: if 50x is not
        # available off-hours, the over-levered accounts never exist.
        ceiling = (
            params.max_leverage_offhours
            if (
                controls.time_of_day_leverage_caps
                and scenario.has_cash_session
                and scenario.offhours
            )
            else params.max_leverage_rth
        )
        self.accounts = scenario.population.build(
            rng_population,
            price=scenario.initial_price,
            leverage_ceiling=ceiling,
            tier_leverage=params,
            isolated_default=controls.isolated_margin_default,
        )
        self._by_id = {a.id: a for a in self.accounts}
        self._assign_faults(rng_faults)

        self.book = Book(scenario.book, scenario.initial_price)
        self.feed = OracleFeed(scenario.oracle_sources, scenario.oracle_faults)
        self.mark_calc = MarkCalculator(params)
        self.liq = LiquidationEngine(params, insurance_balance=scenario.backstop_vault_inr)
        self.vol = VolatilityTracker()
        self.breaker = CircuitBreaker(params, scenario.instrument_tier, scenario.offhours)
        self.velocity = VelocityMonitor(params, scenario.instrument_tier, scenario.offhours)

        self.flags = MarketFlags(max_leverage=ceiling)
        self.auto_liq_pause = False
        self.auto_reduce_only = False
        self.operator_throttle = False
        """Set by the Protect Switch and by an explicit throttle order. Without
        this the operator's headline decision changes nothing in the simulation
        and the war room is theatre."""

        self._actions: dict[int, list[OperatorAction]] = {}
        for action in actions:
            self._actions.setdefault(action.tick, []).append(action)

        self.tick = 0
        self.frames: list[Frame] = []
        self.events: list[LiquidationEvent] = []
        self.log: list[str] = []

        self.cum_liquidated_accounts = 0
        self.cum_liquidated_notional = 0.0
        self.cum_unnecessary = 0
        self.cum_unnecessary_notional = 0.0
        self.cum_adl_accounts = 0
        self.cum_adl_notional = 0.0
        self.cum_margin_calls = 0
        self.cum_saved_grace = 0
        self.cum_upi_credits = 0
        self.peak_unfilled = 0.0
        self.throttled_ticks = 0
        self.max_divergence_bps = 0.0
        self.min_mark = math.inf
        self.min_reference = math.inf
        self.min_book = math.inf
        self.max_mark = 0.0
        self.min_depth = 1.0

        self.open_interest_start = sum(a.notional(scenario.initial_price) for a in self.accounts)
        self.collateral_start = sum(a.collateral for a in self.accounts)
        self.equity_start = sum(a.equity(scenario.initial_price) for a in self.accounts)

    # -- setup -------------------------------------------------------------

    def _assign_faults(self, rng: Rng) -> None:
        """Decide which accounts an outage or a UPI delay touches. Done once, up
        front, from its own stream, so the assignment is stable no matter how
        many draws the rest of the simulation makes."""
        outage = self.scenario.outage
        upi = self.scenario.upi_delay

        # An outage hits whoever happens to be using the app.
        if outage is not None:
            for account in self.accounts:
                if rng.chance(outage.affected_frac):
                    account.affected_by_outage = True

        # A UPI top-up does not. People top up BECAUSE they are facing a margin
        # call, so the deposit cohort is the at-risk cohort -- the most levered
        # accounts, not a random slice of the book. Assigning it at random
        # spreads the deposits across people who were never in danger and makes
        # the control look inert when it is in fact doing its job.
        if upi is not None:
            ranked = sorted(self.accounts, key=lambda a: (-a.leverage, a.id))
            cohort = ranked[: int(round(upi.affected_frac * len(ranked)))]
            for account in cohort:
                account.upi_deposit_inr = rng.lognormal(upi.amount_median, 0.6)
                account.upi_initiated_tick = upi.initiated_tick
                account.upi_settles_tick = upi.settles_tick

    # -- the loop ----------------------------------------------------------

    def step(self) -> Frame:
        if self.finished:
            return self.frames[-1]

        tick = self.tick
        params = self.params
        scenario = self.scenario
        lines: list[str] = []

        self.flags.tick_expiries(tick)

        # 1. exogenous price
        true_price = scenario.initial_price * self.path[tick]

        # 2. oracle
        live_readings, ref_readings = self.feed.observe(
            tick=tick, true_price=true_price, rng=self._rng_oracle
        )
        composite = build_composite(
            live_readings,
            params,
            tick=tick,
            majors=scenario.is_major,
            expected_rung=scenario.expected_rung,
        )
        reference = build_composite(
            ref_readings,
            params,
            tick=tick,
            majors=scenario.is_major,
            expected_rung=scenario.expected_rung,
        )

        # 3. oracle health monitor (control #2). The trigger is feed health,
        #    never user pain: pausing liquidations on a healthy feed converts
        #    user losses into our insolvency.
        suspect = composite.health in (OracleHealth.SUSPECT, OracleHealth.NO_COMPOSITE)
        if self.controls.oracle_health_monitor:
            if suspect and not self.auto_liq_pause:
                self.auto_liq_pause = True
                self.auto_reduce_only = True
                lines.append(
                    f"Oracle health monitor fired: {composite.reason}. "
                    "Liquidations paused on this market, risk-increasing orders "
                    "rejected."
                )
            elif not suspect and self.auto_liq_pause:
                self.auto_liq_pause = False
                self.auto_reduce_only = False
                lines.append("Oracle health restored; liquidations resumed.")
        if composite.degraded:
            self.flags.max_leverage = min(
                self.flags.max_leverage, params.max_leverage_degraded
            )

        # 4. book
        dislocation = scenario.dislocation.at(tick) if scenario.dislocation else 0.0
        self.book.settle(true_price, dislocation)
        self.vol.push(self.book.mid)
        self.book.update_liquidity(self.vol.realised_bps)

        # 5. volatility controls
        if self.controls.velocity_logic:
            pause = self.velocity.step(self.book.mid, tick)
            if pause is not None:
                self.flags.velocity_paused_until = pause.until
                if pause.escalated:
                    lines.append(
                        f"Velocity logic escalated to level {pause.level}: the move "
                        f"was still over {self.velocity.trigger_pct:.2f}% in "
                        f"{params.velocity_window_seconds}s when the "
                        f"{params.velocity_cooldown_seconds}s cooldown ended. "
                        f"{pause.ticks}s pause."
                    )
                else:
                    lines.append(
                        f"Velocity logic: {self.velocity.trigger_pct:.2f}% in "
                        f"{params.velocity_window_seconds}s. {pause.ticks}s pause to "
                        "let participants reassess; the layer then cools down for "
                        f"{params.velocity_cooldown_seconds}s."
                    )
        if self.controls.dynamic_circuit_breaker:
            if self.breaker.check(self.book.mid) and self.flags.dcb_paused_until is None:
                self.flags.dcb_paused_until = tick + params.dcb_pause_ticks
                self.breaker.restart()
                self.flags.stage = ReopenStage.AUCTION
                lines.append(
                    f"Dynamic circuit breaker: {self.breaker.variant_pct:.2f}% "
                    f"band breached on a {params.dcb_lookback_seconds // 60}-minute "
                    f"look-back. {params.dcb_pause_seconds}s pre-open auction; "
                    "look-back window restarts on resume."
                )
            else:
                self.breaker.push(self.book.mid)

        # 6. mark
        seconds_to_funding = float(
            params.funding_period_seconds
            - (tick * TICK_SECONDS) % params.funding_period_seconds
        )
        mark_result = self.mark_calc.step(
            index=composite.price,
            contract_price=self.book.mid,
            reference=reference.price,
            funding_rate=0.0001,
            seconds_to_next_funding=seconds_to_funding,
            anchored=self.controls.oracle_anchored_mark,
        )
        mark = mark_result.mark
        if abs(mark_result.divergence_bps) > abs(self.max_divergence_bps):
            self.max_divergence_bps = mark_result.divergence_bps

        # 7. operator actions
        for action in self._actions.get(tick, ()):
            line = apply_action(action, self.flags, params)
            lines.append(f"[operator] {line}")
            if action.kind in (
                ActionKind.PROTECT_SWITCH,
                ActionKind.THROTTLE_LIQUIDATIONS,
            ):
                self.operator_throttle = True
            if action.kind is ActionKind.HALT_TRADING:
                self._settle_everyone_at_mark(mark, tick, lines)

        # 8. outage reachability, then the waterfall
        self._update_reachability(tick)
        outcome = LiquidationOutcome()
        liquidations_paused = self.flags.liquidations_paused or self.auto_liq_pause
        if not (liquidations_paused or self.flags.trading_paused):
            self.liq.settle_upi_deposits(self.accounts, tick)
            due = self.liq.evaluate(
                self.accounts,
                mark=mark,
                tick=tick,
                grace_enabled=self.controls.margin_grace_window,
                upi_credit_enabled=self.controls.upi_prefunded_credit,
                outcome=outcome,
            )
            self.liq.run(
                due,
                book=self.book,
                mark=mark,
                reference=reference.price,
                tick=tick,
                throttle_enabled=(
                    self.controls.liquidation_throttle or self.operator_throttle
                ),
                two_stage_enabled=self.controls.two_stage_liquidation,
                all_accounts=self.accounts,
                outcome=outcome,
            )

        # 9. forced flow feeds the next tick's price. The spiral.
        self.book.apply_flow(outcome.net_sell_notional)

        frame = self._emit(tick, true_price, composite, reference, mark_result, outcome, lines)
        self.tick += 1
        return frame

    def _update_reachability(self, tick: int) -> None:
        """An outage does not change the market; it changes whether the user can
        do anything about it. A grace window the user cannot reach is worthless,
        which is exactly the class D harm."""
        outage = self.scenario.outage
        if outage is None:
            return
        active = outage.active(tick)
        for account in self.accounts:
            if getattr(account, "affected_by_outage", False):
                account.reachable = not active

    def _settle_everyone_at_mark(self, mark: float, tick: int, lines: list[str]) -> None:
        """haltTrading: cancels all orders and settles every position at the
        current mark. If that mark is the one under dispute, a pricing dispute
        has just become a settlement dispute for the entire book."""
        settled = 0
        for account in self.accounts:
            if not account.open:
                continue
            account.realised_pnl += int(account.side) * account.qty * (
                mark - account.entry_price
            )
            account.liquidated_qty += account.qty
            account.liquidation_value += account.qty * mark
            account.qty = 0.0
            account.state = AccountState.CLOSED
            account.liquidated_tick = tick
            settled += 1
        lines.append(
            f"[operator] haltTrading settled {settled} open positions at "
            f"{mark:,.2f}. Nobody chose that price."
        )

    def _emit(
        self,
        tick: int,
        true_price: float,
        composite: Composite,
        reference: Composite,
        mark_result: MarkResult,
        outcome: LiquidationOutcome,
        lines: list[str],
    ) -> Frame:
        mark = mark_result.mark
        closed_now = [
            e for e in outcome.events if e.qty > 0 and not self._still_open(e.account_id)
        ]
        unnecessary_now = sum(1 for e in closed_now if e.survived_at_reference)
        unnecessary_notional_now = math.fsum(
            e.notional for e in closed_now if e.survived_at_reference
        )

        self.events.extend(outcome.events)
        self.cum_liquidated_accounts += len(closed_now)
        self.cum_liquidated_notional += math.fsum(e.notional for e in outcome.events)
        self.cum_unnecessary += unnecessary_now
        self.cum_unnecessary_notional += unnecessary_notional_now
        self.cum_adl_accounts += outcome.adl_accounts
        self.cum_adl_notional += outcome.adl_notional
        self.cum_margin_calls += outcome.margin_calls_opened
        self.cum_saved_grace += outcome.saved_by_grace
        self.cum_upi_credits += outcome.upi_credits_issued
        self.peak_unfilled = max(self.peak_unfilled, outcome.unfilled_notional)
        if outcome.throttled_accounts:
            self.throttled_ticks += 1

        self.min_mark = min(self.min_mark, mark)
        self.max_mark = max(self.max_mark, mark)
        if reference.price:
            self.min_reference = min(self.min_reference, reference.price)
        self.min_book = min(self.min_book, self.book.mid)
        self.min_depth = min(self.min_depth, self.book.depth_pct_of_baseline())

        open_accounts = [a for a in self.accounts if a.open]
        margin_calls_open = sum(
            1 for a in open_accounts if a.state is AccountState.MARGIN_CALL
        )

        frame = Frame(
            tick=tick,
            t_seconds=tick * TICK_SECONDS,
            true_price=true_price,
            composite=composite.price,
            composite_rung=composite.rung,
            oracle_health=composite.health.value,
            oracle_reason=composite.reason,
            reference=reference.price,
            book_mid=self.book.mid,
            best_bid=self.book.best_bid,
            best_ask=self.book.best_ask,
            spread_bps=self.book.spread_bps,
            depth_pct_of_baseline=self.book.depth_pct_of_baseline(),
            mark=mark,
            mark_source=mark_result.source.value,
            divergence_bps=mark_result.divergence_bps,
            reduce_only=self.flags.reduce_only or self.auto_reduce_only,
            liquidations_paused=self.flags.liquidations_paused or self.auto_liq_pause,
            trading_paused=self.flags.trading_paused,
            pause_reason=(
                "halt" if self.flags.halted
                else "circuit_breaker" if self.flags.dcb_paused_until is not None
                else "velocity" if self.flags.velocity_paused_until is not None
                else None
            ),
            velocity_level=self.velocity.level,
            halted=self.flags.halted,
            max_leverage=self.flags.max_leverage,
            stage=self.flags.stage.value,
            liquidated_this_tick=len(closed_now),
            liquidated_notional_this_tick=math.fsum(e.notional for e in outcome.events),
            cum_liquidated_accounts=self.cum_liquidated_accounts,
            cum_liquidated_notional=self.cum_liquidated_notional,
            throttled_accounts=outcome.throttled_accounts,
            margin_calls_open=margin_calls_open,
            saved_by_grace=self.cum_saved_grace,
            upi_credits_issued=self.cum_upi_credits,
            adl_accounts=self.cum_adl_accounts,
            adl_notional=self.cum_adl_notional,
            insurance_balance=self.liq.insurance_balance,
            unnecessary_liquidations=unnecessary_now,
            accounts_open=len(open_accounts),
            aggregate_equity=math.fsum(a.equity(mark) for a in open_accounts),
            log=tuple(lines),
            sources=observations(composite, self.params, tick=tick),
        )
        self.frames.append(frame)
        self.log.extend(f"t+{tick:04d}s  {line}" for line in lines)
        return frame

    def _still_open(self, account_id: str) -> bool:
        account = self._by_id.get(account_id)
        return account.open if account is not None else False

    # -- driving -----------------------------------------------------------

    def queue_action(self, action: OperatorAction) -> None:
        """Schedule an operator decision for a tick that has not run yet.

        Stepped runs need this: the war room decides at T+120 while the engine
        sits at tick 120, so the action cannot have been supplied up front. It
        is still part of the determinism contract -- replaying the same action
        sequence against the same seed reproduces the run exactly, which is how
        a live engine is rebuilt after a process restart.
        """
        if action.tick < self.tick:
            raise ValueError(
                f"cannot queue an action at tick {action.tick}; the engine is "
                f"already at tick {self.tick}. The log is append-only forward."
            )
        self._actions.setdefault(action.tick, []).append(action)

    @property
    def finished(self) -> bool:
        return self.tick >= self.scenario.n_ticks

    def run(self) -> RunResult:
        while not self.finished:
            self.step()
        return self.result()

    def result(self) -> RunResult:
        scenario = self.scenario
        # Every run is valued at the SAME price -- the final Reference
        # Composite -- so two control stacks can be compared. Valuing each run
        # at its own final mark would mean a stack that merely moved the mark
        # looked like it moved the money, which is a measurement artifact and
        # not a result.
        reference_final = scenario.initial_price
        if self.frames:
            last = self.frames[-1]
            reference_final = last.reference or last.mark

        reference_min = (
            self.min_reference if math.isfinite(self.min_reference) else reference_final
        )
        equity_end = math.fsum(
            a.collateral + a.realised_pnl + a.unrealised(reference_final)
            for a in self.accounts
        )
        counterfactual_end = math.fsum(
            self._counterfactual_equity(a, reference_final, reference_min)
            for a in self.accounts
        )
        deposits = math.fsum(a.deposits_credited for a in self.accounts)
        user_loss = self.equity_start + deposits - equity_end
        counterfactual_loss = self.equity_start + deposits - counterfactual_end

        summary = RunSummary(
            scenario_key=scenario.key,
            seed=self.seed,
            policy_version=self.params.version,
            controls=self.controls.as_dict(),
            ticks=len(self.frames),
            accounts_total=len(self.accounts),
            open_interest_start=self.open_interest_start,
            aggregate_collateral_start=self.collateral_start,
            accounts_liquidated=self.cum_liquidated_accounts,
            liquidated_notional=self.cum_liquidated_notional,
            unnecessary_liquidations=self.cum_unnecessary,
            unnecessary_notional=self.cum_unnecessary_notional,
            adl_accounts=self.cum_adl_accounts,
            adl_notional=self.cum_adl_notional,
            insurance_opening=self.liq.insurance_opening,
            insurance_final=self.liq.insurance_balance,
            insurance_drawn=max(0.0, self.liq.insurance_opening - self.liq.insurance_balance),
            margin_calls_opened=self.cum_margin_calls,
            saved_by_grace=self.cum_saved_grace,
            upi_credits_issued=self.cum_upi_credits,
            throttled_ticks=self.throttled_ticks,
            peak_unfilled_notional=self.peak_unfilled,
            max_divergence_bps=self.max_divergence_bps,
            peak_mark_pct=self._pct(self.max_mark),
            trough_mark_pct=self._pct(self.min_mark),
            trough_reference_pct=self._pct(self.min_reference),
            trough_book_pct=self._pct(self.min_book),
            min_depth_pct_of_baseline=self.min_depth,
            user_equity_start=self.equity_start,
            deposits_credited=deposits,
            user_equity_end=equity_end,
            user_loss=user_loss,
            counterfactual_equity_end=counterfactual_end,
            counterfactual_loss=counterfactual_loss,
            attributable_loss=user_loss - counterfactual_loss,
        )
        return RunResult(
            summary=summary,
            frames=self.frames,
            events=self.events,
            accounts=self.accounts,
            log=self.log,
        )

    def _counterfactual_equity(
        self, account: Account, reference_final: float, reference_min: float
    ) -> float:
        """What this account would be worth had it been processed at the
        Reference Composite instead of the disputed mark.

        This is NOT "what if nobody had ever been liquidated". An account that
        breaches maintenance margin even against the honest price would have
        been liquidated anyway, and restoring it would hand it a windfall.

        That exclusion is not our invention, which matters when a judge asks
        whether compensation is just moral hazard. OKX's January 2019 notice on
        its ETH futures index error is the template: it named the exact error
        windows, set a crediting deadline, did not roll anything back, and
        explicitly excluded "customers who experienced trading losses under
        normal circumstances". Compensate the defect, not the market.

        Getting this wrong inverts the sign of the whole measure: in a market
        that ends lower, holding an unliquidated position to the close loses
        more than being closed early, so a naive never-liquidated counterfactual
        reports the cascade as having HELPED.

        So: an account that survives at the honest price is restored and marked
        at the final Reference Composite. An account that does not survive it is
        valued where the honest price would have closed it.
        """
        restored_qty = account.qty + account.liquidated_qty
        if restored_qty <= 0.0:
            return account.collateral
        probe = Account(
            id=account.id,
            side=account.side,
            qty=restored_qty,
            entry_price=account.entry_price,
            leverage=account.leverage,
            collateral=account.collateral,
            mode=account.mode,
        )
        probe.collateral += account.deposits_credited
        if probe.equity(reference_min) < probe.mm_required(reference_min, self.params):
            return max(0.0, probe.equity(reference_min))
        return probe.equity(reference_final)

    def _pct(self, price: float) -> float:
        if not math.isfinite(price) or self.scenario.initial_price <= 0:
            return 0.0
        return (price / self.scenario.initial_price - 1.0) * 100.0
