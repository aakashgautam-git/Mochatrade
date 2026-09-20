"""Reference Composite Price, the degrading ladder, and oracle health.

The single most product-specific problem in the brief: MochaTrade's flagship is
US stock perps trading 24/7 in IST. US cash equities are open 19:00-01:30 IST,
so a 15% wick on a TSLA perp at 04:00 IST on a Sunday has no external reference
price at all. "Compare it to Binance" is not available. The composite must
therefore be defined ex ante, published, and able to degrade gracefully:

    L1  >=3 major spot venues (crypto) or the US cash market (equities, RTH)
    L2  index futures (ES/NQ) + ADRs + ETF NAV proxy
    L3  median of >=2 independent perp venues
    L4  no valid composite -> the market is force-flagged DEGRADED:
        max leverage 3x, reduce-only, liquidations paused

Two protections matter more than the weighting formula, both from Binance's
published index method:

- Outlier clamp: a source deviating more than the clamp from the median is
  capped at (1 +/- clamp) x median.
- Staleness kill: a source that has not updated inside the staleness window has
  its weight set to zero.

Binance had both on 10 Oct 2025 and still got hurt, because the defect was not
in the formula. It was that *collateral* was marked off a venue-local price:
USDe printed ~$0.65 on Binance while holding ~$1.00 everywhere else. The clamp
cannot save you once enough honest sources have dropped out and the survivor is
the liar, which is a failure this module models explicitly and which the
scenarios exercise.

Two composites are produced every tick and the distinction carries the whole
remediation story:

    live       what MochaTrade actually published and marked against, faults
               and all. This is the number that liquidated people.
    reference  the same ladder reconstructed from unfaulted sources. This is
               the Reference Composite the APE test compares against and the
               price a class C make-whole is computed at.

On a HIP-3 market MochaTrade sets this oracle and is slashable up to 100% of a
500,000 HYPE stake for a bad one. A bad oracle is not a refund problem here, it
is a slashing event.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Sequence

from .params import RiskParams
from .rng import Rng


class SourceKind(Enum):
    """What a price source is, which fixes the ladder rung it can serve."""

    SPOT_VENUE = "spot_venue"
    CASH_MARKET = "cash_market"
    INDEX_FUTURE = "index_future"
    ADR = "adr"
    ETF_NAV = "etf_nav"
    PERP_VENUE = "perp_venue"


RUNG_BY_KIND: dict[SourceKind, int] = {
    SourceKind.SPOT_VENUE: 1,
    SourceKind.CASH_MARKET: 1,
    SourceKind.INDEX_FUTURE: 2,
    SourceKind.ADR: 2,
    SourceKind.ETF_NAV: 2,
    SourceKind.PERP_VENUE: 3,
}


class FaultKind(Enum):
    DEVIATE = "deviate"
    """The source keeps updating but prints a wrong price. The dangerous one:
    it looks alive."""

    STALE = "stale"
    """The source stops updating. Caught by the staleness kill, but every source
    it takes out brings the composite closer to having no quorum."""

    DOWN = "down"
    """The source is unreachable."""

    CLOSED = "closed"
    """Not a fault: the cash market is simply shut. Modelled the same way so
    off-hours ladder degradation falls out of the same code path."""


class OracleHealth(Enum):
    HEALTHY = "healthy"
    SOURCES_DEGRADED = "sources_degraded"
    """Some sources dropped out; the composite still has quorum on its rung."""

    SUSPECT = "suspect"
    """A source was clamped, or the ladder fell to a lower rung. This is the
    trigger for auto reduce-only plus a liquidation pause. The trigger must be
    oracle health, never user pain: pausing liquidations while the feed is
    healthy converts user losses into MochaTrade's insolvency."""

    NO_COMPOSITE = "no_composite"
    """Ladder L4. Force-flag the market DEGRADED."""


@dataclass(frozen=True, slots=True)
class OracleSource:
    name: str
    kind: SourceKind
    weight: float = 1.0
    noise_bps: float = 6.0
    is_major: bool = False
    """Majors (BTC, ETH, SOL) get Binance's tighter 1% clamp."""

    @property
    def rung(self) -> int:
        return RUNG_BY_KIND[self.kind]


@dataclass(frozen=True, slots=True)
class SourceFault:
    """An injected defect on one source, active over a tick range."""

    source: str
    kind: FaultKind
    start_tick: int
    end_tick: int
    deviation_pct: float = 0.0
    """For DEVIATE: signed percent offset applied to the true price."""

    def active(self, tick: int) -> bool:
        return self.start_tick <= tick < self.end_tick


