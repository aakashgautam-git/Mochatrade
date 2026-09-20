"""Guards the one architectural rule the whole demo rests on.

riskengine is pure Python: deterministic, dependency-free and testable without
Django. This test fails the moment that stops being true.
"""
from __future__ import annotations

import ast
import importlib
import pkgutil
from pathlib import Path

import riskengine

ENGINE_DIR = Path(riskengine.__file__).parent
FORBIDDEN_ROOTS = {"django", "rest_framework", "corsheaders", "core", "config"}


def _module_paths() -> list[Path]:
    return sorted(ENGINE_DIR.glob("*.py"))


def _imported_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def test_riskengine_has_modules() -> None:
    assert len(_module_paths()) > 1, "riskengine should not be empty"


def test_riskengine_never_imports_django() -> None:
    offenders: list[str] = []
    for path in _module_paths():
        leaked = _imported_roots(path) & FORBIDDEN_ROOTS
        if leaked:
            offenders.append(f"{path.name}: {sorted(leaked)}")
    assert not offenders, "riskengine must stay Django-free -> " + "; ".join(offenders)


def test_every_riskengine_module_imports_standalone() -> None:
    """Importable with no Django settings configured and no database."""
    for module in pkgutil.iter_modules([str(ENGINE_DIR)]):
        importlib.import_module(f"riskengine.{module.name}")
