"""SessionStart drain: the specs owner's session applies its own backlog.

task-complete-reconciler 2.1. `otaman complete` files a task-complete on the
bus; only the specs owner's edit to tasks.md survives the next
`git pull --ff-only`, so every non-owner filing waits for that owner to
reconcile. Nothing made them. The measured cost (reconciler proposal): ~2 weeks
of unapplied completes on pmeets, the lens reporting 5/11 against a real 11/11,
and no surface saying so.

D2 — the hook drains, the verb is the engine. Everything testable lives in
`otaman spec sweep` (cli 1.2), runnable by hand on any tenant, from cron, or
from here. This module holds only what the hook must decide before calling it:
whether THIS agent is the specs owner, and how to report an outcome honestly.

The owner gate is not a safety mechanism — core's `actualize_tasks` already
refuses a non-owner's write. It exists so 16 agents do not each sweep every
change on every session start for a write only one of them can perform.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

#: Verdicts. Each is a DIFFERENT event and must stay distinguishable — a drain
#: that found nothing owed and a drain that could not run both print no ticks,
#: and only one of them is fine. That conflation is the failure this change
#: exists to end, so reproducing it here would be a poor joke.
DRAINED = "drained"
NOTHING_OWED = "nothing-owed"
NOT_OWNER = "skipped-not-owner"
NO_OWNER_RESOLVED = "not-checked-no-owner-resolved"
SWEEP_UNAVAILABLE = "not-checked-sweep-unavailable"
NO_CLI = "not-checked-no-otaman-on-path"
FAILED = "failed"

#: Verdicts that mean the drain did NOT happen and nobody should read the
#: absence of ticks as "nothing was owed".
NOT_CHECKED = (NO_OWNER_RESOLVED, SWEEP_UNAVAILABLE, NO_CLI)

SWEEP_TIMEOUT_S = 120


@dataclass(frozen=True)
class DrainResult:
    verdict: str
    reason: str
    output: str = ""

    @property
    def performed(self) -> bool:
        """Did the sweep actually run? `not-checked` is not a pass."""
        return self.verdict in (DRAINED, NOTHING_OWED, FAILED)


def resolve_specs_owner(config: dict[str, Any]) -> str | None:
    """The agent owning the specs repo, from `specs.path` -> that repo's owner.

    Returns None rather than guessing. A hardcoded "spec-agent" would send a
    program whose specs live elsewhere to an agent absent from its fleet, and
    the drain would then be permanently skipped for everyone — silently,
    because "not the owner" is an ordinary outcome.
    """
    specs = config.get("specs")
    if not isinstance(specs, dict):
        return None
    path = specs.get("path")
    if not path:
        return None
    for repo in config.get("repos", []) or []:
        if isinstance(repo, dict) and repo.get("path") == path and repo.get("owner"):
            return str(repo["owner"])
    return None


def sweep_supported(otaman: str) -> bool:
    """Does the INSTALLED cli carry `spec sweep` (cli 1.2)?

    The bundle lags the checkout by design, so an installed `otaman` without
    the subcommand is expected, not broken. Probing `otaman spec` and reading
    its action list beats parsing a version: the question is whether the verb
    is there, and that is what this asks.
    """
    try:
        proc = subprocess.run([otaman, "spec"], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return False
    return "sweep" in (proc.stdout + proc.stderr)


def drain(agent: str | None, config: dict[str, Any], cwd: Path) -> DrainResult:
    """Apply this tenant's owed ticks, if this agent is the one who may.

    Returns a verdict for every path. Nothing here returns silence: a caller
    that cannot tell "nothing owed" from "could not run" reproduces the exact
    blindness the reconciler was built to remove.
    """
    owner = resolve_specs_owner(config)
    if owner is None:
        return DrainResult(
            NO_OWNER_RESOLVED,
            "no specs owner resolved from platform.yaml (specs.path matches no repo with an "
            "owner) — the drain cannot know whether it should run",
        )

    if agent != owner:
        return DrainResult(NOT_OWNER, f"this agent is {agent!r}, specs owner is {owner!r}")

    otaman = shutil.which("otaman")
    if not otaman:
        return DrainResult(NO_CLI, "no `otaman` on PATH — the drain could not run")

    if not sweep_supported(otaman):
        return DrainResult(
            SWEEP_UNAVAILABLE,
            "the installed otaman has no `spec sweep` (cli 1.2 not in this bundle) — "
            "filed ticks are NOT being applied; run `otaman upgrade`",
        )

    env = {**os.environ, "OTAMAN_AGENT": owner}
    try:
        proc = subprocess.run(
            [otaman, "spec", "sweep", "--apply"],
            capture_output=True,
            text=True,
            timeout=SWEEP_TIMEOUT_S,
            cwd=str(cwd),
            env=env,
        )
    except subprocess.TimeoutExpired:
        return DrainResult(FAILED, f"`otaman spec sweep --apply` exceeded {SWEEP_TIMEOUT_S}s")
    except (OSError, subprocess.SubprocessError) as exc:
        return DrainResult(FAILED, f"`otaman spec sweep --apply` could not run: {exc}")

    out = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0:
        return DrainResult(FAILED, f"`otaman spec sweep --apply` exited {proc.returncode}", out)
    if "Nothing owed" in out:
        return DrainResult(NOTHING_OWED, "every filed tick was already applied", out)
    return DrainResult(DRAINED, "applied the filed ticks", out)
