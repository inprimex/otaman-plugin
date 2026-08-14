"""Regression test for launch-agents.ps1's runner-mediated project_root bug.

Reported by deploy-agent (2026-07-08) while re-verifying R2/R3 on the
greenbin fleet: the runner-first dispatch loop passed `$cfgParent` (the
launcher's own LOCAL config folder, e.g. a Windows path) as the /spawn
request's `project_root` field. otaman-runner's spawner.py takes that value
at face value and sets it directly as `OTAMAN_ROOT` in the spawned tmux
session's env — so every remote-runner session ended up with a stale local
Windows path as its OTAMAN_ROOT, confirmed via `ps` on the actual spawned
command.

Fix: `Resolve-RunnerProjectRoot` prefers the active connection's
`ssh_remote_root` (the same field the direct-SSH path already uses for
remote paths) and only falls back to the local config folder when the
connection has no remote root configured — e.g. a runner co-located with
the launcher itself.

Runs the real PS1 function via a real pwsh interpreter (dot-sourcing the
launcher's function-definitions prefix), same harness pattern as
test_f072_attach_no_eval.py.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).parent.parent
PS1_LAUNCHER = REPO / "scripts" / "launch-agents.ps1"
PWSH = shutil.which("pwsh")

pwsh_only = pytest.mark.skipif(PWSH is None, reason="pwsh not available")


def _ps1_defs_prefix() -> str:
    text = PS1_LAUNCHER.read_text(encoding="utf-8")
    return text[: text.index("# Load settings, pick active connection")]


@pytest.fixture(scope="module")
def ps1_harness(tmp_path_factory) -> Path:
    p = tmp_path_factory.mktemp("runner-root-ps1") / "harness.ps1"
    p.write_text(_ps1_defs_prefix(), encoding="utf-8")
    return p


def _resolve(harness: Path, active_conn: dict | None, local_config_parent: str) -> str:
    if active_conn is None:
        conn_literal = "$null"
    else:
        pairs = "; ".join(f"'{k}' = '{v}'" for k, v in active_conn.items())
        conn_literal = f"@{{ {pairs} }}"
    body = f"""
. "{harness}"
$conn = {conn_literal}
Resolve-RunnerProjectRoot -ActiveConn $conn -LocalConfigParent '{local_config_parent}'
"""
    f = harness.parent / "run.ps1"
    f.write_text(body, encoding="utf-8")
    proc = subprocess.run(
        [PWSH, "-NoProfile", "-NonInteractive", "-File", str(f)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 0, f"pwsh failed: {proc.stderr}"
    return proc.stdout.strip().splitlines()[-1]


@pwsh_only
class TestResolveRunnerProjectRoot:
    def test_prefers_remote_root_when_configured(self, ps1_harness):
        result = _resolve(
            ps1_harness,
            {"ssh_remote_root": "/home/greenbin/orgs/greenbin"},
            r"C:\work\launchers\greenbin-runner",
        )
        assert result == "/home/greenbin/orgs/greenbin"

    def test_falls_back_to_local_config_parent_when_no_remote_root(self, ps1_harness):
        result = _resolve(ps1_harness, {}, r"C:\work\launchers\greenbin-runner")
        assert result == r"C:\work\launchers\greenbin-runner"

    def test_falls_back_when_active_conn_is_null(self, ps1_harness):
        result = _resolve(ps1_harness, None, "/local/config")
        assert result == "/local/config"


class TestDispatchSiteUsesResolver:
    def test_call_site_no_longer_passes_cfgparent_directly(self):
        text = PS1_LAUNCHER.read_text(encoding="utf-8")
        assert "-ProjectRoot $cfgParent" not in text, (
            "runner-mediated spawn must not hand the runner a local launcher path"
        )
        assert "-ProjectRoot $runnerProjectRoot" in text
        assert (
            "Resolve-RunnerProjectRoot -ActiveConn $activeConn -LocalConfigParent $cfgParent"
            in text
        )
