"""The only place the API layer is allowed to touch the engine.

Three jobs, and every rule that matters for Phase 4 lives here:

1. **Configuration comes from the active RiskPolicy, never from the dataclass
   defaults.** `params()` is the single call site. No view, serializer or
   command may import `DEFAULT_PARAMS` or construct `RiskParams` -- enforced by
   `tests/test_api.py::test_no_view_bypasses_the_active_policy`, not by
   discipline. The point: a judge edits a margin tier in the admin, reloads the
   page, and the numbers move. If a view reached past the policy, the admin
   would be a decorative surface wired to nothing.

2. **Runs are persisted and reused.** A repeat view is a database read, never a
   re-simulation. The cache key is
   (scenario, controls_enabled, seed, policy_fingerprint) -- the fingerprint
   hashes the actual parameter values rather than the policy version, because
   editing a margin tier does not bump the version and keying on the version
   would serve a stale run that contradicts what the admin now says.

3. **Live stepped engines for the war room.** Held in a module-level dict keyed
   by incident code and never trusted to survive: if the process restarted, the
   engine is rebuilt silently by replaying the persisted action log from tick 0.
   That works only because the engine is deterministic, which is the whole
   reason the determinism contract was worth paying for.
"""
from __future__ import annotations

import hashlib
import json
import threading
from datetime import datetime, timedelta
from dataclasses import asdict
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from riskengine import classifier, remediation
from riskengine.controls import ActionKind, ControlStack, OperatorAction
from riskengine.indian import inr_text
from riskengine.engine import FRAME_SCHEMA, Engine
from riskengine.scenario import Scenario as EngineScenario
from riskengine.scenario import by_key

from .models import (
    ENGINE_SOURCE,
    SCALAR_PARAM_NAMES,
    ActionType,
    Claim,
    ClaimStatus,
    DepthSnapshot,
    Incident,
    IncidentAction,
    IncidentStatus,
    LiquidationRecord,
    PolicyInstrumentTier,
    PolicyMarginTier,
    PriceObservation,
    PriceSource,
    RiskPolicy,
    RunStatus,
    Scenario,
    SimAccount,
    SimRun,
)


class PolicyUnavailable(RuntimeError):
    """No active RiskPolicy. The app refuses to guess parameters. Served as 503:
    the server is not ready, and nothing the caller sends will fix that."""


class ScenarioUnavailable(RuntimeError):
    """A Scenario row points at an engine key that no longer exists, or an
    incident has no run to step. Served as 409: a conflict with stored state."""


# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------

def active_policy() -> RiskPolicy:
    policy = RiskPolicy.objects.filter(is_active=True).first()
    if policy is None:
        raise PolicyUnavailable(
            "No active RiskPolicy. Run `python manage.py seed_policy`. "
            "The engine is never run against hardcoded defaults."
        )
    return policy


def params_for(policy: RiskPolicy):
    """The ONLY route by which this project instantiates engine parameters."""
    return policy.to_params()


FUNDING_ONLY: frozenset[str] = frozenset({
    "incident_reserve_opening_inr",
    "reserve_funding_share_of_fees",
    "reserve_target_multiple_of_worst_loss",
})
"""Parameters that decide who FUNDS a payout and nothing else: neither the
engine nor the classifier nor any make-whole formula reads them. A new policy
version that differs only here produces byte-identical runs, so it must hit the
same cache -- which is also how 'Recalibrate from simulation' shows its loop
closing in one step."""


def fingerprint(params: Any) -> str:
    """A stable hash of everything that determines a stored run's contents.

    Two inputs. The parameter VALUES, not the version string -- a policy edit
    that leaves the version alone still has to invalidate every cached run, and
    a new version with identical values must not. And the engine's
    FRAME_SCHEMA -- a run stored before a frame field existed must not be
    served as though it had that field.
    """
    values = {k: v for k, v in asdict(params).items() if k != "version" and k not in FUNDING_ONLY}
    payload = {"frame_schema": FRAME_SCHEMA, "params": values}
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:32]


# --------------------------------------------------------------------------
# Scenario resolution
# --------------------------------------------------------------------------

def engine_scenario(row: Scenario) -> EngineScenario:
    """Map a database Scenario to its engine definition.

    The library stays the source of the definitions; the database is the source
    the app reads. `engine_key` is the join.
    """
    key = row.engine_key or row.slug
    try:
        return by_key(key)
    except KeyError as exc:
        raise ScenarioUnavailable(
            f"Scenario {row.slug!r} points at engine key {key!r}, which is not "
            f"in riskengine.scenario.library(). Re-run `manage.py seed_scenarios`."
        ) from exc


