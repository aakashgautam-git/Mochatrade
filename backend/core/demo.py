"""The demo incidents a fresh database opens with.

Forensics, Remediation, Comms, the Report and /status all read an incident's
record, and a fresh database has none until someone runs the war-room clock.
This module runs three drills end to end so every page opens on real engine
data. Nothing here is written by hand: each drill is declared, its market is
stepped on the live engine, and every later step goes through the same API
calls the war room and the comms desk make, so the classifier, the waterfall
and the language guardrails all do their real work on the drill's own tape.

    G  long_tail_manipulation, controls on.   Resolved: FIU-IND report, venue
       evidence pack, every claim approved by the IC from the Incident Reserve.
    D  broker_outage, controls on.            Resolved: the fault is ours,
       provisional credit inside the hour, reconciled and paid, staged reopen.
    C  macro_cascade, controls OFF.           In flight at T+40, the one the
       pages open on. Without the automatic stack the Protect Switch lands at
       the playbook's T+5 deadline and is still too late: the claims exceed the
       per-incident cap, so the waterfall goes pro-rata. The reopen update
       waits for the IC, and the reopen and the handover are left to drill live.

Time. A drill plays an hour in a few seconds, so every timestamp the API wrote
is re-stamped afterwards at `declared_at` plus the drill second it happened.
That is the mapping the war room's log already shows. The declaration time is
set before anything is derived from it, so the next-update times, the
provisional-credit deadline and the SEBI dates inside the published text agree
with the stamps.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from django.db.models import Model
from django.utils import timezone
from rest_framework.test import APIClient

from . import comms, runner
from .models import ActionType, Claim, CommsUpdate, Incident, IncidentAction, Scenario

IC, OPS, COMMS = "CEO", "CTO", "Support lead"
"""The war room's default role holders: research 6 pre-assigns IC to the CEO,
OPS to the CTO and COMMS to the third founder."""

MIN = 60

WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")

SHIP: dict[str, tuple[str, int]] = {
    "C": ("an oracle-anchored mark with an outlier clamp and a staleness kill, never the last traded price", 7),
    "D": ("a margin-call grace window with one-tap top-up and a pre-funded UPI buffer", 14),
    "G": ("isolated margin by default on long-tail markets, with haircuts that scale with volatility", 7),
}
"""The mechanism change each handover commits to, with its effort from the
research's ranked list (section 8: changes 1, 5 and 9 -- one week, two weeks,
one week). The template leaves the ship date for a human; in the demo drill the
human commits to the date that effort gives."""


class DemoError(RuntimeError):
    """A drill step the API refused. The seed stops rather than write half an incident."""


@dataclass
class Drill:
    """One incident driven through the API, on one playbook clock."""

    api: APIClient
    incident: Incident
    n_ticks: int
    clock: int = 0
    stamps: list[tuple[type[Model], int, str, int]] = field(default_factory=list)

    @property
    def code(self) -> str:
        return self.incident.code

    def _post(self, url: str, body: dict[str, Any] | None = None) -> Any:
        r = self.api.post(f"/api/incidents/{self.code}/{url}", body or {}, format="json")
        if r.status_code not in (200, 201):
            raise DemoError(f"{self.code} {url}: {r.status_code} {r.content[:400]!r}")
        return r.json()

    def _get(self, url: str) -> Any:
        r = self.api.get(f"/api/incidents/{self.code}/{url}")
        if r.status_code != 200:
            raise DemoError(f"{self.code} {url}: {r.status_code} {r.content[:400]!r}")
        return r.json()

    # -- the clock -----------------------------------------------------------

    def at(self, seconds: int) -> None:
        """Run the market on the engine up to `seconds`, then the drill clock."""
        if seconds < self.clock:
            raise DemoError(f"{self.code}: the clock only runs forward ({self.clock} -> {seconds}).")
        while self.clock < min(seconds, self.n_ticks):
            n = min(600, min(seconds, self.n_ticks) - self.clock)
            self.clock = self._post("step/", {"ticks": n})["to_tick"]
        if seconds > self.clock:
            self.clock = self._post("clock/", {"to_seconds": seconds})["drill_clock_s"]

    def stamp(self, model: type[Model], pk: int, name: str) -> None:
        self.stamps.append((model, pk, name, self.clock))

    # -- decisions -----------------------------------------------------------

    def act(self, action_type: str, actor: str, rationale: str) -> None:
        self._post("action/", {"action_type": action_type, "actor": actor, "rationale": rationale})
        if action_type == ActionType.RESOLVE:
            self.stamp(Incident, self.incident.pk, "resolved_at")

    def classify(self, rationale: str) -> dict[str, Any]:
        return self._post("classify/", {"actor": OPS, "rationale": rationale})["verdict"]

    def open_claims(self, rationale: str) -> dict[str, Any]:
        return self._post("claims/", {"actor": IC, "rationale": rationale})

    def decide_claims(self, category: str, decision: str, actor: str, reason: str) -> int:
        claims = [c for c in self._get("claims/")["claims"] if c["category"] == category]
        for c in claims:
            self._post(f"claims/{c['id']}/decide/", {"decision": decision, "decided_by": actor, "reason": reason})
            self.stamp(Claim, c["id"], "decided_at")
        return len(claims)

    # -- comms ---------------------------------------------------------------

    def _draft(self, key: str, channel: str) -> tuple[str, str, str]:
        for t in self._get("comms/templates/"):
            if t["key"] == key:
                for d in t["drafts"]:
                    if d["channel"] == channel:
                        return t["audience"], d["headline"], d["body"]
        raise DemoError(f"{self.code}: no {key!r} template on {channel}.")

    def _next_update(self, key: str) -> str:
        at = self.incident.declared_at + timedelta(seconds=comms.next_update_for(key, self.clock))
        return timezone.localtime(at).isoformat()

    def publish(self, key: str, *channels: str, fill: dict[str, str] | None = None) -> None:
        """One update, published in the room on each channel under one number."""
        sequence: int | None = None
        for channel in channels:
            audience, headline, body = self._draft(key, channel)
            for old, new in (fill or {}).items():
                body = body.replace(old, new)
            request: dict[str, Any] = {
                "channel": channel, "headline": headline, "body": body, "audience": audience,
                "template": key, "drafted_by": COMMS, "is_published": True,
            }
            if audience == "PUBLIC" and key != "handover":
                request["next_update_at"] = self._next_update(key)
            if sequence is not None:
                request["sequence"] = sequence
            update = self._post("comms/", request)
            sequence = update["sequence"]
            self.stamp(CommsUpdate, update["id"], "approved_at")
            self.stamp(CommsUpdate, update["id"], "published_at")

    def submit(self, key: str, channel: str) -> int:
        """COMMS drafts from the template and sends it to the IC."""
        audience, headline, body = self._draft(key, channel)
        request: dict[str, Any] = {
            "channel": channel, "headline": headline, "body": body, "audience": audience,
            "template": key, "drafted_by": COMMS, "submit": True,
        }
        if audience == "PUBLIC":
            request["next_update_at"] = self._next_update(key)
        return int(self._post("comms/", request)["id"])

    def approve(self, update_id: int, note: str) -> None:
        self._post(f"comms/{update_id}/approve/", {"decision": "APPROVE", "approver": IC, "note": note})
        self.stamp(CommsUpdate, update_id, "approved_at")

    def send(self, update_id: int) -> None:
        self._post(f"comms/{update_id}/publish/", {"publisher": COMMS})
        self.stamp(CommsUpdate, update_id, "published_at")

    # -- time ----------------------------------------------------------------

    def restamp(self) -> None:
        """Put every timestamp the drill wrote on the drill's own clock."""
        start = self.incident.declared_at
        for a in IncidentAction.objects.filter(incident=self.incident):
            IncidentAction.objects.filter(pk=a.pk).update(wall_clock=start + timedelta(seconds=a.tick))
        for model, pk, name, second in self.stamps:
            model.objects.filter(pk=pk).update(**{name: start + timedelta(seconds=second)})


