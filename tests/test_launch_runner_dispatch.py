"""Tests for auto-session-spawn-implementation tasks 4.2 + 4.3 + 4.4.

Both launchers (``launch-agents.sh`` and ``launch-agents.ps1``) now dispatch
through ``otaman-runner`` by default in tmux mode. ``--no-runner`` /
``-NoRunner`` is the opt-out. POST body includes the new ``human`` field
(default ``$USER`` / ``$env:USERNAME``).

These tests verify:
- The bash launcher's CLI parsing accepts ``--no-runner`` and defaults
  ``VIA_RUNNER=1``.
- The bash ``runner_spawn_one`` function body has the ``human`` field and the
  dispatch site forwards a ``$_human`` value.
- The PS1 launcher's param block declares both ``-ViaRunner`` (deprecated
  no-op) and ``-NoRunner`` (opt-out); ``Invoke-RunnerSpawn`` accepts ``$Human``
  and emits it in the body.
- A runtime mock-server test for the bash side: spin up a real localhost
  HTTP server, invoke ``runner_spawn_one`` via ``bash -c``, capture the POST
  body, and assert the field shape — including ``agent`` = owner (so the
  runner derives the canonical ``<program>:<owner>`` session name) and the
  ``human`` field.
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest


REPO = Path(__file__).parent.parent
BASH_LAUNCHER = REPO / "scripts" / "launch-agents.sh"
PS1_LAUNCHER = REPO / "scripts" / "launch-agents.ps1"


# ---------------------------------------------------------------------------
# Bash text-based contract tests
# ---------------------------------------------------------------------------

class TestBashLauncherContract:
    @pytest.fixture(scope="class")
    def text(self) -> str:
        return BASH_LAUNCHER.read_text(encoding="utf-8")

    def test_default_via_runner_is_on(self, text: str):
        assert "\nVIA_RUNNER=1\n" in text, (
            "VIA_RUNNER must default to 1 (runner-first per task 4.2)"
        )

    def test_no_runner_flag_accepted(self, text: str):
        assert "--no-runner)" in text, (
            "--no-runner opt-out case missing from arg parser"
        )

    def test_via_runner_is_deprecated_noop(self, text: str):
        # --via-runner case still exists but no longer sets VIA_RUNNER=1
        # (it's a no-op now since runner-first is the default).
        idx = text.index("--via-runner)")
        # Slice the next 6 lines after the case label
        snippet = text[idx : idx + 200]
        assert "VIA_RUNNER=1" not in snippet, (
            "--via-runner case must not set VIA_RUNNER (it's the default now)"
        )

    def test_runner_spawn_one_body_has_human(self, text: str):
        # Quick structural check — the JSON body emitted by runner_spawn_one
        # must include the human field.
        idx = text.index("runner_spawn_one()")
        end = text.index("\n}\n", idx)
        snippet = text[idx:end]
        assert '"human": human' in snippet, (
            "runner_spawn_one body must emit human field"
        )

    def test_dispatch_passes_human(self, text: str):
        # Sanity: the tmux branch passes _human as the trailing argument.
        # Quoting and whitespace can vary; just require both the variable
        # initialisation and the call-site reference.
        assert '_human="${USER:-${LOGNAME:-}}"' in text
        assert '"$_human"' in text

    def test_tmux_new_session_sets_window_name(self, text: str):
        # Per fix-launcher-tmux-session-naming task 1.5: tmux new-session
        # must include `-n "$name"` so the status bar reads
        # "<project>:<owner>:<repo>". The fallback (direct-tmux) path
        # creates the session; runner-path callers leave window naming
        # to the runner.
        assert 'tmux new-session -d -s "$session" -n "$name" -c "$path"' in text


# ---------------------------------------------------------------------------
# PS1 text-based contract tests
# ---------------------------------------------------------------------------

class TestPs1LauncherContract:
    @pytest.fixture(scope="class")
    def text(self) -> str:
        return PS1_LAUNCHER.read_text(encoding="utf-8")

    def test_no_runner_switch_declared(self, text: str):
        assert "[switch]$NoRunner" in text, (
            "$NoRunner param missing from launch-agents.ps1 param block"
        )

    def test_via_runner_still_declared_as_deprecated(self, text: str):
        # Back-compat: -ViaRunner stays in the param block but is a no-op.
        assert "[switch]$ViaRunner" in text, (
            "$ViaRunner must remain declared as deprecated no-op for back-compat"
        )

    def test_invoke_runner_spawn_accepts_human(self, text: str):
        # Find Invoke-RunnerSpawn signature and verify $Human param.
        idx = text.index("function Invoke-RunnerSpawn")
        snippet = text[idx : idx + 1500]
        assert "[string] $Human" in snippet, (
            "Invoke-RunnerSpawn must accept a $Human parameter"
        )
        assert "human" in snippet and "if ($Human)" in snippet, (
            "Invoke-RunnerSpawn body must include the human field"
        )

    def test_dispatch_gate_inverted(self, text: str):
        # The runner dispatch block now triggers unless -NoRunner is set.
        assert "if (-not $NoRunner)" in text, (
            "Dispatch site must gate on -not $NoRunner (runner is default)"
        )

    def test_dispatch_passes_username(self, text: str):
        assert "$human = $env:USERNAME" in text
        assert "-Human $human" in text

    def test_wrap_with_tmux_accepts_window_name(self, text: str):
        # Per fix-launcher-tmux-session-naming task 2.5: Wrap-WithTmux now
        # accepts a $WindowName parameter and emits `-n '<repo>'` when set.
        # Slice from function header to the first `^}` that closes it.
        idx = text.index("function Wrap-WithTmux")
        end = text.index("\n}\n", idx)
        snippet = text[idx:end]
        assert "[string]$WindowName" in snippet, (
            "Wrap-WithTmux must accept a $WindowName parameter"
        )
        assert "-n '$WindowName'" in snippet, (
            "Wrap-WithTmux must emit `-n '<repo>'` in tmux new-session args"
        )

    def test_build_ssh_command_passes_repo_as_window_name(self, text: str):
        # The Wrap-WithTmux call in Build-SshCommand must forward $RepoName
        # as the WindowName so the remote tmux window picks it up.
        assert "-WindowName $RepoName" in text


# ---------------------------------------------------------------------------
# Runtime test — mock HTTP server captures the bash runner_spawn_one body
# ---------------------------------------------------------------------------

class _BodyCapture:
    """Shared state for the mock-server handler — captures POST bodies."""

    def __init__(self):
        self.bodies: list[dict] = []
        self.lock = threading.Lock()


def _make_handler(capture: _BodyCapture, response_body: dict):
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length).decode("utf-8")
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                payload = {"_raw": raw}
            with capture.lock:
                capture.bodies.append(payload)
            body = json.dumps(response_body).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args, **_kwargs):  # silence stderr noise
            pass

    return Handler


@pytest.fixture
def mock_runner():
    """Start a localhost HTTP mock server that records POST bodies."""
    capture = _BodyCapture()
    response = {
        "session_id": "test-session",
        "attach": {
            "attach_command": "true",  # exec true is a noop that exits 0
            "session_name": "test:test-agent",
        },
    }
    handler_cls = _make_handler(capture, response)
    server = HTTPServer(("127.0.0.1", 0), handler_cls)
    port = server.server_port
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield {"port": port, "capture": capture}
    finally:
        server.shutdown()
        server.server_close()


def test_runner_spawn_one_posts_expected_body(mock_runner, tmp_path):
    """Invoke the bash ``runner_spawn_one`` function directly against a real
    mock server and assert the POSTed body shape matches what the runner
    expects per the auto-session-spawn-implementation contract.
    """
    port = mock_runner["port"]
    # Source the launcher then call the function. ``return 0`` at the end
    # keeps the subprocess clean.
    script = f"""
