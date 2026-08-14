"""Regression tests for ``otaman_plugin.servers`` package shape.

Per ``ce-org-agent-bootstrap`` task 3.1, both MCP servers must be
importable as Python modules under ``otaman_plugin.servers`` so that the
per-org runner can invoke them with ``python -m otaman_plugin.servers.bus_server``
after a plain ``pip install otaman-plugin`` — no source vendoring.

These tests pin the import path so a future refactor that moves the
files back outside the package (or drops the ``__init__.py``) fails
loudly here instead of silently breaking the CE runtime.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    "module_path",
    [
        "otaman_plugin.servers",
        "otaman_plugin.servers.bus_server",
        "otaman_plugin.servers.estimation_server",
    ],
)
def test_module_is_importable(module_path: str):
    """The module loads cleanly under its packaged dotted name."""
    # Force a fresh import so caching from earlier test runs doesn't mask
    # a real import-time error.
    sys.modules.pop(module_path, None)
    mod = importlib.import_module(module_path)
    assert mod is not None
    assert hasattr(mod, "__file__")


def test_server_files_live_inside_package():
    """The servers/*.py files moved INTO the package, not next to it.

    Asserts the files exist at the post-restructure location AND are NOT
    at the legacy ``servers/<name>.py`` top-level location — a regression
    guard against accidentally re-introducing the dual-location shape.
    """
    repo = Path(__file__).resolve().parent.parent
    new_bus = repo / "src" / "otaman_plugin" / "servers" / "bus_server.py"
    new_est = repo / "src" / "otaman_plugin" / "servers" / "estimation_server.py"
    legacy_bus = repo / "servers" / "bus_server.py"
    legacy_est = repo / "servers" / "estimation_server.py"

    assert new_bus.is_file(), "bus_server.py missing under src/otaman_plugin/servers/"
    assert new_est.is_file(), "estimation_server.py missing under src/otaman_plugin/servers/"
    assert not legacy_bus.exists(), (
        "bus_server.py reintroduced at legacy servers/ location; the "
        "ce-org-agent-bootstrap restructure removed it intentionally"
    )
    assert not legacy_est.exists(), "estimation_server.py reintroduced at legacy servers/ location"


def test_servers_package_has_init():
    """``__init__.py`` is required for the dotted-module import to work."""
    repo = Path(__file__).resolve().parent.parent
    init_file = repo / "src" / "otaman_plugin" / "servers" / "__init__.py"
    assert init_file.is_file(), (
        "__init__.py missing from otaman_plugin/servers/; package import "
        "would silently fail on Python <3.3 and confuse static analysers"
    )


@pytest.mark.parametrize(
    "module_path",
    ["otaman_plugin.servers.bus_server", "otaman_plugin.servers.estimation_server"],
)
def test_module_has_main_entry_point(module_path: str):
    """Per task 3.1, both modules keep an ``if __name__ == "__main__"``
    block so direct script invocation works alongside ``python -m``."""
    mod = importlib.import_module(module_path)
    src = Path(mod.__file__).read_text(encoding="utf-8")
    assert 'if __name__ == "__main__":' in src, (
        f"{module_path} dropped its __main__ entry point; both `python -m "
        f"{module_path}` AND direct script invocation must work"
    )
