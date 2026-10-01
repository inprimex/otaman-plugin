"""Hook-contract conformance suite (harness-version-management 2.1).

Seven shipped guards read the Claude Code PreToolUse payload. None of them
owns its shape, so an upstream change can disarm a guard with no change to our
code and nothing saying so. hvm pins the harness version; this is the suite a
candidate must pass before the fleet's pin moves (2.2 invokes it per
candidate).

THE DIRECTION MATTERS. `agent_id`/`agent_type` appear ONLY in a subagent call,
and `session_id` is identical for both — so `agent_id` presence is the only
fork-vs-main-thread signal. check-destructive-op.sh uses it to demand fresh
confirmation when a FORK runs `gh pr merge`.

If a candidate stops emitting agent_id for subagents, that guard answers
"main thread", the fork's merge is unchallenged, and otaman-plugin#24 walks
through. The opposite drift is noisy but safe. A suite asserting only "the
field is read" passes in BOTH cases, so these assert behaviour in both
directions.

`test_payload_contract_is_pinned` is named in check-destructive-op.sh's own
comment as the thing that would catch this. It did not exist until now.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from otaman_plugin.hook_contract import (
    CONSUMERS,
    NON_DISCRIMINATING_FIELDS,
    SUBAGENT_ONLY_FIELDS,
    harness_version,
    payload_json,
    reference_payload,
    verify_declarations,
)

REPO = Path(__file__).resolve().parent.parent
GUARD = REPO / "scripts" / "check-destructive-op.sh"


def _run_guard(payload: str, cwd: Path) -> dict | None:
    proc = subprocess.run(
        ["bash", str(GUARD)],
        input=payload,
        capture_output=True,
        text=True,
        timeout=20,
        cwd=str(cwd),
        env={"PATH": "/usr/bin:/bin", "HOME": str(cwd)},
    )
    out = proc.stdout.strip()
    return json.loads(out) if out else None


def _decision(parsed: dict | None) -> str | None:
    if not parsed:
        return None
    return parsed.get("hookSpecificOutput", {}).get("permissionDecision")


class TestPayloadContractIsPinned:
    """The test check-destructive-op.sh's comment has promised all along."""

    def test_subagent_fields_are_named_explicitly(self):
        assert SUBAGENT_ONLY_FIELDS == ("agent_id", "agent_type")

    def test_session_id_is_recorded_as_non_discriminating(self):
        """It is the field a reader reaches for first and must never use —
        identical for a fork and the main thread."""
        assert "session_id" in NON_DISCRIMINATING_FIELDS

    def test_the_two_reference_payloads_differ_only_in_the_subagent_fields(self):
        main = reference_payload(subagent=False)
        sub = reference_payload(subagent=True)
        assert set(sub) - set(main) == set(SUBAGENT_ONLY_FIELDS)
        assert main["session_id"] == sub["session_id"], "session_id must not distinguish them"

    def test_main_thread_payload_carries_no_subagent_fields(self):
        main = reference_payload(subagent=False)
        for field in SUBAGENT_ONLY_FIELDS:
            assert field not in main


class TestAgentIdBothDirections:
    """The reference test 2.1 asks for by name."""

    def test_a_FORK_merging_is_challenged(self, tmp_path):
        """ARMED direction. This is the one a candidate can silently break."""
        parsed = _run_guard(payload_json(subagent=True, command="gh pr merge 1 --squash"), tmp_path)
        assert _decision(parsed) == "ask", "a fork's merge was NOT challenged — guard disarmed"

    def test_the_MAIN_THREAD_merging_is_not_challenged(self, tmp_path):
        """The other direction. A guard that challenges everything gets turned
        off, and then it guards nothing — so over-firing is a failure too."""
        parsed = _run_guard(
            payload_json(subagent=False, command="gh pr merge 1 --squash"), tmp_path
        )
        assert _decision(parsed) != "ask", "main-thread merge was challenged — guard over-fires"

    def test_the_two_directions_actually_differ(self, tmp_path):
        """Guards the DISTINCTION rather than either side, so a change that
        collapses both into one answer fails here even if each assertion above
        could be satisfied some other way."""
        fork = _decision(_run_guard(payload_json(subagent=True, command="gh pr merge 1"), tmp_path))
        main = _decision(
            _run_guard(payload_json(subagent=False, command="gh pr merge 1"), tmp_path)
        )
        assert fork != main

    def test_agent_type_alone_also_identifies_a_fork(self, tmp_path):
        """The guard accepts either field. A candidate emitting only one must
        still be recognised."""
        payload = reference_payload(subagent=True, command="gh pr merge 1")
        del payload["agent_id"]
        assert _decision(_run_guard(json.dumps(payload), tmp_path)) == "ask"

    def test_an_empty_agent_id_is_not_a_fork(self, tmp_path):
        """`"agent_id": ""` must not read as a subagent — the guard requires a
        non-empty value, and a candidate emitting empty strings on the main
        thread would otherwise challenge every merge."""
        payload = reference_payload(subagent=False, command="gh pr merge 1")
        payload["agent_id"] = ""
        assert _decision(_run_guard(json.dumps(payload), tmp_path)) != "ask"


class TestDeclarationsMatchTheCode:
    def test_every_consumer_reads_what_it_declares(self):
        """Drift in either direction: a declaration naming a field the script
        stopped reading leaves the suite asserting a contract nobody depends
        on, green while the real dependency moved somewhere unwatched.

        This caught a wrong declaration of mine on its first run —
        check-blocked.sh was declared as reading tool_name when it reads only
        file_path and takes tool scoping from hooks.json's matcher.
        """
        bad = [r for r in verify_declarations(REPO) if not r.ok]
        assert not bad, [f"{r.consumer}: {r.reason}" for r in bad]

    def test_all_seven_consumers_are_covered(self):
        """The spec says seven. A consumer added without a declaration would
        depend on the payload with nothing checking it."""
        assert len(CONSUMERS) == 7

    def test_every_declared_consumer_exists(self):
        for consumer in CONSUMERS:
            assert (REPO / consumer.script).is_file(), consumer.script

    def test_the_destructive_guard_declares_the_subagent_fields(self):
        """It is the only consumer whose correctness DEPENDS on the
        discrimination, so losing them there is the disarming case."""
        guard = next(c for c in CONSUMERS if c.script.endswith("check-destructive-op.sh"))
        for field in SUBAGENT_ONLY_FIELDS:
            assert field in guard.requires
        assert "DISARM" in guard.note.upper()


class TestRunnableAgainstACandidate:
    """2.2 invokes this per candidate binary, so the suite must name what it
    tested — a report that does not say which binary it passed against would
    vouch for whatever happened to be installed."""

    def test_harness_version_is_reported(self):
        version = harness_version()
        assert version is None or version[0].isdigit()

    def test_an_absent_binary_is_none_not_a_crash(self):
        assert harness_version("no-such-harness-xyz") is None
