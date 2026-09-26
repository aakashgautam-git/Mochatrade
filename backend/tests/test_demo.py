"""Phase 12: the demo drills a fresh database opens with.

The seed must leave every page with real engine data -- a classified incident,
claims through the waterfall, published updates and a live status page -- and
must get there through the same API the war room uses, so a rebuilt engine
replays to exactly the run that was stored.
"""
from __future__ import annotations

import json
import re
from datetime import timedelta

import pytest
from django.core.management import call_command
from django.utils import timezone
from rest_framework.test import APIClient

from core import runner
from core.models import (
    ClaimStatus, CommsUpdate, Incident, IncidentStatus, Instrument, RiskPolicy, Scenario, SimRun,
)

pytestmark = pytest.mark.django_db


@pytest.fixture(scope="module")
def demo(django_db_setup, django_db_blocker):
    with django_db_blocker.unblock():
        call_command("seed_policy", force=True, verbosity=0)
        call_command("seed_scenarios", verbosity=0)
        call_command("seed_demo", verbosity=0)
        yield list(Incident.objects.order_by("declared_at"))
        # Module scope commits outside the per-test transaction: leave the
        # database as empty as every other test expects it.
        for code in Incident.objects.values_list("code", flat=True):
            runner.forget_engine(code)
        Incident.objects.all().delete()
        SimRun.objects.all().delete()
        Scenario.objects.all().delete()
        Instrument.objects.all().delete()
        RiskPolicy.objects.all().delete()


def test_three_drills_one_per_class(demo) -> None:
    assert [(i.run.scenario.slug, i.run.controls_enabled, i.classification, i.status) for i in demo] == [
        ("long_tail_manipulation", True, "G", IncidentStatus.RESOLVED),
        ("broker_outage", True, "D", IncidentStatus.RESOLVED),
        ("macro_cascade", False, "C", IncidentStatus.REMEDIATING),
    ]


def test_the_headline_drill_goes_pro_rata_above_the_cap(demo) -> None:
    live = demo[-1]
    plan = live.remediation_detail["waterfall"]
    assert plan["pro_rata"] and plan["total_claims"] > plan["cap"]
    c = live.claims.filter(category="C")
    assert c.exists() and all(x.status == ClaimStatus.AUTO_APPROVED and x.provisional_credit_inr > 0 for x in c)
    assert live.updates.filter(approval="PENDING").count() == 1


def test_claims_carry_human_decisions_on_the_resolved_drills(demo) -> None:
    g, d, _ = demo
    assert all(c.status == ClaimStatus.APPROVED and c.decided_by for c in g.claims.filter(category="G"))
    assert all(c.status == ClaimStatus.PAID and c.decided_by for c in d.claims.filter(category="D"))


def test_every_stamp_sits_on_the_drill_clock(demo) -> None:
    for inc in demo:
        for a in inc.actions.all():
            assert a.wall_clock == inc.declared_at + timedelta(seconds=a.tick)
    g, d, live = demo
    assert d.resolved_at <= live.declared_at and g.resolved_at <= d.declared_at
    # The in-flight drill's clock (T+40) reads as the time the seed ran.
    assert abs(live.declared_at + timedelta(seconds=live.drill_clock_s) - timezone.now()) < timedelta(minutes=5)
    assert g.declared_at < d.declared_at < live.declared_at
    assert d.resolved_at == d.declared_at + timedelta(seconds=d.actions.get(action_type="RESOLVE").tick)


def test_every_public_update_promises_a_time_after_it_was_sent(demo) -> None:
    for u in CommsUpdate.objects.filter(is_published=True, audience="PUBLIC").exclude(template="handover"):
        m = re.search(r"Next update (?:at )?(\d{2}):(\d{2}) IST", u.body)
        assert m, u.body
        sent = timezone.localtime(u.published_at)
        promised = sent.replace(hour=int(m.group(1)), minute=int(m.group(2)), second=0, microsecond=0)
        if promised < sent:
            promised += timedelta(days=1)
        assert timedelta(minutes=5) <= promised - sent <= timedelta(minutes=20), (u.template, u.body)
        assert u.next_update_at == promised


def test_a_rebuilt_engine_replays_the_stored_run(demo) -> None:
    for inc in demo:
        runner.forget_engine(inc.code)
        engine = runner.live_engine(inc)
        replayed = json.loads(json.dumps([f.as_dict() for f in engine.frames]))
        assert replayed == inc.run.tick_data


def test_every_page_has_data(demo) -> None:
    api = APIClient()
    status = api.get("/api/status/").json()
    assert len(status["incidents"]) == 3 and status["overall"]["state"] != "operational"
    for inc in demo:
        report = api.get(f"/api/incidents/{inc.code}/report/").json()
        assert report["classification"]["status"] == "classified"
        assert report["claims"]["status"] == "open"
        assert report["obligations"]["notified_within_hour"]
        assert api.get(f"/api/incidents/{inc.code}/evidence/?from=0&to=5").json()["observations"]


def test_seeding_again_leaves_existing_incidents_alone(demo) -> None:
    before = Incident.objects.count()
    call_command("seed_demo", verbosity=0)
    assert Incident.objects.count() == before
