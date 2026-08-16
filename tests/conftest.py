"""Shared pytest fixtures for hook subprocess tests."""

from __future__ import annotations

import stat
from pathlib import Path

import pytest

_CORE_SRC = str(Path(__file__).resolve().parent.parent.parent / "otaman-core" / "src")


@pytest.fixture(autouse=True)
def _strip_bus_resolution_env(monkeypatch):
    """Interim bus-test-isolation hardening (deploy-agent broadcast
    20260816T193911; structural fix tracked as bus-test-isolation 4.2 —
    converge onto ``otaman_core.testing`` once core 1.1 lands).

    Live sessions can carry a stale ``OTAMAN_ROOT`` pointing at the org
    level. Root resolution is marker → env → walk-up, so any test that
    exercises real bus-write code with an unresolvable cwd would silently
    recreate and write into a rogue org-level bus (the 2026-08-16
    incident). Strip the resolution env vars for every test; tests that
    exercise the env-var path set their own values on top of this.
    """
    for var in ("OTAMAN_ROOT", "MAESTRO_ROOT", "OTAMAN_AGENT"):
        monkeypatch.delenv(var, raising=False)


@pytest.fixture
def otaman_stub_bin(tmp_path):
    """A fake `otaman` executable, on its own PATH-prependable directory,
    implementing only `whoami --resolve-only` (F013).

    Delegates to the real `otaman_core.identity.resolve_enforcement_identity()`
    — the same function the real CLI wraps (see
    otaman-cli/src/otaman_cli/commands/status_cluster.py
    `_cmd_whoami_resolve_only`) — rather than reimplementing the resolution
    logic in the test. This exercises the hooks' actual shell-out contract
    without depending on whatever otaman-cli release happens to be
    pipx-installed on the machine running the tests (which may predate the
    --resolve-only flag entirely and would otherwise silently print its full
    human-readable `whoami` banner instead of erroring).
    """
    bin_dir = tmp_path / "_stub_bin"
    bin_dir.mkdir()
    stub = bin_dir / "otaman"
    stub.write_text(
        f"""#!/usr/bin/env python3
import sys
sys.path.insert(0, {_CORE_SRC!r})
if sys.argv[1:] == ["whoami", "--resolve-only"]:
    from otaman_core.identity import resolve_enforcement_identity
    result = resolve_enforcement_identity()
    if result.agent:
        print(result.agent)
        sys.exit(0)
    sys.exit(1)
sys.exit(2)
""",
        encoding="utf-8",
    )
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return bin_dir


@pytest.fixture
def otaman_stale_stub_bin(tmp_path):
    """A fake `otaman` simulating a pre-F013 CLI build: it doesn't recognize
    `--resolve-only` and falls through to printing a multi-line human-
    readable banner instead of erroring (the real failure mode observed
    from a stale pipx-installed otaman-cli during development of this fix).

    Used to prove resolve_enforcement_identity() in _resolve.sh fails
    closed (treats this as unresolved) rather than misparsing the banner as
    a garbage agent identity.
    """
    bin_dir = tmp_path / "_stale_stub_bin"
    bin_dir.mkdir()
    stub = bin_dir / "otaman"
    stub.write_text(
        """#!/usr/bin/env python3
print("  ──────────────────────────────────────")
print("    Otaman: plugin-agent")
print("  ──────────────────────────────────────")
""",
        encoding="utf-8",
    )
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return bin_dir
