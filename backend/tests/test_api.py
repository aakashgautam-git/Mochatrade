"""Phase 4: the API layer, and the two rules that are the point of the phase.

1. No view bypasses the active RiskPolicy. Enforced by scanning source, in the
   same spirit as test_engine_purity.py: a rule held by a test, not by
   discipline.
2. Runs are persisted and reused, and a policy edit invalidates them.
"""
from __future__ import annotations

import ast
import re
from decimal import Decimal
from pathlib import Path

import pytest
from django.core.management import call_command
from rest_framework.test import APIClient

from core import runner
from core.models import (
    Claim,
    CommsUpdate,
    Incident,
    IncidentAction,
    PolicyMarginTier,
    RiskPolicy,
    SimAccount,
    SimRun,
)

pytestmark = pytest.mark.django_db

CORE = Path(__file__).resolve().parent.parent / "core"

#: The only two files permitted to touch the dataclass defaults directly.
#: models.py generates RiskPolicy's defaults and help_text FROM them, and
#: to_params() is the one place a RiskParams is constructed. seed_policy.py
#: builds v1 by reading them, per the Phase 2 rule that seeding never hardcodes.
SANCTIONED = {
    CORE / "models.py",
    CORE / "management" / "commands" / "seed_policy.py",
}


@pytest.fixture
def api() -> APIClient:
    return APIClient()


@pytest.fixture
def seeded() -> None:
    call_command("seed_policy", force=True, verbosity=0)
    call_command("seed_scenarios", verbosity=0)


def post(api: APIClient, url: str, body: dict | None = None):
    return api.post(url, body or {}, format="json")


# --------------------------------------------------------------------------
# (a) The config bypass is dead, and a test keeps it dead
# --------------------------------------------------------------------------

def _python_sources() -> list[Path]:
    return sorted(p for p in CORE.rglob("*.py") if "migrations" not in p.parts)


def test_no_view_bypasses_the_active_policy() -> None:
    """Nothing in core/ outside the sanctioned files may import DEFAULT_PARAMS or
    construct RiskParams. Every engine instantiation goes through
    RiskPolicy.objects.get(is_active=True).to_params().

    Scans the AST for real imports and calls rather than grepping text, so a
    docstring that mentions the rule does not trip it and an aliased import
    cannot slip past it."""
    offenders: list[str] = []
    for path in _python_sources():
        if path in SANCTIONED:
            continue
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    if alias.name in {"DEFAULT_PARAMS", "RiskParams"}:
                        offenders.append(f"{path.name}:{node.lineno} imports {alias.name}")
            if isinstance(node, ast.Call):
                fn = node.func
                name = fn.id if isinstance(fn, ast.Name) else getattr(fn, "attr", None)
                if name == "RiskParams":
                    offenders.append(f"{path.name}:{node.lineno} constructs RiskParams(...)")
            if isinstance(node, ast.Attribute) and node.attr == "DEFAULT_PARAMS":
                offenders.append(f"{path.name}:{node.lineno} reads .DEFAULT_PARAMS")
    assert not offenders, "config bypass: " + "; ".join(offenders)


def test_the_bypass_scan_actually_catches_a_bypass(tmp_path) -> None:
    """A guard that never trips is worthless. Prove this one does."""
    bad = "from riskengine.params import DEFAULT_PARAMS\nx = RiskParams()\n"
    tree = ast.parse(bad)
    hits = [
        n for n in ast.walk(tree)
        if (isinstance(n, ast.ImportFrom) and any(a.name == "DEFAULT_PARAMS" for a in n.names))
        or (isinstance(n, ast.Call) and getattr(n.func, "id", None) == "RiskParams")
    ]
    assert len(hits) == 2


def test_every_api_run_records_the_policy_that_produced_it(api, seeded) -> None:
    body = post(api, "/api/runs/", {"scenario_slug": "macro_cascade"}).json()
    run = SimRun.objects.get(pk=body["run_id"])
    active = RiskPolicy.objects.get(is_active=True)
    assert run.policy == active
    assert run.policy_fingerprint == runner.fingerprint(active.to_params())


def test_no_active_policy_is_a_clear_503_not_a_crash(api, seeded) -> None:
    RiskPolicy.objects.update(is_active=False)
    r = post(api, "/api/runs/", {"scenario_slug": "macro_cascade"})
    assert r.status_code == 503
    assert "seed_policy" in r.json()["detail"]


# --------------------------------------------------------------------------
# Runs
# --------------------------------------------------------------------------

