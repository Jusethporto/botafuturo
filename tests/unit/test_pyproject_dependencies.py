"""Tests that pyproject.toml declares the dependencies the design requires.

The config file itself is scaffolding (no unit-testable logic), but the
*set of declared dependencies* is a real contract this project relies on
(pydantic-settings as a runtime dependency, keyring as optional, pytest /
pytest-asyncio as dev/test dependencies), so it is worth pinning down with
a test rather than trusting it stays correct by hand.
"""
from __future__ import annotations

import sys
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - project targets 3.11+
    import tomli as tomllib  # type: ignore[no-redef]

PYPROJECT_PATH = Path(__file__).resolve().parents[2] / "pyproject.toml"


def _load_pyproject() -> dict:
    with PYPROJECT_PATH.open("rb") as fh:
        return tomllib.load(fh)


def test_requires_python_311_or_newer() -> None:
    data = _load_pyproject()
    requires_python = data["project"]["requires-python"]
    assert ">=3.11" in requires_python


def test_declares_pydantic_settings_as_dependency() -> None:
    data = _load_pyproject()
    dependencies = data["project"]["dependencies"]
    assert any(dep.lower().startswith("pydantic-settings") for dep in dependencies)


def test_declares_keyring_as_optional_dependency() -> None:
    data = _load_pyproject()
    optional = data["project"]["optional-dependencies"]
    all_optional_deps = [dep.lower() for group in optional.values() for dep in group]
    assert any(dep.startswith("keyring") for dep in all_optional_deps)


def test_declares_pytest_and_pytest_asyncio_dev_dependencies() -> None:
    data = _load_pyproject()
    optional = data["project"]["optional-dependencies"]
    dev_deps = [dep.lower() for dep in optional.get("dev", [])]
    assert any(dep.startswith("pytest-asyncio") for dep in dev_deps)
    assert any(
        dep.startswith("pytest") and not dep.startswith("pytest-asyncio")
        for dep in dev_deps
    )