# --------------------------------------------------------------------------
# The three drills
# --------------------------------------------------------------------------

def _ship(category: str, declared_at: datetime) -> dict[str, str]:
    what, days = SHIP[category]
    when = timezone.localtime(declared_at + timedelta(days=days)).strftime("%d %b %Y")
    return {"The fix ships on [ship date].": f"The fix, {what}, ships on {when}."}


def _drill_g(d: Drill) -> None:
    d.at(2 * MIN)
    d.act(ActionType.PROTECT_SWITCH, OPS, "Contain: reduce-only, liquidation TWAP throttle, 3x max leverage. haltTrading stays holstered.")
    d.at(3 * MIN)
    d.act(ActionType.SNAPSHOT_EVIDENCE, OPS, "Write-once snapshot of book, tape, per-source oracle inputs, marks, liquidations and deposits.")
    d.at(4 * MIN + 30)
    d.publish("first-word", "STATUS_PAGE", "X", "TELEGRAM")
    d.at(12 * MIN)
    d.classify("Two venues printed beyond the NRR on the same side and our book followed. Run on the full tape.")
    d.at(14 * MIN)
    d.publish("preliminary", "STATUS_PAGE", "X")
    d.at(16 * MIN)
    fiu = d.submit("fiu-ind-report", "EMAIL")
    d.at(17 * MIN)
    d.approve(fiu, "Identifiable manipulation: report to FIU-IND now, as the policy says.")
    d.send(fiu)
    d.at(18 * MIN)
    pack = d.submit("venue-evidence-pack", "EMAIL")
    d.at(19 * MIN)
    d.approve(pack, "File the evidence pack with the venue on our users' behalf.")
    d.send(pack)
    d.at(22 * MIN)
    d.act(ActionType.QUANTIFY, IC, "Affected set and counterfactual equity at the start of the push computed; the Incident Reserve covers it.")
    d.at(26 * MIN)
    d.open_claims("Class G: funded from the Incident Reserve, each claim waits for the IC; recovery is pursued against the attacker.")
    d.at(29 * MIN)
    d.publish("the-number", "STATUS_PAGE", "X")
    d.at(35 * MIN)
    d.decide_claims("G", "APPROVED", IC,
                    "Force-closed inside the manipulation episode. Paid from the Incident Reserve; recovery pursued against the attacker.")
    _reopen_and_hand_over(d, "G")


