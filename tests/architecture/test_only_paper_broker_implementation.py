"""Architecture test: `PaperBrokerAdapter` must be the ONLY `BrokerPort`
implementation living under `src/botafuturo`.

`BrokerPort` is a `Protocol`, not an ABC, so "implements the port" means
"structurally satisfies it" -- this imports every module under
`src/botafuturo`, inspects each class DEFINED there (not merely re-exported),
and checks it against `BrokerPort` via `isinstance()` on a bare instance
(constructed with `object.__new__`, bypassing `__init__`, since a
runtime-checkable `Protocol`'s `isinstance` check only inspects attribute
*presence* -- `MODE`/`balance`/`place`/`settle` -- never calls them).

`tests/fakes/broker.py::FakeBroker` is a deliberate TEST-ONLY exception: it
lives under `tests/`, not `src/`, so this scan never sees it.
"""
from __future__ import annotations

import importlib
import inspect
from pathlib import Path
from typing import List

from botafuturo.ports.broker import BrokerPort

SRC_DIR = Path(__file__).resolve().parents[2] / "src"
SRC_ROOT = SRC_DIR / "botafuturo"


def _module_name_for(path: Path) -> str:
    relative = path.relative_to(SRC_DIR)
    parts = relative.with_suffix("").parts
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _satisfies_broker_port(cls: type) -> bool:
    if cls is BrokerPort:
        return False
    try:
        instance = object.__new__(cls)
    except TypeError:
        return False
    try:
        return isinstance(instance, BrokerPort)
    except TypeError:
        return False


def _find_broker_port_implementations() -> List[str]:
    implementations: List[str] = []
    for path in sorted(SRC_ROOT.rglob("*.py")):
        module_name = _module_name_for(path)
        module = importlib.import_module(module_name)
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if obj.__module__ != module_name:
                continue  # only classes DEFINED here, not merely imported
            if _satisfies_broker_port(obj):
                implementations.append(f"{module_name}.{obj.__name__}")
    return implementations


def test_only_paper_broker_adapter_implements_broker_port() -> None:
    implementations = _find_broker_port_implementations()
    names = {entry.rsplit(".", 1)[-1] for entry in implementations}

    assert names == {"PaperBrokerAdapter"}, (
        "Expected exactly one BrokerPort implementation under src/botafuturo "
        f"(PaperBrokerAdapter), found: {sorted(implementations)}"
    )