def control_stack(enabled: bool) -> ControlStack:
    return ControlStack.full() if enabled else ControlStack.none()


# --------------------------------------------------------------------------
# Persistence and cache
# --------------------------------------------------------------------------

def get_or_run(
    row: Scenario,
    *,
    controls_enabled: bool,
    seed: int | None = None,
    policy: RiskPolicy | None = None,
) -> tuple[SimRun, bool]:
    """Return a completed SimRun, executing it only if nothing matches.

    Second return value is True when the engine actually ran, so callers and
    tests can tell a cache hit from a miss.
    """
    policy = policy or active_policy()
    params = params_for(policy)
    print_key = fingerprint(params)
    scenario = engine_scenario(row)
    effective_seed = int(seed if seed is not None else scenario.seed)

    cached = (
        SimRun.objects.filter(
            scenario=row,
            controls_enabled=controls_enabled,
            seed=effective_seed,
            policy_fingerprint=print_key,
            status=RunStatus.DONE,
        )
        .order_by("-created_at")
        .first()
    )
    if cached is not None:
        return cached, False

    engine = Engine(scenario, params, control_stack(controls_enabled), seed=effective_seed)
    result = engine.run()
    frames = [f.as_dict() for f in result.frames]

    # One transaction: a DONE run without its tape would be served from the
    # cache forever with an empty evidence trail.
    with transaction.atomic():
        run = SimRun.objects.create(
            scenario=row,
            policy=policy,
            controls_enabled=controls_enabled,
            seed=effective_seed,
            policy_fingerprint=print_key,
            status=RunStatus.DONE,
            current_tick=len(frames),
            total_ticks=len(frames),
            result_summary=result.summary.as_dict(),
            modelled_claims=_modelled(engine),
            tick_data=frames,
        )
        write_observations(run, frames)
    return run, True


# --------------------------------------------------------------------------
# The evidence tape
# --------------------------------------------------------------------------

def _dec(value: Any) -> Decimal | None:
    return None if value is None else Decimal(repr(float(value)))


def observation_rows(run: SimRun, frames: list[dict]) -> list[PriceObservation]:
    """Per tick: every oracle source, then the three derived prices -- our mark,
    the composite we published, and the Reference Composite rebuilt afterwards.
    Derived rows carry no rung, which is how the tape tells them apart."""
    rows: list[PriceObservation] = []
    for f in frames:
        tick = f["tick"]
        for o in f.get("sources") or ():
            rows.append(
                PriceObservation(
                    run=run,
                    tick=tick,
                    source=ENGINE_SOURCE.get(o["source"], o["source"].upper()[:16]),
                    rung=o["rung"],
                    price=_dec(o["price"]),
                    raw_price=_dec(o["raw_price"]),
                    is_stale=o["is_stale"],
                    weight=o["weight"],
                    used=o["used"],
                    clamped=o["clamped"],
                    excluded_reason=o["excluded_reason"],
                )
            )
        rows.append(PriceObservation(
            run=run, tick=tick, source=PriceSource.MOCHATRADE,
            price=_dec(f["mark"]), weight=0.0,
        ))
        rows.append(PriceObservation(
            run=run, tick=tick, source=PriceSource.COMPOSITE,
            price=_dec(f["composite"]), weight=0.0,
            excluded_reason="" if f["composite"] is not None else f["oracle_reason"][:160],
        ))
        rows.append(PriceObservation(
            run=run, tick=tick, source=PriceSource.REFERENCE,
            price=_dec(f["reference"]), weight=0.0,
        ))
    return rows


def write_observations(run: SimRun, frames: list[dict]) -> int:
    """The whole tape for these frames, in the caller's transaction: oracle
    observations, liquidation fills and depth snapshots."""
    rows = observation_rows(run, frames)
    PriceObservation.objects.bulk_create(rows, batch_size=5000)
    LiquidationRecord.objects.bulk_create(
        [
            LiquidationRecord(
                run=run,
                tick=f["tick"],
                account=x["account_id"],
                stage=x["stage"],
                qty=x["qty"],
                notional_inr=_dec(round(x["notional"], 2)),
                price=_dec(x["price"]),
                via_auction=x["via_auction"],
                closed=x["closed"],
                survived_at_reference=x["survived_at_reference"],
            )
            for f in frames
            for x in f.get("liquidations") or ()
        ],
        batch_size=5000,
    )
    DepthSnapshot.objects.bulk_create(
        [
            DepthSnapshot(
                run=run,
                tick=f["tick"],
                mid=f["book_mid"],
                best_bid=f["best_bid"],
                best_ask=f["best_ask"],
                bucket_bps=f["depth"]["bucket_bps"],
                bids=list(f["depth"]["bids"]),
                asks=list(f["depth"]["asks"]),
                depth_pct_of_baseline=f["depth_pct_of_baseline"],
            )
            for f in frames
            if f.get("depth")
        ],
        batch_size=5000,
    )
    return len(rows)


