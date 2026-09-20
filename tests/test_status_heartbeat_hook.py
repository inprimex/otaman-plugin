"""status-heartbeat 1.1: hooks/status-heartbeat.sh refreshes a live session's
`updated_at` on a bounded cadence.

Measured 2026-09-16: `updated_at == since` for every live record, so a crashed
session kept claiming work and `otaman status` reported a dead fleet as busy.
cli's 1.2 renders a record past the TTL as STALE; this hook is the other half —
what keeps a LIVE session from being falsely accused by that rule.

The two properties that matter, and why each is tested here rather than left to
review: the refresh must actually happen (or every long-running session goes
falsely STALE), and it must be THROTTLED (PreToolUse fires on every Bash/Write/
Edit — this repo already has a documented incident, PR #72, where a per-call
hook blew the UserPromptSubmit timeout on a real workspace).

Real subprocess execution against the actual hook and real status files, same
convention as the other hook suites here (test_check_branch_hook.py,
test_acting_human_boot_hook.py).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).parent.parent
HOOK = REPO / "hooks" / "status-heartbeat.sh"
HOOKS_JSON = REPO / "hooks" / "hooks.json"

HAVE_BASH = shutil.which("bash") is not None

pytestmark = pytest.mark.skipif(not HAVE_BASH, reason="bash not on PATH")


@pytest.fixture(autouse=True)
def _unpin_root(monkeypatch):
    """bus-test-isolation 4.2 footgun: the shared isolate_bus fixture PINS
    OTAMAN_ROOT at a sandbox, which this hook's find_maestro_root would pick up
    instead of each test's own tmp_path. Delete it (and the legacy alias) on top
    of isolate_bus for this file only."""
    monkeypatch.delenv("OTAMAN_ROOT", raising=False)
    monkeypatch.delenv("MAESTRO_ROOT", raising=False)


def _make_workspace(
    tmp_path: Path,
    *,
    agent: str = "plugin-agent",
    state: str = "working",
    updated_at: str = "2026-09-19T10:00:00Z",
    write_status: bool = True,
) -> tuple[Path, Path]:
    """Sibling layout matching production: the otaman root holds .agents/, the
    repo (cwd) holds its own CLAUDE.md naming the agent."""
    root = tmp_path / "otaman-root"
    root.mkdir()
    (root / "platform.yaml").write_text("project: test\n", encoding="utf-8")

    if write_status:
        status_dir = root / ".agents" / "status"
        status_dir.mkdir(parents=True)
        (status_dir / f"{agent}.yaml").write_text(
            yaml.safe_dump(
                {
                    "agent": agent,
                    "state": state,
                    "task": "1.1 do the thing",
                    "change": "status-heartbeat",
                    "outcome": None,
                    "blocked_by": None,
                    "since": "2026-09-19T10:00:00Z",
                    "updated_at": updated_at,
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )

    repo = tmp_path / "repo"
    repo.mkdir()
    # Real marker format (see this repo's own .otaman): a BARE relative-path
    # line, plus `agent:`. A `otaman_root: <path>` key is NOT parsed — the
    # resolver reads the bare form or the legacy `maestro_root:` key, and
    # silently ignores unknown keys.
    (repo / ".otaman").write_text(f"../otaman-root\nagent: {agent}\n", encoding="utf-8")
    (repo / "CLAUDE.md").write_text(f"You are `{agent}`.\n", encoding="utf-8")
    return root, repo


def _status_path(root: Path, agent: str = "plugin-agent") -> Path:
    return root / ".agents" / "status" / f"{agent}.yaml"


def _read_status(root: Path, agent: str = "plugin-agent") -> dict:
    return yaml.safe_load(_status_path(root, agent).read_text(encoding="utf-8"))


def _age_file(path: Path, seconds: int) -> None:
    """Backdate mtime — the hook uses it as its throttle clock."""
    past = time.time() - seconds
    os.utime(path, (past, past))


def _run_hook(repo: Path, *, interval: str | None = None, env_extra: dict | None = None):
    env = {**os.environ, "OTAMAN_AGENT": ""}
    env.pop("OTAMAN_AGENT")
    if interval is not None:
        env["OTAMAN_HEARTBEAT_INTERVAL"] = interval
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        ["bash", str(HOOK)],
        cwd=str(repo),
        input=json.dumps({"cwd": str(repo)}),
        capture_output=True,
        text=True,
        timeout=15,
        env=env,
    )


class TestRefreshesLiveSession:
    def test_stale_working_record_is_refreshed(self, tmp_path):
        """The core behaviour: past the interval, updated_at moves forward."""
        root, repo = _make_workspace(tmp_path, state="working")
        _age_file(_status_path(root), 600)
        before = _read_status(root)["updated_at"]

        r = _run_hook(repo, interval="300")
        assert r.returncode == 0, r.stderr

        after = _read_status(root)["updated_at"]
        assert after != before
        assert after.endswith("Z")

    def test_waiting_is_refreshed_too(self, tmp_path):
        """`waiting` also claims a live session — staleness.py's STALEABLE is
        {working, waiting}, and this hook's scope must match it exactly."""
        root, repo = _make_workspace(tmp_path, state="waiting")
        _age_file(_status_path(root), 600)
        before = _read_status(root)["updated_at"]

        _run_hook(repo, interval="300")
        assert _read_status(root)["updated_at"] != before

    def test_every_other_field_survives_byte_for_byte(self, tmp_path):
        """The hook must rewrite ONE line, not round-trip the document — cli's
        FileStatusBackend owns this record's schema, and a hook that reformats
        or drops a field it does not understand would corrupt it."""
        root, repo = _make_workspace(tmp_path, state="working")
        _age_file(_status_path(root), 600)
        before = _read_status(root)

        _run_hook(repo, interval="300")
        after = _read_status(root)

        assert {k: v for k, v in after.items() if k != "updated_at"} == {
            k: v for k, v in before.items() if k != "updated_at"
        }

    def test_written_timestamp_is_parseable_by_cli_staleness(self, tmp_path):
        """What this hook writes must be readable by the rule it exists to
        satisfy — otherwise age_seconds() returns None and the record is
        treated as unparseable rather than fresh."""
        from otaman_cli.status.staleness import age_seconds

        root, repo = _make_workspace(tmp_path, state="working")
        _age_file(_status_path(root), 600)
        _run_hook(repo, interval="300")

        class _Rec:
            updated_at = _read_status(root)["updated_at"]

        age = age_seconds(_Rec())
        assert age is not None, "cli's staleness rule could not parse our stamp"
        # Lower bound is the part that matters, and an earlier version of this
        # test lacked it and passed against a real bug: bash's printf %()T
        # formats LOCAL time, so the hook stamped local-time-labelled-Z and
        # produced a NEGATIVE age (3h in the future on this UTC+3 host).
        # `age < 60` alone is satisfied by any future stamp. Mirrored in a
        # negative-offset zone the same bug yields a hugely POSITIVE age,
        # instantly stale — so both bounds are load-bearing.
        assert 0 <= age < 60, f"stamp is not 'now' in UTC (age={age}s)"

    def test_timestamp_is_utc_not_local_time(self, tmp_path):
        """Pin the timezone bug directly, independent of cli's parser: the
        written stamp must match UTC wall-clock, not the host's local zone.
        Runs the hook under a deliberately shifted TZ so a local-time
        implementation cannot coincidentally pass on a UTC build agent."""
        from datetime import datetime, timezone

        root, repo = _make_workspace(tmp_path, state="working")
        _age_file(_status_path(root), 600)
        _run_hook(repo, interval="300", env_extra={"TZ": "Asia/Tokyo"})  # UTC+9

        written = datetime.fromisoformat(_read_status(root)["updated_at"].replace("Z", "+00:00"))
        drift = abs((datetime.now(timezone.utc) - written).total_seconds())
        assert drift < 60, f"stamp drifted {drift}s from UTC — local time leaked in"


