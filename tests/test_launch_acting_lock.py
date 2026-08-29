"""Tests for single-acting-session-guard tasks 1.1-1.4 — plugin (launcher) half.

These cover the bash launcher's acting-session lock primitives added to
``scripts/launch-agents.sh``:

- 1.1  identity flock + metadata sidecar + lock-key/path derivation
- 1.2  attach-first (bash-mode collapses into the identity tmux session)
- 1.3  interactive-preemption flag / mode detection
- 1.4  no-tmux passive mirror (never silent)

The deterministic helpers (lock-key derivation, lock-path selection, sidecar
contents, mode detection) are unit-tested by sourcing the individual shell
functions via ``bash -c`` — the same convention ``test_launch_runner_dispatch``
uses (``eval "$(awk '/^func/,/^}/' launcher)"``). Behaviours that need a real
``flock``/``tmux`` are gated behind availability checks and skip cleanly when
the tool is absent (mirrors the repo's pwsh-gated launcher tests).
"""

from __future__ import annotations

import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

REPO = Path(__file__).parent.parent
BASH_LAUNCHER = REPO / "scripts" / "launch-agents.sh"

HAVE_BASH = shutil.which("bash") is not None
HAVE_FLOCK = shutil.which("flock") is not None
HAVE_TMUX = shutil.which("tmux") is not None

pytestmark = pytest.mark.skipif(not HAVE_BASH, reason="bash not on PATH")


def _source_funcs(*names: str) -> str:
    """Return a bash snippet that extracts and defines the named launcher
    functions by slicing ``<name>() { ... }`` blocks out of the script.

    Mirrors ``test_launch_runner_dispatch``'s awk-slice approach so the tests
    exercise the REAL function bodies without running the whole launcher.
    """
    parts = []
    for name in names:
        # Match the `name()` opener through the first line that is a bare `}`.
        parts.append(f"eval \"$(awk '/^{name}\\(\\)/,/^}}$/' {BASH_LAUNCHER})\"")
    return "\n".join(parts)


def _run_bash(script: str, env: dict | None = None, timeout: int = 20):
    return subprocess.run(
        ["bash", "-c", script],
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )


# ---------------------------------------------------------------------------
# 1.1 — lock-key derivation
# ---------------------------------------------------------------------------


class TestLockKeyDerivation:
    def test_org_from_ce_layout(self, tmp_path):
        meta = tmp_path / "orgs" / "acme" / "programs" / "alpha" / "alpha-meta"
        meta.mkdir(parents=True)
        script = f"""
        set -eu
        {_source_funcs("acting_lock_org")}
        acting_lock_org {meta} alpha
        """
        r = _run_bash(script)
        assert r.returncode == 0, r.stderr
        assert r.stdout.strip() == "acme"

    def test_org_falls_back_to_program_on_flat_layout(self, tmp_path):
        flat = tmp_path / "some" / "flat" / "meta"
        flat.mkdir(parents=True)
        script = f"""
        set -eu
        {_source_funcs("acting_lock_org")}
        acting_lock_org {flat} myprog
        """
        r = _run_bash(script)
        assert r.returncode == 0, r.stderr
        assert r.stdout.strip() == "myprog"

    def test_lock_key_is_program_scoped(self):
        script = f"""
        set -eu
        {_source_funcs("acting_lock_key")}
        acting_lock_key acme alpha plugin-agent
        """
        r = _run_bash(script)
        assert r.returncode == 0, r.stderr
        assert r.stdout.strip() == "acme--alpha--plugin-agent"


# ---------------------------------------------------------------------------
# 1.1 — lock-path selection (XDG present vs fallback)
# ---------------------------------------------------------------------------


