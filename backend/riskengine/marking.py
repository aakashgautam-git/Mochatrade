"""Mark price construction. Never liquidate on last-traded price.

Binance's published method, mirrored because it is the industry reference:

    Price Index = sum(weight_i * spot_price_i), weight-normalised
    Mark Price  = median(Price1, Price2, Contract Price)
      Price1 = Index * (1 + lastFundingRate * timeToNextFunding / fundingPeriod)
      Price2 = Index + MovingAverage(30s basis)

Hyperliquid does the same thing structurally: liquidations use a mark that
combines external CEX prices with the venue's own book state, which is more
robust than any single instantaneous book price.

This module is the difference between amplifier 3 firing and not firing. Under
LTP marking a venue-local wick liquidates accounts that were solvent against
the composite. Under median marking the wick has to convince two of three
inputs, and the book alone is only one of them.

What the median does NOT do, and this matters enough to state plainly: it does
not protect against a bad oracle. Price1 and Price2 are both derived from the
Index, so a defective index carries two of the three legs and the mark follows
it wherever it goes. The median defends against a bad *book*; it is blind to a
bad *feed*.

That asymmetry is the reason the control stack has a separate oracle-health
monitor (control #2) that pauses liquidations on a suspect feed. Marking cannot
be the defence, because marking is downstream of the thing that broke. It is
also precisely the research brief's point about 10 Oct 2025: Binance had this
formula and still got hit, because the failure was never in the formula.

And it is why a class C event is MochaTrade's liability rather than the
market's. On a market we deployed, we chose the sources, we set the weights,
and the mark did what we told it to.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from enum import Enum

from .params import RiskParams


class MarkSource(Enum):
    PRICE1 = "price1"
    """Index carried forward by funding."""

    PRICE2 = "price2"
    """Index plus the smoothed basis."""

    CONTRACT = "contract"
    """The book's own mid."""

    LTP = "ltp"
    """No composite anchor at all. This is the control being OFF, and it is the
    single largest source of avoidable liquidations in the simulator."""


@dataclass(frozen=True, slots=True)
class MarkResult:
    mark: float
    source: MarkSource
    index: float | None
    price1: float | None
    price2: float | None
    contract_price: float
    basis_ma: float
    divergence_bps: float
    """Signed deviation of the mark from the Reference Composite, in bps. The
    primary auto-pager trigger at T+0..2, and criterion 1 of the APE test."""

    anchored: bool


@dataclass(slots=True)
class MarkCalculator:
    """Holds the rolling basis window. One instance per market per run."""

    params: RiskParams
    _basis: deque[float] = field(default_factory=deque)

    def __post_init__(self) -> None:
        self._basis = deque(maxlen=self.params.basis_ma_ticks)

    @property
    def basis_ma(self) -> float:
        if not self._basis:
            return 0.0
        return sum(self._basis) / len(self._basis)

    def step(
        self,
        *,
        index: float | None,
        contract_price: float,
        reference: float | None,
        funding_rate: float,
        seconds_to_next_funding: float,
        anchored: bool,
    ) -> MarkResult:
        """Produce this tick's mark.

        `index` is the live composite -- what we published, defects included.
        `reference` is the reconstructed honest composite, used only to measure
        divergence. Marking never reads it: you do not get to mark against a
        price you could not have known at the time.

        `anchored=False` is control #1 switched off: the mark becomes the book,
        and a venue-local wick liquidates everyone it touches.
        """
        if index is not None and index > 0.0:
            self._basis.append(contract_price - index)
        basis_ma = self.basis_ma

        if not anchored or index is None or index <= 0.0:
            mark = contract_price
            source = MarkSource.LTP if not anchored else MarkSource.CONTRACT
            price1 = price2 = None
        else:
            periods = seconds_to_next_funding / max(
                1.0, float(self.params.funding_period_seconds)
            )
            price1 = index * (1.0 + funding_rate * periods)
            price2 = index + basis_ma
            candidates = ((price1, MarkSource.PRICE1), (price2, MarkSource.PRICE2),
                          (contract_price, MarkSource.CONTRACT))
            mark, source = sorted(candidates, key=lambda c: c[0])[1]

        if reference and reference > 0.0:
            divergence = (mark - reference) / reference / 1e-4
        else:
            divergence = 0.0

        return MarkResult(
            mark=mark,
            source=source,
            index=index,
            price1=price1,
            price2=price2,
            contract_price=contract_price,
            basis_ma=basis_ma,
            divergence_bps=divergence,
            anchored=anchored,
        )