class TestThrottle:
    def test_within_interval_does_not_write(self, tmp_path):
        """The hot path. PreToolUse fires on every Bash/Write/Edit; a per-call
        write is the amplification the task explicitly forbids."""
        root, repo = _make_workspace(tmp_path, state="working")
        _age_file(_status_path(root), 10)
        before_mtime = _status_path(root).stat().st_mtime
        before = _read_status(root)["updated_at"]

        r = _run_hook(repo, interval="300")
        assert r.returncode == 0

        assert _status_path(root).stat().st_mtime == before_mtime
        assert _read_status(root)["updated_at"] == before

    def test_repeated_calls_inside_the_interval_write_once(self, tmp_path):
        """Ten tool calls in a row must produce at most one write."""
        root, repo = _make_workspace(tmp_path, state="working")
        _age_file(_status_path(root), 600)

        _run_hook(repo, interval="300")
        after_first = _status_path(root).stat().st_mtime

        for _ in range(9):
            _run_hook(repo, interval="300")

        assert _status_path(root).stat().st_mtime == after_first


class TestExemptStates:
    @pytest.mark.parametrize("state", ["idle", "blocked", "afk"])
    def test_non_claiming_states_are_never_refreshed(self, tmp_path, state):
        """Deliberately identical scope to staleness.py's STALEABLE. `afk` is
        the live `human` record — a deliberate 89-day-old human state that must
        not be made to look like a live session."""
        root, repo = _make_workspace(tmp_path, state=state)
        _age_file(_status_path(root), 6000)
        before = _read_status(root)["updated_at"]

        r = _run_hook(repo, interval="300")
        assert r.returncode == 0
        assert _read_status(root)["updated_at"] == before


