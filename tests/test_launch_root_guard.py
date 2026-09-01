"""Durable guard (deploy-agent 2026-08-31 incident, msg 20260831T195825):
launch-agents.sh must refuse to run as root (uid 0) — a root-run session
left ~/.claude/projects/<program> owned root:root (romans:romans in the
observed incident), EACCES'ing every later non-root session's transcript
writes for that program.

EUID is a bash builtin sourced from the real process's effective UID, not
from the environment — there is no way to make a subprocess actually run
as uid 0 inside this sandbox (no real root, and unshare -r/user-namespace
remap is blocked here too). So this pins the guard structurally: it must
exist, and it must run before ANY session-spawning code path (the
otaman-root resolution / tmux / claude-exec logic), rather than being
skippable by an early return or added after the fact where a future edit
could reorder past it. The non-root path itself is exercised for real by
the existing --dry-run / --list-repos tests elsewhere.
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).parent.parent
BASH_LAUNCHER = REPO / "scripts" / "launch-agents.sh"


def _source() -> str:
    return BASH_LAUNCHER.read_text(encoding="utf-8")


def test_root_guard_present_and_refuses_uid_zero():
    source = _source()
    assert 'if [[ "${EUID:-$(id -u)}" -eq 0 ]]; then' in source
    assert "refusing to launch as root" in source


def test_root_guard_runs_before_any_spawn_path():
    source = _source()
    guard_pos = source.index('if [[ "${EUID:-$(id -u)}" -eq 0 ]]; then')
    resolve_root_pos = source.index("# Resolve otaman root + determine python interpreter")
    tmux_new_session_pos = source.index("tmux new-session")
    exec_claude_pos = source.index("exec claude -c")

    assert guard_pos < resolve_root_pos
    assert guard_pos < tmux_new_session_pos
    assert guard_pos < exec_claude_pos


def test_root_guard_exits_nonzero_on_the_root_branch():
    source = _source()
    guard_start = source.index('if [[ "${EUID:-$(id -u)}" -eq 0 ]]; then')
    guard_block = source[guard_start : guard_start + 400]
    assert "exit 1" in guard_block