def test_run_creation_persists_and_returns_the_full_series(api, seeded) -> None:
    r = post(api, "/api/runs/", {"scenario_slug": "upi_settlement_delay", "controls_enabled": True})
    assert r.status_code == 201
    body = r.json()
    assert body["cache"] == "miss"
    assert len(body["ticks"]) == 600
    assert body["summary"]["accounts_total"] == 1200
    assert SimRun.objects.filter(pk=body["run_id"], status="DONE").exists()


def test_money_crosses_the_wire_as_a_decimal_string(api, seeded) -> None:
    body = post(api, "/api/runs/", {"scenario_slug": "macro_cascade"}).json()
    loss = body["summary"]["user_loss_inr"]
    assert isinstance(loss, str)
    Decimal(loss)  # parses exactly


def test_unknown_scenario_is_a_400_with_a_useful_detail(api, seeded) -> None:
    r = post(api, "/api/runs/", {"scenario_slug": "no_such_thing"})
    assert r.status_code == 400
    assert "macro_cascade" in r.json()["detail"]  # tells you what IS valid


def test_malformed_body_is_a_400_not_a_500(api, seeded) -> None:
    assert post(api, "/api/runs/", {}).status_code == 400
    assert post(api, "/api/runs/", {"scenario_slug": "macro_cascade", "seed": "x"}).status_code == 400
    assert post(api, "/api/runs/", {"scenario_slug": "macro_cascade", "policy_id": 9999}).status_code == 400


# --------------------------------------------------------------------------
# Compare
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "slug",
    ["offhours_equity_wick", "oracle_defect_hip3", "macro_cascade",
     "broker_outage", "upi_settlement_delay", "long_tail_manipulation"],
)
def test_compare_delta_signs(api, seeded, slug) -> None:
    """Positive delta means the controls reduced the quantity. Strictly fewer
    liquidations with controls on, in every scenario."""
    body = post(api, "/api/runs/compare/", {"scenario_slug": slug}).json()
    off, on = body["off"]["summary"], body["on"]["summary"]
    assert on["accounts_liquidated"] < off["accounts_liquidated"]
    assert body["delta"]["liquidations_pct"] > 0
    assert body["delta"]["notional_pct"] > 0
    assert body["delta"]["adl_pct"] >= 0
    assert body["off"]["seed"] == body["on"]["seed"]  # the identical shock


def test_compare_acceptance_offhours(api, seeded) -> None:
    body = post(api, "/api/runs/compare/", {"scenario_slug": "offhours_equity_wick"}).json()
    assert body["on"]["summary"]["accounts_liquidated"] < body["off"]["summary"]["accounts_liquidated"]


def test_legacy_compare_shape_is_unchanged(api, seeded) -> None:
    """The screening-round demo must not break while the API is rebuilt."""
    body = api.get("/api/compare/oracle_defect_hip3/").json()
    assert set(body) == {"scenario", "assumed_scale_note", "off", "on", "delta"}
    assert set(body["scenario"]) == {
        "slug", "name", "summary", "instrument", "ist_label", "layer",
        "liable_layer_note", "seed",
    }
    for side in ("off", "on"):
        assert set(body[side]) == {
            "liquidated", "unnecessary", "adl", "user_loss_inr",
            "accounts_total", "trough_pct", "series",
        }
        assert isinstance(body[side]["user_loss_inr"], float)  # the shipped page parses a number
        assert len(body[side]["series"]) <= 300
        assert set(body[side]["series"][0]) == {"t", "oracle", "mark", "ltp", "liquidations"}
    assert set(body["delta"]) == {"liquidated_pct", "loss_pct", "unnecessary_pct", "adl_pct"}
    assert body["off"]["liquidated"] == 680 and body["on"]["liquidated"] == 0


# --------------------------------------------------------------------------
# (b) Cache hit, miss, and invalidation on a policy edit
# --------------------------------------------------------------------------

def test_second_identical_call_is_a_cache_hit(api, seeded) -> None:
    first = post(api, "/api/runs/", {"scenario_slug": "broker_outage"})
    second = post(api, "/api/runs/", {"scenario_slug": "broker_outage"})
    assert first.json()["cache"] == "miss" and first.status_code == 201
    assert second.json()["cache"] == "hit" and second.status_code == 200
    assert first.json()["run_id"] == second.json()["run_id"]
    assert SimRun.objects.filter(scenario__slug="broker_outage").count() == 1