class TestNeverBlocksOrSpeaks:
    def test_silent_on_success(self, tmp_path):
        """A PreToolUse hook that prints is a hook that injects text into every
        tool call; one that emits JSON could be read as a permission decision."""
        root, repo = _make_workspace(tmp_path, state="working")
        _age_file(_status_path(root), 600)
        r = _run_hook(repo, interval="300")
        assert r.stdout == ""

    def test_no_status_record_is_a_silent_noop(self, tmp_path):
        """No record means set-status never ran. The heartbeat refreshes an
        existing claim; it must never invent one nobody declared."""
        root, repo = _make_workspace(tmp_path, write_status=False)
        r = _run_hook(repo, interval="300")
        assert r.returncode == 0
        assert r.stdout == ""
        assert not (root / ".agents" / "status").exists()

    def test_unresolvable_root_is_a_silent_noop(self, tmp_path):
        """Run from a directory with no otaman root anywhere above it."""
        orphan = tmp_path / "orphan"
        orphan.mkdir()
        r = subprocess.run(
            ["bash", str(HOOK)],
            cwd=str(orphan),
            input=json.dumps({"cwd": str(orphan)}),
            capture_output=True,
            text=True,
            timeout=15,
            env={k: v for k, v in os.environ.items() if k != "OTAMAN_AGENT"},
        )
        assert r.returncode == 0
        assert r.stdout == ""

    def test_unwritable_status_file_does_not_fail_the_hook(self, tmp_path):
        """A read-only record must degrade to a no-op, never a non-zero exit —
        failing here would stall the tool call the hook is attached to."""
        root, repo = _make_workspace(tmp_path, state="working")
        _age_file(_status_path(root), 600)
        status_dir = root / ".agents" / "status"
        mode = status_dir.stat().st_mode
        status_dir.chmod(0o500)
        try:
            r = _run_hook(repo, interval="300")
            assert r.returncode == 0
            assert r.stdout == ""
        finally:
            status_dir.chmod(mode)


class TestWiring:
    def test_registered_on_both_hook_points(self):
        """Prompts alone miss an autonomously-working session (few prompts, many
        tool calls); tool calls alone miss a session idling at a prompt. The
        spec says "while the session lives", which needs both."""
        doc = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))
        points = {
            point
            for point, entries in doc["hooks"].items()
            for entry in entries
            for h in entry["hooks"]
            if "status-heartbeat.sh" in h["command"]
        }
        assert points == {"PreToolUse", "UserPromptSubmit"}

    def test_pretooluse_matcher_covers_the_real_work_tools(self):
        doc = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))
        matchers = [
            entry["matcher"]
            for entry in doc["hooks"]["PreToolUse"]
            for h in entry["hooks"]
            if "status-heartbeat.sh" in h["command"]
        ]
        assert matchers, "heartbeat not wired into PreToolUse"
        for tool in ("Bash", "Write", "Edit"):
            assert any(tool in m for m in matchers)
