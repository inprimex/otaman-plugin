"""Tests for single-acting-session-guard tasks 1.1-1.4 — plugin (launcher) half.

Per interop ruling 20260829T222512 the bash launcher is a THIN WRAPPER over the
CLI verb ``otaman acting-lock`` (the lock primitive lives in
``otaman_core.acting_lock``, exposed via cli). The launcher no longer owns any
lock-key / lockfile-path / sidecar / preempt-marker logic — so there is nothing
of that kind left to unit-test here.

Instead these tests exercise the WRAPPER behaviour by putting a fake ``otaman``
(and, where needed, a fake ``tmux``/``claude``) on ``PATH`` in a temp dir and
driving the real ``scripts/launch-agents.sh``. The fake ``otaman`` records the
argv it was called with and returns a configurable exit code, letting us assert:

- 1.1  bash-mode with no live session wraps ``otaman acting-lock run
       --mode <mode> ... -- ...`` (the respawn loop is the wrapped command).
- 1.2  attach-first: a live identity tmux session makes a second launch attach
       and NOT invoke ``acting-lock run`` again (skipped without real tmux).
- 1.3  mode detection: ``--interactive`` / ``--background`` flip ``--mode`` and
       ``--preempt`` is present iff interactive; the TTY-inference default.
- 1.4  no-tmux: with tmux absent and the stub ``acting-lock run`` returning
       exit 2, the launcher probes the holder and does not double-act.
- --dry-run honesty: no calls to the ``otaman`` stub, nothing spawned.

Behaviours needing a real ``tmux`` are gated behind availability checks and skip
cleanly when the tool is absent (mirrors the repo's pwsh-gated launcher tests).
"""

from __future__ import annotations

import os
import shlex
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).parent.parent
BASH_LAUNCHER = REPO / "scripts" / "launch-agents.sh"

HAVE_BASH = shutil.which("bash") is not None
HAVE_TMUX = shutil.which("tmux") is not None
HAVE_PYTHON3 = shutil.which("python3") is not None

pytestmark = pytest.mark.skipif(not HAVE_BASH, reason="bash not on PATH")


# ---------------------------------------------------------------------------
# Fixtures: a fake otaman folder + fake PATH tools
# ---------------------------------------------------------------------------


def _make_otaman_root(tmp_path: Path, *, project: str = "proj", owner: str = "agent") -> Path:
    """Create a minimal otaman root with a .otaman marker + platform.yaml."""
    root = tmp_path / "meta"
    root.mkdir()
    # find_maestro_root keys on the .otaman marker.
    (root / ".otaman").write_text("", encoding="utf-8")
    (root / "platform.yaml").write_text(
        f"project: {project}\nrepos:\n  - name: {owner}\n    owner: {owner}\n    path: .\n",
        encoding="utf-8",
    )
    return root