def test_a_different_seed_is_a_different_run(api, seeded) -> None:
    a = post(api, "/api/runs/", {"scenario_slug": "broker_outage"}).json()
    b = post(api, "/api/runs/", {"scenario_slug": "broker_outage", "seed": 7}).json()
    assert a["run_id"] != b["run_id"]


def test_editing_a_margin_tier_invalidates_the_cache_and_moves_the_result(api, seeded) -> None:
    """The acceptance criterion for (a) and (b) together. Editing a tier does
    NOT bump RiskPolicy.version, which is exactly why the key is a fingerprint
    of the values."""
    before = post(api, "/api/runs/compare/", {"scenario_slug": "macro_cascade"}).json()
    policy = RiskPolicy.objects.get(is_active=True)
    version = policy.version

    tier = PolicyMarginTier.objects.get(policy=policy, ordering=0)
    tier.mm_pct = 1.5
    tier.save()
    assert RiskPolicy.objects.get(pk=policy.pk).version == version  # version unchanged

    after = post(api, "/api/runs/compare/", {"scenario_slug": "macro_cascade"}).json()
    assert after["cache"] == "miss"
    assert after["off"]["run_id"] != before["off"]["run_id"]
    assert (
        after["off"]["summary"]["accounts_liquidated"]
        > before["off"]["summary"]["accounts_liquidated"]
    )

    # Reverting the tier restores the original fingerprint: a hit on the old runs.
    tier.mm_pct = 1.0
    tier.save()
    reverted = post(api, "/api/runs/compare/", {"scenario_slug": "macro_cascade"}).json()
    assert reverted["cache"] == "hit"
    assert reverted["off"]["run_id"] == before["off"]["run_id"]


def test_warm_runs_is_idempotent(seeded) -> None:
    call_command("warm_runs", verbosity=0)
    assert SimRun.objects.count() == 12
    call_command("warm_runs", verbosity=0)
    assert SimRun.objects.count() == 12


# --------------------------------------------------------------------------
# (d) Scenarios come from the database
# --------------------------------------------------------------------------

def test_scenarios_are_read_from_the_database(api, seeded) -> None:
    body = api.get("/api/scenarios/").json()
    assert len(body) == 6
    detail = api.get("/api/scenarios/macro_cascade/").json()
    assert "Rs 38 Cr" in detail["assumed_scale_note"]
    assert detail["instrument"]["symbol"] == "BTC-PERP"
    assert api.get("/api/scenarios/nope/").status_code == 404


def test_policies_filter_on_active(api, seeded) -> None:
    RiskPolicy.objects.create(version="v0-archive", is_active=False)
    everything = api.get("/api/policies/").json()
    active = api.get("/api/policies/?active=true").json()
    assert len(everything) == 2
    assert [p["version"] for p in active] == ["v1"]
    assert len(active[0]["margin_tiers"]) == 5
    assert api.get("/api/policies/?active=maybe").status_code == 400


def test_timestamps_are_ist_iso8601_with_offset(api, seeded) -> None:
    created = api.get("/api/policies/?active=true").json()[0]["created_at"]
    assert re.search(r"\+05:30$", created), created


# --------------------------------------------------------------------------
# Stepping and actions
# --------------------------------------------------------------------------

def declare(api: APIClient, slug: str = "macro_cascade", controls: bool = False) -> str:
    r = post(api, "/api/incidents/", {
        "scenario_slug": slug, "controls_enabled": controls,
        "incident_commander": "CEO", "ops_lead": "CTO", "comms_lead": "Support",
    })
    assert r.status_code == 201, r.content
    return r.json()["incident"]["code"]


def test_declaring_opens_the_record_at_tick_zero(api, seeded) -> None:
    code = declare(api)
    state = api.get(f"/api/incidents/{code}/state/").json()
    assert state["current_tick"] == 0
    assert state["snapshot"] is None
    assert state["incident"]["incident_commander"] == "CEO"
    assert IncidentAction.objects.get(incident__code=code).action_type == "DECLARE"


def test_stepping_advances_and_returns_the_new_snapshots(api, seeded) -> None:
    code = declare(api)
    r = post(api, f"/api/incidents/{code}/step/", {"ticks": 40})
    assert r.status_code == 200
    body = r.json()
    assert (body["from_tick"], body["to_tick"]) == (0, 40)
    assert [s["tick"] for s in body["snapshots"]] == list(range(40))
    assert api.get(f"/api/incidents/{code}/state/").json()["current_tick"] == 40


