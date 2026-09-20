"""The anti-drift guard.

`RiskPolicy` is a mirror of `riskengine.params.RiskParams`, and this module is
what keeps it one. If a field is added to the dataclass and not to the model --
or the other way round -- the build fails here rather than silently running the
engine on a stale policy for the rest of the project.

It also asserts the round trip, because "the field exists" and "the field
survives a trip through the database" are different claims, and only the second
one matters to a seeded simulation.
"""
from __future__ import annotations

from dataclasses import fields as dataclass_fields
from decimal import Decimal

import pytest

from core.models import (
    ADMIN_ONLY_FIELDS,
    RELATED_PARAM_FIELDS,
    SCALAR_PARAM_NAMES,
    PolicyInstrumentTier,
    PolicyMarginTier,
    RiskPolicy,
)
from riskengine.params import DEFAULT_PARAMS, FIELD_SOURCES, RiskParams

pytestmark = pytest.mark.django_db


def _model_field_names() -> set[str]:
    return {f.name for f in RiskPolicy._meta.get_fields() if f.concrete}


def _param_field_names() -> set[str]:
    return {f.name for f in dataclass_fields(RiskParams)}


# -- the 1:1 correspondence ------------------------------------------------

def test_every_risk_param_exists_on_the_policy_model() -> None:
    """A parameter the engine reads that the policy cannot express is a
    parameter nobody can change without editing Python."""
    missing = _param_field_names() - _model_field_names() - set(RELATED_PARAM_FIELDS)
    assert not missing, f"RiskParams fields absent from RiskPolicy: {sorted(missing)}"


def test_every_policy_field_maps_back_to_a_risk_param() -> None:
    """A policy field the engine never reads is a knob wired to nothing, which
    is worse than no knob at all -- someone will turn it and expect an effect."""
    orphans = _model_field_names() - _param_field_names() - ADMIN_ONLY_FIELDS
    assert not orphans, f"RiskPolicy fields with no RiskParams counterpart: {sorted(orphans)}"


def test_the_two_field_sets_are_exactly_one_to_one() -> None:
    params = _param_field_names()
    model = _model_field_names() - ADMIN_ONLY_FIELDS
    related = set(RELATED_PARAM_FIELDS)
    assert model | related == params, (
        f"only in RiskParams: {sorted(params - model - related)}; "
        f"only in RiskPolicy: {sorted(model - params)}"
    )


def test_ladders_are_related_rows_not_json() -> None:
    """The margin ladder is five tiers, and a judge is more likely to want to
    change it live than anything else on the policy. It has to be editable."""
    for param_name, accessor in RELATED_PARAM_FIELDS.items():
        assert param_name in _param_field_names()
        assert hasattr(RiskPolicy, accessor)
        assert param_name not in _model_field_names()


# -- generated defaults and help text --------------------------------------

def test_defaults_are_read_from_the_dataclass_not_retyped() -> None:
    for name in SCALAR_PARAM_NAMES:
        field = RiskPolicy._meta.get_field(name)
        assert field.default == getattr(DEFAULT_PARAMS, name), (
            f"{name}: model default {field.default!r} != "
            f"dataclass default {getattr(DEFAULT_PARAMS, name)!r}"
        )


def test_help_text_is_the_citation_verbatim() -> None:
    """The string next to a number in the admin is the same string the policy
    page renders. One source of provenance, not two that drift."""
    for name in SCALAR_PARAM_NAMES:
        field = RiskPolicy._meta.get_field(name)
        assert field.help_text == FIELD_SOURCES[name]
        assert field.help_text, f"{name} has no citation"


# -- the round trip --------------------------------------------------------

def seeded_policy(version: str = "v1") -> RiskPolicy:
    from django.core.management import call_command

    call_command("seed_policy", policy_version=version, force=True, verbosity=0)
    return RiskPolicy.objects.get(version=version)


def test_to_params_reconstructs_the_dataclass_exactly() -> None:
    """Exact, not approximate. A seeded run reproduces byte-identically only if
    the policy hands the engine the same floats it started from."""
    policy = seeded_policy()
    assert policy.to_params() == DEFAULT_PARAMS


def test_margin_ladder_survives_the_percent_conversion() -> None:
    """16.7 / 100.0 is 0.16699999999999998. Storing maintenance margin as a
    percent for humans and a fraction for the engine has to go through Decimal
    or the top tier silently drifts."""
    policy = seeded_policy()
    rebuilt = policy.to_params()
    assert rebuilt.margin_tiers == DEFAULT_PARAMS.margin_tiers
    assert rebuilt.mm_rate(6_00_00_000.0) == 0.167


def test_round_trip_survives_a_database_reload() -> None:
    seeded_policy()
    reloaded = RiskPolicy.objects.get(version="v1")
    assert reloaded.to_params() == DEFAULT_PARAMS


def test_the_engine_accepts_what_the_policy_produces() -> None:
    """The point of all of the above."""
    from riskengine.controls import ControlStack
    from riskengine.engine import Engine
    from riskengine.scenario import by_key

    params = seeded_policy().to_params()
    scenario = by_key("macro_cascade")
    from_db = Engine(scenario, params, ControlStack.full()).run().summary
    from_code = Engine(scenario, DEFAULT_PARAMS, ControlStack.full()).run().summary
    assert from_db.as_dict() == from_code.as_dict()


# -- seeding ---------------------------------------------------------------

def test_seed_creates_exactly_one_active_policy() -> None:
    seeded_policy("v1")
    seeded_policy("v2")
    assert RiskPolicy.objects.filter(is_active=True).count() == 1
    assert RiskPolicy.objects.get(is_active=True).version == "v2"


def test_published_ladders_are_seeded_with_the_table_from_the_brief() -> None:
    policy = seeded_policy()
    tiers = list(policy.instrument_tier_rows.order_by("tier"))
    assert [(t.tier, t.nrr_pct, t.nrr_offhours_pct) for t in tiers] == [
        (1, 3.0, 5.0),
        (2, 5.0, 8.0),
        (3, 10.0, 15.0),
    ]
    assert [t.dcb_variant_pct for t in tiers] == [2.5, 5.0, 10.0]

    ladder = list(policy.margin_tier_rows.order_by("ordering"))
    assert [(t.max_leverage, t.mm_pct) for t in ladder] == [
        (50.0, 1.0), (25.0, 2.0), (10.0, 5.0), (5.0, 10.0), (3.0, pytest.approx(16.7)),
    ]
    assert ladder[-1].notional_ceiling is None  # top tier is unbounded


def test_acceptance_readout() -> None:
    """The literal acceptance check from the phase spec."""
    seeded_policy()
    assert RiskPolicy.objects.get(is_active=True).nrr_tier1_pct == 3.0
