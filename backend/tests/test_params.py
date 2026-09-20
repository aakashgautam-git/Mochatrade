"""RiskPolicy v1: the numbers, and their provenance.

These assertions are deliberately literal. If someone changes a risk parameter,
they should have to change a test that states the old value out loud, and then
go and change the citation next to it.
"""
from __future__ import annotations

from dataclasses import fields

import pytest

from riskengine.params import (
    DEFAULT_PARAMS,
    DERIVED_FIELDS,
    FIELD_SOURCES,
    RiskParams,
)

LAKH = 1_00_000.0
CRORE = 1_00_00_000.0


def test_every_field_has_a_citation() -> None:
    """No unsourced risk parameter, ever. Phase 2 renders these as help_text."""
    names = {f.name for f in fields(RiskParams)} - {"version"}
    assert names == set(FIELD_SOURCES), (
        f"missing citations: {sorted(names - set(FIELD_SOURCES))}; "
        f"orphan citations: {sorted(set(FIELD_SOURCES) - names)}"
    )


def test_derived_fields_are_declared_as_such() -> None:
    """Three values are ours, not the brief's. They say so in their own text."""
    assert DERIVED_FIELDS == {
        "partial_liq_target_mm_multiple",
        "velocity_trigger_frac_of_dcb",
        "price_band_frac_of_dcb",
    }


@pytest.mark.parametrize(
    ("notional", "max_leverage", "mm_rate"),
    [
        (50_000.0, 50.0, 0.010),
        (5 * LAKH, 50.0, 0.010),
        (5 * LAKH + 1, 25.0, 0.020),
        (25 * LAKH, 25.0, 0.020),
        (25 * LAKH + 1, 10.0, 0.050),
        (1 * CRORE, 10.0, 0.050),
        (1 * CRORE + 1, 5.0, 0.100),
        (5 * CRORE, 5.0, 0.100),
        (5 * CRORE + 1, 3.0, 0.167),
        (50 * CRORE, 3.0, 0.167),
    ],
)
def test_margin_ladder_boundaries(notional: float, max_leverage: float, mm_rate: float) -> None:
    assert DEFAULT_PARAMS.max_leverage_for_notional(notional) == max_leverage
    assert DEFAULT_PARAMS.mm_rate(notional) == mm_rate


def test_margin_ladder_is_monotonic() -> None:
    """Bigger positions are never cheaper to carry."""
    tiers = DEFAULT_PARAMS.margin_tiers
    assert [t.mm_rate for t in tiers] == sorted(t.mm_rate for t in tiers)
    assert [t.max_leverage for t in tiers] == sorted(
        (t.max_leverage for t in tiers), reverse=True
    )


@pytest.mark.parametrize(
    ("tier", "rth", "offhours"),
    [(1, 3.0, 5.0), (2, 5.0, 8.0), (3, 10.0, 15.0)],
)
def test_non_reviewable_ranges(tier: int, rth: float, offhours: float) -> None:
    """The published NRR table. This is what "abnormal" means, defined ex ante."""
    assert DEFAULT_PARAMS.nrr_pct(tier, offhours=False) == rth
    assert DEFAULT_PARAMS.nrr_pct(tier, offhours=True) == offhours


@pytest.mark.parametrize(("tier", "variant"), [(1, 2.5), (2, 5.0), (3, 10.0)])
def test_dcb_variants_and_offhours_multiplier(tier: int, variant: float) -> None:
    assert DEFAULT_PARAMS.dcb_variant_pct(tier, offhours=False) == variant
    assert DEFAULT_PARAMS.dcb_variant_pct(tier, offhours=True) == pytest.approx(
        variant * 1.6
    )


def test_velocity_fires_before_the_circuit_breaker() -> None:
    """The four volatility layers only work if they fire in order: micro before
    meso. That is the whole point of layering them."""
    for tier in (1, 2, 3):
        for offhours in (False, True):
            velocity = DEFAULT_PARAMS.velocity_trigger_pct(tier, offhours=offhours)
            dcb = DEFAULT_PARAMS.dcb_variant_pct(tier, offhours=offhours)
            assert velocity < dcb


def test_throttle_and_grace_values() -> None:
    assert DEFAULT_PARAMS.twap_slice_ms == 250
    assert DEFAULT_PARAMS.twap_slices_per_tick == 4
    assert DEFAULT_PARAMS.twap_max_participation_pct == 0.20
    assert DEFAULT_PARAMS.twap_participation_band_pct == 0.01
    assert DEFAULT_PARAMS.margin_grace_seconds == 120


def test_compensation_cap_is_below_the_reserve() -> None:
    """The per-incident cap is deliberately finite and deliberately binding. An
    honest finite promise beats an implied infinite one you will break."""
    assert DEFAULT_PARAMS.incident_reserve_opening_inr == 2 * CRORE
    assert DEFAULT_PARAMS.per_incident_cap_inr == 1.5 * CRORE
    assert DEFAULT_PARAMS.per_incident_cap_inr < DEFAULT_PARAMS.incident_reserve_opening_inr


def test_backstop_threshold_is_two_thirds() -> None:
    """Hyperliquid's two-stage design: market first, backstop only below 2/3 MM."""
    assert DEFAULT_PARAMS.backstop_threshold(3000.0) == pytest.approx(2000.0)


def test_params_are_frozen_and_versioned() -> None:
    """A policy change is a new version, not a mutation."""
    with pytest.raises(Exception):
        DEFAULT_PARAMS.outlier_clamp_pct = 0.05  # type: ignore[misc]
    evolved = DEFAULT_PARAMS.evolve(version="v2", outlier_clamp_pct=0.05)
    assert evolved.outlier_clamp_pct == 0.05
    assert DEFAULT_PARAMS.outlier_clamp_pct == 0.03
