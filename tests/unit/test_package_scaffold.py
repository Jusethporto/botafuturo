"""Smoke tests for the top-level `botafuturo` package scaffold.

These tests exercise the only testable behavior introduced by the
project-scaffolding phase: that the package is installed/importable and
exposes a well-formed version string. Directory-only `__init__.py` files
with no logic are intentionally left untested (they carry no behavior).
"""
from __future__ import annotations

import re


def test_botafuturo_package_is_importable() -> None:
    import botafuturo

    assert botafuturo is not None


def test_botafuturo_exposes_semver_version() -> None:
    import botafuturo

    assert hasattr(botafuturo, "__version__")
    assert re.match(r"^\d+\.\d+\.\d+", botafuturo.__version__)


def test_layer_packages_are_importable() -> None:
    import importlib

    for module_name in (
        "botafuturo.domain",
        "botafuturo.ports",
        "botafuturo.adapters",
        "botafuturo.adapters.exnova",
        "botafuturo.adapters.paper",
        "botafuturo.adapters.logging",
        "botafuturo.config",
        "botafuturo.cli",
    ):
        assert importlib.import_module(module_name) is not None