# --------------------------------------------------------------------------
# Live stepped engines
# --------------------------------------------------------------------------

_LIVE: dict[str, Engine] = {}

_LOCKS: dict[str, threading.RLock] = {}
_LOCKS_GUARD = threading.Lock()


def lock_for(code: str) -> threading.RLock:
    """One lock per incident. The dev server is multi-threaded, and a live
    engine is a plain in-memory object: without this, an operator decision
    arriving while the clock is stepping read the tick, the step advanced the
    engine, and the engine then refused an action queued in its own past -- an
    intermittent 400 on exactly the click that matters most."""
    with _LOCKS_GUARD:
        lock = _LOCKS.get(code)
        if lock is None:
            lock = _LOCKS[code] = threading.RLock()
        return lock

#: Django action types that have a real effect on the simulation, and the
#: engine action they map to. Everything else is recorded in the audit log but
#: changes no state -- DECLARE and CLASSIFY are decisions about the incident,
#: not instructions to the market.
ENGINE_ACTIONS: dict[str, ActionKind] = {
    ActionType.PROTECT_SWITCH: ActionKind.PROTECT_SWITCH,
    ActionType.REDUCE_ONLY: ActionKind.REDUCE_ONLY,
    ActionType.PAUSE_LIQUIDATIONS: ActionKind.PAUSE_LIQUIDATIONS,
    ActionType.LIQ_THROTTLE: ActionKind.THROTTLE_LIQUIDATIONS,
    ActionType.LEVERAGE_CAP: ActionKind.SET_MAX_LEVERAGE,
    ActionType.HALT_MARKET: ActionKind.HALT_TRADING,
    ActionType.SNAPSHOT_EVIDENCE: ActionKind.SNAPSHOT_EVIDENCE,
    ActionType.PUBLISH_UPDATE: ActionKind.PUBLISH_UPDATE,
    ActionType.STAGED_REOPEN: ActionKind.STAGED_REOPEN,
}

IRREVERSIBLE = {ActionType.HALT_MARKET}


def live_engine(incident) -> Engine:
    """The engine backing a stepped incident, rebuilt if the process restarted.

    Rebuilding replays the persisted IncidentAction log from tick 0 and steps
    forward to the recorded tick. Silent and automatic, and exact because the
    engine is deterministic: the same seed plus the same action sequence gives
    byte-identical state.
    """
    engine = _LIVE.get(incident.code)
    if engine is not None:
        return engine

    run = incident.run
    if run is None:
        raise ScenarioUnavailable(
            f"Incident {incident.code} has no run attached; it cannot be stepped."
        )

    policy = run.policy
    scenario = engine_scenario(run.scenario)
    actions = tuple(
        OperatorAction(
            tick=a.tick,
            kind=ENGINE_ACTIONS[a.action_type],
            value=(a.params or {}).get("value"),
            note=(a.params or {}).get("note", ""),
        )
        for a in incident.actions.order_by("tick", "id")
        if a.action_type in ENGINE_ACTIONS
    )
    engine = Engine(
        scenario,
        params_for(policy),
        control_stack(run.controls_enabled),
        seed=run.seed,
        actions=actions,
    )
    target = min(run.current_tick, scenario.n_ticks)
    while engine.tick < target:
        engine.step()

    _LIVE[incident.code] = engine
    return engine


def forget_engine(code: str) -> None:
    _LIVE.pop(code, None)


def persist_live(incident, engine: Engine) -> None:
    """Checkpoint a stepped run so a restart can rebuild it, and extend its
    evidence tape by exactly the ticks not yet written -- never re-writing the
    ones already there, including after a rebuild."""
    run = incident.run
    written = PriceObservation.objects.filter(run=run).aggregate(m=Max("tick"))["m"]
    fresh = [f.as_dict() for f in engine.frames if written is None or f.tick > written]
    run.current_tick = engine.tick
    run.total_ticks = engine.scenario.n_ticks
    run.tick_data = [f.as_dict() for f in engine.frames]
    run.status = RunStatus.DONE if engine.finished else RunStatus.RUNNING
    if engine.finished:
        run.result_summary = engine.result().summary.as_dict()
    with transaction.atomic():
        run.save(
            update_fields=[
                "current_tick",
                "total_ticks",
                "tick_data",
                "status",
                "result_summary",
            ]
        )
        write_observations(run, fresh)