set -eu
export PYTHON=python3
PATH="/usr/bin:/bin:$PATH"
# Inline minimal stubs for the resolver source — runner_spawn_one needs none
# of the resolved state, just $PYTHON.
eval "$(awk '/^runner_spawn_one\\(\\)/,/^}}$/' {BASH_LAUNCHER})"
runner_spawn_one 127.0.0.1 {port} test-token \
    plugin-agent otaman-plugin /tmp/project myaccount alice
"""
    result = subprocess.run(
        ["bash", "-c", script],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, (
        f"runner_spawn_one failed:\nstdout={result.stdout}\nstderr={result.stderr}"
    )
    # Server must have received exactly one POST
    bodies = mock_runner["capture"].bodies
    assert len(bodies) == 1, f"expected 1 POST, got {len(bodies)}: {bodies}"
    body = bodies[0]
    # Required fields per the runner daemon's _request_from_dict
    assert body["agent"] == "plugin-agent"
    assert body["repo"] == "otaman-plugin"
    assert body["project_root"] == "/tmp/project"
    assert body["mode"] == "interactive"
    # New fields per auto-session-spawn-implementation §4
    assert body["account"] == "myaccount"
    assert body["human"] == "alice"


def test_runner_spawn_one_returns_attach_command(mock_runner):
    """The function must echo the attach_command on success."""
    port = mock_runner["port"]
    script = f"""
set -eu
export PYTHON=python3
PATH="/usr/bin:/bin:$PATH"
eval "$(awk '/^runner_spawn_one\\(\\)/,/^}}$/' {BASH_LAUNCHER})"
runner_spawn_one 127.0.0.1 {port} test-token \
    plugin-agent otaman-plugin /tmp/project '' bob
"""
    result = subprocess.run(
        ["bash", "-c", script],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "true", (
        f"expected attach_command 'true' on stdout, got: {result.stdout!r}"
    )


def test_runner_spawn_one_handles_unreachable():
    """When the runner is unreachable, runner_spawn_one must return non-zero
    so the launcher's outer caller can trigger the local-fallback branch."""
    # Port 1 is reserved + unbindable for a server, so connect refused fast.
    script = f"""
set -eu
export PYTHON=python3
PATH="/usr/bin:/bin:$PATH"
eval "$(awk '/^runner_spawn_one\\(\\)/,/^}}$/' {BASH_LAUNCHER})"
runner_spawn_one 127.0.0.1 1 test-token \
    plugin-agent otaman-plugin /tmp/project '' alice
"""
    result = subprocess.run(
        ["bash", "-c", script],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode != 0, (
        f"expected non-zero exit on unreachable runner; got 0 with stdout={result.stdout!r}"
    )
    # stderr should mention HTTP error (curl's connect-refused goes there)
    assert "HTTP error" in result.stderr or "Connection refused" in result.stderr
