"""Model behaviour: incident codes, the append-only log, claims, invariants."""
from __future__ import annotations

from decimal import Decimal

import pytest
from django.apps import apps
from django.db import models
from django.utils import timezone

from core.models import (
    Claim,
    ClaimStatus,
    Classification,
    CommsUpdate,
    Incident,
    IncidentAction,
    Instrument,
    RiskPolicy,
    Scenario,
    SimAccount,
    SimRun,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def policy() -> RiskPolicy:
    from django.core.management import call_command

    call_command("seed_policy", force=True, verbosity=0)
    return RiskPolicy.objects.get(is_active=True)


@pytest.fixture
def instrument() -> Instrument:
    return Instrument.objects.create(
        symbol="BTC-PERP", display_name="Bitcoin perpetual", asset_class="CRYPTO",
        tier=1, has_rth=False, base_price=Decimal("9200000"), max_leverage=50.0,
    )


@pytest.fixture
def scenario(instrument: Instrument) -> Scenario:
    return Scenario.objects.create(
        name="Macro cascade", slug="macro-cascade", instrument=instrument,
        seed=20251010, shock_pct=-14.5, shock_duration_s=110, total_duration_s=720,
        book_depth_inr=Decimal("3500000"), n_accounts=1200,
    )


@pytest.fixture
def run(scenario: Scenario, policy: RiskPolicy) -> SimRun:
    return SimRun.objects.create(
        scenario=scenario, policy=policy, controls_enabled=False,
        seed=20251010, total_ticks=720,
    )


# -- structural conventions ------------------------------------------------

def test_every_model_has_str_and_ordering() -> None:
    for model in apps.get_app_config("core").get_models():
        assert model._meta.ordering, f"{model.__name__} has no Meta.ordering"
        assert "__str__" in model.__dict__, f"{model.__name__} has no __str__"


def test_every_model_is_registered_in_admin() -> None:
    from django.contrib import admin

    registered = set(admin.site._registry)
    for model in apps.get_app_config("core").get_models():
        if model._meta.verbose_name in {"margin tier", "instrument tier"}:
            continue  # edited as inlines on the policy they belong to
        assert model in registered, f"{model.__name__} is not registered in admin"


def test_admin_headers_name_the_product_and_the_thesis() -> None:
    from django.contrib import admin

    assert admin.site.site_header == "MochaTrade Crisis Command"
    assert "made whole" in admin.site.index_title


def test_foreign_keys_are_covered_by_list_select_related() -> None:
    """Otherwise the incident list page issues a query per row, which is exactly
    the kind of thing that stalls a live demo."""
    from django.contrib import admin

    for model, model_admin in admin.site._registry.items():
        has_fk = any(
            isinstance(f, (models.ForeignKey, models.OneToOneField))
            for f in model._meta.get_fields()
            if getattr(f, "concrete", False)
        )
        shows_fk = any(
            isinstance(model._meta.get_field(name), models.ForeignKey)
            for name in model_admin.list_display
            if name in {f.name for f in model._meta.get_fields() if getattr(f, "concrete", False)}
        )
        if has_fk and shows_fk:
            assert model_admin.list_select_related, (
                f"{model.__name__}Admin shows a FK in list_display without "
                f"list_select_related"
            )


# -- RiskPolicy ------------------------------------------------------------

def test_only_one_policy_can_be_active(policy: RiskPolicy) -> None:
    second = RiskPolicy.objects.create(version="v9", is_active=True)
    policy.refresh_from_db()
    assert not policy.is_active
    assert RiskPolicy.objects.filter(is_active=True).get() == second


def test_policy_str_flags_the_active_one(policy: RiskPolicy) -> None:
    assert str(policy) == "RiskPolicy v1 (active)"


# -- Incident --------------------------------------------------------------

def test_incident_code_is_generated_and_sequential() -> None:
    first = Incident.objects.create()
    second = Incident.objects.create()
    today = timezone.localtime(timezone.now()).date()
    assert first.code == f"INC-{today:%Y%m%d}-01"
    assert second.code == f"INC-{today:%Y%m%d}-02"


def test_incident_code_is_not_overwritten_on_later_saves() -> None:
    incident = Incident.objects.create()
    code = incident.code
    incident.status = "CONTAINED"
    incident.save()
    incident.refresh_from_db()
    assert incident.code == code


def test_explicit_incident_code_is_respected() -> None:
    assert Incident.objects.create(code="INC-20251010-42").code == "INC-20251010-42"


@pytest.mark.parametrize(
    ("classification", "owes"),
    [
        (Classification.A, False),  # genuine move: no remedy, publish the tape
        (Classification.B, False),  # thin book: fee rebate, no cash
        (Classification.C, True),   # our oracle: full make-whole
        (Classification.D, True),   # our outage: make-whole in window
        (Classification.E, True),   # UPI delay: we chose the rail
        (Classification.F, False),  # venue or ADL: no cash liability
        (Classification.G, False),  # manipulation: reserve, not remedy
        (Classification.UNCLASSIFIED, False),
    ],
)
def test_remedy_matrix_decides_who_pays(classification: str, owes: bool) -> None:
    incident = Incident.objects.create(classification=classification)
    assert incident.owes_cash_remedy is owes


def test_minutes_open_uses_resolution_time_when_resolved() -> None:
    declared = timezone.now() - timezone.timedelta(minutes=60)
    incident = Incident.objects.create(
        declared_at=declared, resolved_at=declared + timezone.timedelta(minutes=45)
    )
    assert incident.minutes_open == 45.0


# -- IncidentAction: the audit log ----------------------------------------

def test_action_log_admin_refuses_add_change_and_delete() -> None:
    """Append-only, enforced rather than merely intended. A log that can be
    rewritten after the fact is worth nothing."""
    from django.contrib import admin

    model_admin = admin.site._registry[IncidentAction]
    assert model_admin.has_add_permission(None) is False
    assert model_admin.has_change_permission(None) is False
    assert model_admin.has_change_permission(None, object()) is False
    assert model_admin.has_delete_permission(None) is False
    assert model_admin.has_delete_permission(None, object()) is False


def test_action_log_fields_are_all_read_only() -> None:
    from django.contrib import admin

    model_admin = admin.site._registry[IncidentAction]
    editable = {
        f.name for f in IncidentAction._meta.get_fields()
        if getattr(f, "concrete", False) and f.editable and f.name != "id"
    }
    assert editable <= set(model_admin.readonly_fields)


def test_action_log_orders_by_the_clock() -> None:
    incident = Incident.objects.create()
    for tick in (30, 0, 120):
        IncidentAction.objects.create(
            incident=incident, tick=tick, actor="IC", action_type="DECLARE",
            rationale="x",
        )
    assert [a.tick for a in incident.actions.all()] == [0, 30, 120]


def test_irreversible_actions_are_flagged() -> None:
    """haltTrading settles every position at the disputed mark. The log has to
    say so at the moment it is taken, not in the post-mortem."""
    incident = Incident.objects.create()
    halt = IncidentAction.objects.create(
        incident=incident, tick=200, actor="IC", action_type="HALT_MARKET",
        rationale="Oracle unrecoverable.", reversible=False,
    )
    assert halt.reversible is False
    labels = dict(IncidentAction._meta.get_field("action_type").choices)
    assert "settles everyone at mark" in labels["HALT_MARKET"]


# -- Claims ----------------------------------------------------------------

def test_claim_shortfall_is_zero_until_the_cap_binds(run: SimRun) -> None:
    account = SimAccount.objects.create(
        run=run, handle="MT00001", side="LONG", notional_inr=Decimal("180000"),
        leverage=20.0, entry_price=Decimal("9200000"), collateral_inr=Decimal("9000"),
    )
    incident = Incident.objects.create(classification=Classification.C)
    claim = Claim.objects.create(
        incident=incident, account=account, category=Classification.C,
        executed_price=Decimal("8000000"), reference_composite_price=Decimal("9000000"),
        deviation_pct=-11.1, counterfactual_equity_inr=Decimal("9000"),
        claimed_inr=Decimal("40000"), approved_inr=Decimal("40000"),
    )
    assert claim.shortfall_inr == Decimal("0")

    claim.approved_inr = Decimal("25000")  # pro-rata once the cap binds
    assert claim.shortfall_inr == Decimal("15000")


def test_one_claim_per_account_per_incident(run: SimRun) -> None:
    from django.db.utils import IntegrityError

    account = SimAccount.objects.create(
        run=run, handle="MT00002", side="LONG", notional_inr=Decimal("180000"),
        leverage=20.0, entry_price=Decimal("9200000"), collateral_inr=Decimal("9000"),
    )
    incident = Incident.objects.create()
    kwargs = dict(
        incident=incident, account=account, executed_price=Decimal("1"),
        reference_composite_price=Decimal("1"), deviation_pct=0.0,
        counterfactual_equity_inr=Decimal("0"),
    )
    Claim.objects.create(**kwargs)
    with pytest.raises(IntegrityError):
        Claim.objects.create(**kwargs)


def test_claim_admin_bulk_actions_exist() -> None:
    from django.contrib import admin

    actions = admin.site._registry[Claim].actions
    assert "approve_selected" in actions
    assert "mark_paid" in actions


# -- Runs and comms --------------------------------------------------------

def test_run_progress_is_safe_before_it_starts(scenario: Scenario, policy: RiskPolicy) -> None:
    run = SimRun.objects.create(scenario=scenario, policy=policy, seed=1, total_ticks=0)
    assert run.progress_pct == 0.0
    run.total_ticks, run.current_tick = 720, 360
    assert run.progress_pct == 50.0


def test_run_str_names_the_control_stack(run: SimRun) -> None:
    assert "controls OFF" in str(run)


def test_comms_updates_are_unique_per_sequence_and_channel() -> None:
    from django.db.utils import IntegrityError

    incident = Incident.objects.create()
    CommsUpdate.objects.create(
        incident=incident, sequence=1, channel="STATUS_PAGE", headline="We see it", body="."
    )
    CommsUpdate.objects.create(
        incident=incident, sequence=1, channel="X", headline="We see it", body="."
    )
    with pytest.raises(IntegrityError):
        CommsUpdate.objects.create(
            incident=incident, sequence=1, channel="X", headline="dup", body="."
        )


def test_account_liquidation_flag(run: SimRun) -> None:
    account = SimAccount.objects.create(
        run=run, handle="MT00003", side="LONG", notional_inr=Decimal("180000"),
        leverage=20.0, entry_price=Decimal("9200000"), collateral_inr=Decimal("9000"),
    )
    assert account.was_liquidated is False
    account.liquidated_at_tick = 140
    assert account.was_liquidated is True