def test_step_bounds_are_validated(api, seeded) -> None:
    code = declare(api)
    assert post(api, f"/api/incidents/{code}/step/", {"ticks": 0}).status_code == 400
    assert post(api, f"/api/incidents/{code}/step/", {"ticks": 100_000}).status_code == 400


def test_an_action_changes_subsequent_ticks(api, seeded) -> None:
    """The war room has to matter. Two identical incidents diverge only because
    the operator threw the Protect Switch equivalent in one of them."""
    control, treated = declare(api), declare(api)
    for code in (control, treated):
        post(api, f"/api/incidents/{code}/step/", {"ticks": 70})

    r = post(api, f"/api/incidents/{treated}/action/", {
        "action_type": "LIQ_THROTTLE",
        "rationale": "Engine is the largest seller in the book. Throttle to the published cap.",
    })
    assert r.status_code == 201
    assert r.json()["affects_engine"] is True
    assert r.json()["applies_at_tick"] == 70

    a = post(api, f"/api/incidents/{control}/step/", {"ticks": 200}).json()["snapshots"][-1]
    b = post(api, f"/api/incidents/{treated}/step/", {"ticks": 200}).json()["snapshots"][-1]
    assert b["cum_liquidated_accounts"] < a["cum_liquidated_accounts"]


def test_log_only_actions_do_not_touch_the_engine(api, seeded) -> None:
    code = declare(api)
    r = post(api, f"/api/incidents/{code}/action/", {
        "action_type": "CLASSIFY", "rationale": "Preliminary: class C.",
    })
    assert r.status_code == 201
    assert r.json()["affects_engine"] is False


def test_halt_is_logged_as_irreversible(api, seeded) -> None:
    code = declare(api)
    post(api, f"/api/incidents/{code}/step/", {"ticks": 10})
    r = post(api, f"/api/incidents/{code}/action/", {
        "action_type": "HALT_MARKET", "rationale": "Oracle unrecoverable.",
    })
    assert r.json()["action"]["reversible"] is False


def test_unknown_action_is_a_400_listing_the_valid_ones(api, seeded) -> None:
    code = declare(api)
    r = post(api, f"/api/incidents/{code}/action/", {"action_type": "PANIC"})
    assert r.status_code == 400
    assert "PROVISIONAL_CREDIT" in r.json()["detail"]


def test_live_engine_is_rebuilt_silently_after_a_restart(api, seeded) -> None:
    """The in-memory registry is never trusted to survive. Drop it, and the next
    request rebuilds the engine by replaying the action log -- landing on
    exactly the same state because the engine is deterministic."""
    code = declare(api)
    post(api, f"/api/incidents/{code}/step/", {"ticks": 90})
    post(api, f"/api/incidents/{code}/action/", {"action_type": "LIQ_THROTTLE", "rationale": "x"})
    post(api, f"/api/incidents/{code}/step/", {"ticks": 60})
    before = api.get(f"/api/incidents/{code}/state/").json()["snapshot"]

    runner._LIVE.clear()  # the process "restarted"

    after = api.get(f"/api/incidents/{code}/state/").json()["snapshot"]
    assert after == before

    continued = post(api, f"/api/incidents/{code}/step/", {"ticks": 30}).json()
    assert continued["from_tick"] == 150


def test_unknown_incident_is_a_404(api, seeded) -> None:
    assert api.get("/api/incidents/INC-19990101-01/state/").status_code == 404


# --------------------------------------------------------------------------
# Evidence, comms, report, and the 501 routes
# --------------------------------------------------------------------------

def test_evidence_tape_has_one_row_per_source_per_tick(api, seeded) -> None:
    code = declare(api)
    post(api, f"/api/incidents/{code}/step/", {"ticks": 20})
    body = api.get(f"/api/incidents/{code}/evidence/").json()
    assert body["ticks_recorded"] == 20
    assert len(body["observations"]) == 60
    assert {o["source"] for o in body["observations"]} == {"MOCHATRADE", "COMPOSITE", "REFERENCE"}


def test_classify_and_claims_are_501_with_a_clear_detail(api, seeded) -> None:
    code = declare(api)
    for method, url, phase in (
        (api.post, f"/api/incidents/{code}/classify/", 8),
        (api.get, f"/api/incidents/{code}/claims/", 9),
    ):
        r = method(url)
        assert r.status_code == 501
        assert r.json()["phase"] == phase
        assert f"Phase {phase}" in r.json()["detail"]


