"""Security regression tests for F072 — runner attach_command executed via eval.

The launchers used to run the runner's network-supplied `attach_command`
string as a shell command (bash `eval "exec $_attach_first"`; PowerShell
interpolation into `ssh.exe`/`bash -ic`). A tampered/spoofed /spawn reply
could inject arbitrary commands on the developer's machine.

Fix: the launchers now take only the structured `attach.session_name` from
the reply, validate it against a strict charset, and reconstruct the attach
invocation locally (`tmux attach -t "=<session>"`) — never executing runner
text. These tests prove a malicious reply cannot execute code and that the
`eval` sink is gone.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

REPO = Path(__file__).parent.parent
BASH_LAUNCHER = REPO / "scripts" / "launch-agents.sh"
PS1_LAUNCHER = REPO / "scripts" / "launch-agents.ps1"
PWSH = shutil.which("pwsh")


# ---------------------------------------------------------------------------
# Mock runner that returns an attacker-controlled /spawn reply
# ---------------------------------------------------------------------------

def _make_server(response_obj: dict) -> HTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            length = int(self.headers.get("Content-Length", "0"))
            self.rfile.read(length)
            body = json.dumps(response_obj).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_a, **_k):
            pass

    return HTTPServer(("127.0.0.1", 0), Handler)


def _run_spawn_one(port: int) -> subprocess.CompletedProcess:
    # Source just runner_spawn_one out of the launcher and call it.
    script = f"""
set -eu
export PYTHON=python3
PATH="/usr/bin:/bin:$PATH"
eval "$(awk '/^runner_spawn_one\\(\\)/,/^}}$/' {BASH_LAUNCHER})"
runner_spawn_one 127.0.0.1 {port} test-token plugin-agent otaman-plugin /tmp/project '' bob
"""
    return subprocess.run(["bash", "-c", script], capture_output=True, text=True, timeout=15)


# ---------------------------------------------------------------------------
# Bash: runner_spawn_one only returns a validated session_name
# ---------------------------------------------------------------------------

class TestBashRunnerSpawnOne:
    def test_rejects_malicious_session_name_no_code_execution(self, tmp_path):
        # The classic injection: a tampered reply whose session_name embeds a
        # shell payload. If any layer eval'd it, the marker file would appear.
        marker = tmp_path / "PWNED"
        payload = f"x; touch {marker}"
        server = _make_server(
            {"attach": {"session_name": payload, "attach_command": f"tmux attach -t {payload}"}}
        )
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            result = _run_spawn_one(server.server_port)
        finally:
            server.shutdown()
            server.server_close()
        # Must fail closed (non-zero) and must NOT echo the poisoned value.
        assert result.returncode != 0, (
            f"malicious session_name must be rejected; got rc=0 stdout={result.stdout!r}"
        )
        assert not marker.exists(), "injection executed — a shell ran the payload"
        assert "invalid session_name" in result.stderr

    def test_accepts_valid_session_name(self, tmp_path):
        server = _make_server(
            {"attach": {"session_name": "myproj:plugin-agent", "attach_command": "tmux attach -t x"}}
        )
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            result = _run_spawn_one(server.server_port)
        finally:
            server.shutdown()
            server.server_close()
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "myproj:plugin-agent"

    def test_missing_session_name_rejected(self):
        # Reply with only attach_command (no session_name) must fail closed.
        server = _make_server({"attach": {"attach_command": "tmux attach -t x"}})
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            result = _run_spawn_one(server.server_port)
        finally:
            server.shutdown()
            server.server_close()
        assert result.returncode != 0
        assert "session_name" in result.stderr


class TestBashSink:
    def test_no_eval_exec_of_runner_value(self):
        text = BASH_LAUNCHER.read_text(encoding="utf-8")
        assert 'eval "exec $_attach' not in text, "the eval-exec injection sink must be gone"
        assert 'eval "exec $_session' not in text, "must not eval the session value either"

    def test_attaches_via_argv_literal_target(self):
        text = BASH_LAUNCHER.read_text(encoding="utf-8")
        assert 'exec tmux attach -t "=$_session_first"' in text, (
            "attach must go through argv with a literal '=<session>' target"
        )


# ---------------------------------------------------------------------------
# PS1: Invoke-RunnerSpawn validates + returns session_name (pwsh execution)
# ---------------------------------------------------------------------------

pwsh_only = pytest.mark.skipif(PWSH is None, reason="pwsh not available")


def _ps1_defs_prefix() -> str:
    text = PS1_LAUNCHER.read_text(encoding="utf-8")
    return text[: text.index("# Load settings, pick active connection")]


@pytest.fixture(scope="module")
def ps1_harness(tmp_path_factory) -> Path:
    p = tmp_path_factory.mktemp("f072-ps1") / "harness.ps1"
    p.write_text(_ps1_defs_prefix(), encoding="utf-8")
    return p


def _invoke_runner_spawn(harness: Path, session_name_literal: str | None) -> dict:
    """Dot-source the launcher defs, stub Invoke-RestMethod to return a reply
    whose attach.session_name is `session_name_literal` (or absent if None),
    then call Invoke-RunnerSpawn and report ok/err + returned value."""
    if session_name_literal is None:
        attach = "@{ attach_command = 'x' }"
    else:
        esc = session_name_literal.replace("'", "''")
        attach = f"@{{ session_name = '{esc}'; attach_command = 'tmux attach -t whatever' }}"
    body = f"""
. "{harness}"
function Invoke-RestMethod {{ param([Parameter(ValueFromRemainingArguments=$true)]$rest) return [pscustomobject]@{{ attach = [pscustomobject]{attach} }} }}
$ep = @{{ Host = '127.0.0.1'; Port = 8200; Token = 't' }}
try {{
    $v = Invoke-RunnerSpawn -Endpoint $ep -Agent a -Repo r -ProjectRoot /tmp
    $result = @{{ ok = $true; val = $v }}
}} catch {{
    $result = @{{ ok = $false; err = "$_" }}
}}
$result | ConvertTo-Json -Compress
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
    return json.loads(proc.stdout.strip().splitlines()[-1])


@pwsh_only
class TestPs1InvokeRunnerSpawn:
    def test_returns_valid_session_name(self, ps1_harness):
        r = _invoke_runner_spawn(ps1_harness, "myproj:plugin-agent")
        assert r["ok"] is True
        assert r["val"] == "myproj:plugin-agent"

    def test_rejects_session_name_with_shell_metachars(self, ps1_harness):
        r = _invoke_runner_spawn(ps1_harness, "x; rm -rf ~")
        assert r["ok"] is False
        assert "F072" in r["err"] or "unexpected characters" in r["err"]

    def test_rejects_session_name_with_quote(self, ps1_harness):
        r = _invoke_runner_spawn(ps1_harness, "x'; calc; '")
        assert r["ok"] is False

    def test_rejects_missing_session_name(self, ps1_harness):
        r = _invoke_runner_spawn(ps1_harness, None)
        assert r["ok"] is False
        assert "session_name" in r["err"]


class TestPs1Sink:
    def test_builds_attach_locally_from_session(self):
        text = PS1_LAUNCHER.read_text(encoding="utf-8")
        assert "tmux attach -t '=$sessionName'" in text, (
            "PS1 must build the attach command locally from the validated session name"
        )

    def test_invoke_runner_spawn_returns_session_not_command(self):
        text = PS1_LAUNCHER.read_text(encoding="utf-8")
        assert "return [string]$resp.attach.attach_command" not in text, (
            "must not return the runner's attach_command string"
        )
        assert "$resp.attach.session_name" in text
