"""Pre-execute every scenario in both control modes against the active policy,
model what each run would owe, so Recalibrate reads rather than re-runs, and
measure what each control is worth (the full stack without it).

A judge clicking through six scenarios should read from the database, not wait
for twelve simulations. Idempotent: a run already cached for the current policy
fingerprint is skipped, so this is cheap to call on every seed.
"""
from __future__ import annotations

import os
import time

from django.core.management.base import BaseCommand, CommandError

from core import runner
from core.models import Scenario


class Command(BaseCommand):
    help = "Run and persist all scenarios, controls off and on, against the active policy."

    def handle(self, *args: object, **options: object) -> None:
        rows = list(Scenario.objects.select_related("instrument").order_by("slug"))
        if not rows:
            raise CommandError("No scenarios. Run `manage.py seed_scenarios` first.")
        try:
            policy = runner.active_policy()
        except runner.PolicyUnavailable as exc:
            raise CommandError(str(exc)) from exc

        started = time.perf_counter()
        executed = cached = 0
        for row in rows:
            for enabled in (False, True):
                t0 = time.perf_counter()
                run, ran = runner.get_or_run(row, controls_enabled=enabled, policy=policy)
                runner.modelled_claims(run)
                ms = (time.perf_counter() - t0) * 1000
                executed += ran
                cached += not ran
                label = "controls ON " if enabled else "controls OFF"
                verb = "ran   " if ran else "cached"
                self.stdout.write(
                    f"  {verb} {row.slug:24s} {label}  "
                    f"liq {run.result_summary['accounts_liquidated']:5d}  {ms:7.0f} ms"
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"Warm: {executed} executed, {cached} already cached, policy "
                f"{policy.version}, {time.perf_counter() - started:.1f}s total."
            )
        )

        # What each control is worth: alone, and last into the full stack.
        started = time.perf_counter()
        workers = max(1, min(8, os.cpu_count() or 1))
        ran = runner.warm_attribution(rows, policy=policy, workers=workers)
        self.stdout.write(f"  worth  {ran} attribution runs on {workers} worker(s), {time.perf_counter() - started:.1f}s")
        for row in rows:
            t0 = time.perf_counter()
            result = runner.attribution(row, policy=policy)
            best = result["controls"][0]
            self.stdout.write(
                f"  worth  {row.slug:24s} {len(result['controls'])} controls  "
                f"most valuable: {best['control']}  {(time.perf_counter() - t0) * 1000:7.0f} ms"
            )
        self.stdout.write(
            self.style.SUCCESS(f"Attribution: {len(rows)} scenarios, {time.perf_counter() - started:.1f}s total.")
        )