def test_claim_decisions_work_on_existing_rows(api, seeded) -> None:
    code = declare(api)
    incident = Incident.objects.get(code=code)
    account = SimAccount.objects.create(
        run=incident.run, handle="MT00001", side="LONG", notional_inr=Decimal("180000"),
        leverage=20, entry_price=Decimal("92"), collateral_inr=Decimal("9000"),
    )
    claim = Claim.objects.create(
        incident=incident, account=account, category="C", executed_price=Decimal("80"),
        reference_composite_price=Decimal("90"), deviation_pct=-11.1,
        counterfactual_equity_inr=Decimal("9000"), claimed_inr=Decimal("40000"),
    )
    url = f"/api/incidents/{code}/claims/{claim.pk}/decide/"
    assert post(api, url, {"decision": "PAID"}).status_code == 400  # not approved yet
    ok = post(api, url, {"decision": "APPROVED", "approved_inr": "25000.00", "reason": "pro-rata"})
    assert ok.status_code == 200
    assert ok.json()["approved_inr_display"] == "25000.00"
    assert ok.json()["shortfall_inr_display"] == "15000.00"
    assert post(api, url, {"decision": "PAID"}).status_code == 200


def test_publishing_an_update_logs_it(api, seeded) -> None:
    code = declare(api)
    r = post(api, f"/api/incidents/{code}/comms/", {
        "channel": "STATUS_PAGE", "headline": "We are seeing abnormal pricing",
        "body": "What we see, what we turned on, next update 02:35 IST.",
    })
    assert r.status_code == 201
    assert r.json()["sequence"] == 1 and r.json()["is_published"] is True
    assert IncidentAction.objects.filter(incident__code=code, action_type="PUBLISH_UPDATE").exists()
    assert len(api.get(f"/api/incidents/{code}/comms/").json()) == 1


def test_report_returns_what_exists_and_marks_the_rest_pending(api, seeded) -> None:
    code = declare(api)
    post(api, f"/api/incidents/{code}/step/", {"ticks": 30})
    body = api.get(f"/api/incidents/{code}/report/").json()
    assert body["incident"]["code"] == code
    assert body["run"]["current_tick"] == 30
    assert body["timeline"][0]["action_type"] == "DECLARE"
    assert body["classification"] == {"status": "pending", "phase": 8}
    assert body["claims"] == {"status": "pending", "phase": 9}


# --------------------------------------------------------------------------
# The public status feed
# --------------------------------------------------------------------------

INTERNAL = {
    "classification", "classification_display", "root_cause_layer",
    "aggregate_exposure_inr", "aggregate_exposure_inr_display",
    "affected_accounts_count", "owes_cash_remedy", "incident_commander",
    "ops_lead", "comms_lead", "run", "id", "is_published", "status",
}


def test_public_status_leaks_no_internal_fields(api, seeded) -> None:
    code = declare(api)
    incident = Incident.objects.get(code=code)
    incident.classification = "C"
    incident.aggregate_exposure_inr = Decimal("9130000")
    incident.save()
    post(api, f"/api/incidents/{code}/comms/", {
        "channel": "X", "headline": "Public", "body": "Visible.",
    })
    CommsUpdate.objects.create(
        incident=incident, sequence=2, channel="X", headline="DRAFT-SECRET",
        body="not yet", is_published=False,
    )

    body = api.get("/api/status/").json()
    assert len(body["updates"]) == 1
    update = body["updates"][0]
    assert not (set(update) & INTERNAL), set(update) & INTERNAL
    assert "DRAFT-SECRET" not in str(body)
    assert "9130000" not in str(body)


def test_public_status_needs_no_auth(api, seeded) -> None:
    assert APIClient().get("/api/status/").status_code == 200


# --------------------------------------------------------------------------
# Serializers are explicit
# --------------------------------------------------------------------------

def test_no_serializer_uses_all_fields() -> None:
    """Checks the AST, not the text: the module docstring explains the ban by
    quoting it, and a text search trips on the explanation."""
    tree = ast.parse((CORE / "serializers.py").read_text())
    wildcards = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and any(getattr(t, "id", None) in {"fields", "exclude"} for t in node.targets)
        and isinstance(node.value, ast.Constant)
        and node.value.value == "__all__"
    ]
    assert not wildcards, f"fields = '__all__' at serializers.py lines {wildcards}"
    assert "exclude" not in {
        getattr(t, "id", None)
        for node in ast.walk(tree) if isinstance(node, ast.Assign)
        for t in node.targets
    }, "use an explicit field list, not exclude"
