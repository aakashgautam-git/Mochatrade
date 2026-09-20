"""The admin is a demo surface, so it has to actually render.

Registration is not the same as loading: a bad `list_display`, a broken
`@admin.display` helper or a formatting error in the timeline only shows up when
a page is fetched. These tests fetch them.
"""
from __future__ import annotations

from decimal import Decimal

import pytest
from django.apps import apps
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone

from core.models import (
    Claim,
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
def admin_client(client):
    User.objects.create_superuser("ic", "ic@mochatrade.test", "pw")
    client.force_login(User.objects.get(username="ic"))
    return client


@pytest.fixture
def populated() -> Incident:
    """A small but complete incident, so every admin page has something to render."""
    from django.core.management import call_command

    call_command("seed_policy", force=True, verbosity=0)
    policy = RiskPolicy.objects.get(is_active=True)
    instrument = Instrument.objects.create(
        symbol="TSLA-PERP", display_name="Tesla perpetual", asset_class="EQUITY",
        tier=2, has_rth=True, base_price=Decimal("36000"),
    )
    scenario = Scenario.objects.create(
        name="Oracle defect", slug="oracle-defect", instrument=instrument, seed=20260402,
        shock_pct=-3.5, shock_duration_s=60, total_duration_s=600,
        book_depth_inr=Decimal("900000"),
    )
    run = SimRun.objects.create(
        scenario=scenario, policy=policy, seed=20260402, total_ticks=600, status="DONE"
    )
    account = SimAccount.objects.create(
        run=run, handle="MT00001", side="LONG", notional_inr=Decimal("180000"),
        leverage=20.0, entry_price=Decimal("36000"), collateral_inr=Decimal("9000"),
        liquidated_at_tick=160,
    )
    incident = Incident.objects.create(
        run=run, classification=Classification.C, root_cause_layer="MARKET",
        incident_commander="CEO", ops_lead="CTO", comms_lead="Support",
        affected_accounts_count=562, aggregate_exposure_inr=Decimal("9130000"),
    )
    IncidentAction.objects.create(
        incident=incident, tick=0, actor="IC", action_type="DECLARE",
        rationale="Mark-oracle divergence past 50bps. SEV-1, I am IC.",
    )
    IncidentAction.objects.create(
        incident=incident, tick=120, actor="OPS", action_type="PAUSE_LIQUIDATIONS",
        rationale="Two L2 sources diverged together; the feed is suspect, not the users.",
        reversible=False,
    )
    Claim.objects.create(
        incident=incident, account=account, category=Classification.C,
        status="AUTO_APPROVED", executed_price=Decimal("31200"),
        reference_composite_price=Decimal("34800"), deviation_pct=-10.34,
        counterfactual_equity_inr=Decimal("8100"), claimed_inr=Decimal("6400"),
        approved_inr=Decimal("6400"), provisional_credit_inr=Decimal("6400"),
    )
    CommsUpdate.objects.create(
        incident=incident, sequence=1, channel="STATUS_PAGE",
        headline="We are seeing abnormal pricing on TSLA-PERP",
        body="What we see, what we turned on, next update at 02:35 IST.",
        next_update_at=timezone.now(), is_published=True,
    )
    return incident


def test_admin_index_loads(admin_client, populated) -> None:
    response = admin_client.get(reverse("admin:index"))
    assert response.status_code == 200
    assert b"MochaTrade Crisis Command" in response.content


@pytest.mark.parametrize(
    "model",
    [m for m in apps.get_app_config("core").get_models()],
    ids=lambda m: m.__name__,
)
def test_every_changelist_renders(admin_client, populated, model) -> None:
    from django.contrib import admin as django_admin

    if model not in django_admin.site._registry:
        pytest.skip(f"{model.__name__} is edited as an inline")
    url = reverse(f"admin:{model._meta.app_label}_{model._meta.model_name}_changelist")
    assert admin_client.get(url).status_code == 200


def test_incident_change_page_renders_the_timeline(admin_client, populated) -> None:
    url = reverse("admin:core_incident_change", args=[populated.pk])
    response = admin_client.get(url)
    assert response.status_code == 200
    body = response.content.decode()
    assert "SEV-1, I am IC" in body
    assert "IRREVERSIBLE" in body
    assert "T+120s" in body


def test_policy_change_page_shows_the_citations(admin_client, populated) -> None:
    policy = RiskPolicy.objects.get(is_active=True)
    response = admin_client.get(reverse("admin:core_riskpolicy_change", args=[policy.pk]))
    assert response.status_code == 200
    body = response.content.decode()
    assert "Binance" in body
    assert "DERIVED" in body
    assert "Non-Reviewable Range" in body


def test_action_log_cannot_be_added_or_deleted_over_http(admin_client, populated) -> None:
    """Not merely absent from the UI -- refused by the server."""
    action = populated.actions.first()
    assert admin_client.get(reverse("admin:core_incidentaction_add")).status_code == 403
    delete_url = reverse("admin:core_incidentaction_delete", args=[action.pk])
    assert admin_client.get(delete_url).status_code == 403
    assert admin_client.post(delete_url, {"post": "yes"}).status_code == 403
    assert IncidentAction.objects.filter(pk=action.pk).exists()


def test_action_log_change_page_is_view_only(admin_client, populated) -> None:
    action = populated.actions.first()
    url = reverse("admin:core_incidentaction_change", args=[action.pk])
    response = admin_client.get(url)
    assert response.status_code == 200
    assert b'name="rationale"' not in response.content

    admin_client.post(url, {"rationale": "rewritten after the fact"})
    action.refresh_from_db()
    assert "rewritten" not in action.rationale


def test_claim_bulk_actions_work(admin_client, populated) -> None:
    claim = populated.claims.first()
    claim.status = "PENDING"
    claim.approved_inr = Decimal("0")
    claim.save()

    url = reverse("admin:core_claim_changelist")
    admin_client.post(url, {"action": "approve_selected", "_selected_action": [claim.pk]})
    claim.refresh_from_db()
    assert claim.status == "APPROVED"
    assert claim.approved_inr == claim.claimed_inr
    assert claim.decided_by == "ic"

    admin_client.post(url, {"action": "mark_paid", "_selected_action": [claim.pk]})
    claim.refresh_from_db()
    assert claim.status == "PAID"


def test_mark_paid_skips_claims_that_were_never_approved(admin_client, populated) -> None:
    claim = populated.claims.first()
    claim.status = "PENDING"
    claim.save()
    admin_client.post(
        reverse("admin:core_claim_changelist"),
        {"action": "mark_paid", "_selected_action": [claim.pk]},
    )
    claim.refresh_from_db()
    assert claim.status == "PENDING"