def _drill_d(d: Drill) -> None:
    d.at(2 * MIN)
    d.act(ActionType.PROTECT_SWITCH, OPS, "Contain: reduce-only, liquidation TWAP throttle, 3x max leverage. haltTrading stays holstered.")
    d.at(2 * MIN + 30)
    d.act(ActionType.SNAPSHOT_EVIDENCE, OPS, "Snapshot now, with app and API telemetry: our own layer is the one failing.")
    d.at(4 * MIN)
    d.publish("first-word", "STATUS_PAGE", "X", "WHATSAPP")
    d.at(11 * MIN)
    d.classify("App and API were down while the move ran. Run on the full tape.")
    d.at(13 * MIN)
    d.publish("preliminary", "STATUS_PAGE", "X")
    d.at(15 * MIN)
    sebi = d.submit("sebi-glitch-notice", "EMAIL")
    d.at(16 * MIN)
    d.approve(sebi, "Our outage ran longer than five minutes: a reportable glitch under the framework we adopted.")
    d.send(sebi)
    d.at(21 * MIN)
    d.act(ActionType.QUANTIFY, IC, "Affected set and equity at the moment of lockout computed; the Incident Reserve covers it.")
    d.at(25 * MIN)
    d.open_claims("Class D is ours: provisional credit to every locked-out account inside the hour, no ticket needed.")
    d.at(28 * MIN)
    d.publish("the-number", "STATUS_PAGE", "X")
    d.at(30 * MIN)
    d.act(ActionType.PROVISIONAL_CREDIT, OPS, "Provisional credit pushed to every class D account as locked trading credit.")
    d.at(32 * MIN)
    d.publish("your-account", "EMAIL")
    d.at(44 * MIN)
    d.decide_claims("D", "PAID", OPS,
                    "Reconciled against the INR ledger; provisional credit converted to withdrawable cash.")
    _reopen_and_hand_over(d, "D")


def _reopen_and_hand_over(d: Drill, category: str) -> None:
    d.at(45 * MIN)
    d.act(ActionType.STAGED_REOPEN, OPS, "Oracle healthy five minutes, spread and depth back: reduce-only to post-only.")
    d.at(46 * MIN)
    d.publish("reopen", "STATUS_PAGE", "X")
    d.at(50 * MIN)
    d.act(ActionType.STAGED_REOPEN, OPS, "Post-only held clean: reopen through the short auction.")
    d.at(51 * MIN)
    d.act(ActionType.STAGED_REOPEN, OPS, "The auction uncrossed inside the collar: continuous trading.")
    d.at(57 * MIN)
    d.publish("handover", "STATUS_PAGE", fill=_ship(category, d.incident.declared_at))
    d.at(59 * MIN)
    d.act(ActionType.RESOLVE, IC, "Handover: what happened, who is affected, what we pay, when it lands, and the RCA date.")