@dataclass(frozen=True, slots=True)
class SourceReading:
    """One source's contribution to one composite, kept for the evidence tape.

    The brief's point 3 in "what would make me stay as a user" is the raw tape,
    so the user can check the story themselves. This is that tape.
    """

    name: str
    kind: SourceKind
    rung: int
    weight: float
    raw_price: float
    used_price: float
    last_update_tick: int
    stale: bool
    down: bool
    clamped: bool
    faulted: bool
    used: bool = False
    """True if this reading fed the composite that was published this tick."""

    @property
    def contributed(self) -> bool:
        return self.used


@dataclass(frozen=True, slots=True)
class Composite:
    price: float | None
    rung: int
    health: OracleHealth
    readings: tuple[SourceReading, ...]
    n_used: int
    dispersion_bps: float
    reason: str

    @property
    def degraded(self) -> bool:
        return self.rung >= 4 or self.price is None


@dataclass(slots=True)
class OracleFeed:
    """The set of sources for one market, plus their injected faults."""

    sources: tuple[OracleSource, ...]
    faults: tuple[SourceFault, ...] = ()
    _last_update: dict[str, int] = field(default_factory=dict)
    _last_price: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for source in self.sources:
            self._last_update.setdefault(source.name, 0)
            self._last_price.setdefault(source.name, 0.0)

    def faults_for(self, name: str, tick: int) -> SourceFault | None:
        for fault in self.faults:
            if fault.source == name and fault.active(tick):
                return fault
        return None

    def observe(
        self, *, tick: int, true_price: float, rng: Rng
    ) -> tuple[tuple[SourceReading, ...], tuple[SourceReading, ...]]:
        """Produce this tick's raw readings.

        Returns (live, reference). `live` carries the injected faults: it is
        what MochaTrade actually saw. `reference` is the same tick rebuilt as
        if our defects had not happened, which is what a post-incident
        investigation reconstructs and what a class C make-whole is computed
        against. A genuinely CLOSED cash market is excluded from both, because
        that is market structure and not our failure.

        Staleness is deliberately NOT flagged here. A stale source keeps
        publishing its last price and keeps being believed until the staleness
        window expires -- that five-minute blind spot is real, and hiding it
        would flatter the design. `build_composite` derives the flag.
        """
        live: list[SourceReading] = []
        reference: list[SourceReading] = []

        for source in self.sources:
            noise = rng.normal(0.0, source.noise_bps * 1e-4)
            honest = true_price * (1.0 + noise)
            fault = self.faults_for(source.name, tick)

            if fault is None:
                price, down, faulted = honest, False, False
            elif fault.kind is FaultKind.DEVIATE:
                price = true_price * (1.0 + fault.deviation_pct / 100.0 + noise)
                down, faulted = False, True
            elif fault.kind is FaultKind.STALE:
                price = self._last_price.get(source.name) or honest
                down, faulted = False, True
            else:  # DOWN or CLOSED
                price = self._last_price.get(source.name) or honest
                down, faulted = True, True

            # A source that is down or stale does not refresh its timestamp.
            if fault is None or fault.kind is FaultKind.DEVIATE:
                self._last_update[source.name] = tick
                self._last_price[source.name] = price

            live.append(
                SourceReading(
                    name=source.name,
                    kind=source.kind,
                    rung=source.rung,
                    weight=source.weight,
                    raw_price=price,
                    used_price=price,
                    last_update_tick=self._last_update.get(source.name, tick),
                    stale=False,
                    down=down,
                    clamped=False,
                    faulted=faulted,
                )
            )

            closed = fault is not None and fault.kind is FaultKind.CLOSED
            reference.append(
                SourceReading(
                    name=source.name,
                    kind=source.kind,
                    rung=source.rung,
                    weight=source.weight,
                    raw_price=honest,
                    used_price=honest,
                    last_update_tick=tick,
                    stale=False,
                    down=closed,
                    clamped=False,
                    faulted=False,
                )
            )

        return tuple(live), tuple(reference)


def _median(values: Sequence[float]) -> float:
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    if n % 2 == 1:
        return ordered[mid]
    return 0.5 * (ordered[mid - 1] + ordered[mid])


