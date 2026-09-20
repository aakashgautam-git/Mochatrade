"""Mark price: the median, and the one thing it cannot protect against."""
from __future__ import annotations

import pytest

from riskengine.marking import MarkCalculator, MarkSource
from riskengine.params import DEFAULT_PARAMS as P


def warm(calc: MarkCalculator, *, index: float, book: float, ticks: int = 30) -> None:
    for _ in range(ticks):
        calc.step(
            index=index,
            contract_price=book,
            reference=index,
            funding_rate=0.0001,
            seconds_to_next_funding=1800.0,
            anchored=True,
        )


def step(calc: MarkCalculator, *, index, book, reference, anchored=True):
    return calc.step(
        index=index,
        contract_price=book,
        reference=reference,
        funding_rate=0.0001,
        seconds_to_next_funding=1800.0,
        anchored=anchored,
    )


def test_median_absorbs_a_venue_local_wick() -> None:
    """A 15% wick on the book has to convince two of three inputs. It cannot."""
    calc = MarkCalculator(P)
    warm(calc, index=100.0, book=100.0)
    result = step(calc, index=100.0, book=85.0, reference=100.0)
    assert result.mark > 99.0
    assert result.source is not MarkSource.CONTRACT
    assert abs(result.divergence_bps) < 100.0


def test_ltp_marking_passes_the_wick_straight_through() -> None:
    """Control #1 switched off. This is the single largest source of avoidable
    liquidations in the simulator."""
    calc = MarkCalculator(P)
    warm(calc, index=100.0, book=100.0)
    result = step(calc, index=100.0, book=85.0, reference=100.0, anchored=False)
    assert result.mark == 85.0
    assert result.source is MarkSource.LTP
    assert result.divergence_bps == pytest.approx(-1500.0, rel=1e-6)


def test_median_is_blind_to_a_bad_oracle() -> None:
    """Price1 and Price2 both derive from the Index, so a defective index
    carries two of three legs and the mark follows it. The median defends
    against a bad book; it cannot defend against a bad feed. That asymmetry is
    exactly why the control stack needs a separate oracle-health monitor."""
    calc = MarkCalculator(P)
    warm(calc, index=100.0, book=100.0)
    result = step(calc, index=90.0, book=100.0, reference=100.0)
    assert result.mark < 91.0
    assert result.divergence_bps < -900.0


def test_basis_leg_is_a_moving_average_not_a_snapshot() -> None:
    calc = MarkCalculator(P)
    warm(calc, index=100.0, book=100.0)
    assert calc.basis_ma == pytest.approx(0.0, abs=1e-9)
    for _ in range(5):
        step(calc, index=100.0, book=90.0, reference=100.0)
    assert -10.0 < calc.basis_ma < 0.0


def test_basis_window_is_thirty_samples() -> None:
    assert P.basis_ma_ticks == 30
    calc = MarkCalculator(P)
    for _ in range(100):
        step(calc, index=100.0, book=90.0, reference=100.0)
    assert calc.basis_ma == pytest.approx(-10.0, rel=1e-6)


def test_no_composite_falls_back_to_the_book() -> None:
    """Ladder L4. The mark has nothing to anchor to, which is precisely why L4
    also forces reduce-only and pauses liquidations."""
    calc = MarkCalculator(P)
    result = step(calc, index=None, book=88.0, reference=100.0)
    assert result.mark == 88.0
    assert result.source is MarkSource.CONTRACT


def test_marking_never_reads_the_reference_price() -> None:
    """You do not get to mark against a price you could not have known at the
    time. `reference` measures divergence and nothing else."""
    calc_a, calc_b = MarkCalculator(P), MarkCalculator(P)
    warm(calc_a, index=100.0, book=100.0)
    warm(calc_b, index=100.0, book=100.0)
    a = step(calc_a, index=97.0, book=96.0, reference=100.0)
    b = step(calc_b, index=97.0, book=96.0, reference=42.0)
    assert a.mark == b.mark
    assert a.divergence_bps != b.divergence_bps


def test_funding_leg_carries_the_index() -> None:
    calc = MarkCalculator(P)
    result = calc.step(
        index=100.0,
        contract_price=100.0,
        reference=100.0,
        funding_rate=0.01,
        seconds_to_next_funding=float(P.funding_period_seconds),
        anchored=True,
    )
    assert result.price1 == pytest.approx(101.0, rel=1e-9)
