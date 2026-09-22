"""status-heartbeat gate 2.1 assertion 1 — the *clean test*: a session with
hooks running stays fresh past the TTL, and does so BECAUSE of the hook.

Why this file exists rather than "the hook has unit tests already": two
earlier attempts to observe the hook on the live fleet were thrown out, and
neither failed because the hook was broken.

1. Every long-running session predated the 2026-09-22T14:14Z hook sync, so
   none of them had the hook loaded at all.
2. cofounder-agent re-armed a fixture and saw `updated_at` move — but the
   movement was written by `otaman ack`, not by the hook. Acking a
   task-assignment auto-writes a `working` record (agent-status-presence 1.6,
   otaman-cli `commands/bus_messaging.py:900`). The observation was real; the
   attribution was wrong.

So the thing under test is not "does the hook write a timestamp" (covered in
test_status_heartbeat_hook.py) but "is the hook the *cause* of the movement".
That is an attribution claim, and an attribution claim needs both directions —
no-silent-success clause 3. A positive arm alone cannot distinguish the hook
from any other writer that happens to touch the file on the same schedule,
which is precisely the mistake that voided attempt 2.

Both arms run in one sandbox that contains NO otaman CLI, NO bus, and no
writer of any kind except the hook itself, so "everything else held constant"
is a property of the fixture rather than a promise in a comment.

THE NEGATIVE ARM'S OWN TRAP. cli hit this on a different change: they
"disabled" a component, saw nothing happen, and recorded a null result — but
the component had never actually been disabled, so the null proved nothing. A
negative arm is only evidence if the disabled state is *verified* disabled.
Asserting "no movement" is not that verification; a typo'd path produces the
same silence as a correctly disabled hook. So `test_disabled_arm_really_is_
disabled` asserts the invocation genuinely fails to execute BEFORE any arm
trusts a null result.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

REPO = Path(__file__).parent.parent
HOOK = REPO / "hooks" / "status-heartbeat.sh"

HAVE_BASH = shutil.which("bash") is not None
pytestmark = pytest.mark.skipif(not HAVE_BASH, reason="bash not on PATH")

# Compresses the hook's 300s production throttle so a test can cross it.
# The interval is the only thing scaled — the code path taken is identical.
TEST_INTERVAL = "1"

SINCE = "2026-09-22T22:28:23Z"
BASELINE_UPDATED = "2026-09-22T22:28:24Z"


@pytest.fixture(autouse=True)
def _unpin_root(monkeypatch):
    # bus-test-isolation 4.2 pins OTAMAN_ROOT for the whole suite; this fixture
    # resolves a root from scratch through the `.otaman` marker, so the pin has
    # to come off — and off the subprocess env too (see _fire).
    monkeypatch.delenv("OTAMAN_ROOT", raising=False)
    monkeypatch.delenv("MAESTRO_ROOT", raising=False)


def _sandbox(tmp_path: Path, *, state: str = "working") -> tuple[Path, Path]:
    """A fleet with exactly one status record and no other writer in it."""
    meta = tmp_path / "meta"
    (meta / ".agents" / "status").mkdir(parents=True)
    (meta / ".agents" / "status" / "plugin-agent.yaml").write_text(
        "agent: plugin-agent\n"
        f"state: {state}\n"
        "task: null\n"
        "change: null\n"
        f"since: '{SINCE}'\n"
        f"updated_at: '{BASELINE_UPDATED}'\n",
        encoding="utf-8",
    )

    repo = tmp_path / "repo"
    repo.mkdir()
    # Bare relative-path line + `agent:` — the marker format the resolver
    # actually parses. An `otaman_root:` key is NOT read.
    (repo / ".otaman").write_text("../meta\nagent: plugin-agent\n", encoding="utf-8")
    # The hook sniffs identity out of CLAUDE.md with a single sed, avoiding a
    # python3 spawn on the per-tool-call path.
    (repo / "CLAUDE.md").write_text(
        "You are `plugin-agent`. You own this repo.\n", encoding="utf-8"
    )
    return meta, repo


def _status(meta: Path) -> dict[str, str]:
    out = {}
    for line in (meta / ".agents" / "status" / "plugin-agent.yaml").read_text().splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            out[k.strip()] = v.strip().strip("'\"")
    return out


def _fire(hook: Path, repo: Path, home: Path) -> subprocess.CompletedProcess:
    """One PreToolUse firing: event JSON on stdin, exactly as Claude Code sends."""
    env = {
        **os.environ,
        "HOME": str(home),  # the resolver rejects a marker resolving outside $HOME
        "OTAMAN_HEARTBEAT_INTERVAL": TEST_INTERVAL,
    }
    env.pop("OTAMAN_ROOT", None)
    env.pop("MAESTRO_ROOT", None)
    return subprocess.run(
        ["bash", str(hook)],
        input=f'{{"cwd": "{repo}", "tool_name": "Bash"}}',
        cwd=repo,
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
    )


class TestDisabledArmIsVerifiablyDisabled:
    """Runs FIRST by file order, and deliberately so: nothing below may trust a
    null result until the disabled state has been shown to be real."""

    def test_disabled_arm_really_is_disabled(self, tmp_path):
        """cli's trap: a null result from a component that was never actually
        off. Prove non-execution directly instead of inferring it from silence.
        """
        _, repo = _sandbox(tmp_path)
        absent = REPO / "hooks" / "status-heartbeat.sh.DISABLED-FOR-TEST"
        assert not absent.exists(), "the 'disabled' path must genuinely not exist"

        r = _fire(absent, repo, tmp_path)
        # bash could not run it at all. This is the assertion that makes the
        # negative arm mean something: silence WITH a nonzero exit is a hook
        # that did not run; silence with exit 0 would be a hook that ran and
        # chose to do nothing — a completely different claim.
        assert r.returncode != 0, "a 'disabled' hook that still exits 0 was never disabled"


class TestNegativeArm:
    def test_no_movement_when_the_hook_does_not_run(self, tmp_path):
        """Same sandbox, same elapsed time, same everything — minus the hook."""
        meta, repo = _sandbox(tmp_path)
        before = _status(meta)

        absent = REPO / "hooks" / "status-heartbeat.sh.DISABLED-FOR-TEST"
        for _ in range(4):
            _fire(absent, repo, tmp_path)
            time.sleep(0.4)

        after = _status(meta)
        assert after["updated_at"] == before["updated_at"] == BASELINE_UPDATED, (
            "something OTHER than the hook moved updated_at — the sandbox is not "
            "clean and the positive arm's attribution would be worthless"
        )


class TestPositiveArm:
    def test_updated_at_advances_past_since(self, tmp_path):
        """The gate's actual wording: the record stays fresh while the session
        lives. `since` frozen + `updated_at` advancing is what 'fresh without
        restating the claim' looks like on disk."""
        meta, repo = _sandbox(tmp_path)

        r = _fire(HOOK, repo, tmp_path)
        assert r.returncode == 0, r.stderr
        # Throttled on the first firing (file mtime is ~now), so cross it.
        time.sleep(1.2)
        r = _fire(HOOK, repo, tmp_path)
        assert r.returncode == 0, r.stderr

        after = _status(meta)
        assert after["updated_at"] != BASELINE_UPDATED, "the hook did not refresh the record"
        assert after["since"] == SINCE, "the heartbeat must never restate the claim"
        assert after["state"] == "working", "the heartbeat must never change state"

    def test_the_hook_is_the_only_difference_between_the_arms(self, tmp_path):
        """The two arms side by side in one test, so the comparison cannot
        drift apart as the file is edited."""
        meta_off, repo_off = _sandbox(tmp_path / "off")
        meta_on, repo_on = _sandbox(tmp_path / "on")
        absent = REPO / "hooks" / "status-heartbeat.sh.DISABLED-FOR-TEST"

        for _ in range(3):
            _fire(absent, repo_off, tmp_path / "off")
            _fire(HOOK, repo_on, tmp_path / "on")
            time.sleep(0.6)

        assert _status(meta_off)["updated_at"] == BASELINE_UPDATED
        assert _status(meta_on)["updated_at"] != BASELINE_UPDATED


class TestScopeHoldsUnderTheCleanTest:
    """The freshness claim must not leak into states that never make it.
    `idle`/`blocked` are never rendered STALE, and `human`/`afk` is a
    deliberate long-lived state that must not be made to look like a live
    session — heartbeating any of them would manufacture false liveness."""

    @pytest.mark.parametrize("state", ["idle", "blocked", "human", "afk"])
    def test_ineligible_states_are_not_refreshed(self, tmp_path, state):
        meta, repo = _sandbox(tmp_path, state=state)
        for _ in range(3):
            _fire(HOOK, repo, tmp_path)
            time.sleep(0.5)
        assert _status(meta)["updated_at"] == BASELINE_UPDATED, (
            f"state {state!r} is not heartbeat-eligible but was refreshed anyway"
        )
