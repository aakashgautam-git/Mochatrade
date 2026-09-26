"""REST API. Server holds run state; there are no websockets.

Every engine instantiation in this module goes through `runner`, which reads the
active RiskPolicy. Nothing here imports `DEFAULT_PARAMS` or constructs
`RiskParams` -- a test scans for it and fails the build if one appears.

Error contract: bad input is a 400 with a `detail` a human can act on. A missing
resource named in the URL is a 404. A server that has not been seeded is a 503.
A user mistake is never a 500.
"""
from __future__ import annotations

from typing import Any

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from riskengine.controls import OperatorAction

from . import runner
from .triage import triage
from .models import (
    ActionType,
    Claim,
    ClaimStatus,
    CommsUpdate,
    Incident,
    IncidentAction,
    IncidentStatus,
    Instrument,
    PriceObservation,
    RiskPolicy,
    Scenario,
)
from .serializers import (
    ActionRequestSerializer,
    ClaimDecisionSerializer,
    ClassificationSerializer,
    ClassifyRequestSerializer,
    ClockRequestSerializer,
    ClaimSerializer,
    CommsCreateSerializer,
    CommsUpdateSerializer,
    CompareRequestSerializer,
    DeclareIncidentSerializer,
    IncidentActionSerializer,
    IncidentSerializer,
    IncidentStateSerializer,
    InstrumentSerializer,
    PriceObservationSerializer,
    PublicStatusUpdateSerializer,
    RiskPolicySerializer,
    RunRequestSerializer,
    RunSerializer,
    RunSummarySerializer,
    ScenarioDetailSerializer,
    ScenarioListSerializer,
    StepRequestSerializer,
    TickSerializer,
)

LEGACY_MAX_POINTS = 300


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def _bad(detail: str) -> Response:
    return Response({"detail": detail}, status=status.HTTP_400_BAD_REQUEST)


def _scenario_or_400(slug: str) -> Scenario | Response:
    row = Scenario.objects.select_related("instrument").filter(slug=slug).first()
    if row is None:
        known = ", ".join(Scenario.objects.values_list("slug", flat=True)) or "none seeded"
        return _bad(f"Unknown scenario_slug {slug!r}. Known scenarios: {known}.")
    return row


def _reduction(before: float, after: float) -> float:
    """Percent by which the controls REDUCED a quantity. Positive is better;
    zero when there was nothing to reduce."""
    if not before:
        return 0.0
    return round((1.0 - after / before) * 100.0, 1)


def _wick(summary: dict) -> float:
    """Largest excursion of the mark from its opening price, either direction.
    A pump (the manipulation scenario) is as much a wick as a crash."""
    return max(abs(summary.get("trough_mark_pct", 0.0)), abs(summary.get("peak_mark_pct", 0.0)))


def _run_payload(run) -> dict:
    return {
        "run_id": run.id,
        "controls_enabled": run.controls_enabled,
        "seed": run.seed,
        "policy_version": run.policy.version,
        "summary": RunSummarySerializer(run.result_summary).data,
        "ticks": TickSerializer(run.tick_data, many=True).data,
    }


# --------------------------------------------------------------------------
# Policy, instruments, scenarios
# --------------------------------------------------------------------------

class PolicyListView(APIView):
    def get(self, request: Request) -> Response:
        qs = RiskPolicy.objects.prefetch_related("margin_tier_rows", "instrument_tier_rows")
        active = request.query_params.get("active")
        if active is not None:
            if active.lower() not in {"true", "false", "1", "0"}:
                return _bad("`active` must be true or false.")
            qs = qs.filter(is_active=active.lower() in {"true", "1"})
        return Response(RiskPolicySerializer(qs, many=True).data)


class InstrumentListView(APIView):
    def get(self, request: Request) -> Response:
        return Response(InstrumentSerializer(Instrument.objects.all(), many=True).data)


class ScenarioListView(APIView):
    def get(self, request: Request) -> Response:
        qs = Scenario.objects.select_related("instrument")
        return Response(ScenarioListSerializer(qs, many=True).data)


