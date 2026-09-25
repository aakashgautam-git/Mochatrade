"""The risk-control stack, the volatility-control layers, and the Protect Switch.

This module is the proof. The app's second job is to show that these controls
measurably reduce damage: run the identical seeded shock with the stack off,
then on, and quantify the delta. So every control is independently togglable
and every one maps to an amplifier it kills.

Ranked by damage reduction per engineering-week (research brief section 8):

     1. Mark = oracle-anchored composite with clamp + staleness kill, never LTP
     2. Oracle health monitor -> auto reduce-only + liquidation pause
     3. Liquidation TWAP throttle + max participation rate of resting depth
     4. Time-of-day leverage caps for equity perps (50x RTH -> 5x off-hours)
     5. Margin-call grace window + one-tap top-up + pre-funded UPI buffer
     6. Two-stage partial liquidation (market first, backstop below 2/3 MM)
     7. Published APE policy + funded Incident Reserve       (policy, phase 6)
     8. Status page + automated comms + evidence snapshotter (product)
     9. Isolated-margin default for long-tail; vol-scaled haircuts
    10. Quarterly game-day: run this playbook against the simulator

Volatility control mechanisms are layered because no single control can do the
job (CFTC/FIA, Sept 2023):

    pre-trade price bands -> velocity logic (~5s pause) -> dynamic circuit
    breakers (60-min rolling look-back, 2-min pre-open) -> daily price limits

The transparency rule is part of the design and not decoration: parameters must
be publicly available and replicable so a participant can compute the triggers
themselves, with market-wide notification when a control fires. Everything here
reads its numbers from RiskParams, which is published.

The Protect Switch (playbook T+2..5) is one pre-authorised action, no approval
needed: risk-increasing orders become reduce-only, the liquidation engine goes
to TWAP throttle, max leverage drops to 3x, and if the oracle is suspect,
liquidations pause on that market only. `haltTrading` stays holstered, because
it cancels all orders and settles everyone at the current mark -- the very mark
under dispute. Halting is how a pricing dispute becomes a settlement dispute.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field, replace
from enum import Enum

from .params import RiskParams


@dataclass(frozen=True, slots=True)
class ControlStack:
    """Which controls are switched on. Frozen: a change is a new stack."""

    oracle_anchored_mark: bool = False
    oracle_health_monitor: bool = False
    liquidation_throttle: bool = False
    time_of_day_leverage_caps: bool = False
    margin_grace_window: bool = False
    upi_prefunded_credit: bool = False
    two_stage_liquidation: bool = False
    pre_trade_price_bands: bool = False
    velocity_logic: bool = False
    dynamic_circuit_breaker: bool = False
    isolated_margin_default: bool = False

    @classmethod
    def none(cls) -> "ControlStack":
        """Every control off. The counterfactual: what the crash costs when a
        broker ships the obvious thing and nothing else."""
        return cls()

    @classmethod
    def full(cls) -> "ControlStack":
        """Every control on. The proposal."""
        return cls(
            oracle_anchored_mark=True,
            oracle_health_monitor=True,
            liquidation_throttle=True,
            time_of_day_leverage_caps=True,
            margin_grace_window=True,
            upi_prefunded_credit=True,
            two_stage_liquidation=True,
            pre_trade_price_bands=True,
            velocity_logic=True,
            dynamic_circuit_breaker=True,
            isolated_margin_default=True,
        )

    def with_only(self, name: str) -> "ControlStack":
        """One control on, everything else off. Isolates a single control's
        contribution so the proof page can attribute the delta."""
        return replace(ControlStack.none(), **{name: True})

    def without(self, name: str) -> "ControlStack":
        """Everything except one. The other half of attribution: what does
        removing this one control cost?"""
        return replace(self, **{name: False})

    @property
    def enabled(self) -> tuple[str, ...]:
        return tuple(k for k, v in self.as_dict().items() if v)

    def as_dict(self) -> dict[str, bool]:
        return {
            "oracle_anchored_mark": self.oracle_anchored_mark,
            "oracle_health_monitor": self.oracle_health_monitor,
            "liquidation_throttle": self.liquidation_throttle,
            "time_of_day_leverage_caps": self.time_of_day_leverage_caps,
            "margin_grace_window": self.margin_grace_window,
            "upi_prefunded_credit": self.upi_prefunded_credit,
            "two_stage_liquidation": self.two_stage_liquidation,
            "pre_trade_price_bands": self.pre_trade_price_bands,
            "velocity_logic": self.velocity_logic,
            "dynamic_circuit_breaker": self.dynamic_circuit_breaker,
            "isolated_margin_default": self.isolated_margin_default,
        }


CONTROL_LABELS: dict[str, str] = {
    "oracle_anchored_mark": "Oracle-anchored mark price (never LTP)",
    "oracle_health_monitor": "Oracle health monitor -> reduce-only + liq pause",
    "liquidation_throttle": "Liquidation TWAP throttle + participation cap",
    "time_of_day_leverage_caps": "Time-of-day leverage caps",
    "margin_grace_window": "Margin-call grace window",
    "upi_prefunded_credit": "Pre-funded UPI margin credit",
    "two_stage_liquidation": "Two-stage partial liquidation",
    "pre_trade_price_bands": "Pre-trade price bands",
    "velocity_logic": "Velocity logic",
    "dynamic_circuit_breaker": "Dynamic circuit breaker",
    "isolated_margin_default": "Isolated margin by default",
}

CONTROL_KILLS: dict[str, str] = {
    "oracle_anchored_mark": "Amplifier 3 - the price feed as the weapon",
    "oracle_health_monitor": "Amplifier 3 - liquidating on a feed we distrust",
    "liquidation_throttle": "Amplifier 1 - the engine as the largest seller",
    "time_of_day_leverage_caps": "The product's own worst vector - 50x off-hours",
    "margin_grace_window": "Amplifiers 1 and 5, and the UPI dependency",
    "upi_prefunded_credit": "The imported NPCI uptime risk",
    "two_stage_liquidation": "Amplifier 1 - punitive closes before market ones",
    "pre_trade_price_bands": "A single client's algo bug (Binance.US, Oct 2021)",
    "velocity_logic": "The micro-scale leg of the cascade",
    "dynamic_circuit_breaker": "The meso-scale leg of the cascade",
    "isolated_margin_default": "Amplifier 4 - one bad asset wiping a portfolio",
}


class ActionKind(Enum):
    """What the operator can do in the war room. Every one of these changes the
    simulation; none of them is cosmetic."""

    PROTECT_SWITCH = "protect_switch"
    REDUCE_ONLY = "reduce_only"
    PAUSE_LIQUIDATIONS = "pause_liquidations"
    RESUME_LIQUIDATIONS = "resume_liquidations"
    SET_MAX_LEVERAGE = "set_max_leverage"
    THROTTLE_LIQUIDATIONS = "throttle_liquidations"
    HALT_TRADING = "halt_trading"
    STAGED_REOPEN = "staged_reopen"
    SNAPSHOT_EVIDENCE = "snapshot_evidence"
    PUBLISH_UPDATE = "publish_update"


@dataclass(frozen=True, slots=True)
class OperatorAction:
    """A decision taken at a given tick. Replayed as part of the determinism
    contract: same seed plus same action sequence gives the same output."""

    tick: int
    kind: ActionKind
    value: float | None = None
    note: str = ""


class ReopenStage(Enum):
    HALTED = "halted"
    REDUCE_ONLY = "reduce_only"
    POST_ONLY = "post_only"
    AUCTION = "auction"
    CONTINUOUS = "continuous"


@dataclass(slots=True)
class MarketFlags:
    """The live state of every switch the operator and the automation share."""

    reduce_only: bool = False
    liquidations_paused: bool = False
    halted: bool = False
    max_leverage: float = 50.0
    stage: ReopenStage = ReopenStage.CONTINUOUS
    dcb_paused_until: int | None = None
    velocity_paused_until: int | None = None
    protect_switch_tick: int | None = None
    halt_tick: int | None = None
    evidence_snapshot_ticks: tuple[int, ...] = ()
    notes: tuple[str, ...] = ()

    @property
    def trading_paused(self) -> bool:
        return (
            self.halted
            or self.dcb_paused_until is not None
            or self.velocity_paused_until is not None
        )

    def tick_expiries(self, tick: int) -> None:
        if self.dcb_paused_until is not None and tick >= self.dcb_paused_until:
            self.dcb_paused_until = None
            self.notes += ("DCB pause expired; reopening through auction",)
        if self.velocity_paused_until is not None and tick >= self.velocity_paused_until:
            self.velocity_paused_until = None


@dataclass(slots=True)
class CircuitBreaker:
    """Meso layer. CME's dynamic circuit breaker: a rolling look-back high/low
    plus or minus the variant; a breach triggers a short pre-open; the look-back
    window restarts on resume."""

    params: RiskParams
    tier: int
    offhours: bool
    _window: deque[float] = field(default_factory=deque)

    def __post_init__(self) -> None:
        self._window = deque(maxlen=self.params.dcb_lookback_ticks)

    @property
    def variant_pct(self) -> float:
        return self.params.dcb_variant_pct(self.tier, offhours=self.offhours)

    def bounds(self) -> tuple[float, float] | None:
        if len(self._window) < 2:
            return None
        lo, hi = min(self._window), max(self._window)
        variant = self.variant_pct / 100.0
        return lo * (1.0 - variant), hi * (1.0 + variant)

    def check(self, price: float) -> bool:
        """True if this price breaches the band. Call before pushing."""
        bounds = self.bounds()
        if bounds is None:
            return False
        lower, upper = bounds
        return price < lower or price > upper

    def push(self, price: float) -> None:
        self._window.append(price)

    def restart(self) -> None:
        """The look-back window restarts on resume, per CME. Without this, the
        pre-crash high keeps the band open forever and the breaker never re-arms."""
        self._window.clear()


@dataclass(frozen=True, slots=True)
class VelocityPause:
    """One firing of the velocity layer."""

    tick: int
    until: int
    level: int
    escalated: bool

    @property
    def ticks(self) -> int:
        return self.until - self.tick


@dataclass(slots=True)
class VelocityMonitor:
    """Micro layer. Analyses moves over seconds and calls a brief pause to let
    participants reassess. CFTC/FIA cite about five seconds.

    Two rules on top of the raw trigger, both learned the hard way:

    - Cooldown. After a pause ends, the layer may not fire again for
      `velocity_cooldown_seconds`. Without it, a falling market re-triggers three
      seconds after every reopen and trading stutters: 56 pauses in one run.
    - Escalation. If the move is still too fast in the first window after the
      cooldown, the next pause is longer rather than the same length again. A
      market that has not calmed in 30 seconds will not calm in another five.
      A full calm window after the cooldown resets the ladder.
    """

    params: RiskParams
    tier: int
    offhours: bool
    _window: deque[float] = field(default_factory=deque)
    level: int = 0
    paused_until: int | None = None
    cooldown_until: int | None = None
    fires: int = 0

    def __post_init__(self) -> None:
        self._window = deque(maxlen=self.params.velocity_window_ticks)

    @property
    def trigger_pct(self) -> float:
        return self.params.velocity_trigger_pct(self.tier, offhours=self.offhours)

    def check(self, price: float) -> bool:
        breached = False
        if len(self._window) >= 2:
            first = self._window[0]
            if first > 0.0:
                move = abs(price - first) / first * 100.0
                breached = move >= self.trigger_pct
        self._window.append(price)
        return breached

    def restart(self) -> None:
        self._window.clear()

    def step(self, price: float, tick: int) -> VelocityPause | None:
        """Observe this tick's price; return a pause if the layer fires now.

        The price is always pushed, so the window keeps measuring through pauses
        and cooldowns and a check at cooldown end sees the real recent move.
        """
        breached = self.check(price)

        if self.paused_until is not None:
            if tick < self.paused_until:
                return None
            self.cooldown_until = self.paused_until + self.params.velocity_cooldown_ticks
            self.paused_until = None

        if self.cooldown_until is not None and tick < self.cooldown_until:
            return None

        escalation_window_open = (
            self.cooldown_until is not None
            and tick < self.cooldown_until + self.params.velocity_window_ticks
        )
        if not breached:
            if self.cooldown_until is not None and not escalation_window_open:
                self.level = 0
            return None

        self.level = self.level + 1 if escalation_window_open else 0
        until = tick + self.params.velocity_pause_ticks(self.level)
        self.paused_until = until
        self.fires += 1
        return VelocityPause(tick=tick, until=until, level=self.level, escalated=self.level > 0)


def apply_action(
    action: OperatorAction,
    flags: MarketFlags,
    params: RiskParams,
) -> str:
    """Apply one operator decision to the market flags and describe it.

    The returned string is the war-room log line, so it has to be honest about
    the cost of the decision as well as its benefit. Reduce-only lets people
    leave but blocks the trader who wanted to add margin or fade the move; that
    cost is named here, not hidden.
    """
    if action.kind is ActionKind.PROTECT_SWITCH:
        flags.reduce_only = True
        flags.max_leverage = params.max_leverage_degraded
        flags.stage = ReopenStage.REDUCE_ONLY
        flags.protect_switch_tick = action.tick
        return (
            "Protect Switch thrown: reduce-only, liquidation engine throttled, "
            f"max leverage {params.max_leverage_degraded:.0f}x. Cost accepted: "
            "traders who wanted to add margin or fade the move are blocked too."
        )

    if action.kind is ActionKind.REDUCE_ONLY:
        flags.reduce_only = True
        flags.stage = ReopenStage.REDUCE_ONLY
        return "Risk-increasing orders rejected; positions can still be closed."

    if action.kind is ActionKind.PAUSE_LIQUIDATIONS:
        flags.liquidations_paused = True
        return (
            "Liquidations paused on this market. Valid only while the price is "
            "suspect: pausing on a healthy feed converts user losses into ours."
        )

    if action.kind is ActionKind.RESUME_LIQUIDATIONS:
        flags.liquidations_paused = False
        return "Liquidations resumed; oracle health restored."

    if action.kind is ActionKind.SET_MAX_LEVERAGE:
        flags.max_leverage = float(action.value or params.max_leverage_degraded)
        return f"Max leverage set to {flags.max_leverage:.0f}x."

    if action.kind is ActionKind.THROTTLE_LIQUIDATIONS:
        return (
            "Liquidation engine throttled to the published participation cap "
            f"({params.twap_max_participation_pct:.0%} of resting depth per "
            f"{params.twap_slice_ms}ms slice)."
        )

    if action.kind is ActionKind.HALT_TRADING:
        flags.halted = True
        flags.halt_tick = action.tick
        flags.stage = ReopenStage.HALTED
        return (
            "haltTrading called. This cancels all orders and settles every "
            "position at the current mark -- the mark under dispute. A pricing "
            "dispute is now a settlement dispute. Nuclear option, used."
        )

    if action.kind is ActionKind.STAGED_REOPEN:
        order = (
            ReopenStage.HALTED,
            ReopenStage.REDUCE_ONLY,
            ReopenStage.POST_ONLY,
            ReopenStage.AUCTION,
            ReopenStage.CONTINUOUS,
        )
        idx = min(order.index(flags.stage) + 1, len(order) - 1)
        flags.stage = order[idx]
        if flags.stage is ReopenStage.CONTINUOUS:
            flags.reduce_only = False
            flags.halted = False
        return (
            f"Reopen advanced to {flags.stage.value}. Never straight into "
            "continuous trading, or you print a second wick on the reopen."
        )

    if action.kind is ActionKind.SNAPSHOT_EVIDENCE:
        flags.evidence_snapshot_ticks += (action.tick,)
        return (
            "Write-once snapshot taken: L2 book, trade tape, per-source oracle "
            "inputs, mark series, liquidation events, app/API telemetry, "
            "deposit queue. Retained two years per the SEBI glitch framework."
        )

    if action.kind is ActionKind.PUBLISH_UPDATE:
        flags.notes += (action.note or "Public update published.",)
        return action.note or "Public update published."

    return "No-op."