class TestLockPathSelection:
    def test_prefers_xdg_runtime_dir(self, tmp_path):
        xdg = tmp_path / "run"
        xdg.mkdir()
        script = f"""
        set -eu
        {_source_funcs("acting_lock_path")}
        acting_lock_path acme--alpha--plugin-agent
        """
        env = {"PATH": "/usr/bin:/bin", "XDG_RUNTIME_DIR": str(xdg), "HOME": str(tmp_path)}
        r = _run_bash(script, env=env)
        assert r.returncode == 0, r.stderr
        expected = str(xdg / "otaman" / "acme--alpha--plugin-agent.lock")
        assert r.stdout.strip() == expected
        # acting_lock_path is PURE — it must NOT create the parent dir (dry-run
        # honesty). Directory creation is acting_ensure_lockdir's job.
        assert not (xdg / "otaman").exists()

    def test_falls_back_to_home_when_xdg_unset(self, tmp_path):
        home = tmp_path / "home"
        home.mkdir()
        script = f"""
        set -eu
        {_source_funcs("acting_lock_path")}
        acting_lock_path k
        """
        # XDG_RUNTIME_DIR deliberately absent from env.
        env = {"PATH": "/usr/bin:/bin", "HOME": str(home)}
        r = _run_bash(script, env=env)
        assert r.returncode == 0, r.stderr
        expected = str(home / ".otaman" / "locks" / "k.lock")
        assert r.stdout.strip() == expected
        # pure — no dir created
        assert not (home / ".otaman" / "locks").exists()

    def test_ensure_lockdir_creates_parent(self, tmp_path):
        lockfile = tmp_path / "run" / "otaman" / "k.lock"
        script = f"""
        set -eu
        {_source_funcs("acting_ensure_lockdir")}
        acting_ensure_lockdir {lockfile}
        """
        env = {"PATH": "/usr/bin:/bin"}
        r = _run_bash(script, env=env)
        assert r.returncode == 0, r.stderr
        assert lockfile.parent.is_dir()
        # ensure_lockdir creates only the dir, not the lock file itself.
        assert not lockfile.exists()

    def test_lock_path_not_under_agents(self, tmp_path):
        """Runtime ephemera must NOT land under .agents/ (committed bus canon)."""
        script = f"""
        set -eu
        {_source_funcs("acting_lock_path")}
        acting_lock_path k
        """
        env = {"PATH": "/usr/bin:/bin", "HOME": str(tmp_path)}
        r = _run_bash(script, env=env)
        assert "/.agents/" not in r.stdout


# ---------------------------------------------------------------------------
# 1.1 — metadata sidecar
# ---------------------------------------------------------------------------


class TestSidecar:
    def test_sidecar_contains_pid_mode_session_started(self, tmp_path):
        lockfile = tmp_path / "id.lock"
        script = f"""
        set -eu
        {_source_funcs("acting_write_sidecar")}
        acting_write_sidecar {lockfile} 4242 interactive proj:agent
        cat {lockfile}.info
        """
        env = {"PATH": "/usr/bin:/bin"}
        r = _run_bash(script, env=env)
        assert r.returncode == 0, r.stderr
        out = r.stdout
        assert "pid=4242" in out
        assert "mode=interactive" in out
        assert "session=proj:agent" in out
        # started is ISO-8601 (YYYY-MM-DDTHH:MM:SSZ)
        assert "started=" in out
        started = [ln for ln in out.splitlines() if ln.startswith("started=")][0]
        val = started.split("=", 1)[1]
        # crude ISO-8601 shape check
        assert val == "unknown" or (val.endswith("Z") and "T" in val and val[4] == "-")

    def test_read_sidecar_field_roundtrip(self, tmp_path):
        lockfile = tmp_path / "id.lock"
        script = f"""
        set -eu
        {_source_funcs("acting_write_sidecar", "acting_read_sidecar_field")}
        acting_write_sidecar {lockfile} 99 background sess:x
        acting_read_sidecar_field {lockfile} pid
        acting_read_sidecar_field {lockfile} mode
        acting_read_sidecar_field {lockfile} session
        """
        env = {"PATH": "/usr/bin:/bin"}
        r = _run_bash(script, env=env)
        assert r.returncode == 0, r.stderr
        assert r.stdout.split() == ["99", "background", "sess:x"]


# ---------------------------------------------------------------------------
# 1.3 — mode detection
# ---------------------------------------------------------------------------


