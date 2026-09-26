"""What each control is worth: alone and last into the full stack, measured
on the engine and cached like runs."""
from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor

import pytest
from django.core.management import call_command
from rest_framework.test import APIClient

from core import runner
from riskengine.params import DEFAULT_PARAMS
from riskengine.scenario import by_key
from core.models import ControlAttribution, Scenario

pytestmark = pytest.mark.django_db

SLUG = "long_tail_manipulation"  # the quickest scenario to run 22 times


@pytest.fixture
def seeded() -> None:
    call_command("seed_policy", force=True, verbosity=0)
    call_command("seed_scenarios", verbosity=0)


def test_every_control_is_measured_both_ways(seeded) -> None:
    result = runner.attribution(Scenario.objects.get(slug=SLUG))
    names = {c["control"] for c in result["controls"]}
    assert len(names) == 11
    assert ControlAttribution.objects.filter(scenario__slug=SLUG).count() == 22
    by = {c["control"]: c for c in result["controls"]}
    # The throttle is what saves the long-tail book, on its own and last in.
    assert by["liquidation_throttle"]["alone"]["accounts_liquidated"] > 0
    # A control the engine cannot show an effect for says so instead of a zero.
    iso = by["isolated_margin_default"]
    assert iso["not_modelled"]
    assert iso["alone"]["accounts_liquidated"] == 0 and iso["last_in"]["accounts_liquidated"] == 0
    # The ends of the comparison are the cached controls-off and controls-on runs.
    assert result["none"]["accounts_liquidated"] > result["full"]["accounts_liquidated"]


def test_attribution_is_read_from_the_cache_the_second_time(seeded, monkeypatch) -> None:
    row = Scenario.objects.get(slug=SLUG)
    first = runner.attribution(row)
    monkeypatch.setattr(runner, "_attribution_summary", lambda *a, **k: pytest.fail("re-ran a cached control"))
    assert runner.attribution(row) == first


def test_a_pool_computes_exactly_what_one_process_does() -> None:
    """warm_runs measures in a process pool; the engine is pure, so a worker
    must return byte-for-byte what the calling process would."""
    job = (SLUG, DEFAULT_PARAMS, "liquidation_throttle", ControlAttribution.ALONE, by_key(SLUG).seed)
    with ProcessPoolExecutor(max_workers=1) as pool:
        pooled = pool.submit(runner._attribution_summary, *job).result()
    assert pooled == runner._attribution_summary(*job)


def test_the_api_serves_both_views(seeded) -> None:
    api = APIClient()
    one = api.get(f"/api/scenarios/{SLUG}/attribution/").json()
    assert {"alone", "last_in", "not_modelled", "label", "kills"} <= set(one["controls"][0])
    assert isinstance(one["full"]["attributable_loss"], str)  # money is a string on the wire
    assert api.get("/api/scenarios/nope/attribution/").status_code == 400
