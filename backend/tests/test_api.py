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
from django.utils import timezone
from rest_framework.test import APIClient

from core import runner
from core.models import (
    Claim,
    CommsUpdate,
    DepthSnapshot,
    LiquidationRecord,
    Incident,
    IncidentAction,
    PolicyMarginTier,
    PriceObservation,
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
    assert "₹38 Cr" in detail["assumed_scale_note"]
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
    """Six oracle sources plus our mark, the published composite and the
    Reference Composite: nine rows a tick, read from the persisted tape."""
    code = declare(api)
    post(api, f"/api/incidents/{code}/step/", {"ticks": 20})
    body = api.get(f"/api/incidents/{code}/evidence/").json()
    assert body["ticks_recorded"] == 20
    assert len(body["observations"]) == 20 * 9
    sources = {o["source"] for o in body["observations"]}
    assert {"MOCHATRADE", "COMPOSITE", "REFERENCE", "BINANCE"} <= sources
    oracle = [o for o in body["observations"] if o["rung"] is not None]
    assert len(oracle) == 20 * 6 and all(o["excluded_reason"] or o["used"] for o in oracle)
    window = api.get(f"/api/incidents/{code}/evidence/?from=5&to=6").json()
    assert {o["tick"] for o in window["observations"]} == {5, 6}
    assert api.get(f"/api/incidents/{code}/evidence/?from=9&to=3").status_code == 400


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
    assert body["classification"]["status"] == "unclassified"
    assert body["classification"]["verdict"] is None
    assert body["claims"]["status"] == "not_opened" and body["claims"]["remediation"] is None


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
        "channel": "X", "headline": "Public", "body": "Visible. Next update at 04:25 IST.",
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


# --------------------------------------------------------------------------
# The persisted evidence tape (pre-Phase-5)
# --------------------------------------------------------------------------

def test_a_completed_run_writes_its_tape(api, seeded) -> None:
    """Per tick: every oracle source, plus our mark, the published composite and
    the reconstructed Reference Composite."""
    body = post(api, "/api/runs/", {"scenario_slug": "oracle_defect_hip3", "controls_enabled": False}).json()
    run = SimRun.objects.get(pk=body["run_id"])
    rows = PriceObservation.objects.filter(run=run)
    assert rows.count() == run.total_ticks * (6 + 3)
    assert rows.filter(source="REFERENCE", rung__isnull=True).count() == run.total_ticks

    clamped = rows.filter(source="ADR", clamped=True)
    assert clamped.exists()
    row = clamped.order_by("tick").first()
    assert row.raw_price > row.price  # the honest source, dragged down by the median


def test_a_closed_market_is_stored_with_no_price(api, seeded) -> None:
    body = post(api, "/api/runs/", {"scenario_slug": "offhours_equity_wick"}).json()
    cash = PriceObservation.objects.filter(run_id=body["run_id"], source="US_CASH")
    assert cash.count() == 600
    assert not cash.exclude(price__isnull=True).exists()
    assert "closed" in cash.first().excluded_reason


def test_ticks_on_the_wire_carry_the_sources(api, seeded) -> None:
    body = post(api, "/api/runs/", {"scenario_slug": "offhours_equity_wick"}).json()
    sources = body["ticks"][10]["sources"]
    assert [s["source"] for s in sources][0] == "us_cash_market"
    assert sources[0]["price"] is None


def test_frame_schema_is_part_of_the_cache_key(api, seeded, monkeypatch) -> None:
    """A run stored before a frame field existed must not be served as though it
    had that field."""
    first = post(api, "/api/runs/", {"scenario_slug": "broker_outage"}).json()
    monkeypatch.setattr(runner, "FRAME_SCHEMA", runner.FRAME_SCHEMA + 1)
    second = post(api, "/api/runs/", {"scenario_slug": "broker_outage"}).json()
    assert second["cache"] == "miss"
    assert second["run_id"] != first["run_id"]


def test_stepped_runs_extend_the_tape_without_duplicates(api, seeded) -> None:
    """Incremental writes, including across a silent rebuild after a restart."""
    code = declare(api, slug="oracle_defect_hip3")
    run = Incident.objects.get(code=code).run
    post(api, f"/api/incidents/{code}/step/", {"ticks": 25})
    assert PriceObservation.objects.filter(run=run).count() == 25 * 9

    runner._LIVE.clear()
    post(api, f"/api/incidents/{code}/step/", {"ticks": 15})
    rows = PriceObservation.objects.filter(run=run)
    assert rows.count() == 40 * 9
    assert rows.values("tick", "source").distinct().count() == 40 * 9


# --------------------------------------------------------------------------
# Liquidation records and depth snapshots (Phase 5.5 C)
# --------------------------------------------------------------------------

def test_a_completed_run_writes_fills_and_depth(api, seeded) -> None:
    body = post(api, "/api/runs/", {"scenario_slug": "macro_cascade", "controls_enabled": False}).json()
    run = SimRun.objects.get(pk=body["run_id"])
    fills = sum(len(f["liquidations"]) for f in run.tick_data)
    assert LiquidationRecord.objects.filter(run=run).count() == fills > 0
    assert DepthSnapshot.objects.filter(run=run).count() == run.total_ticks
    closed = LiquidationRecord.objects.filter(run=run, closed=True).values("account").distinct().count()
    assert closed == body["summary"]["accounts_liquidated"]


def test_ticks_on_the_wire_carry_fills_and_depth(api, seeded) -> None:
    body = post(api, "/api/runs/", {"scenario_slug": "macro_cascade", "controls_enabled": False}).json()
    tick = max(body["ticks"], key=lambda t: len(t["liquidations"]))
    assert tick["liquidations"][0]["stage"] in {"partial", "market", "backstop", "adl"}
    assert len(tick["depth"]["bids"]) == 10
    assert tick["best_bid"] < tick["best_ask"]


def test_stepped_runs_extend_fills_and_depth_without_duplicates(api, seeded) -> None:
    code = declare(api, slug="macro_cascade")
    run = Incident.objects.get(code=code).run
    post(api, f"/api/incidents/{code}/step/", {"ticks": 120})
    runner._LIVE.clear()
    post(api, f"/api/incidents/{code}/step/", {"ticks": 60})
    assert DepthSnapshot.objects.filter(run=run).count() == 180
    assert DepthSnapshot.objects.filter(run=run).values("tick").distinct().count() == 180
    run.refresh_from_db()
    fills = sum(len(f["liquidations"]) for f in run.tick_data)
    assert LiquidationRecord.objects.filter(run=run).count() == fills


# --------------------------------------------------------------------------
# Phase 7: war room
# --------------------------------------------------------------------------

def test_state_carries_triage_actions_and_the_drill_clock(api, seeded) -> None:
    code = declare(api)
    post(api, f"/api/incidents/{code}/step/", {"ticks": 30})
    state = api.get(f"/api/incidents/{code}/state/").json()
    assert [l["tier"] for l in state["triage"]] == ["L3", "L2", "L1"]
    assert all(l["status"] in {"ok", "warn", "fail"} for l in state["triage"])
    assert state["actions"][0]["action_type"] == "DECLARE"
    assert state["drill_clock_s"] == 30 and state["drill_total_s"] == 3600
    assert state["scenario"]["n_ticks"] == 720


def test_triage_blames_the_broker_during_our_own_outage(api, seeded) -> None:
    """broker_outage takes the app and API down from tick 120 to 480."""
    code = declare(api, slug="broker_outage", controls=True)
    post(api, f"/api/incidents/{code}/step/", {"ticks": 200})
    broker = next(l for l in api.get(f"/api/incidents/{code}/state/").json()["triage"] if l["layer"] == "broker")
    assert broker["status"] == "fail"
    assert "most likely" in broker["headline"]


def test_protect_switch_is_a_real_engine_action(api, seeded) -> None:
    control, treated = declare(api), declare(api)
    for code in (control, treated):
        post(api, f"/api/incidents/{code}/step/", {"ticks": 70})
    r = post(api, f"/api/incidents/{treated}/action/", {"action_type": "PROTECT_SWITCH", "rationale": "T+2 contain."})
    assert r.json()["affects_engine"] is True
    a = post(api, f"/api/incidents/{control}/step/", {"ticks": 200}).json()["snapshots"][-1]
    b = post(api, f"/api/incidents/{treated}/step/", {"ticks": 200}).json()["snapshots"][-1]
    assert b["reduce_only"] is True
    assert b["cum_liquidated_accounts"] < a["cum_liquidated_accounts"]


def test_the_clock_runs_forward_only_and_only_after_the_market_event(api, seeded) -> None:
    code = declare(api, slug="oracle_defect_hip3")
    assert post(api, f"/api/incidents/{code}/clock/", {"to_seconds": 900}).status_code == 400
    post(api, f"/api/incidents/{code}/step/", {"ticks": 600})
    ok = post(api, f"/api/incidents/{code}/clock/", {"to_seconds": 900})
    assert ok.status_code == 200 and ok.json()["drill_clock_s"] == 900
    assert post(api, f"/api/incidents/{code}/clock/", {"to_seconds": 600}).status_code == 400
    assert post(api, f"/api/incidents/{code}/clock/", {"to_seconds": 4000}).status_code == 400


def test_after_the_market_event_only_post_market_decisions_apply(api, seeded) -> None:
    code = declare(api, slug="oracle_defect_hip3")
    post(api, f"/api/incidents/{code}/step/", {"ticks": 600})
    post(api, f"/api/incidents/{code}/clock/", {"to_seconds": 1800})
    refused = post(api, f"/api/incidents/{code}/action/", {"action_type": "LIQ_THROTTLE", "rationale": "x"})
    assert refused.status_code == 400 and "no longer changes anything" in refused.json()["detail"]
    logged = post(api, f"/api/incidents/{code}/action/", {"action_type": "CLASSIFY", "rationale": "Class C."})
    assert logged.status_code == 201
    assert logged.json()["applies_at_tick"] == 1800
    assert Incident.objects.get(code=code).status == "DIAGNOSED"


def test_a_resolved_incident_closes_its_log(api, seeded) -> None:
    code = declare(api)
    post(api, f"/api/incidents/{code}/action/", {"action_type": "RESOLVE", "rationale": "Handover."})
    assert post(api, f"/api/incidents/{code}/action/", {"action_type": "CLASSIFY"}).status_code == 400


def test_incidents_can_be_listed_and_their_ticks_fetched(api, seeded) -> None:
    code = declare(api)
    post(api, f"/api/incidents/{code}/step/", {"ticks": 25})
    assert api.get("/api/incidents/").json()[0]["code"] == code
    ticks = api.get(f"/api/incidents/{code}/ticks/?since=10").json()
    assert ticks["from_tick"] == 10 and [t["tick"] for t in ticks["ticks"]] == list(range(10, 25))
    assert api.get(f"/api/incidents/{code}/ticks/?since=x").status_code == 400


def test_live_engine_work_holds_the_incident_lock(api, seeded, monkeypatch) -> None:
    """The dev server is threaded. An action that reads the tick while a step
    is advancing the same engine used to be refused as 'in the past' (a 400 on
    the Protect Switch click). Every touch of a live engine must hold the
    incident's lock; another thread must not be able to take it meanwhile."""
    import threading

    from riskengine.engine import Engine

    code = declare(api)
    free_while_working: list[bool] = []

    def probe() -> None:
        lock = runner.lock_for(code)
        got = lock.acquire(blocking=False)
        if got:
            lock.release()
        free_while_working.append(got)

    def spy(real):
        def wrapped(self, *args, **kwargs):
            t = threading.Thread(target=probe)
            t.start()
            t.join()
            return real(self, *args, **kwargs)
        return wrapped

    monkeypatch.setattr(Engine, "step", spy(Engine.step))
    monkeypatch.setattr(Engine, "queue_action", spy(Engine.queue_action))
    post(api, f"/api/incidents/{code}/step/", {"ticks": 3})
    post(api, f"/api/incidents/{code}/action/", {"action_type": "PROTECT_SWITCH", "rationale": "x"})
    assert free_while_working and not any(free_while_working)



# --------------------------------------------------------------------------
# Phase 8: forensics
# --------------------------------------------------------------------------

def test_classify_needs_a_tape(api, seeded) -> None:
    code = declare(api)
    r = post(api, f"/api/incidents/{code}/classify/")
    assert r.status_code == 400 and "has not started" in r.json()["detail"]
    assert api.get(f"/api/incidents/{code}/classify/").json()["status"] == "unclassified"


def test_classify_writes_a_verdict_and_one_claim_per_account(api, seeded) -> None:
    """Our own oracle defect, controls off: the market marks on the last trade,
    so the incident is ours and the accounts it liquidated say why."""
    code = declare(api, slug="oracle_defect_hip3", controls=False)
    post(api, f"/api/incidents/{code}/step/", {"ticks": 600})
    r = post(api, f"/api/incidents/{code}/classify/", {"actor": "CTO", "rationale": "Ran the APE test."})
    assert r.status_code == 200, r.content
    body = r.json()
    assert body["status"] == "classified" and body["market_finished"] is True
    verdict = body["verdict"]
    assert verdict["category"] == "C" and verdict["layer"] == "market"
    assert verdict["provisional"] is False and verdict["evidence"]
    assert verdict["signals"]["composite_defect"]["peak_bps"] < -verdict["nrr_bps"]
    claims = body["claims"]
    assert len(claims) == sum(verdict["counts"].values()) > 0
    assert {c["category"] for c in claims} <= set("ABCDEFG")
    for c in claims:
        assert c["reason"]
        assert set(c["evidence"]["criteria"]) == {"deviation", "reversion", "survival"}
    ape = [c for c in claims if c["evidence"]["ape"]]
    assert ape and not any(c["category"] == "A" for c in ape)

    incident = Incident.objects.get(code=code)
    assert incident.classification == "C" and incident.root_cause_layer == "MARKET"
    assert incident.status == "DIAGNOSED"
    assert incident.affected_accounts_count == verdict["counts"]["C"] + verdict["counts"]["D"] + verdict["counts"]["E"] + verdict["counts"]["G"]
    logged = incident.actions.filter(action_type="CLASSIFY").get()
    assert logged.params["category"] == "C" and logged.actor == "CTO"
    assert SimAccount.objects.filter(run=incident.run).count() == len(claims)
    report = api.get(f"/api/incidents/{code}/report/").json()
    assert report["classification"]["verdict"]["category"] == "C"


def test_a_mid_event_verdict_is_provisional_and_rerunning_spares_decided_claims(api, seeded) -> None:
    code = declare(api, slug="macro_cascade", controls=False)
    post(api, f"/api/incidents/{code}/step/", {"ticks": 240})
    first = post(api, f"/api/incidents/{code}/classify/").json()
    assert first["verdict"]["provisional"] is True
    claim = Claim.objects.filter(incident__code=code).first()
    post(api, f"/api/incidents/{code}/claims/{claim.id}/decide/", {"decision": "REJECTED", "reason": "IC call."})
    post(api, f"/api/incidents/{code}/step/", {"ticks": 480})
    again = post(api, f"/api/incidents/{code}/classify/").json()
    assert again["verdict"]["provisional"] is False
    assert len(again["claims"]) >= len(first["claims"])
    claim.refresh_from_db()
    assert claim.status == "REJECTED" and claim.reason == "IC call."
    assert Incident.objects.get(code=code).actions.filter(action_type="CLASSIFY").count() == 2



# --------------------------------------------------------------------------
# Phase 9: remediation
# --------------------------------------------------------------------------

def test_opening_claims_funds_the_waterfall_and_goes_pro_rata_above_the_cap(api, seeded) -> None:
    """The macro cascade without the controls: our market marked on the last
    trade, the claims exceed the published cap, and the payout says so."""
    code = declare(api, slug="macro_cascade", controls=False)
    for ticks in (600, 120):
        post(api, f"/api/incidents/{code}/step/", {"ticks": ticks})
    r = post(api, f"/api/incidents/{code}/claims/", {"actor": "CEO"})
    assert r.status_code == 200, r.content
    body = r.json()
    assert body["status"] == "open" and body["classification"] == "C"
    plan = body["remediation"]["waterfall"]
    policy = RiskPolicy.objects.get(is_active=True)
    assert plan["pro_rata"] is True and plan["total_claims"] > policy.per_incident_cap_inr
    assert plan["payable"] == pytest.approx(policy.per_incident_cap_inr)
    assert [t["step"] for t in plan["tranches"]] == [1, 2, 3, 4, 5]
    assert plan["tranches"][1]["drawn"] == pytest.approx(policy.per_incident_cap_inr)  # the reserve covers it

    c = [x for x in body["claims"] if x["category"] == "C"]
    assert c and all(x["status"] == "AUTO_APPROVED" for x in c)
    paid = sum(Decimal(x["approved_inr_display"]) for x in c)
    assert abs(paid - Decimal(str(policy.per_incident_cap_inr))) < Decimal("1")  # rounding only
    for x in c:
        remedy = x["evidence"]["remedy"]
        assert remedy["pro_rata"] is True
        assert remedy["cash_inr"] + remedy["make_good_inr"] == pytest.approx(remedy["make_whole"], abs=0.01)
        assert Decimal(x["provisional_credit_inr"]) == Decimal(x["approved_inr_display"])
    assert all(x["status"] == "REJECTED" for x in body["claims"] if x["category"] in {"A", "F"})

    incident = Incident.objects.get(code=code)
    assert incident.status == "REMEDIATING"
    assert float(incident.aggregate_exposure_inr) == pytest.approx(plan["total_claims"], abs=0.01)
    assert incident.actions.filter(action_type="OPEN_CLAIMS").get().params["pro_rata"] is True
    report = api.get(f"/api/incidents/{code}/report/").json()
    assert report["claims"]["remediation"]["waterfall"]["pro_rata"] is True


def test_a_human_decision_survives_reopening_and_a_rejection_draws_nothing(api, seeded) -> None:
    code = declare(api, slug="broker_outage", controls=True)
    post(api, f"/api/incidents/{code}/step/", {"ticks": 600})
    first = post(api, f"/api/incidents/{code}/claims/").json()
    d = [x for x in first["claims"] if x["category"] == "D" and Decimal(x["claimed_inr_display"]) > 0]
    assert d and first["remediation"]["waterfall"]["pro_rata"] is False
    target = d[0]
    post(api, f"/api/incidents/{code}/claims/{target['id']}/decide/", {"decision": "REJECTED", "reason": "Duplicate account."})
    again = post(api, f"/api/incidents/{code}/claims/").json()
    kept = next(x for x in again["claims"] if x["id"] == target["id"])
    assert kept["status"] == "REJECTED" and kept["reason"] == "Duplicate account."
    total_first = first["remediation"]["waterfall"]["total_claims"]
    total_again = again["remediation"]["waterfall"]["total_claims"]
    assert total_again == pytest.approx(total_first - float(target["claimed_inr_display"]), abs=0.02)


def test_a_second_incident_sees_what_the_first_drew_from_the_reserve(api, seeded) -> None:
    first = declare(api, slug="broker_outage", controls=True)
    post(api, f"/api/incidents/{first}/step/", {"ticks": 600})
    drawn = post(api, f"/api/incidents/{first}/claims/").json()["remediation"]["waterfall"]["tranches"][1]["drawn"]
    assert drawn > 0
    second = declare(api, slug="broker_outage", controls=True)
    post(api, f"/api/incidents/{second}/step/", {"ticks": 600})
    reserve = post(api, f"/api/incidents/{second}/claims/").json()["remediation"]["reserve"]
    assert reserve["drawn_by_other_incidents"] == pytest.approx(drawn, abs=0.01)
    assert reserve["available"] == pytest.approx(reserve["opening"] - drawn, abs=0.01)


def test_the_reserve_is_not_part_of_the_run_cache_key_but_the_cap_is(seeded) -> None:
    params = RiskPolicy.objects.get(is_active=True).to_params()
    assert runner.fingerprint(params.evolve(incident_reserve_opening_inr=9e7)) == runner.fingerprint(params)
    assert runner.fingerprint(params.evolve(version="v9")) == runner.fingerprint(params)
    assert runner.fingerprint(params.evolve(per_incident_cap_inr=9e7)) != runner.fingerprint(params)


def test_recalibrate_from_simulation_resolves_the_circularity_in_one_step(api, seeded) -> None:
    """Two scenarios keep the test quick; the command runs all of them."""
    from core.models import Scenario

    Scenario.objects.exclude(slug__in=["upi_settlement_delay", "long_tail_manipulation"]).delete()
    v1 = RiskPolicy.objects.get(is_active=True)
    r = post(api, "/api/policies/recalibrate/", {"actor": "CFO"})
    assert r.status_code == 201, r.content
    body = r.json()
    assert len(body["rows"]) == 4 and body["previous_version"] == v1.version
    worst = max(Decimal(x["claims_total_inr"]) for x in body["rows"])
    assert Decimal(body["worst"]["claims_total_inr"]) == worst
    assert Decimal(body["target_reserve_inr"]) == (worst * 2).quantize(Decimal("0.01"))
    assert body["same_runs"] is True and body["converged"] is False

    v2 = RiskPolicy.objects.get(is_active=True)
    assert v2.version == body["new_version"] != v1.version
    assert v2.incident_reserve_opening_inr == pytest.approx(float(worst * 2), abs=0.01)
    assert v2.per_incident_cap_inr == v1.per_incident_cap_inr  # the cap is never raised
    assert v2.to_params().evolve(version=v1.version, incident_reserve_opening_inr=v1.incident_reserve_opening_inr) == v1.to_params()
    assert "Recalibrated from simulation" in v2.notes

    again = post(api, "/api/policies/recalibrate/", {"actor": "CFO"})
    assert again.status_code == 200
    assert again.json()["converged"] is True and again.json()["new_version"] is None
    assert RiskPolicy.objects.count() == 2



# --------------------------------------------------------------------------
# Phase 10: comms and the public status page
# --------------------------------------------------------------------------

CLEAN = "We see abnormal moves. What we turned on: reduce-only. Next update at 04:25 IST. CEO"


def test_draft_submit_approve_publish(api, seeded) -> None:
    code = declare(api)
    base = f"/api/incidents/{code}/comms/"
    draft = post(api, base, {"headline": "Abnormal moves", "body": CLEAN, "is_published": False, "template": "first-word"})
    assert draft.status_code == 201 and draft.json()["approval"] == "DRAFT"
    queued = post(api, base, {"headline": "Abnormal moves", "body": CLEAN, "submit": True, "template": "first-word"})
    uid = queued.json()["id"]
    assert queued.json()["approval"] == "PENDING" and queued.json()["is_published"] is False
    assert post(api, f"{base}{uid}/publish/").status_code == 400  # not approved yet
    assert post(api, f"{base}{uid}/approve/", {"decision": "REJECT"}).status_code == 400  # a rejection needs a reason
    ok = post(api, f"{base}{uid}/approve/", {"decision": "APPROVE", "approver": "CEO"})
    assert ok.json()["approval"] == "APPROVED" and ok.json()["approved_by"] == "CEO"
    out = post(api, f"{base}{uid}/publish/", {"publisher": "Support"})
    assert out.json()["is_published"] is True
    logged = IncidentAction.objects.get(incident__code=code, action_type="PUBLISH_UPDATE")
    assert logged.actor == "Support" and logged.params["audience"] == "PUBLIC"
    public = api.get("/api/status/").json()
    assert [u["headline"] for u in public["updates"]] == ["Abnormal moves"]
    assert public["incidents"][0]["code"] == code and public["incidents"][0]["state"] == "investigating"


def test_a_blocked_draft_can_be_saved_but_never_sent(api, seeded) -> None:
    code = declare(api)
    base = f"/api/incidents/{code}/comms/"
    bad = {"headline": "Update", "body": "Losses were due to market conditions. Your funds are safe. Next update at 04:25 IST."}
    refused = post(api, base, {**bad, "submit": True})
    assert refused.status_code == 400
    rules = {f["rule"] for f in refused.json()["findings"] if f["severity"] == "block"}
    assert {"market-conditions", "funds-safe"} <= rules
    assert post(api, base, bad).status_code == 400  # the one-click publish path is guarded too
    saved = post(api, base, {**bad, "is_published": False})
    assert saved.status_code == 201 and any(f["severity"] == "block" for f in saved.json()["guardrails"])
    check = post(api, f"{base}check/", {"headline": "Update", "body": CLEAN}).json()
    assert check["blocked"] is False and check["facts"]["classified"] is False


def test_messages_to_affected_users_the_venue_or_a_regulator_never_reach_the_public_page(api, seeded) -> None:
    code = declare(api)
    base = f"/api/incidents/{code}/comms/"
    for audience in ("AFFECTED", "VENUE", "REGULATOR"):
        r = post(api, base, {"headline": f"to {audience}", "body": "Private note. Next update at 04:25 IST.", "audience": audience, "channel": "EMAIL"})
        assert r.status_code == 201, r.content
    assert post(api, base, {"headline": "x", "body": "Private. Next update at 04:25 IST.", "audience": "VENUE", "channel": "X"}).status_code == 400
    assert api.get("/api/status/").json()["updates"] == []


def test_templates_are_filled_from_the_incident(api, seeded) -> None:
    code = declare(api, slug="oracle_defect_hip3")
    post(api, f"/api/incidents/{code}/step/", {"ticks": 60})
    templates = api.get(f"/api/incidents/{code}/comms/templates/").json()
    keys = {t["key"] for t in templates}
    assert {"first-word", "preliminary", "the-number", "handover", "your-account", "venue-evidence-pack",
            "sebi-glitch-notice", "fiu-ind-report"} <= keys
    first = next(t for t in templates if t["key"] == "first-word")
    status_page = next(d for d in first["drafts"] if d["channel"] == "STATUS_PAGE")
    assert "TSLA-PERP" in status_page["body"] and "Next update at" in status_page["body"]
    assert not [f for f in status_page["findings"] if f["severity"] == "block"]
    number = next(t for t in templates if t["key"] == "the-number")["drafts"][0]
    assert "once it is computed" in number["body"]


def test_the_public_page_reads_the_live_system_in_plain_words(api, seeded) -> None:
    code = declare(api, slug="broker_outage", controls=True)
    post(api, f"/api/incidents/{code}/step/", {"ticks": 200})
    body = api.get("/api/status/").json()
    app = next(c for c in body["components"] if c["name"] == "App and order API")
    assert app["state"] == "major_outage" and body["overall"]["state"] == "major_outage"
    for item in body["components"] + body["incidents"]:
        assert not (set(item) & INTERNAL)
    post(api, f"/api/incidents/{code}/action/", {"action_type": "RESOLVE", "rationale": "Handover."})
    after = api.get("/api/status/").json()
    assert after["overall"]["state"] == "operational"
    assert all(c["state"] == "operational" for c in after["components"])


# --------------------------------------------------------------------------
# Phase 11: the report
# --------------------------------------------------------------------------

def test_the_report_carries_the_money_and_the_regulatory_clock(api, seeded) -> None:
    code = declare(api, slug="broker_outage", controls=True)
    post(api, f"/api/incidents/{code}/step/", {"ticks": 600})
    before = api.get(f"/api/incidents/{code}/report/").json()
    assert before["obligations"]["notified_within_hour"] is False
    assert before["obligations"]["first_update_minutes"] is None
    post(api, f"/api/incidents/{code}/comms/", {"headline": "Abnormal moves", "body": CLEAN})
    post(api, f"/api/incidents/{code}/claims/")
    body = api.get(f"/api/incidents/{code}/report/").json()
    incident = Incident.objects.get(code=code)
    assert body["obligations"]["notified_within_hour"] is True
    assert body["obligations"]["rca_due"].startswith((incident.declared_at + timezone.timedelta(days=14)).date().isoformat())
    assert body["obligations"]["channels_used"] == ["STATUS_PAGE"]
    summary = body["claims_summary"]
    assert summary["accounts_owed_cash"] > 0 and Decimal(summary["provisional_credit_inr"]) > 0
    assert body["classification"]["claims"] == [] and body["claims"]["claims"] == []  # aggregates, not rows
    assert body["classification"]["verdict"]["category"] == "D"
    assert "oracle_anchored_mark" in body["controls"]