def start_stepped_run(
    incident, row: Scenario, *, controls_enabled: bool, seed: int | None
) -> SimRun:
    """Create the SimRun behind a declared incident, at tick zero."""
    policy = active_policy()
    params = params_for(policy)
    scenario = engine_scenario(row)
    effective_seed = int(seed if seed is not None else scenario.seed)

    run = SimRun.objects.create(
        scenario=row,
        policy=policy,
        controls_enabled=controls_enabled,
        seed=effective_seed,
        policy_fingerprint=fingerprint(params),
        status=RunStatus.RUNNING,
        current_tick=0,
        total_ticks=scenario.n_ticks,
        result_summary={},
        tick_data=[],
    )
    _LIVE[incident.code] = Engine(
        scenario, params, control_stack(controls_enabled), seed=effective_seed
    )
    return run


def declare_incident(
    row: Scenario,
    *,
    controls_enabled: bool,
    seed: int | None = None,
    severity: str = "SEV1",
    incident_commander: str = "",
    ops_lead: str = "",
    comms_lead: str = "",
    declared_at: datetime | None = None,
) -> Incident:
    """Open the record at T+0: the incident, its stepped run at tick zero, and
    the DECLARE entry in the log. `declared_at` defaults to now; the demo seed
    passes the time its drill began, so every time derived from it (the next
    update, the provisional-credit deadline, the SEBI dates) is the drill's."""
    at = declared_at or timezone.now()
    with transaction.atomic():
        incident = Incident.objects.create(
            severity=severity,
            declared_at=at,
            incident_commander=incident_commander,
            ops_lead=ops_lead,
            comms_lead=comms_lead,
        )
        incident.run = start_stepped_run(incident, row, controls_enabled=controls_enabled, seed=seed)
        incident.save(update_fields=["run"])
        IncidentAction.objects.create(
            incident=incident,
            tick=0,
            wall_clock=at,
            actor=incident_commander or "IC",
            action_type=ActionType.DECLARE,
            rationale="SEV-1 declared. Roles assumed as pre-assigned.",
        )
    return incident


DRILL_SECONDS = 3600
"""The playbook runs T+0 to T+60 minutes."""


def drill_clock(incident, engine: Engine) -> int:
    """The playbook clock: the engine tick while the market event runs, then
    whatever the operator has advanced it to."""
    return max(incident.drill_clock_s, engine.tick)


def elapsed_seconds(incident) -> float:
    return round((timezone.now() - incident.declared_at).total_seconds(), 1)


PAISE = Decimal("0.01")


def money(value: Any) -> str:
    """Money crosses the wire as a decimal string, always to two places.

    JSON numbers are IEEE doubles, and a compensation figure that changes in the
    last place because it went through JavaScript is not a figure anyone should
    put in a public incident report. A Decimal is quantized directly and never
    detoured through float; an engine float enters via its shortest repr, so
    0.1 arrives as 0.10 and not as 0.1000000000000000055511151231257827.
    """
    if value is None:
        value = 0
    amount = value if isinstance(value, Decimal) else Decimal(repr(float(value)))
    return str(amount.quantize(PAISE, rounding=ROUND_HALF_UP))


# --------------------------------------------------------------------------
# Forensics: the published APE test, run against the incident's own tape
# --------------------------------------------------------------------------

DECIDED = {ClaimStatus.APPROVED, ClaimStatus.REJECTED, ClaimStatus.PAID}
LIABLE = {"C", "D", "E", "G"}
"""Categories where somebody other than the market owes the user: us (C, D, E)
or the attacker, fronted by the Incident Reserve (G)."""