def _write_exec(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


# Coreutils the launcher shells out to (bash builtins like printf/read/cd are
# not listed). We symlink ONLY these into the test bindir so a "no tmux" test
# genuinely has no ``tmux`` reachable — real ``/usr/bin`` is kept off PATH so a
# system tmux can never leak in and defeat the no-tmux branch.
_COREUTILS = (
    "bash",
    "python3",
    "sed",
    "grep",
    "tr",
    "date",
    "mkdir",
    "dirname",
    "cat",
    "cut",
    "env",
    "uname",
    "seq",
    "sleep",
)


def _link_coreutils(bindir: Path) -> None:
    for name in _COREUTILS:
        if name == "python3":
            # The launcher parses platform.yaml with `python3` (needs PyYAML).
            # Provide the TEST interpreter (sys.executable), which always has
            # PyYAML in a pytest run — so the hermetic PATH is deterministic
            # across hosts/CI. Use a WRAPPER, not a symlink: a venv interpreter
            # symlinked outside its venv fails pyvenv.cfg discovery and loses
            # its site-packages (PyYAML). Exec-ing it by absolute path keeps
            # venv resolution intact.
            wrapper = bindir / "python3"
            wrapper.write_text(f'#!/bin/sh\nexec {shlex.quote(sys.executable)} "$@"\n')
            wrapper.chmod(0o755)
            continue
        src = shutil.which(name)
        if src and not (bindir / name).exists():
            os.symlink(src, bindir / name)


def _make_bindir(
    tmp_path: Path,
    *,
    with_tmux: bool,
    with_claude: bool = True,
    otaman_run_rc: int = 0,
    args_log: Path | None = None,
    probe_log: Path | None = None,
) -> Path:
    """Build a temp PATH dir with fake tools.

    The fake ``otaman`` records each ``acting-lock run`` argv line to
    ``args_log`` and returns ``otaman_run_rc`` for ``run``; ``probe`` records to
    ``probe_log`` and emits a JSON holder. Other ``otaman`` subcommands (e.g.
    ``launcher register``) are accepted as no-ops.
    """
    bindir = tmp_path / "bin"
    bindir.mkdir()
    _link_coreutils(bindir)

    args_log = args_log or (tmp_path / "otaman_run_args.log")
    probe_log = probe_log or (tmp_path / "otaman_probe.log")

    otaman = bindir / "otaman"
    _write_exec(
        otaman,
        f"""#!/usr/bin/env bash
if [[ "$1" == "acting-lock" && "$2" == "run" ]]; then
    printf '%s\\n' "$*" >> {args_log}
    exit {otaman_run_rc}
fi
if [[ "$1" == "acting-lock" && "$2" == "probe" ]]; then
    printf '%s\\n' "$*" >> {probe_log}
    # emit a live-holder JSON so acting_print_holder can parse it
    h='{{"pid": 4242, "mode": "background", "tmux_session": "proj_agent", "started_at": "x"}}'
    printf '{{"held": true, "holder": %s}}\\n' "$h"
    exit 0
fi
# any other subcommand (launcher register, ...) — silent no-op
exit 0
""",
    )

    if with_tmux:
        # A fake tmux that reports NO existing session and records new-session /
        # send-keys / attach lines, so tests can assert the create-and-wrap path
        # without a real multiplexer.
        tmux_log = tmp_path / "tmux.log"
        _write_exec(
            bindir / "tmux",
            f"""#!/usr/bin/env bash
printf '%s\\n' "$*" >> {tmux_log}
case "$1" in
  has-session) exit 1 ;;   # no live identity session
  *) exit 0 ;;
esac
""",
        )

    if with_claude:
        _write_exec(bindir / "claude", "#!/usr/bin/env bash\nexit 0\n")

    return bindir


def _run_launcher(root: Path, bindir: Path, *extra_args: str, force_no_tty: bool = True):
    """Drive launch-agents.sh from inside ``root`` with a curated PATH.

    ``force_no_tty`` (default) runs via subprocess pipes, so stdin/stdout are not
    TTYs -> background mode is inferred unless a flag forces otherwise.

    PATH is HERMETIC: only ``bindir`` (fakes + symlinked coreutils). Real system
    dirs are deliberately excluded so a system ``tmux`` can never leak in and
    defeat a no-tmux test.
    """
    env = {
        "PATH": str(bindir),
        "HOME": str(root.parent),
        # Strip OTAMAN_ROOT/etc so find_maestro_root uses the marker in `root`.
    }
    return subprocess.run(
        [shutil.which("bash"), str(BASH_LAUNCHER), *extra_args],
        cwd=str(root),
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
    )


# ---------------------------------------------------------------------------
# Text-contract sanity: the launcher no longer reimplements the primitive
# ---------------------------------------------------------------------------


class TestWrapperContract:
    @pytest.fixture(scope="class")
    def text(self) -> str:
        return BASH_LAUNCHER.read_text(encoding="utf-8")

    def test_wraps_acting_lock_run(self, text):
        assert "otaman acting-lock run --mode" in text

    def test_no_bash_lock_primitive(self, text):
        # None of the FORBIDDEN in-bash lock machinery may reappear.
        for banned in (
            "acting_lock_org",
            "acting_lock_key",
            "acting_lock_path",
            "acting_ensure_lockdir",
            "acting_write_sidecar",
            "acting_read_sidecar_field",
            "acting_write_preempt",
            "--_acting-inner",
        ):
            assert banned not in text, f"forbidden lock-primitive symbol present: {banned}"
        # The bash launcher must never INVOKE flock itself (cli owns the lock).
        # The word may appear in comments describing what cli does; guard only
        # against an actual `flock -n`/`flock -x`/`exec {fd}>` acquisition.
        assert "flock -n" not in text, "bash must not call flock — cli owns the lock"
        assert "flock -x" not in text, "bash must not call flock — cli owns the lock"
        assert "{lockfd}" not in text, "bash must not open a lock fd — cli owns the lock"

    def test_old_split_brain_line_gone(self, text):
        assert '"${claude_cmd_continue[@]}" || exec "${claude_cmd_fresh[@]}"' not in text

    def test_interactive_and_background_flags(self, text):
        assert "--interactive)" in text
        assert "--background)" in text

    def test_attach_uses_exact_match_target(self, text):
        assert 'tmux has-session -t "=${ACTING_SESSION}"' in text
        assert 'tmux attach-session -t "=${ACTING_SESSION}"' in text

    def test_probe_used_for_holder(self, text):
        assert "otaman acting-lock probe --json" in text


# ---------------------------------------------------------------------------
# 1.1 / 1.3 — bash-mode wraps `acting-lock run` with the right mode + preempt
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not HAVE_PYTHON3, reason="python3 needed to parse platform.yaml")
class TestWrapInvocation:
    def _assert_wrapped(self, argline: str, *, mode: str, preempt: bool):
        assert f"acting-lock run --mode {mode}" in argline
        assert "-- bash -lc" in argline
        if preempt:
            assert "--preempt" in argline
        else:
            assert "--preempt" not in argline

    def test_no_tmux_background_wraps_run(self, tmp_path):
        """No tmux, no forced flag, non-TTY -> background, no --preempt."""
        root = _make_otaman_root(tmp_path)
        args_log = tmp_path / "run.log"
        bindir = _make_bindir(tmp_path, with_tmux=False, otaman_run_rc=0, args_log=args_log)
        r = _run_launcher(root, bindir)
        assert r.returncode == 0, r.stderr
        assert args_log.exists(), f"acting-lock run never invoked. stderr:\n{r.stderr}"
        self._assert_wrapped(args_log.read_text(), mode="background", preempt=False)

    def test_no_tmux_interactive_flag_adds_preempt(self, tmp_path):
        root = _make_otaman_root(tmp_path)
        args_log = tmp_path / "run.log"
        bindir = _make_bindir(tmp_path, with_tmux=False, otaman_run_rc=0, args_log=args_log)
        r = _run_launcher(root, bindir, "--interactive")
        assert r.returncode == 0, r.stderr
        self._assert_wrapped(args_log.read_text(), mode="interactive", preempt=True)

    def test_background_flag_never_preempts(self, tmp_path):
        root = _make_otaman_root(tmp_path)
        args_log = tmp_path / "run.log"
        bindir = _make_bindir(tmp_path, with_tmux=False, otaman_run_rc=0, args_log=args_log)
        r = _run_launcher(root, bindir, "--background")
        assert r.returncode == 0, r.stderr
        self._assert_wrapped(args_log.read_text(), mode="background", preempt=False)

    def test_tmux_present_creates_session_and_wraps_run(self, tmp_path):
        """With a (fake) tmux reporting no live session, the launcher creates
        the identity session and send-keys the wrapper into it."""
        root = _make_otaman_root(tmp_path)
        args_log = tmp_path / "run.log"
        bindir = _make_bindir(tmp_path, with_tmux=True, args_log=args_log)
        r = _run_launcher(root, bindir, "--interactive")
        # The wrapper runs inside the pane via send-keys, so the fake otaman is
        # not called in THIS process; assert the tmux send-keys carried it.
        tmux_log = (tmp_path / "tmux.log").read_text()
        assert "new-session" in tmux_log
        assert "acting-lock run --mode interactive" in tmux_log
        assert "--preempt" in tmux_log
        assert r.returncode == 0, r.stderr