class ScenarioDetailView(APIView):
    def get(self, request: Request, slug: str) -> Response:
        row = get_object_or_404(Scenario.objects.select_related("instrument"), slug=slug)
        return Response(ScenarioDetailSerializer(row).data)


# --------------------------------------------------------------------------
# Runs
# --------------------------------------------------------------------------

class RunCreateView(APIView):
    """POST /api/runs/ -- run to completion (or serve from cache), one shot."""

    def post(self, request: Request) -> Response:
        req = RunRequestSerializer(data=request.data)
        if not req.is_valid():
            return Response(req.errors, status=status.HTTP_400_BAD_REQUEST)
        data = req.validated_data

        row = _scenario_or_400(data["scenario_slug"])
        if isinstance(row, Response):
            return row

        policy = None
        if data.get("policy_id") is not None:
            policy = RiskPolicy.objects.filter(pk=data["policy_id"]).first()
            if policy is None:
                return _bad(f"No RiskPolicy with id {data['policy_id']}.")

        run, executed = runner.get_or_run(
            row,
            controls_enabled=data["controls_enabled"],
            seed=data.get("seed"),
            policy=policy,
        )
        payload = _run_payload(run)
        payload["cache"] = "miss" if executed else "hit"
        return Response(payload, status=status.HTTP_201_CREATED if executed else status.HTTP_200_OK)


class RunCompareView(APIView):
    """POST /api/runs/compare/ -- the identical seeded shock, both control modes."""

    def post(self, request: Request) -> Response:
        req = CompareRequestSerializer(data=request.data)
        if not req.is_valid():
            return Response(req.errors, status=status.HTTP_400_BAD_REQUEST)
        data = req.validated_data

        row = _scenario_or_400(data["scenario_slug"])
        if isinstance(row, Response):
            return row

        off, off_ran = runner.get_or_run(row, controls_enabled=False, seed=data.get("seed"))
        on, on_ran = runner.get_or_run(row, controls_enabled=True, seed=data.get("seed"))
        a, b = off.result_summary, on.result_summary

        return Response(
            {
                "scenario_slug": row.slug,
                "seed": off.seed,
                "policy_version": off.policy.version,
                "cache": "miss" if (off_ran or on_ran) else "hit",
                "off": _run_payload(off),
                "on": _run_payload(on),
                "delta": {
                    "liquidations_pct": _reduction(a["accounts_liquidated"], b["accounts_liquidated"]),
                    "notional_pct": _reduction(a["liquidated_notional"], b["liquidated_notional"]),
                    "wick_pct": _reduction(_wick(a), _wick(b)),
                    "adl_pct": _reduction(a["adl_accounts"], b["adl_accounts"]),
                },
            }
        )


class LegacyCompareView(APIView):
    """GET /api/compare/<slug>/ -- the screening-round demo's exact shape.

    Kept byte-compatible so the live demo cannot break while the rest of the API
    is rebuilt underneath it. Now served from persisted runs against the active
    policy rather than by re-simulating with hardcoded defaults, so it is both
    faster and honest about which policy produced it.

    Money stays numeric HERE ONLY, because the shipped frontend parses it as a
    number. Every new endpoint sends money as a decimal string.
    """

    def get(self, request: Request, slug: str) -> Response:
        row = get_object_or_404(Scenario.objects.select_related("instrument"), slug=slug)
        scenario = runner.engine_scenario(row)
        off, _ = runner.get_or_run(row, controls_enabled=False)
        on, _ = runner.get_or_run(row, controls_enabled=True)

        def side(run) -> dict[str, Any]:
            s = run.result_summary
            return {
                "liquidated": s["accounts_liquidated"],
                "unnecessary": s["unnecessary_liquidations"],
                "adl": s["adl_accounts"],
                "user_loss_inr": round(s["user_loss"], 2),
                "accounts_total": s["accounts_total"],
                "trough_pct": round(s["trough_mark_pct"], 2),
                "series": _legacy_series(run.tick_data),
            }

        a, b = side(off), side(on)
        return Response(
            {
                "scenario": {
                    "slug": scenario.key,
                    "name": scenario.title,
                    "summary": scenario.summary,
                    "instrument": scenario.instrument,
                    "ist_label": scenario.ist_label,
                    "layer": scenario.layer.value,
                    "liable_layer_note": scenario.liable_layer_note,
                    "seed": off.seed,
                },
                "assumed_scale_note": row.assumed_scale_note or scenario.assumed_scale_note,
                "off": a,
                "on": b,
                "delta": {
                    "liquidated_pct": _reduction(a["liquidated"], b["liquidated"]),
                    "loss_pct": _reduction(a["user_loss_inr"], b["user_loss_inr"]),
                    "unnecessary_pct": _reduction(a["unnecessary"], b["unnecessary"]),
                    "adl_pct": _reduction(a["adl"], b["adl"]),
                },
            }
        )


