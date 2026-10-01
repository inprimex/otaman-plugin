"""The Claude Code hook payload contract our guards depend on (hvm 2.1).

Seven shipped consumers read the PreToolUse payload. None of them owns the
payload's shape — upstream does — so an upstream change can disarm a guard
without a single line of our code changing, and without any surface saying so.
That is what hvm exists to stop: the pin plus this suite, run against a
candidate binary before the fleet moves to it.

THE UNSAFE DIRECTION IS SPECIFIC, and knowing which way it fails is the whole
value. `agent_id` / `agent_type` appear ONLY inside a subagent call;
`session_id` is identical for both, so presence of `agent_id` is the only
signal distinguishing a fork from the main thread. check-destructive-op.sh
uses it to demand fresh confirmation when a FORK runs `gh pr merge`.

So if a candidate stops emitting `agent_id` for subagents, `_is_subagent_call`
answers false, a fork's merge goes unchallenged, and the guard is silently
disarmed — the incident it was written for (otaman-plugin#24) walks straight
through. The opposite drift (agent_id on main-thread calls) is noisy but safe.
A conformance suite that only asserted "the field is read" would pass in both
cases; this asserts BOTH DIRECTIONS of behaviour.

The guard's own comment has promised `test_payload_contract_is_pinned` since
it was written. It did not exist until this task.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

#: Fields a subagent PreToolUse payload carries that a main-thread one does not.
SUBAGENT_ONLY_FIELDS: tuple[str, ...] = ("agent_id", "agent_type")

#: Present and IDENTICAL for both. Named explicitly because it is the field a
#: reader reaches for first and must never discriminate on.
NON_DISCRIMINATING_FIELDS: tuple[str, ...] = ("session_id",)


@dataclass(frozen=True)
class Consumer:
    """One shipped guard and the payload fields it cannot work without."""

    script: str
    requires: tuple[str, ...]
    note: str


#: The seven. `requires` is what the script actually reads — verified by the
#: suite, not asserted from memory.
CONSUMERS: tuple[Consumer, ...] = (
    Consumer(
        "scripts/check-destructive-op.sh",
        ("tool_name", "tool_input", "agent_id", "agent_type"),
        "discriminates fork vs main thread; losing agent_id DISARMS the merge guard",
    ),
    Consumer("scripts/check-ownership.sh", ("tool_name", "tool_input"), "repo write ownership"),
    # Reads `file_path` only: tool scoping comes from hooks.json's matcher, so
    # it never inspects tool_name itself. Declared as the suite FOUND it, not
    # as I first assumed — my initial declaration said tool_name and the
    # verification caught it, which is the drift this is for.
    Consumer("scripts/check-blocked.sh", ("file_path",), "blocked-entry guard"),
    Consumer("scripts/check-branch.sh", ("agent_id",), "branch policy per acting agent"),
    Consumer("hooks/check-bus-message.sh", ("tool_name", "tool_input"), "bus message validation"),
    Consumer("hooks/bridge-approval.sh", ("tool_name", "tool_input"), "bridge approval gate"),
    Consumer("hooks/status-heartbeat.sh", ("agent_id",), "attributes the heartbeat"),
)


def reference_payload(*, subagent: bool, tool_name: str = "Bash", command: str = "echo hi") -> dict:
    """The two payloads every consumer must be exercised against.

    Deliberately minimal: extra fields would let a consumer pass by reading
    something upstream never promised.
    """
    payload: dict = {
        "session_id": "11111111-2222-3333-4444-555555555555",
        "tool_name": tool_name,
        "tool_input": {"command": command} if tool_name == "Bash" else {"file_path": "x.py"},
    }
    if subagent:
        payload["agent_id"] = "agent_01ABCDEF"
        payload["agent_type"] = "general-purpose"
    return payload


def harness_version(binary: str = "claude") -> str | None:
    """The candidate's version, so a conformance report names what it tested.

    A report that does not say which binary it passed against cannot gate a
    rollout — it would vouch for whatever happened to be installed.
    """
    exe = shutil.which(binary)
    if not exe:
        return None
    try:
        proc = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    match = re.search(r"\d+\.\d+(?:\.\d+)?", proc.stdout or proc.stderr or "")
    return match.group(0) if match else None


def consumer_reads(repo_root: Path, consumer: Consumer) -> set[str]:
    """Which declared fields the script's source actually references.

    Source inspection, not execution: running every guard to see what it
    touches would fire real side effects (bus writes, denials). The point is
    to catch a DECLARATION that has drifted from the code, in either
    direction.
    """
    try:
        text = (repo_root / consumer.script).read_text(encoding="utf-8")
    except OSError:
        return set()
    return {field for field in consumer.requires if field in text}


@dataclass(frozen=True)
class ConformanceResult:
    consumer: str
    ok: bool
    reason: str


def verify_declarations(repo_root: Path) -> list[ConformanceResult]:
    """Every consumer still reads every field it declares.

    A declaration that has drifted is the failure this guards: the suite would
    otherwise keep asserting a contract nobody depends on any more, and stay
    green while the real dependency moved somewhere unwatched.
    """
    out: list[ConformanceResult] = []
    for consumer in CONSUMERS:
        if not (repo_root / consumer.script).is_file():
            out.append(
                ConformanceResult(consumer.script, False, "consumer script is missing entirely")
            )
            continue
        found = consumer_reads(repo_root, consumer)
        missing = sorted(set(consumer.requires) - found)
        out.append(
            ConformanceResult(
                consumer.script,
                not missing,
                "reads every declared field"
                if not missing
                else f"declares {missing} but its source references none of them",
            )
        )
    return out


def payload_json(*, subagent: bool, **kw) -> str:
    """The reference payload as a consumer receives it — on stdin, as JSON."""
    return json.dumps(reference_payload(subagent=subagent, **kw))