def build_composite(
    readings: Sequence[SourceReading],
    params: RiskParams,
    *,
    tick: int,
    majors: bool = False,
    expected_rung: int = 1,
) -> Composite:
    """Walk the ladder and return the best composite available, with its rung.

    Rung selection is strictly best-first: L1, then L2, then L3. A rung is
    usable only if it has its published minimum number of live sources. That
    minimum is the whole defence against a single surviving liar setting the
    price for everyone -- when quorum fails the ladder steps down rather than
    trusting the survivor, and stepping down is itself a SUSPECT signal.

    Every reading is returned annotated, whether or not it fed the price. That
    is the evidence tape: a user can replay it and check our story.

    Degradation is judged against `expected_rung`, the rung this market is
    published as operating on in this session. A US equity perp at 04:00 IST is
    SUPPOSED to be on L2: the cash market is shut, and that is disclosed in
    advance. Treating the expected rung as SUSPECT would latch the health
    monitor on for the entire Indian trading day and pause liquidations
    permanently -- which is the exact failure the brief warns about, because
    pausing liquidations on a feed that is behaving as designed converts user
    losses into our insolvency. "Abnormal" is defined against a published
    baseline, never against whatever is convenient.
    """
    minimums = {
        1: params.composite_l1_min_sources,
        2: params.composite_l2_min_sources,
        3: params.composite_l3_min_sources,
    }
    clamp = params.clamp_pct_for(is_major=majors)
    stale_after = params.staleness_ticks

    # Staleness kill: a source that has not updated inside the window has its
    # weight set to zero. Binance's published rule, five minutes.
    annotated = [
        SourceReading(
            name=r.name,
            kind=r.kind,
            rung=r.rung,
            weight=r.weight,
            raw_price=r.raw_price,
            used_price=r.used_price,
            last_update_tick=r.last_update_tick,
            stale=(tick - r.last_update_tick) >= stale_after,
            down=r.down,
            clamped=False,
            faulted=r.faulted,
        )
        for r in readings
    ]
    live = [r for r in annotated if not r.down and not r.stale]

    for rung in (1, 2, 3):
        candidates = [r for r in live if r.rung == rung]
        # The brief defines L1 as ">=3 major spot venues (crypto) OR the US cash
        # market (equities, RTH)". The cash market is one authoritative venue,
        # not three correlated ones, so the quorum it has to meet is one. Using
        # the crypto minimum for an equity perp means L1 can never form and the
        # composite sits permanently below its published rung.
        required = minimums[rung]
        if rung == 1 and all(r.kind is SourceKind.CASH_MARKET for r in candidates):
            required = 1
        if len(candidates) < required:
            continue

        median = _median([r.used_price for r in candidates])
        if median <= 0.0:
            continue

        lo, hi = median * (1.0 - clamp), median * (1.0 + clamp)
        selected: dict[str, SourceReading] = {}
        any_clamped = False
        for r in candidates:
            used = min(max(r.used_price, lo), hi)
            was_clamped = used != r.used_price
            any_clamped = any_clamped or was_clamped
            selected[r.name] = SourceReading(
                name=r.name,
                kind=r.kind,
                rung=r.rung,
                weight=r.weight,
                raw_price=r.raw_price,
                used_price=used,
                last_update_tick=r.last_update_tick,
                stale=r.stale,
                down=r.down,
                clamped=was_clamped,
                faulted=r.faulted,
                used=True,
            )

        chosen = tuple(selected.values())
        total_weight = math.fsum(r.weight for r in chosen)
        if total_weight <= 0.0:
            continue
        price = math.fsum(r.used_price * r.weight for r in chosen) / total_weight
        dispersion = max(abs(r.used_price - median) for r in chosen) / median / 1e-4

        dropped = len(annotated) - len(live)
        if any_clamped:
            health = OracleHealth.SUSPECT
            reason = "a source was clamped against the median"
        elif rung > expected_rung:
            health = OracleHealth.SUSPECT
            reason = (
                f"composite fell to ladder L{rung}, below the published L"
                f"{expected_rung} for this session"
            )
        elif rung > 1:
            health = OracleHealth.SOURCES_DEGRADED
            reason = f"operating on ladder L{rung}, as published for this session"
        elif dropped:
            health = OracleHealth.SOURCES_DEGRADED
            reason = f"{dropped} source(s) stale or down, quorum held on L1"
        else:
            health = OracleHealth.HEALTHY
            reason = "all sources live on L1"

        tape = tuple(selected.get(r.name, r) for r in annotated)
        return Composite(
            price=price,
            rung=rung,
            health=health,
            readings=tape,
            n_used=len(chosen),
            dispersion_bps=dispersion,
            reason=reason,
        )

    return Composite(
        price=None,
        rung=4,
        health=OracleHealth.NO_COMPOSITE,
        readings=tuple(annotated),
        n_used=0,
        dispersion_bps=0.0,
        reason=(
            "no ladder rung reached quorum; market force-flagged DEGRADED "
            "(3x max leverage, reduce-only, liquidations paused)"
        ),
    )
