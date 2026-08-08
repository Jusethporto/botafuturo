"""Architecture test: the paper broker adapter must have ZERO network
capability -- it is a pure in-memory simulation (see
`adapters/paper/broker.py`'s module docstring: "no real money, no external
broker call").

AST-walks every module under `src/botafuturo/adapters/paper` and fails if any
of them import the (deferred) real Exnova adapter or any networking library.
"""
from __future__ import annotations

import ast
from pathlib import Path
from typing import List, Set

PAPER_ROOT = (
    Path(__file__).resolve().parents[2] / "src" / "botafuturo" / "adapters" / "paper"
)

_FORBIDDEN_MODULES = frozenset(
    {
        "botafuturo.adapters.exnova",
        "websockets",
        "aiohttp",
        "httpx",
        "requests",
        "socket",
    }
)


def _imported_module_names(path: Path) -> Set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: Set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def _is_forbidden(module_name: str) -> bool:
    return any(
        module_name == forbidden or module_name.startswith(f"{forbidden}.")
        for forbidden in _FORBIDDEN_MODULES
    )


def test_paper_adapter_has_no_forbidden_network_imports() -> None:
    violations: List[str] = []
    for path in sorted(PAPER_ROOT.rglob("*.py")):
        for module_name in sorted(_imported_module_names(path)):
            if _is_forbidden(module_name):
                violations.append(f"{path.name}: imports {module_name!r}")

    assert not violations, (
        "Paper broker adapter must have zero network capability, found "
        "forbidden imports:\n" + "\n".join(violations)
    )