def _legacy_series(frames: list[dict]) -> list[dict]:
    """Downsample to <=300 points. Prices sampled at the bucket head;
    liquidations SUMMED across the bucket so cascade spikes survive."""
    total = len(frames)
    if total == 0:
        return []
    step = max(1, -(-total // LEGACY_MAX_POINTS))
    out = []
    for start in range(0, total, step):
        bucket = frames[start : start + step]
        head = bucket[0]
        out.append(
            {
                "t": head["tick"],
                "oracle": round(head["composite"], 2) if head["composite"] else None,
                "mark": round(head["mark"], 2),
                "ltp": round(head["book_mid"], 2),
                "liquidations": sum(f["liquidated_this_tick"] for f in bucket),
            }
        )
    return out


# --------------------------------------------------------------------------
# Incidents: the war room
# --------------------------------------------------------------------------

def _incident(code: str) -> Incident:
    return get_object_or_404(
        Incident.objects.select_related("run", "run__scenario", "run__policy"), code=code
    )


#: Decisions that still mean something once the market event has ended. The
#: live controls (pauses, throttle, leverage, halt) do not: there is no market
#: left for them to change.
POST_MARKET_ACTIONS = {
    ActionType.SNAPSHOT_EVIDENCE,
    ActionType.PUBLISH_UPDATE,
    ActionType.CLASSIFY,
    ActionType.QUANTIFY,
    ActionType.OPEN_CLAIMS,
    ActionType.PROVISIONAL_CREDIT,
    ActionType.STAGED_REOPEN,
    ActionType.RESOLVE,
}

STATUS_AFTER = {
    ActionType.CLASSIFY: IncidentStatus.DIAGNOSED,
    ActionType.QUANTIFY: IncidentStatus.REMEDIATING,
    ActionType.OPEN_CLAIMS: IncidentStatus.REMEDIATING,
    ActionType.PROVISIONAL_CREDIT: IncidentStatus.REMEDIATING,
}


def _state_payload(incident: Incident) -> dict:
    engine = runner.live_engine(incident)
    frame = engine.frames[-1].as_dict() if engine.frames else None
    flags = engine.flags
    scenario = engine.scenario
    return IncidentStateSerializer(
        {
            "incident": incident,
            "scenario": {
                "slug": incident.run.scenario.slug if incident.run else scenario.key,
                "name": scenario.title,
                "instrument": scenario.instrument,
                "ist_label": scenario.ist_label,
                "layer": scenario.layer.value,
                "n_ticks": scenario.n_ticks,
            },
            "elapsed_seconds": runner.elapsed_seconds(incident),
            "drill_clock_s": runner.drill_clock(incident, engine),
            "drill_total_s": runner.DRILL_SECONDS,
            "current_tick": engine.tick,
            "total_ticks": scenario.n_ticks,
            "finished": engine.finished,
            "snapshot": frame,
            "active_controls": engine.controls.as_dict(),
            "flags": {
                "reduce_only": flags.reduce_only or engine.auto_reduce_only,
                "liquidations_paused": flags.liquidations_paused or engine.auto_liq_pause,
                "halted": flags.halted,
                "max_leverage": flags.max_leverage,
                "stage": flags.stage.value,
                "operator_throttle": engine.operator_throttle,
            },
            "triage": triage(engine),
            "actions": incident.actions.order_by("tick", "id"),
        }
    ).data


class IncidentCreateView(APIView):
    """GET lists recent incidents so a drill can be resumed; POST declares one,
    opens the record and starts a stepped run."""

    def get(self, request: Request) -> Response:
        qs = Incident.objects.select_related("run", "run__scenario").order_by("-declared_at")[:20]
        return Response(IncidentSerializer(qs, many=True).data)

    def post(self, request: Request) -> Response:
        req = DeclareIncidentSerializer(data=request.data)
        if not req.is_valid():
            return Response(req.errors, status=status.HTTP_400_BAD_REQUEST)
        data = req.validated_data

        row = _scenario_or_400(data["scenario_slug"])
        if isinstance(row, Response):
            return row

        with transaction.atomic():
            incident = Incident.objects.create(
                severity=data["severity"],
                incident_commander=data["incident_commander"],
                ops_lead=data["ops_lead"],
                comms_lead=data["comms_lead"],
            )
            incident.run = runner.start_stepped_run(
                incident, row, controls_enabled=data["controls_enabled"], seed=data.get("seed")
            )
            incident.save(update_fields=["run"])
            IncidentAction.objects.create(
                incident=incident,
                tick=0,
                actor=data["incident_commander"] or "IC",
                action_type=ActionType.DECLARE,
                rationale="SEV-1 declared. Roles assumed as pre-assigned.",
            )

        return Response(_state_payload(incident), status=status.HTTP_201_CREATED)


class IncidentStateView(APIView):
    def get(self, request: Request, code: str) -> Response:
        with runner.lock_for(code):
            return Response(_state_payload(_incident(code)))


class IncidentStepView(APIView):
    def post(self, request: Request, code: str) -> Response:
        with runner.lock_for(code):
            req = StepRequestSerializer(data=request.data)
            if not req.is_valid():
                return Response(req.errors, status=status.HTTP_400_BAD_REQUEST)

            incident = _incident(code)
            engine = runner.live_engine(incident)
            if engine.finished:
                return _bad(f"{code} has already run to completion; there are no ticks left.")

            before = engine.tick
            new = []
            for _ in range(req.validated_data["ticks"]):
                if engine.finished:
                    break
                new.append(engine.step().as_dict())
            runner.persist_live(incident, engine)
            if engine.tick > incident.drill_clock_s:
                incident.drill_clock_s = engine.tick
                incident.save(update_fields=["drill_clock_s"])

            return Response(
                {
                    "from_tick": before,
                    "to_tick": engine.tick,
                    "finished": engine.finished,
                    "snapshots": TickSerializer(new, many=True).data,
                }
            )


class IncidentActionView(APIView):
    """POST /api/incidents/{code}/action/ -- a war-room decision.

    Written to the append-only log first, then applied to the live engine at the
    current tick, so the log is never behind the market it describes.
    """

    def post(self, request: Request, code: str) -> Response:
        with runner.lock_for(code):
            req = ActionRequestSerializer(data=request.data)
            if not req.is_valid():
                return Response(req.errors, status=status.HTTP_400_BAD_REQUEST)
            data = req.validated_data

            valid = {c for c, _ in ActionType.choices}
            if data["action_type"] not in valid:
                return _bad(
                    f"Unknown action_type {data['action_type']!r}. "
                    f"Valid: {', '.join(sorted(valid))}."
                )

            incident = _incident(code)
            engine = runner.live_engine(incident)
            if incident.status == IncidentStatus.RESOLVED:
                return _bad(f"{code} is resolved; the log is closed.")
            if engine.finished and data["action_type"] not in POST_MARKET_ACTIONS:
                return _bad(
                    f"The market event in {code} has ended, so {data['action_type']} "
                    f"no longer changes anything. Post-market decisions still apply: "
                    f"{', '.join(sorted(POST_MARKET_ACTIONS))}."
                )

            live = not engine.finished
            tick = engine.tick if live else runner.drill_clock(incident, engine)
            with transaction.atomic():
                logged = IncidentAction.objects.create(
                    incident=incident,
                    tick=tick,
                    actor=data["actor"],
                    action_type=data["action_type"],
                    params=data["params"],
                    rationale=data["rationale"],
                    reversible=data["action_type"] not in runner.IRREVERSIBLE,
                )
                kind = runner.ENGINE_ACTIONS.get(data["action_type"]) if live else None
                if kind is not None:
                    engine.queue_action(
                        OperatorAction(
                            tick=tick,
                            kind=kind,
                            value=data["params"].get("value"),
                            note=data["params"].get("note", ""),
                        )
                    )
                if data["action_type"] == ActionType.RESOLVE:
                    incident.status = IncidentStatus.RESOLVED
                    incident.resolved_at = timezone.now()
                    incident.save(update_fields=["status", "resolved_at"])
                elif data["action_type"] in STATUS_AFTER:
                    incident.status = STATUS_AFTER[data["action_type"]]
                    incident.save(update_fields=["status"])
                elif incident.status == IncidentStatus.DECLARED and kind is not None:
                    incident.status = IncidentStatus.CONTAINED
                    incident.save(update_fields=["status"])

            return Response(
                {
                    "action": IncidentActionSerializer(logged).data,
                    "affects_engine": kind is not None,
                    "applies_at_tick": tick,
                    "note": (
                        "Applied to the live engine; takes effect on the next step."
                        if kind is not None
                        else "Recorded in the audit log. This decision is about the "
                        "incident, not an instruction to the market."
                    ),
                },
                status=status.HTTP_201_CREATED,
            )


class IncidentClockView(APIView):
    """POST /api/incidents/{code}/clock/ -- advance the playbook clock once the
    market event has ended. Forward only, capped at T+60."""

    def post(self, request: Request, code: str) -> Response:
        with runner.lock_for(code):
            req = ClockRequestSerializer(data=request.data)
            if not req.is_valid():
                return Response(req.errors, status=status.HTTP_400_BAD_REQUEST)
            incident = _incident(code)
            engine = runner.live_engine(incident)
            if not engine.finished:
                return _bad(
                    f"The market event is still running (tick {engine.tick} of "
                    f"{engine.scenario.n_ticks}); step the engine instead."
                )
            target = min(req.validated_data["to_seconds"], runner.DRILL_SECONDS)
            current = runner.drill_clock(incident, engine)
            if target < current:
                return _bad(f"The clock only runs forward; it is already at {current}s.")
            incident.drill_clock_s = target
            incident.save(update_fields=["drill_clock_s"])
            return Response(_state_payload(incident))


class IncidentTicksView(APIView):
    """GET /api/incidents/{code}/ticks/?since=N -- the frames so far, for the
    war-room chart after a reload."""

    def get(self, request: Request, code: str) -> Response:
        with runner.lock_for(code):
            since = request.query_params.get("since", "0")
            if not since.isdigit():
                return _bad("`since` must be a non-negative integer tick.")
            engine = runner.live_engine(_incident(code))
            frames = [f.as_dict() for f in engine.frames[int(since):]]
            return Response({"from_tick": int(since), "ticks": TickSerializer(frames, many=True).data})


class NotYetImplemented(APIView):
    """A route that exists so its phase only has to fill in the body."""

    phase: int = 0
    feature: str = ""

    def _501(self) -> Response:
        return Response(
            {
                "detail": (
                    f"{self.feature} lands in Phase {self.phase}. The route, "
                    f"serializer and test exist now; the engine logic does not yet."
                ),
                "phase": self.phase,
            },
            status=status.HTTP_501_NOT_IMPLEMENTED,
        )


def _classification_payload(incident: Incident, engine) -> dict[str, Any]:
    detail = incident.classification_detail or None
    claims = incident.claims.select_related("account").order_by("account__liquidated_at_tick", "account__handle")
    return ClassificationSerializer({
        "status": "classified" if detail else "unclassified",
        "incident_code": incident.code,
        "market_finished": engine.finished,
        "current_tick": engine.tick,
        "verdict": detail,
        "claims": list(claims) if detail else [],
    }).data


class IncidentClassifyView(APIView):
    """GET/POST /api/incidents/{code}/classify/ -- the published APE test.

    POST runs it over everything the incident's engine has recorded so far and
    writes one claim per force-closed account, each carrying its category and
    the numbers behind it. Run mid-event it is marked provisional: fills in the
    last 60 seconds cannot pass or fail the reversion test yet. GET returns the
    last verdict without re-running anything.
    """

    def get(self, request: Request, code: str) -> Response:
        with runner.lock_for(code):
            incident = _incident(code)
            engine = runner.live_engine(incident)
            return Response(_classification_payload(incident, engine))

    def post(self, request: Request, code: str) -> Response:
        with runner.lock_for(code):
            incident = _incident(code)
            if incident.status == IncidentStatus.RESOLVED:
                return _bad("This incident is resolved; its classification is part of the record.")
            body = ClassifyRequestSerializer(data=request.data)
            body.is_valid(raise_exception=True)
            engine = runner.live_engine(incident)
            if not engine.frames:
                return _bad("Nothing to classify yet: the market has not started. Run the clock first.")
            runner.classify_incident(
                incident,
                engine,
                actor=body.validated_data["actor"] or incident.ops_lead or "OPS",
                rationale=body.validated_data["rationale"],
            )
            incident.refresh_from_db()
            return Response(_classification_payload(incident, engine))


class IncidentClaimsView(NotYetImplemented):
    phase, feature = 9, "Computed claims with counterfactual equity"

    def get(self, request: Request, code: str) -> Response:
        _incident(code)
        return self._501()


class ClaimDecideView(APIView):
    """A claim's decision is a state transition, independent of how it was
    computed, so it works now on any Claim row -- including ones entered in the
    admin -- and Phase 9 only has to start producing the rows."""

    def post(self, request: Request, code: str, claim_id: int) -> Response:
        incident = _incident(code)
        claim = get_object_or_404(
            Claim.objects.select_related("account"), pk=claim_id, incident=incident
        )
        req = ClaimDecisionSerializer(data=request.data)
        if not req.is_valid():
            return Response(req.errors, status=status.HTTP_400_BAD_REQUEST)
        data = req.validated_data

        if data["decision"] == ClaimStatus.PAID and claim.status not in (
            ClaimStatus.APPROVED,
            ClaimStatus.AUTO_APPROVED,
        ):
            return _bad("Only an approved claim can be marked paid. Approve it first.")

        claim.status = data["decision"]
        if data["decision"] == ClaimStatus.APPROVED:
            claim.approved_inr = (
                data["approved_inr"] if data.get("approved_inr") is not None else claim.claimed_inr
            )
        if data["decision"] == ClaimStatus.REJECTED:
            claim.approved_inr = 0
        claim.reason = data["reason"]
        claim.decided_by = data["decided_by"]
        claim.decided_at = timezone.now()
        claim.save()
        return Response(ClaimSerializer(claim).data)


class IncidentEvidenceView(APIView):
    """GET /api/incidents/{code}/evidence/?from=N&to=M -- the tape.

    One row per source per tick, straight from the persisted PriceObservation
    rows: every oracle source as it printed and as the composite used it, with
    the reason for every exclusion, then our mark, the composite we published
    and the Reference Composite. Anyone holding this can recompute the APE test.
    """

    def get(self, request: Request, code: str) -> Response:
        with runner.lock_for(code):
            incident = _incident(code)
            engine = runner.live_engine(incident)
            try:
                lo = int(request.query_params.get("from", 0))
                hi = int(request.query_params.get("to", max(0, engine.tick - 1)))
            except ValueError:
                return _bad("'from' and 'to' must be tick numbers.")
            if lo < 0 or hi < lo:
                return _bad("'from' must be at least 0 and no greater than 'to'.")
            rows = PriceObservation.objects.filter(run=incident.run, tick__gte=lo, tick__lte=hi).order_by("tick", "id")
            return Response(
                {
                    "incident_code": code,
                    "ticks_recorded": len(engine.frames),
                    "from_tick": lo,
                    "to_tick": hi,
                    "observations": PriceObservationSerializer(
                        [
                            {
                                "tick": r.tick, "source": r.source,
                                "source_display": r.get_source_display(), "rung": r.rung,
                                "price": None if r.price is None else float(r.price),
                                "raw_price": None if r.raw_price is None else float(r.raw_price),
                                "is_stale": r.is_stale, "weight": r.weight, "used": r.used,
                                "clamped": r.clamped, "excluded_reason": r.excluded_reason,
                            }
                            for r in rows
                        ],
                        many=True,
                    ).data,
                }
            )


class IncidentCommsView(APIView):
    def get(self, request: Request, code: str) -> Response:
        incident = _incident(code)
        return Response(CommsUpdateSerializer(incident.updates.all(), many=True).data)

    def post(self, request: Request, code: str) -> Response:
        with runner.lock_for(code):
            incident = _incident(code)
            req = CommsCreateSerializer(data=request.data)
            if not req.is_valid():
                return Response(req.errors, status=status.HTTP_400_BAD_REQUEST)
            data = req.validated_data

            sequence = data.get("sequence") or (
                (incident.updates.order_by("-sequence").values_list("sequence", flat=True).first() or 0)
                + 1
            )
            if incident.updates.filter(sequence=sequence, channel=data["channel"]).exists():
                return _bad(f"Update #{sequence} on {data['channel']} already exists.")

            publish = data.get("is_published", True)
            update = CommsUpdate.objects.create(
                incident=incident,
                sequence=sequence,
                channel=data["channel"],
                headline=data["headline"],
                body=data["body"],
                next_update_at=data.get("next_update_at"),
                is_published=publish,
                published_at=timezone.now() if publish else None,
            )
            if publish:
                engine = runner.live_engine(incident)
                IncidentAction.objects.create(
                    incident=incident,
                    tick=engine.tick,
                    actor=incident.comms_lead or "COMMS",
                    action_type=ActionType.PUBLISH_UPDATE,
                    params={"channel": update.channel, "sequence": update.sequence},
                    rationale=update.headline,
                )
            return Response(CommsUpdateSerializer(update).data, status=status.HTTP_201_CREATED)


class IncidentReportView(APIView):
    """GET /api/incidents/{code}/report/ -- the RCA payload.

    Everything that exists is reported now. Claims are marked pending until
    Phase 9 computes them, rather than failing the whole report because one
    section is not built.
    """

    def get(self, request: Request, code: str) -> Response:
        with runner.lock_for(code):
            incident = _incident(code)
            engine = runner.live_engine(incident)
            summary = engine.result().summary.as_dict() if engine.frames else {}
            return Response(
                {
                    "incident": IncidentSerializer(incident).data,
                    "run": {
                        "scenario_slug": incident.run.scenario.slug if incident.run else None,
                        "policy_version": incident.run.policy.version if incident.run else None,
                        "seed": incident.run.seed if incident.run else None,
                        "current_tick": engine.tick,
                        "summary": RunSummarySerializer(summary).data if summary else None,
                    },
                    "timeline": IncidentActionSerializer(
                        incident.actions.order_by("tick", "id"), many=True
                    ).data,
                    "comms": CommsUpdateSerializer(incident.updates.all(), many=True).data,
                    "classification": _classification_payload(incident, engine),
                    "claims": {"status": "pending", "phase": 9},
                }
            )


# --------------------------------------------------------------------------
# Public
# --------------------------------------------------------------------------

class PublicStatusView(APIView):
    """GET /api/status/ -- the public status page. Published updates only."""

    authentication_classes: list = []
    permission_classes: list = []

    def get(self, request: Request) -> Response:
        qs = (
            CommsUpdate.objects.filter(is_published=True)
            .select_related("incident")
            .order_by("-published_at", "-sequence")
        )
        return Response({"updates": PublicStatusUpdateSerializer(qs, many=True).data})