def _inr(value: float) -> Decimal:
    return Decimal(repr(float(value))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _px(value: float | None) -> Decimal:
    return Decimal(repr(float(value or 0.0))).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


def classify_incident(incident, engine: Engine, *, actor: str, rationale: str):
    """Run the APE test over everything this incident's engine has recorded and
    write the verdict down: one SimAccount and one Claim per force-closed
    account, each with its category and the working behind it; the incident's
    class, layer and evidence; and a CLASSIFY entry in the action log.

    Re-running on a longer tape refreshes every claim nobody has decided yet.
    A claim a human approved, rejected or paid is never rewritten by a machine.
    """
    result = classifier.classify(
        engine.scenario, engine.params, engine.frames, engine.events, engine.accounts,
        finished=engine.finished,
    )
    run = incident.run
    by_id = {a.id: a for a in engine.accounts}
    tick = engine.tick if not engine.finished else drill_clock(incident, engine)
    with transaction.atomic():
        existing = {sa.handle: sa for sa in SimAccount.objects.filter(run=run)}
        fresh: list[SimAccount] = []
        for v in result.accounts:
            a = by_id[v.account_id]
            _, counterfactual = engine.valuation(a)
            sa = existing.get(v.account_id) or SimAccount(run=run, handle=v.account_id)
            sa.side = v.side
            sa.notional_inr = _inr(v.entry_notional)
            sa.leverage = v.leverage
            sa.entry_price = _px(v.entry_price)
            sa.collateral_inr = _inr(v.collateral)
            sa.liquidated_at_tick = v.first_tick
            sa.liquidation_price = _px(v.executed_price)
            sa.realised_pnl_inr = _inr(a.realised_pnl)
            sa.was_adl = v.category == "F"
            sa.counterfactual_equity_inr = _inr(counterfactual)
            if sa.pk is None:
                fresh.append(sa)
            else:
                sa.save()
        SimAccount.objects.bulk_create(fresh, batch_size=500)
        accounts = {sa.handle: sa for sa in SimAccount.objects.filter(run=run)}

        claims = {c.account.handle: c for c in incident.claims.select_related("account")}
        new_claims: list[Claim] = []
        for v in result.accounts:
            a = by_id[v.account_id]
            equity, counterfactual = engine.valuation(a)
            claim = claims.get(v.account_id)
            if claim is not None and claim.status in DECIDED and claim.decided_by:
                continue
            claim = claim or Claim(incident=incident, account=accounts[v.account_id])
            claim.category = v.category
            claim.executed_price = _px(v.executed_price)
            claim.reference_composite_price = _px(v.reference_price)
            claim.deviation_pct = round(v.deviation_bps / 100.0, 3)
            claim.counterfactual_equity_inr = _inr(counterfactual)
            claim.reason = v.reason
            claim.evidence = {
                **v.as_dict(),
                "equity_inr": round(equity, 2),
                "counterfactual_equity_inr": round(counterfactual, 2),
            }
            if claim.pk is None:
                new_claims.append(claim)
            else:
                claim.save()
        Claim.objects.bulk_create(new_claims, batch_size=500)

        detail = result.as_dict()
        detail.pop("accounts")
        incident.classification = result.category
        incident.root_cause_layer = result.layer.upper()
        incident.affected_accounts_count = sum(result.counts[c] for c in LIABLE)
        incident.classification_detail = detail
        if incident.status in (IncidentStatus.DECLARED, IncidentStatus.CONTAINED):
            incident.status = IncidentStatus.DIAGNOSED
        incident.save(update_fields=[
            "classification", "root_cause_layer", "affected_accounts_count",
            "classification_detail", "status",
        ])
        IncidentAction.objects.create(
            incident=incident,
            tick=tick,
            actor=actor,
            action_type=ActionType.CLASSIFY,
            params={
                "category": result.category,
                "counts": result.counts,
                "provisional": result.provisional,
                "at_tick": result.at_tick,
            },
            rationale=rationale or f"Class {result.category}. {result.headline}",
            reversible=True,
        )
    return result


# --------------------------------------------------------------------------
# Remediation: make-whole, the waterfall, and the reserve's own calibration
# --------------------------------------------------------------------------

def _remedies_for(engine: Engine, verdict):
    accounts = {a.id: a for a in engine.accounts}
    valuations = {v.account_id: engine.valuation(accounts[v.account_id]) for v in verdict.accounts}
    return remediation.remedies(verdict, accounts, engine.events, engine.frames, valuations)


def _modelled(engine: Engine) -> dict[str, Any]:
    """What a finished run would owe under the published formulas, uncapped."""
    verdict = classifier.classify(
        engine.scenario, engine.params, engine.frames, engine.events, engine.accounts,
        finished=engine.finished,
    )
    items = _remedies_for(engine, verdict)
    cash = [r for r in items if r.kind == "cash"]
    return {
        "category": verdict.category,
        "claims_total_inr": round(sum(r.make_whole for r in cash), 2),
        "cash_accounts": len(cash),
        "counts": verdict.counts,
    }


def modelled_claims(run: SimRun) -> dict[str, Any]:
    """A cached run's modelled claims, computed once for runs stored before
    claims were modelled. Deterministic: the replay is the same run."""
    if run.modelled_claims:
        return run.modelled_claims
    params = params_for(run.policy)
    engine = Engine(
        engine_scenario(run.scenario), params, control_stack(run.controls_enabled), seed=run.seed
    )
    engine.run()
    run.modelled_claims = _modelled(engine)
    run.save(update_fields=["modelled_claims"])
    return run.modelled_claims


def reserve_drawn_by_others(incident) -> float:
    """What earlier incidents have already drawn from the Incident Reserve. The
    reserve is one ring-fenced balance, published, so a second incident in the
    same month sees what the first one left."""
    drawn = 0.0
    for other in Incident.objects.exclude(pk=incident.pk).exclude(remediation_detail={}):
        tranches = (other.remediation_detail.get("waterfall") or {}).get("tranches") or []
        drawn += sum(float(t.get("drawn") or 0.0) for t in tranches if t.get("step") == 2)
    return drawn


def open_claims(incident, engine: Engine, *, actor: str, rationale: str):
    """Size every claim by the published formula for its class and fund the
    lot through the waterfall, in order, up to the per-incident cap.

    Clear-cut C/D/E claims are auto-approved and their provisional credit is
    set now, due inside the speed-clause window: nobody files a ticket to get
    their own money back. G waits for the IC. A, B and F owe no cash: B's fees
    are rebated, F's evidence pack goes to the venue. A claim a human already
    decided keeps its decision; a rejected one draws nothing.
    """
    detail = incident.classification_detail or {}
    if not detail or detail.get("at_tick") != (engine.frames[-1].tick if engine.frames else 0):
        classify_incident(
            incident, engine, actor=actor,
            rationale="Re-run before sizing claims, so every claim is judged on the full tape.",
        )
        incident.refresh_from_db()
    params = engine.params
    verdict = classifier.classify(
        engine.scenario, params, engine.frames, engine.events, engine.accounts, finished=engine.finished,
    )
    items = {r.account_id: r for r in _remedies_for(engine, verdict)}
    claims = {c.account.handle: c for c in incident.claims.select_related("account")}
    rejected = {h for h, c in claims.items() if c.status == ClaimStatus.REJECTED and c.decided_by}
    funded = [r for h, r in items.items() if h not in rejected]
    reserve_available = max(0.0, params.incident_reserve_opening_inr - reserve_drawn_by_others(incident))
    plan = remediation.waterfall(funded, params, reserve_available=reserve_available)
    deadline = incident.declared_at + timedelta(minutes=params.provisional_credit_minutes)
    tick = engine.tick if not engine.finished else drill_clock(incident, engine)

    with transaction.atomic():
        for handle, r in items.items():
            claim = claims.get(handle)
            if claim is None or (claim.status in DECIDED and claim.decided_by):
                continue
            cash = r.make_whole * plan.ratio if r.kind == "cash" else 0.0
            claim.claimed_inr = _inr(r.make_whole)
            claim.approved_inr = _inr(cash) if r.category in remediation.PROVISIONAL_CLASSES else Decimal("0")
            claim.provisional_credit_inr = (
                _inr(cash) if r.category in remediation.PROVISIONAL_CLASSES else Decimal("0")
            )
            if r.category in remediation.PROVISIONAL_CLASSES:
                claim.status = ClaimStatus.AUTO_APPROVED
            elif r.category == "B":
                claim.status = ClaimStatus.AUTO_APPROVED
            elif r.category == "G":
                claim.status = ClaimStatus.PENDING
            else:
                claim.status = ClaimStatus.REJECTED
            claim.evidence = {
                **(claim.evidence or {}),
                "remedy": {
                    **r.as_dict(),
                    "cash_inr": round(cash, 2),
                    "make_good_inr": round(r.make_whole - cash, 2) if r.kind == "cash" else 0.0,
                    "pro_rata": plan.pro_rata and r.kind == "cash",
                },
            }
            claim.save()

        incident.aggregate_exposure_inr = _inr(plan.total_claims)
        incident.remediation_detail = {
            "policy_version": params.version,
            "computed_at_tick": tick,
            "provisional_deadline": deadline.isoformat(),
            "provisional_minutes": params.provisional_credit_minutes,
            "reserve": {
                "opening": params.incident_reserve_opening_inr,
                "drawn_by_other_incidents": round(params.incident_reserve_opening_inr - reserve_available, 2),
                "available": round(reserve_available, 2),
            },
            "waterfall": plan.as_dict(),
        }
        if incident.status != IncidentStatus.RESOLVED:
            incident.status = IncidentStatus.REMEDIATING
        incident.save(update_fields=["aggregate_exposure_inr", "remediation_detail", "status"])
        IncidentAction.objects.create(
            incident=incident,
            tick=tick,
            actor=actor,
            action_type=ActionType.OPEN_CLAIMS,
            params={
                "total_claims": round(plan.total_claims, 2),
                "payable": round(plan.payable, 2),
                "pro_rata": plan.pro_rata,
                "ratio": round(plan.ratio, 4),
            },
            rationale=rationale or (
                f"Claims opened: {inr_text(plan.total_claims)} claimed, {inr_text(plan.payable)} payable"
                + (f", pro-rata at {plan.ratio:.1%} above the {inr_text(plan.cap)} cap." if plan.pro_rata else ", every claim in full.")
            ),
            reversible=True,
        )
    return plan


def _next_version() -> str:
    numbers = [
        int(v[1:]) for v in RiskPolicy.objects.values_list("version", flat=True)
        if v.startswith("v") and v[1:].isdigit()
    ]
    return f"v{max(numbers, default=0) + 1}"


def clone_policy(policy: RiskPolicy, *, version: str, notes: str, **changes: Any) -> RiskPolicy:
    """A new, active version: every value copied, the named ones changed, the
    ladders copied row for row. The round trip is checked before returning."""
    values = {name: getattr(policy, name) for name in SCALAR_PARAM_NAMES}
    unknown = set(changes) - set(values)
    if unknown:
        raise ValueError(f"Not policy parameters: {sorted(unknown)}")
    values.update(changes)
    with transaction.atomic():
        new = RiskPolicy.objects.create(version=version, name=policy.name, is_active=True, notes=notes, **values)
        for t in policy.margin_tier_rows.all():
            PolicyMarginTier.objects.create(
                policy=new, ordering=t.ordering, notional_floor=t.notional_floor,
                notional_ceiling=t.notional_ceiling, max_leverage=t.max_leverage, mm_pct=t.mm_pct,
            )
        for t in policy.instrument_tier_rows.all():
            PolicyInstrumentTier.objects.create(
                policy=new, tier=t.tier, label=t.label, nrr_pct=t.nrr_pct,
                nrr_offhours_pct=t.nrr_offhours_pct, dcb_variant_pct=t.dcb_variant_pct,
            )
        expected = params_for(policy).evolve(version=version, **changes)
        if params_for(new) != expected:
            raise RuntimeError("The cloned policy does not round-trip. Nothing was written.")
    return new


def recalibrate_reserve(*, actor: str) -> dict[str, Any]:
    """'Recalibrate from simulation'. Research 5.3 sizes the Incident Reserve
    at 2x the worst modelled 30-day loss -- a number only the simulator can
    produce, under a policy that already needs a reserve. Resolve it: run every
    seeded scenario both ways under the active policy, take the worst cash
    liability under the published formulas, and write a new version whose
    reserve is the target. The per-incident cap is not touched.

    Because the reserve feeds neither the engine nor the classifier, the new
    version's runs are the same runs -- the fingerprint says so -- and the
    worst loss under it is the same number. The loop closes in one step; a
    second recalibration writes nothing.
    """
    policy = active_policy()
    params = params_for(policy)
    rows = list(Scenario.objects.select_related("instrument").order_by("slug"))
    if not rows:
        raise ScenarioUnavailable("No scenarios to model. Run `manage.py seed_scenarios`.")
    table: list[dict[str, Any]] = []
    for row in rows:
        for enabled in (True, False):
            run, _ = get_or_run(row, controls_enabled=enabled, policy=policy)
            m = modelled_claims(run)
            table.append({
                "slug": row.slug,
                "name": row.name,
                "controls_enabled": enabled,
                "category": m["category"],
                "claims_total_inr": money(m["claims_total_inr"]),
                "cash_accounts": m["cash_accounts"],
                "above_cap": m["claims_total_inr"] > params.per_incident_cap_inr,
                "run_id": run.pk,
            })
    worst = max(table, key=lambda r: Decimal(r["claims_total_inr"]))
    worst_loss = float(worst["claims_total_inr"])
    target = round(remediation.reserve_target(worst_loss, params), 2)
    previous = params.incident_reserve_opening_inr
    converged = abs(target - previous) < 1.0

    new_policy = None
    if not converged:
        version = _next_version()
        new_policy = clone_policy(
            policy,
            version=version,
            notes=(
                f"Recalibrated from simulation by {actor} on "
                f"{timezone.localtime():%d %b %Y %H:%M} IST. Worst modelled loss: {inr_text(worst_loss)} "
                f"({worst['name']}, controls {'on' if worst['controls_enabled'] else 'off'}) across "
                f"{len(table)} seeded runs under {policy.version}. Reserve set to "
                f"{params.reserve_target_multiple_of_worst_loss:g}x that: {inr_text(target)} "
                f"(was {inr_text(previous)}). Per-incident cap unchanged at {inr_text(params.per_incident_cap_inr)}."
            ),
            incident_reserve_opening_inr=target,
        )
    same_runs = fingerprint(params_for(new_policy)) == fingerprint(params) if new_policy else True
    return {
        "previous_version": policy.version,
        "new_version": new_policy.version if new_policy else None,
        "active_version": (new_policy or policy).version,
        "rows": table,
        "worst": worst,
        "multiple": params.reserve_target_multiple_of_worst_loss,
        "previous_reserve_inr": money(previous),
        "target_reserve_inr": money(target),
        "cap_inr": money(params.per_incident_cap_inr),
        "converged": converged,
        "same_runs": same_runs,
        "explanation": (
            "Already at the fixed point: the reserve equals the target the simulation gives, "
            "so no new version was written."
            if converged else
            f"{new_policy.version if new_policy else ''} differs from {policy.version} only in the reserve, "
            "which neither the engine nor the classifier reads. Its runs are the same cached runs, "
            "so recalibrating again gives the same target and writes nothing: the loop closed in one step."
        ),
    }


# --------------------------------------------------------------------------
# Comms: the facts every template and guardrail reads
# --------------------------------------------------------------------------

def _controls_on(incident, engine: Engine) -> str:
    """What we turned on, in words a user reads: operator switches from the
    log, automatic protections from the engine's live state."""
    done = set(incident.actions.values_list("action_type", flat=True))
    parts: list[str] = []
    if ActionType.PROTECT_SWITCH in done:
        parts.append("reduce-only, a liquidation throttle and a 3x leverage cap")
    else:
        if ActionType.REDUCE_ONLY in done:
            parts.append("reduce-only")
        if ActionType.LIQ_THROTTLE in done:
            parts.append("a liquidation throttle")
        if ActionType.LEVERAGE_CAP in done:
            parts.append("a 3x leverage cap")
    snap = engine.frames[-1] if engine.frames else None
    if (snap and snap.liquidations_paused) or ActionType.PAUSE_LIQUIDATIONS in done:
        parts.append("liquidations paused on this market while prices are verified")
    if snap and snap.trading_paused:
        parts.append("a trading pause that reopens through a short auction")
    if parts:
        return ", ".join(parts)
    return "our automatic volatility controls" if engine.controls.enabled else "nothing yet; the Protect Switch is next"


def comms_facts(incident, engine: Engine):
    from . import comms

    detail = incident.classification_detail or {}
    signals = detail.get("signals") or {}
    plan = (incident.remediation_detail or {}).get("waterfall") or {}
    window = incident.claims.filter(category__in=sorted(LIABLE)).select_related("account")
    ticks = [c.account.liquidated_at_tick for c in window if c.account.liquidated_at_tick is not None]
    deadline = (incident.remediation_detail or {}).get("provisional_deadline")
    return comms.Facts(
        code=incident.code,
        instrument=engine.scenario.instrument,
        scenario=engine.scenario.title,
        classified=bool(detail),
        category=incident.classification if detail else "",
        affected=incident.affected_accounts_count,
        claims_open=bool(plan),
        total_claims=float(plan.get("total_claims") or 0.0),
        payable=float(plan.get("payable") or 0.0),
        shortfall=float(plan.get("shortfall") or 0.0),
        pro_rata=bool(plan.get("pro_rata")),
        ratio=float(plan.get("ratio") or 1.0),
        cap=engine.params.per_incident_cap_inr,
        names=tuple(n for n in (incident.incident_commander, incident.comms_lead) if n),
        declared_at=incident.declared_at,
        drill_seconds=drill_clock(incident, engine),
        event_from_tick=min(ticks) if ticks else None,
        event_to_tick=max(ticks) if ticks else None,
        controls=_controls_on(incident, engine),
        provisional_deadline=datetime.fromisoformat(deadline) if deadline else None,
        solvency_note="",
        mark_on_last_trade=bool(signals.get("ltp_marked_liquidations")) and not signals.get("composite_defect"),
    )