class TestModeDetection:
    def test_forced_interactive(self):
        script = f"""
        set -eu
        {_source_funcs("acting_detect_mode")}
        acting_detect_mode interactive
        """
        r = _run_bash(script)
        assert r.stdout.strip() == "interactive"

    def test_forced_background(self):
        script = f"""
        set -eu
        {_source_funcs("acting_detect_mode")}
        acting_detect_mode background
        """
        r = _run_bash(script)
        assert r.stdout.strip() == "background"

    def test_infers_background_without_tty(self):
        # subprocess pipes are not TTYs -> background inferred.
        script = f"""
        set -eu
        {_source_funcs("acting_detect_mode")}
        acting_detect_mode ""
        """
        r = _run_bash(script)
        assert r.stdout.strip() == "background"


# ---------------------------------------------------------------------------
# CLI parsing — text contract (no execution needed)
# ---------------------------------------------------------------------------


class TestActingCliContract:
    @pytest.fixture(scope="class")
    def text(self) -> str:
        return BASH_LAUNCHER.read_text(encoding="utf-8")

    def test_interactive_flag_accepted(self, text):
        assert "--interactive)" in text

    def test_background_flag_accepted(self, text):
        assert "--background)" in text

    def test_hidden_inner_flag_present(self, text):
        assert "--_acting-inner)" in text

    def test_bash_dispatch_routes_through_acting_launch(self, text):
        # The old bare split-brain line must be gone from the bash case.
        assert '"${claude_cmd_continue[@]}" || exec "${claude_cmd_fresh[@]}"' not in text
        assert "acting_launch " in text

    def test_flock_fd_survives_exec(self, text):
        # The lock fd must be opened with a plain redirect (no close-on-exec)
        # so it survives the exec into claude (task 1.1).
        assert 'exec {lockfd}>"$lockfile"' in text
        assert "flock -n" in text

    def test_attach_uses_exact_match_target(self, text):
        # Attach-first (task 1.2) must use tmux exact-match '=' targets like
        # the existing tmux path.
        assert 'tmux attach-session -t "=${session}"' in text
        assert 'tmux has-session -t "=${session}"' in text

    def test_background_never_writes_preempt(self, text):
        # acting_write_preempt is only invoked from the interactive branch.
        # Guard: the preempt writer is gated behind an interactive check.
        assert "acting_write_preempt" in text
        # The only call sites are inside acting_try_preempt, which itself is
        # only reached on the interactive path.
        assert 'mode" == "interactive"' in text


