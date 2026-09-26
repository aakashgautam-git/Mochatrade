"""Seed the demo incidents, so a fresh database opens with every page populated.

Three drills run end to end on the live engine through the real API: a class G
manipulation and a class D outage, both resolved, and the macro cascade with
the controls off, class C above the cap, in flight at T+40. See core/demo.py.

Safe to run on every seed: it does nothing when any incident already exists,
so it never mixes demo drills into someone's own. `--reset` deletes every
incident first and seeds afresh.
"""
from __future__ import annotations

import time

from django.core.management.base import BaseCommand, CommandError

from core import demo, runner
from core.models import Incident, Scenario


class Command(BaseCommand):
    help = "Run the three demo drills (G, D, and C in flight) so every page opens on real data."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--reset", action="store_true", help="Delete every incident first.")

    def handle(self, *args: object, **options: object) -> None:
        try:
            runner.active_policy()
        except runner.PolicyUnavailable as exc:
            raise CommandError(str(exc)) from exc
        missing = [s.slug for s in demo.DEMOS if not Scenario.objects.filter(slug=s.slug).exists()]
        if missing:
            raise CommandError(f"Missing scenarios {missing}. Run `manage.py seed_scenarios` first.")

        if options["reset"]:
            for code in Incident.objects.values_list("code", flat=True):
                runner.forget_engine(code)
            Incident.objects.all().delete()
        elif Incident.objects.exists():
            self.stdout.write("Incidents already exist; demo drills not seeded. Use --reset to replace them.")
            return

        started = time.perf_counter()
        try:
            incidents = demo.seed()
        except demo.DemoError as exc:
            raise CommandError(str(exc)) from exc
        for inc in incidents:
            plan = (inc.remediation_detail or {}).get("waterfall") or {}
            self.stdout.write(
                f"  {inc.code}  {inc.run.scenario.slug:<24} class {inc.classification}  "
                f"{inc.claims.count():>4} claims  {inc.updates.filter(is_published=True).count():>2} published  "
                f"{'pro-rata ' if plan.get('pro_rata') else ''}{inc.get_status_display().lower()}"
            )
        self.stdout.write(f"Demo: {len(incidents)} incidents in {time.perf_counter() - started:.1f}s.")
