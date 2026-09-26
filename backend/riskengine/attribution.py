"""One attribution run: a scenario under one control stack, alone or last in.

Its own module inside the pure engine package, so a process pool can run it:
on macOS and Windows the pool starts fresh interpreters that import the
function's module, and a module under core/ would import Django models before
Django is set up (AppRegistryNotReady).
"""
from __future__ import annotations

from typing import Any

from .controls import ControlStack
from .engine import Engine
from .params import RiskParams
from .scenario import by_key

ALONE = "alone"
LAST_IN = "last_in"


def stack_for(name: str, mode: str) -> ControlStack:
    """ALONE: only this control on. LAST_IN: the full stack without it."""
    return ControlStack.none().with_only(name) if mode == ALONE else ControlStack.full().without(name)


def summary(key: str, params: RiskParams, name: str, mode: str, seed: int) -> dict[str, Any]:
    return Engine(by_key(key), params, stack_for(name, mode), seed=seed).run().summary.as_dict()
