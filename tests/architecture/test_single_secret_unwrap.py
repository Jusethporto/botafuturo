"""Architecture test: credential reads must be confined to config/secrets.py.

`SecretProvider.get()` (in `config/secrets.py`) is the ONE chokepoint allowed
to unwrap a raw secret value from `os.environ`/`os.getenv` or from
`keyring.get_password`. Every other module must go through `SecretProvider`
instead of reading credentials directly, so this test AST-scans every source
file under `src/botafuturo` to enforce it.
"""
from __future__ import annotations

import ast
from pathlib import Path
from typing import List

SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "botafuturo"
ALLOWED_FILE = (SRC_ROOT / "config" / "secrets.py").resolve()


def _is_os_environ_get(func: ast.Attribute) -> bool:
    return (
        func.attr == "get"
        and isinstance(func.value, ast.Attribute)
        and func.value.attr == "environ"
        and isinstance(func.value.value, ast.Name)
        and func.value.value.id == "os"
    )


def _is_os_getenv(func: ast.Attribute) -> bool:
    return (
        func.attr == "getenv"
        and isinstance(func.value, ast.Name)
        and func.value.id == "os"
    )


def _is_keyring_get_password(func: ast.Attribute) -> bool:
    return (
        func.attr == "get_password"
        and isinstance(func.value, ast.Name)
        and func.value.id == "keyring"
    )


def _is_os_environ_subscript_target(value: ast.AST) -> bool:
    return (
        isinstance(value, ast.Attribute)
        and value.attr == "environ"
        and isinstance(value.value, ast.Name)
        and value.value.id == "os"
    )


class _CredentialAccessVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.violations: List[str] = []

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        if isinstance(func, ast.Attribute):
            if _is_os_environ_get(func):
                self.violations.append(f"line {node.lineno}: os.environ.get(...) call")
            elif _is_os_getenv(func):
                self.violations.append(f"line {node.lineno}: os.getenv(...) call")
            elif _is_keyring_get_password(func):
                self.violations.append(
                    f"line {node.lineno}: keyring.get_password(...) call"
                )
        self.generic_visit(node)

    def visit_Subscript(self, node: ast.Subscript) -> None:
        if _is_os_environ_subscript_target(node.value):
            self.violations.append(f"line {node.lineno}: os.environ[...] subscript")
        self.generic_visit(node)


def _scan(path: Path) -> List[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    visitor = _CredentialAccessVisitor()
    visitor.visit(tree)
    return visitor.violations


def test_credential_reads_confined_to_secrets_module() -> None:
    violations: List[str] = []
    for path in SRC_ROOT.rglob("*.py"):
        if path.resolve() == ALLOWED_FILE:
            continue
        for violation in _scan(path):
            violations.append(f"{path}: {violation}")

    assert not violations, (
        "Credential access found outside config/secrets.py (route it through "
        "SecretProvider.get() instead):\n" + "\n".join(violations)
    )


def test_secrets_module_is_the_expected_chokepoint() -> None:
    violations = _scan(ALLOWED_FILE)
    assert violations, (
        "config/secrets.py is expected to be the single credential-unwrap "
        "chokepoint (os.environ / keyring.get_password calls), but none "
        "were found -- did SecretProvider move?"
    )