# ---------------------------------------------------------------------------
# 1.4 — no-tmux held-lock refusal: probe holder, passive mirror, no double-act
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not HAVE_PYTHON3, reason="python3 needed to parse platform.yaml")
class TestNoTmuxRefusal:
    def test_exit2_triggers_probe_and_mirror(self, tmp_path):
        root = _make_otaman_root(tmp_path)
        args_log = tmp_path / "run.log"
        probe_log = tmp_path / "probe.log"
        # `acting-lock run` returns exit 2 (held) -> launcher must probe + mirror.
        bindir = _make_bindir(
            tmp_path,
            with_tmux=False,
            otaman_run_rc=2,
            args_log=args_log,
            probe_log=probe_log,
        )
        r = _run_launcher(root, bindir)
        # run was attempted exactly once (no double-act).
        assert args_log.read_text().count("acting-lock run") == 1
        # probe was consulted for the holder.
        assert probe_log.exists() and "acting-lock probe" in probe_log.read_text()
        # holder surfaced + passive-mirror messaging.
        assert "role already held" in r.stderr
        assert "PASSIVE read-only mirror" in r.stderr
        # `claude -c` (read-only mirror) is exec'd — fake claude exits 0.
        assert r.returncode == 0, r.stderr


# ---------------------------------------------------------------------------
# 1.2 — attach-first with a REAL tmux: a live identity session is attached
# into and `acting-lock run` is NOT invoked a second time.
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not HAVE_TMUX, reason="tmux not on PATH")
@pytest.mark.skipif(not HAVE_PYTHON3, reason="python3 needed to parse platform.yaml")
class TestAttachFirst:
    def test_live_session_attaches_without_second_run(self, tmp_path):
        root = _make_otaman_root(tmp_path, project="proj", owner="agent")
        args_log = tmp_path / "run.log"
        # Fake otaman (records run) + fake claude, but use REAL tmux on a
        # private socket so has-session finds the pre-created identity session.
        bindir = tmp_path / "bin"
        bindir.mkdir()
        _write_exec(
            bindir / "otaman",
            f"""#!/usr/bin/env bash
if [[ "$1" == "acting-lock" && "$2" == "run" ]]; then
    printf '%s\\n' "$*" >> {args_log}
fi
exit 0
""",
        )
        _write_exec(bindir / "claude", "#!/usr/bin/env bash\nexit 0\n")

        socket = tmp_path / "tmux.sock"
        # Sanitized identity name: project:owner -> proj_agent (tr '.:' '__').
        session = "proj_agent"
        real_tmux = shutil.which("tmux")
        # Wrapper tmux that always targets our private socket.
        _write_exec(
            bindir / "tmux",
            f'#!/usr/bin/env bash\nexec {real_tmux} -S {socket} "$@"\n',
        )
        try:
            subprocess.run(
                [real_tmux, "-S", str(socket), "new-session", "-d", "-s", session, "-n", "w", "sh"],
                check=True,
                capture_output=True,
                timeout=10,
            )
            real_bins = [str(Path(shutil.which("python3")).parent)]
            path = os.pathsep.join([str(bindir), "/usr/bin", "/bin", *real_bins])
            env = {"PATH": path, "HOME": str(root.parent), "TMUX": "fake"}
            # TMUX set -> launcher uses switch-client (no blocking attach).
            r = subprocess.run(
                ["bash", str(BASH_LAUNCHER)],
                cwd=str(root),
                capture_output=True,
                text=True,
                timeout=30,
                env=env,
            )
            assert "is live — attaching" in r.stderr, r.stderr
            # Critical: no second acting-lock run while a live session exists.
            assert not args_log.exists() or "acting-lock run" not in args_log.read_text()
        finally:
            subprocess.run(
                [real_tmux, "-S", str(socket), "kill-server"],
                capture_output=True,
                timeout=10,
            )


