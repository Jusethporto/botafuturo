"""Architecture test: a FORWARD GUARD for the real Exnova broker adapter,
which is deliberately deferred (see `adapters/exnova/__init__.py`'s
docstring and `docs/spike-report.md`).

`src/botafuturo/adapters/exnova/` today contains only a docstring -- no real
code -- so both checks below pass trivially right now. They exist NOW,
before Phase 8/the Exnova adapter lands, so that PR is forced to either keep
the module free of an order-submission surface and a second `BrokerPort`
implementation, or deliberately update/replace this test as part of that
change -- never silently grow one as a side effect.

  1. No function/method named `place`, `buy`, `sell`, `order`, or
     `submit_order` may be DEFINED under this package (an order-submission
     surface belongs to a reviewed, scoped PR, not an incidental helper).
  2. Nothing there may yet structurally satisfy `BrokerPort` (see
     `test_only_paper_broker_implementation.py` for the same structural
     check, applied here to a currently-empty package).
"""
from __future__ import annotations

import ast
import importlib
import inspect
from pathlib import Path
from typing import List

from botafuturo.ports.broker import BrokerPort

SRC_DIR = Path(__file__).resolve().parents[2] / "src"
EXNOVA_ROOT = SRC_DIR / "botafuturo" / "adapters" / "exnova"

_FORBIDDEN_FUNCTION_NAMES = frozenset({"place", "buy", "sell", "order", "submit_order"})


def _module_name_for(path: Path) -> str:
    relative = path.relative_to(SRC_DIR)
    parts = relative.with_suffix("").parts
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _defined_function_names(path: Path) -> List[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: List[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name in _FORBIDDEN_FUNCTION_NAMES:
                names.append(node.name)
    return names


def _satisfies_broker_port(cls: type) -> bool:
    try:
        instance = object.__new__(cls)
    except TypeError:
        return False
    try:
        return isinstance(instance, BrokerPort)
    except TypeError:
        return False


def test_exnova_adapter_defines_no_order_submission_functions() -> None:
    violations: List[str] = []
    for path in sorted(EXNOVA_ROOT.rglob("*.py")):
        for name in _defined_function_names(path):
            violations.append(f"{path.name}: defines forbidden function/method {name!r}")

    assert not violations, (
        "The (deferred) Exnova adapter must not define an order-submission "
        f"surface until that phase is deliberately scoped in: {violations}"
    )


def test_exnova_adapter_defines_no_broker_port_implementation() -> None:
    violators: List[str] = []
    for path in sorted(EXNOVA_ROOT.rglob("*.py")):
        module_name = _module_name_for(path)
        module = importlib.import_module(module_name)
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if obj.__module__ != module_name:
                continue
            if _satisfies_broker_port(obj):
                violators.append(f"{module_name}.{obj.__name__}")

    assert not violators, (
        "src/botafuturo/adapters/exnova must not yet define a BrokerPort "
        f"implementation: {violators}"
    )