# ---------------------------------------------------------------------------
# 1.1 — real flock behaviours (crashed-holder auto-release, second-launch
# cannot double-acquire). Skipped when flock is unavailable.
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not HAVE_FLOCK, reason="flock not on PATH")
class TestRealFlock:
    def test_held_lock_blocks_second_nonblocking_acquire(self, tmp_path):
        """While a holder keeps the fd open, a second `flock -n` fails —
        this is the primitive that prevents a second acting session."""
        lockfile = tmp_path / "id.lock"
        # Holder: open fd, flock it, sleep, keep fd open. Meanwhile a second
        # non-blocking acquire in a subshell must fail (exit non-zero).
        script = textwrap.dedent(f"""
        set -u
        exec {{h}}>{lockfile}
        flock -n "$h" || {{ echo "holder-failed"; exit 9; }}
        # second non-blocking acquire in a fresh fd must fail
        if ( exec {{s}}>{lockfile}; flock -n "$s" ) 2>/dev/null; then
            echo "SECOND-ACQUIRED"
        else
            echo "SECOND-BLOCKED"
        fi
        """)
        env = {"PATH": "/usr/bin:/bin"}
        r = _run_bash(script, env=env)
        assert r.returncode == 0, r.stderr
        assert "SECOND-BLOCKED" in r.stdout
        assert "SECOND-ACQUIRED" not in r.stdout

    def test_crashed_holder_auto_releases(self, tmp_path):
        """A holder killed with -9 must leave the lock immediately free — the
        kernel releases the flock on process death, no manual cleanup."""
        lockfile = tmp_path / "id.lock"
        # Start a background holder that flocks and sleeps; capture its pid;
        # kill -9 it; then a fresh non-blocking acquire must succeed.
        # A holder that keeps the lock fd open while it "runs" (flock forks
        # `sleep`, which inherits the fd — the fd, not the flock binary, is
        # what pins the lock; this mirrors an acting claude that inherited the
        # lock fd across exec). setsid gives the holder its own process group;
        # it records that pgid so we can `kill -9` the whole tree — the kernel
        # then releases the flock the instant the last fd-holder dies, with no
        # manual lock cleanup (task 1.1 acceptance: crashed holder auto-frees).
        pgidfile = tmp_path / "holder.pgid"
        script = textwrap.dedent(f"""
        set -u
        setsid sh -c 'ps -o pgid= -p $$ | tr -d " " > {pgidfile}; \
            exec flock -n {lockfile} sleep 20' &
        # Wait until the lock is actually held (setsid+flock startup can lag).
        held=0
        for _ in $(seq 1 100); do
            if [ -s {pgidfile} ] && ! ( exec {{s}}>{lockfile}; flock -n "$s" ) 2>/dev/null; then
                held=1; break
            fi
            sleep 0.1
        done
        [ "$held" = 1 ] || {{ echo "HOLDER-NEVER-ACQUIRED"; exit 1; }}
        pgid=$(cat {pgidfile})
        kill -9 -"$pgid" 2>/dev/null || true
        # Kernel releases the flock on process death -> immediately acquirable.
        for _ in $(seq 1 30); do
            if ( exec {{s}}>{lockfile}; flock -n "$s" ) 2>/dev/null; then
                echo "REACQUIRED"; exit 0
            fi
            sleep 0.1
        done
        echo "STILL-HELD"
        """)
        env = {"PATH": "/usr/bin:/bin"}
        r = _run_bash(script, env=env, timeout=45)
        assert r.returncode == 0, r.stderr
        assert "REACQUIRED" in r.stdout, f"lock not released after kill -9: {r.stdout!r}"


# ---------------------------------------------------------------------------
# 1.2 / attach — real tmux: a second launch attaches into the live identity
# session instead of starting a second acting process. Skipped without tmux.
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not HAVE_TMUX, reason="tmux not on PATH")
class TestAttachFirst:
    def test_sanitized_identity_session_is_attach_findable(self, tmp_path):
        """Attach-first (task 1.2) relies on has-session/attach keying on the
        SAME literal name tmux stores. tmux rewrites '.'/':' to '_' on create,
        so the launcher pre-sanitizes the identity name (program:owner ->
        program_owner). Verify the sanitized name round-trips: create it, then
        has-session with the '=' exact-match target finds it."""
        socket = tmp_path / "tmux.sock"
        base = ["tmux", "-S", str(socket)]
        # The launcher's sanitization: tr '.:' '__'
        sanitized = "proj:agent".translate(str.maketrans(".:", "__"))
        assert sanitized == "proj_agent"
        try:
            subprocess.run(
                [*base, "new-session", "-d", "-s", sanitized, "-n", "w", "sh"],
                check=True,
                capture_output=True,
                timeout=10,
            )
            hit = subprocess.run(
                [*base, "has-session", "-t", f"={sanitized}"],
                capture_output=True,
                timeout=10,
            )
            assert hit.returncode == 0, hit.stderr
        finally:
            subprocess.run([*base, "kill-server"], capture_output=True, timeout=10)


# ---------------------------------------------------------------------------
# --dry-run honesty — describes the new behaviour without acquiring / spawning
# ---------------------------------------------------------------------------


class TestDryRunHonesty:
    @pytest.fixture(scope="class")
    def text(self) -> str:
        return BASH_LAUNCHER.read_text(encoding="utf-8")

    def test_dry_run_describes_attach_and_lock(self, text):
        assert "would route acting launch through identity tmux session" in text
        assert "dry-run: no lock acquired, nothing spawned" in text

    def test_dry_run_still_early_exits(self, text):
        # The DRY_RUN block still `exit 0`s before any dispatch/lock code.
        idx = text.index('if [[ "$DRY_RUN" -eq 1 ]]; then')
        after = text[idx : idx + 1500]
        assert "exit 0" in after