# ---------------------------------------------------------------------------
# --dry-run honesty — describes wrapper behaviour; no otaman/tmux/claude calls
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not HAVE_PYTHON3, reason="python3 needed to parse platform.yaml")
class TestDryRunHonesty:
    def test_dry_run_no_side_effects(self, tmp_path):
        root = _make_otaman_root(tmp_path)
        args_log = tmp_path / "run.log"
        probe_log = tmp_path / "probe.log"
        bindir = _make_bindir(
            tmp_path,
            with_tmux=True,
            otaman_run_rc=0,
            args_log=args_log,
            probe_log=probe_log,
        )
        r = _run_launcher(root, bindir, "--dry-run")
        assert r.returncode == 0, r.stderr
        # Dry-run must NOT invoke the wrapper or probe, and must NOT spawn tmux.
        assert not args_log.exists(), "dry-run invoked acting-lock run"
        assert not probe_log.exists(), "dry-run invoked acting-lock probe"
        tmux_log = tmp_path / "tmux.log"
        assert not tmux_log.exists(), "dry-run spawned tmux"
        # It should describe the wrapper behaviour.
        assert "otaman acting-lock run --mode" in r.stderr
        assert "dry-run: no probe, no lock acquired, nothing spawned" in r.stderr

    def test_dry_run_text_describes_attach(self):
        text = BASH_LAUNCHER.read_text(encoding="utf-8")
        assert "would route acting launch through identity tmux session" in text
        assert "no second acting process" in text