def _drill_c(d: Drill) -> None:
    d.at(3 * MIN)
    d.act(ActionType.SNAPSHOT_EVIDENCE, OPS, "Write-once snapshot of book, tape, per-source oracle inputs, marks, liquidations and deposits.")
    d.at(5 * MIN)
    d.act(ActionType.PROTECT_SWITCH, OPS,
          "Contain at the T+5 deadline: reduce-only, liquidation TWAP throttle, 3x max leverage. Without the automatic stack this is the first control on.")
    d.publish("first-word", "STATUS_PAGE", "X", "WHATSAPP", "TELEGRAM")
    d.at(13 * MIN)
    d.classify("Liquidations ran on the last traded price, far from the Reference Composite. Run on the full tape.")
    d.at(14 * MIN)
    d.publish("preliminary", "STATUS_PAGE", "X")
    d.at(18 * MIN)
    sebi = d.submit("sebi-glitch-notice", "EMAIL")
    d.at(19 * MIN)
    d.approve(sebi, "Our mark failed for more than five minutes: reportable under the framework we adopted.")
    d.send(sebi)
    d.at(24 * MIN)
    d.act(ActionType.QUANTIFY, IC, "Affected set and counterfactual equity at the Reference Composite computed; the total is above the cap.")
    d.at(28 * MIN)
    d.open_claims("Class C is ours. The total is above the published cap, so every claim is paid the same fraction, announced as pro-rata.")
    d.at(30 * MIN)
    d.publish("the-number", "STATUS_PAGE", "X")
    d.at(32 * MIN)
    d.act(ActionType.PROVISIONAL_CREDIT, OPS, "Provisional credit pushed to every class C account as locked trading credit, at the pro-rata share.")
    d.at(34 * MIN)
    d.publish("your-account", "EMAIL")
    d.at(40 * MIN)
    d.submit("reopen", "STATUS_PAGE")


@dataclass(frozen=True)
class DemoSpec:
    slug: str
    controls_enabled: bool
    expect: str
    drive: Any
    live: bool = False


DEMOS: tuple[DemoSpec, ...] = (
    DemoSpec("long_tail_manipulation", True, "G", _drill_g),
    DemoSpec("broker_outage", True, "D", _drill_d),
    DemoSpec("macro_cascade", False, "C", _drill_c, live=True),
)
"""Oldest first. The in-flight drill is declared last, so every page opens on it."""


def _labelled_time(label: str, before: datetime) -> datetime:
    """The latest moment before `before` matching a scenario's label, e.g.
    'Tuesday 23:05 IST': the drill is set when its scenario says it happens."""
    m = re.match(r"(\w+) (\d{1,2}):(\d{2})", label)
    if not m or m.group(1) not in WEEKDAYS:
        return before - timedelta(days=1)
    local = timezone.localtime(before)
    at = local.replace(hour=int(m.group(2)), minute=int(m.group(3)), second=0, microsecond=0)
    at -= timedelta(days=(at.weekday() - WEEKDAYS.index(m.group(1))) % 7)
    while at > before:
        at -= timedelta(days=7)
    return at


def seed(*, now: datetime | None = None) -> list[Incident]:
    """Run every demo drill against the active policy. Returns the incidents,
    oldest first."""
    now = timezone.localtime(now or timezone.now()).replace(second=0, microsecond=0)
    live_start = now - timedelta(minutes=40)
    api = APIClient()
    out: list[Incident] = []
    # Resolved drills finish before the next one starts: their hour, newest last.
    boundary = live_start - timedelta(hours=1)
    starts: dict[str, datetime] = {}
    for spec in reversed(DEMOS):
        if spec.live:
            starts[spec.slug] = live_start
            continue
        row = Scenario.objects.get(slug=spec.slug)
        start = _labelled_time(runner.engine_scenario(row).ist_label, boundary)
        starts[spec.slug] = start
        boundary = start - timedelta(hours=1)

    for spec in DEMOS:
        row = Scenario.objects.get(slug=spec.slug)
        incident = runner.declare_incident(
            row, controls_enabled=spec.controls_enabled, severity="SEV1",
            incident_commander=IC, ops_lead=OPS, comms_lead=COMMS, declared_at=starts[spec.slug],
        )
        drill = Drill(api, incident, n_ticks=runner.engine_scenario(row).n_ticks)
        spec.drive(drill)
        drill.restamp()
        incident.refresh_from_db()
        if incident.classification != spec.expect:
            raise DemoError(f"{incident.code} ({spec.slug}) classified {incident.classification}, expected {spec.expect}.")
        out.append(incident)
    return out
