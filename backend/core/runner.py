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
from dataclasses import asdict
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from django.utils import timezone

from riskengine.controls import ActionKind, ControlStack, OperatorAction
from riskengine.engine import Engine
from riskengine.scenario import Scenario as EngineScenario
from riskengine.scenario import by_key

from .models import ActionType, RiskPolicy, RunStatus, Scenario, SimRun


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


def fingerprint(params: Any) -> str:
    """A stable hash of every parameter value the engine will actually see.

    Deliberately over the values and not the version string: a policy edit that
    leaves the version alone still has to invalidate every cached run.
    """
    blob = json.dumps(asdict(params), sort_keys=True, separators=(",", ":"), default=str)
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

    result = Engine(
        scenario, params, control_stack(controls_enabled), seed=effective_seed
    ).run()

    run = SimRun.objects.create(
        scenario=row,
        policy=policy,
        controls_enabled=controls_enabled,
        seed=effective_seed,
        policy_fingerprint=print_key,
        status=RunStatus.DONE,
        current_tick=len(result.frames),
        total_ticks=len(result.frames),
        result_summary=result.summary.as_dict(),
        tick_data=[f.as_dict() for f in result.frames],
    )
    return run, True


# --------------------------------------------------------------------------
# Live stepped engines
# --------------------------------------------------------------------------

_LIVE: dict[str, Engine] = {}

#: Django action types that have a real effect on the simulation, and the
#: engine action they map to. Everything else is recorded in the audit log but
#: changes no state -- DECLARE and CLASSIFY are decisions about the incident,
#: not instructions to the market.
ENGINE_ACTIONS: dict[str, ActionKind] = {
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
    """Checkpoint a stepped run so a restart can rebuild it."""
    run = incident.run
    run.current_tick = engine.tick
    run.total_ticks = engine.scenario.n_ticks
    run.tick_data = [f.as_dict() for f in engine.frames]
    run.status = RunStatus.DONE if engine.finished else RunStatus.RUNNING
    if engine.finished:
        run.result_summary = engine.result().summary.as_dict()
    run.save(
        update_fields=[
            "current_tick",
            "total_ticks",
            "tick_data",
            "status",
            "result_summary",
        ]
    )


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
