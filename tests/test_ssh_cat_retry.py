"""Execution-based tests for Invoke-SshCatRemoteFile's retry-with-backoff
(launch-agents.ps1) — deploy-agent's live diagnosis (20260903T210006,
20260903T210830): a transient P2P/NAT-traversal reset mid-handshake on a
mesh (Netbird-relayed) SSH link kills a single-shot invocation even though
the server side is completely healthy — observed ~33% single-call failure
rate against a real mesh peer, zero actual auth rejections. A client-side
"Permission denied (publickey)" in that same investigation turned out to be
ssh's generic fallback message for a reset preauth, not a real credential
problem — confirming retrying blind (not pattern-matching stderr text) is
the right shape of fix.

Same execution harness as test_runner_endpoint_discovery.py: dot-source the
function-definitions prefix of the real script, then call the real
Invoke-SshCatRemoteFile — but with Get-NativeSshInvocation shadowed to
point at a flaky stub script instead of a real ssh.exe, so the retry LOOP
itself is exercised against real process exit codes without a network call.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

REPO = Path(__file__).parent.parent
PS1_LAUNCHER = REPO / "scripts" / "launch-agents.ps1"
PWSH = shutil.which("pwsh")

pytestmark = pytest.mark.skipif(PWSH is None, reason="pwsh not available in this environment")


def _function_defs_prefix() -> str:
    text = PS1_LAUNCHER.read_text(encoding="utf-8")
    marker = "# Load settings, pick active connection"
    idx = text.index(marker)
    return text[:idx]


@pytest.fixture(scope="module")
def harness_path(tmp_path_factory) -> Path:
    d = tmp_path_factory.mktemp("ps1-ssh-cat-harness")
    p = d / "harness.ps1"
    p.write_text(_function_defs_prefix(), encoding="utf-8")
    return p


@pytest.fixture
def flaky_ssh_stub(tmp_path) -> Path:
    """A fake `ssh.exe`, implemented as a .ps1 script invoked via
    `pwsh -File` (cross-platform — a bash-shebang .sh stub can't execute
    natively on Windows without WSL, which is exactly the gap this test
    would otherwise hit on CI's Windows leg). Reads FLAKY_FAIL_COUNT (env)
    and a state file (FLAKY_STATE_FILE) to fail the first N invocations,
    then succeed — simulating N transient resets followed by a working
    connection."""
    stub = tmp_path / "flaky-ssh.ps1"
    stub.write_text(
        textwrap.dedent(
            """\
            $state = $env:FLAKY_STATE_FILE
            if (-not $state) { throw "FLAKY_STATE_FILE not set" }
            $failCount = if ($env:FLAKY_FAIL_COUNT) { [int]$env:FLAKY_FAIL_COUNT } else { 0 }
            $count = 0
            if (Test-Path $state) { $count = [int](Get-Content $state) }
            $count++
            Set-Content -Path $state -Value $count
            if ($count -le $failCount) {
                Write-Error "simulated transient reset"
                exit 255
            }
            Write-Output "stub-output-line"
            exit 0
            """
        ),
        encoding="utf-8",
    )
    return stub


def run_ps(harness_path: Path, body: str, env: dict | None = None) -> dict:
    script = f'. "{harness_path}"\n{body}\n$result | ConvertTo-Json -Depth 8 -Compress\n'
    script_file = harness_path.parent / "run.ps1"
    script_file.write_text(script, encoding="utf-8")
    full_env = dict(os.environ)
    if env:
        full_env.update(env)
    proc = subprocess.run(
        [PWSH, "-NoProfile", "-NonInteractive", "-File", str(script_file)],
        capture_output=True,
        text=True,
        timeout=30,
        env=full_env,
    )
    assert proc.returncode == 0, f"pwsh failed:\nSTDOUT={proc.stdout}\nSTDERR={proc.stderr}"
    out = proc.stdout.strip().splitlines()
    assert out, f"no output from pwsh; stderr={proc.stderr}"
    return json.loads(out[-1])


def _shadow_invocation_body(stub_path: Path) -> str:
    """PS body prefix: shadow Get-NativeSshInvocation to route through the
    flaky stub (via `pwsh -File`, cross-platform) instead of a real
    ssh.exe, matching Invoke-SshCatRemoteFile's exact consumption shape
    (Exe/KeyArgs/Target) — KeyArgs carries the pwsh invocation flags, so
    the real function's own Target/remoteCmd tail becomes harmless extra
    script arguments the stub never reads (it uses env vars only)."""
    return f"""
    function Get-NativeSshInvocation {{
        param([hashtable]$Settings)
        return @{{
            Exe = "{PWSH}"
            KeyArgs = @('-NoProfile', '-NonInteractive', '-File', "{stub_path}")
            Target = 'test@mesh-peer'
        }}
    }}
    """


class TestRetrySucceedsAfterTransientFailures:
    def test_succeeds_on_first_attempt_when_healthy(self, harness_path, tmp_path, flaky_ssh_stub):
        state_file = tmp_path / "state"
        body = (
            _shadow_invocation_body(flaky_ssh_stub)
            + """
        $output = Invoke-SshCatRemoteFile -Settings @{} `
            -RemotePath '~/.otaman/runner.endpoint' -RetryDelaySeconds 0
        $result = @{ output = $output }
        """
        )
        r = run_ps(harness_path, body, env={"FLAKY_STATE_FILE": str(state_file)})
        assert r["output"] == "stub-output-line"
        assert state_file.read_text().strip() == "1"  # no retry needed

    def test_recovers_from_two_transient_failures_within_default_attempts(
        self, harness_path, tmp_path, flaky_ssh_stub
    ):
        state_file = tmp_path / "state"
        body = (
            _shadow_invocation_body(flaky_ssh_stub)
            + """
        $output = Invoke-SshCatRemoteFile -Settings @{} `
            -RemotePath '~/.otaman/runner.endpoint' -RetryDelaySeconds 0
        $result = @{ output = $output }
        """
        )
        r = run_ps(
            harness_path,
            body,
            env={"FLAKY_STATE_FILE": str(state_file), "FLAKY_FAIL_COUNT": "2"},
        )
        assert r["output"] == "stub-output-line"
        assert state_file.read_text().strip() == "3"  # failed twice, succeeded on 3rd

    def test_throws_after_exhausting_max_attempts(self, harness_path, tmp_path, flaky_ssh_stub):
        state_file = tmp_path / "state"
        body = (
            _shadow_invocation_body(flaky_ssh_stub)
            + """
        try {
            Invoke-SshCatRemoteFile -Settings @{} -RemotePath '~/.otaman/runner.endpoint' `
                -MaxAttempts 3 -RetryDelaySeconds 0
            $result = @{ threw = $false }
        } catch {
            $result = @{ threw = $true; message = $_.Exception.Message }
        }
        """
        )
        r = run_ps(
            harness_path,
            body,
            env={"FLAKY_STATE_FILE": str(state_file), "FLAKY_FAIL_COUNT": "99"},
        )
        assert r["threw"] is True
        assert "after 3 attempts" in r["message"]
        assert state_file.read_text().strip() == "3"  # exactly MaxAttempts tries, no more

    def test_max_attempts_is_configurable(self, harness_path, tmp_path, flaky_ssh_stub):
        state_file = tmp_path / "state"
        body = (
            _shadow_invocation_body(flaky_ssh_stub)
            + """
        $output = Invoke-SshCatRemoteFile -Settings @{} -RemotePath '~/.otaman/runner.endpoint' `
            -MaxAttempts 5 -RetryDelaySeconds 0
        $result = @{ output = $output }
        """
        )
        r = run_ps(
            harness_path,
            body,
            env={"FLAKY_STATE_FILE": str(state_file), "FLAKY_FAIL_COUNT": "4"},
        )
        assert r["output"] == "stub-output-line"
        assert state_file.read_text().strip() == "5"


def test_default_max_attempts_is_at_least_two():
    """Structural guard: a single-shot (MaxAttempts=1 default) would be no
    fix at all for the reported ~33% single-call failure rate."""
    text = PS1_LAUNCHER.read_text(encoding="utf-8")
    idx = text.index("function Invoke-SshCatRemoteFile")
    snippet = text[idx : idx + 400]
    assert "[int]$MaxAttempts = 3" in snippet or "[int]$MaxAttempts = 2" in snippet
