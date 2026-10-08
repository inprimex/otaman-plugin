#!/usr/bin/env python3
"""Map OpenSpec tasks to repo owners and generate bus notifications.

Reads tasks.md from an OpenSpec active feature directory, parses task items,
maps them to repo owners using ownership.json, and creates bus messages for
each assigned agent.

Usage:
    python map-tasks.py <path-to-tasks.md>
    python map-tasks.py <openspec-feature-dir>

Output:
    - JSON report to stdout with task-to-owner mapping
    - Bus message files created in .agents/bus/

Exit codes:
    0 — success
    1 — no tasks found or mapping failed
    2 — error (file not found, parse error)
"""

from __future__ import annotations

import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML is required. Install with: pip install pyyaml", file=sys.stderr)
    sys.exit(2)


from otaman_core._resolve import find_maestro_root as find_project_root  # shared resolver
from otaman_core.bus_stem import build_stem  # the ONE stem writer

# spec-gate-hardening 1.3(c): same slug shape otaman-core's validate_message
# enforces on x-gate-waived, so an invalid/malformed env value is dropped
# here rather than shipped as a message that fails validation downstream.
_GATE_WAIVED_SLUG = re.compile(r"^[a-z][a-z0-9-]*[a-z0-9]$")

#: A task line's repo annotation. Used ONLY to tell a DROP (annotated for a
#: repo that resolved to nobody — the haulops silence) from a line that is
#: legitimately nobody's. Owner resolution itself is `map_tasks_to_owners`;
#: this must not become a second implementation of it.
_ANNOTATION_RE = re.compile(r"@otaman-[a-z0-9-]+", re.IGNORECASE)


def _owner_map(entries: Any) -> dict[str, str]:
    """``{repo_name: owner}`` from a ``repos`` list, skipping disabled repos
    (archived/suspended) so tasks are never assigned to them."""
    if not isinstance(entries, list):
        return {}
    return {
        repo["name"]: repo["owner"]
        for repo in entries
        if isinstance(repo, dict)
        and repo.get("name")
        and repo.get("owner")
        and not repo.get("disabled", False)
    }


def load_ownership(project_root: Path) -> dict[str, str]:
    """Owner map from ``.agents/ownership.json``, falling back to
    ``platform.yaml`` ``repos[]``.

    The fallback is not cosmetic. This module replaced a second
    implementation (``scripts/map-tasks.py``) that read owners from
    platform.yaml and never looked at ownership.json, so a tree carrying only
    platform.yaml used to dispatch fine through the hook. Requiring
    ownership.json here would have quietly narrowed that while fixing the
    root-resolution bug — trading one silent dispatch failure for another.

    ownership.json still WINS when present: `otaman init` generates it, and it
    is the file that records `disabled` repos.
    """
    path = project_root / ".agents" / "ownership.json"
    if path.is_file():
        try:
            with open(path, encoding="utf-8") as f:
                owners = _owner_map(json.load(f).get("repos", []))
            if owners:
                return owners
        except (OSError, json.JSONDecodeError):
            pass  # fall through — a broken file should not kill dispatch
    return _owner_map(load_platform_config(project_root).get("repos", []))


def load_platform_config(project_root: Path) -> dict[str, Any]:
    """Load platform.yaml."""
    for name in ("platform.yaml", "platform.yml"):
        path = project_root / name
        if path.exists():
            with open(path, encoding="utf-8") as f:
                return yaml.safe_load(f)
    return {}


def parse_tasks_md(tasks_path: Path) -> list[dict[str, Any]]:
    """Parse a tasks.md file into structured task items.

    Supports formats:
    - [ ] Task description
    - [ ] Task description @repo-name
    - [ ] **repo-name**: Task description
    - Markdown headers as task groups
    """
    content = tasks_path.read_text(encoding="utf-8")
    tasks: list[dict[str, Any]] = []
    current_group = ""

    for line in content.splitlines():
        stripped = line.strip()

        # Track group headers
        header_match = re.match(r"^#{1,3}\s+(.+)", stripped)
        if header_match:
            current_group = header_match.group(1).strip()
            continue

        # Match task items: - [ ] or - [x]
        task_match = re.match(r"^-\s+\[([ xX])\]\s+(.+)", stripped)
        if not task_match:
            continue

        done = task_match.group(1).lower() == "x"
        task_text = task_match.group(2).strip()

        # Try to extract repo hint from @repo-name
        repo_hint = None
        at_match = re.search(r"@([\w-]+)\s*$", task_text)
        if at_match:
            repo_hint = at_match.group(1)
            task_text = task_text[: at_match.start()].strip()

        # Try to extract repo hint from **repo-name**: prefix
        bold_match = re.match(r"\*\*([\w-]+)\*\*:\s*(.+)", task_text)
        if bold_match:
            repo_hint = bold_match.group(1)
            task_text = bold_match.group(2).strip()

        tasks.append(
            {
                "text": task_text,
                "done": done,
                "group": current_group,
                "repo_hint": repo_hint,
            }
        )

    return tasks


def infer_repo_from_task(task_text: str, repo_names: list[str]) -> str | None:
    """Try to infer which repo a task belongs to from keywords in the task text."""
    text_lower = task_text.lower()
    for name in repo_names:
        if name.lower() in text_lower:
            return name
    # Common keyword heuristics
    frontend_keywords = {"ui", "component", "page", "frontend", "css", "layout", "view"}
    backend_keywords = {"endpoint", "api", "database", "migration", "model", "service", "handler"}
    if any(kw in text_lower for kw in frontend_keywords):
        for name in repo_names:
            if any(hint in name.lower() for hint in ("web", "frontend", "app", "ui")):
                return name
    if any(kw in text_lower for kw in backend_keywords):
        for name in repo_names:
            if any(hint in name.lower() for hint in ("api", "service", "backend", "server")):
                return name
    return None


def map_tasks_to_owners(
    tasks: list[dict[str, Any]],
    ownership: dict[str, str],
) -> list[dict[str, Any]]:
    """Map each task to a repo owner. Returns enriched task list."""
    repo_names = list(ownership.keys())
    for task in tasks:
        repo = task.get("repo_hint")
        if not repo:
            repo = infer_repo_from_task(task["text"], repo_names)
        task["repo"] = repo
        task["owner"] = ownership.get(repo, "") if repo else ""
    return tasks


# ---------------------------------------------------------------------------
# The tick-latency window (conformance, spec-agent 20260925T171639)
#
# `otaman complete` files a task-complete on the bus; spec-agent applies the
# tasks.md tick on their next session sweep. Between those two moments the file
# still reads `- [ ]`, so any specs push re-dispatches finished work.
#
# Measured: cli filed srf 1.3 complete at 11:52 and was re-assigned it twice by
# the 14:56/14:58 pushes. Three of my own completed tasks were re-dispatched the
# same way. cli had the context to recognise it; an agent with less would redo
# the work.
#
# Ruling: the bus filing is the authority DURING the window; tasks.md remains
# the durable record it syncs to. So dispatch consults the bus first.

# task-complete-reconciler 1.1 (core #85, 579e105): this reader used to live
# here. Core now owns it — task_id_of, filed_complete_at, filed_complete_ids,
# last_untick_at and is_effectively_complete, ported verbatim — so plugin's
# dispatch consult and cli's sweep/drift-count read ONE implementation. Two
# copies of a rule this subtle (a filing older than its task's most recent
# un-tick is stale evidence) drift apart exactly when it matters.
#
# Probed rather than imported hard: the installed bundle can lag the checkout,
# and a dispatcher must not become unimportable because core has not shipped
# yet. The degradation is loud and re-dispatches — see _consult_filed below.
try:
    from otaman_core.task_complete import (
        COMPLETED_ALL,
        filed_complete_at,
        is_effectively_complete,
        task_id_of,
    )

    _CORE_READER_ERROR: str | None = None
except ImportError as exc:  # pragma: no cover — laggard-bundle path
    COMPLETED_ALL = "*"
    filed_complete_at = None  # type: ignore[assignment]
    is_effectively_complete = None  # type: ignore[assignment]
    task_id_of = None  # type: ignore[assignment]
    _CORE_READER_ERROR = str(exc)


#: An assignment acked with this kind is one the recipient says is DONE.
#: Anything else — unacked, or acked `read` — is work in flight.
_ACK_TERMINAL = "resolved"


def _live_assignment_task_ids(
    project_root: Path, feature_name: str, config: dict[str, Any]
) -> tuple[dict[str, set[str]], list[str]]:
    """`{owner: {task-id, ...}}` already out on the bus and NOT yet resolved.

    THE SECOND SUPPRESSION SIGNAL (relayed from the pmeets tenant via deploy,
    20261008T091419). Until now a FILED COMPLETION was the only thing that
    stopped a re-dispatch, so a task that had been dispatched but not yet
    completed — the normal state of in-flight work — went out again on every
    subsequent tasks.md commit. Measured on otaman-dev: 357 dispatches across
    172 distinct (change, recipient) pairs, 185 re-emissions, 52% of all
    dispatch traffic, worst cases 7x.

    WHAT COUNTS AS LIVE. An assignment in the bus whose ack is absent or
    `read`. An ack of `read` means "seen, queued, in flight" — exactly the
    case that must not be duplicated. An assignment acked `resolved` is NOT
    live: the recipient says it is done, and if no completion was filed then
    the missing filing is the real defect and re-dispatch is how the fleet
    notices. Papering over that here would hide it.

    FAILS OPEN, loudly, like the filed-completion consult: an unreadable bus
    returns no suppressions and a problem string. Silently suppressing
    nothing is indistinguishable from a clean scan; silently suppressing
    everything would drop real assignments.
    """
    bus_rel = config.get("communication", {}).get("bus_path", ".agents/bus")
    active = project_root / bus_rel / "active"
    if not active.is_dir():
        # NOT a problem: an absent bus directory is a determinate answer —
        # nothing has ever been dispatched here, so nothing can be live. Only
        # an unreadable bus is indeterminate. Reporting this as a problem made
        # the could-not-consult warning fire on every first dispatch, which
        # test_available_reader_reports_no_problem correctly refused: "a
        # warning that is always on is a warning nobody reads."
        return {}, []

    live: dict[str, set[str]] = {}
    try:
        candidates = sorted(active.glob(f"*-otaman-to-*-tasks-{feature_name}.md"))
    except OSError as exc:
        return {}, [f"live-assignment consult SKIPPED — {type(exc).__name__}: {exc}"]

    for path in candidates:
        stem = path.name[: -len(".md")]
        # `...-otaman-to-<owner>-tasks-<feature>`
        try:
            owner = stem.split("-otaman-to-", 1)[1].rsplit(f"-tasks-{feature_name}", 1)[0]
        except IndexError:
            continue
        if not owner:
            continue
        ack = active / "acks" / f"{stem}.{owner}.ack"
        try:
            kind = ack.read_text(encoding="utf-8").strip().lower() if ack.is_file() else ""
        except OSError:
            kind = ""
        if _ACK_TERMINAL in kind:
            continue  # recipient says done — a missing filing is a different defect
        try:
            body = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for line in body.splitlines():
            stripped = line.lstrip()
            if not stripped.startswith("- ["):
                continue
            # core's task_id_of matches from the START of the text, so the
            # checkbox prefix has to go first — `_consult_filed` gets this for
            # free by passing the already-parsed task["text"]. Found by the
            # function returning {} against 20 live assignments.
            text = re.sub(r"^-\s*\[[^\]]*\]\s*", "", stripped)
            tid = task_id_of(text)
            if tid:
                live.setdefault(owner, set()).add(tid)
    return live, []


def _consult_filed(
    tasks: list[dict[str, Any]],
    tasks_path: Path,
    project_root: Path,
    feature_name: str,
    config: dict[str, Any],
) -> tuple[list[str], list[str], list[str], list[str]]:
    """Mark tasks already filed complete, or already live on the bus, as done.

    Returns ``(filed_complete, already_live, retracted, problems)`` — four
    OUTCOMES, never one summary. A task skipped because its filing stands, a
    task skipped because an unresolved assignment for it is already out, and a
    task re-dispatched because its filing was retracted are different events,
    and an operator reading only a count cannot tell them apart.

    `already_live` is the second suppression signal (pmeets via deploy,
    20261008T091419). A FILED completion used to be the only thing that
    suppressed a re-dispatch, so in-flight work — dispatched, not yet
    complete, which is the normal state — went out again on every tasks.md
    commit: 52% of all dispatch traffic on this tenant, worst cases 7x.

    When core's reader is unavailable the consult cannot run at all. It then
    re-dispatches everything and SAYS SO: silently skipping the consult looks
    identical to a clean run with nothing filed, which is the precise failure
    this whole mechanism exists to end.
    """
    if _CORE_READER_ERROR is not None:
        return [], [], [], [f"filed-completion consult SKIPPED — {_CORE_READER_ERROR}"]

    filed = filed_complete_at(project_root, feature_name, config)
    live, live_problems = _live_assignment_task_ids(project_root, feature_name, config)
    filed_complete: list[str] = []
    already_live: list[str] = []
    retracted: list[str] = []
    for task in tasks:
        if task["done"]:
            continue
        tid = task_id_of(task.get("text", ""))
        if not tid:
            continue
        if tid not in filed and COMPLETED_ALL not in filed:
            # Nothing filed. Before dispatching, is an unresolved assignment
            # for this exact (owner, task) already out? Re-sending it adds a
            # triage slot and no information.
            owner = task.get("owner")
            if owner and tid in live.get(owner, ()):
                task["done"] = True
                task["already_live"] = True
                already_live.append(task["text"])
            continue
        if not is_effectively_complete(tid, filed, tasks_path):
            # Filed, but the filing predates this task's most recent un-tick.
            # Un-ticking is how a retraction is expressed, so the evidence is
            # stale and the task goes back out rather than being cited forever.
            retracted.append(task["text"])
            continue
        task["done"] = True
        task["filed_complete"] = True
        filed_complete.append(task["text"])
    return filed_complete, already_live, retracted, live_problems


# ---------------------------------------------------------------------------
# The delivery authorization envelope, carried into the assignment (dae 2.3)


def envelope_block(tasks_path: Path) -> tuple[str, list[str]]:
    """The envelope section for an assignment, plus any loud problems.

    A delivering agent must know its action classes WITHOUT reading specs repo
    state — that is the whole point of carrying it. So dispatch resolves the
    change's `authorizes:` here and writes the answer into the message.

    Honesty over brevity: every registry class is `runtime-honored: limited`
    until cli 2.2 records a measured value, and a limited class AUTHORIZES
    NOTHING (design D6). Printing a declared class without that marker would
    tell an agent it may proceed unprompted when the runtime will still stop
    it — the envelope must never promise autonomy the runtime refuses.

    Returns `("", [problem, ...])` on a malformed envelope: nothing is carried,
    which authorizes nothing, and the problem is surfaced rather than swallowed.
    """
    problems: list[str] = []
    cfg_path = tasks_path.parent / ".openspec.yaml"
    if not cfg_path.is_file():
        return "", problems
    try:
        import yaml

        raw = (yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}).get("authorizes")
    except Exception as exc:  # noqa: BLE001 - unreadable config is a problem, not a crash
        return "", [f"could not read {cfg_path.name} for authorizes: {exc}"]
    if raw is None:
        return "", problems

    try:
        from otaman_core.delivery_envelope import (
            LIMITED,
            proceeds_without_prompt,
            runtime_honored,
            validate_envelope,
        )
    except Exception:
        return "", ["installed otaman-core has no delivery_envelope — envelope NOT carried"]

    try:
        env = validate_envelope(raw)
    except Exception as exc:  # noqa: BLE001 - EnvelopeError and anything malformed
        return "", [f"envelope refused, NOT carried (nothing is authorized): {exc}"]
    if not env:
        return "", problems

    lines = ["", "## Delivery authorization envelope", ""]
    lines.append(
        "Declared on this change and carried here so you do not have to read "
        "specs repo state. It expires when the change archives."
    )
    lines.append("")
    lines.append("| action class | scope | runtime-honored | proceeds unprompted |")
    lines.append("|---|---|---|---|")
    any_honored = False
    for cls in sorted(env):
        scope = env[cls]
        scope_txt = ", ".join(scope) if scope else "(every target)"
        marker = runtime_honored(cls) or "not in registry"
        # A scoped class answers differently per target, so ask about each one
        # rather than a representative: "proceeds" here means "for the scope as
        # declared", and a class that proceeds for none of its targets must not
        # read as if it proceeds.
        targets = scope if scope else [None]
        ok = any(proceeds_without_prompt(env, cls, target) for target in targets)
        any_honored = any_honored or ok
        lines.append(f"| `{cls}` | {scope_txt} | {marker} | {'yes' if ok else '**no**'} |")
    lines.append("")
    if not any_honored:
        lines.append(
            "**Nothing here proceeds unprompted.** Every class above is "
            f"`runtime-honored: {LIMITED}` — which authorizes nothing by declaration "
            "(design D6). The runtime still prompts, so these route to "
            "`decision-required` exactly like an undeclared action. Emit before you "
            "block."
        )
    lines.append(
        "Anything NOT listed above is outside every envelope: escalate via "
        "`decision-required` rather than freezing."
    )
    return "\n".join(lines) + "\n", problems


def create_bus_messages(
    project_root: Path,
    tasks: list[dict[str, Any]],
    feature_name: str,
    config: dict[str, Any],
    envelope_section: str = "",
) -> list[str]:
    """Create bus messages for each agent with their assigned tasks.

    spec-gate-hardening 1.3(c): when the dispatching `otaman assign` ran
    under an active gate waiver, it sets OTAMAN_GATE_WAIVED=<violation-slug>
    before calling into this module (in-process, per the agreed seam —
    map_tasks is the actual frontmatter emitter for dispatch assignments,
    cli's own code never writes these files directly). Every assignment
    created in that call carries `x-gate-waived: <slug>` so recipients can
    see the dispatch proceeded despite an unresolved gate violation. Absent
    or malformed env value (doesn't match the slug shape otaman-core's
    validate_message enforces) is silently treated as no active waiver —
    the normal case.
    """
    bus_rel = config.get("communication", {}).get("bus_path", ".agents/bus")
    active_dir = project_root / bus_rel / "active"
    active_dir.mkdir(parents=True, exist_ok=True)
    (active_dir / "acks").mkdir(exist_ok=True)

    gate_waived = os.environ.get("OTAMAN_GATE_WAIVED", "").strip()
    if gate_waived and not _GATE_WAIVED_SLUG.match(gate_waived):
        gate_waived = ""
    gate_waived_line = f"x-gate-waived: {gate_waived}\n" if gate_waived else ""

    # Group tasks by owner
    by_owner: dict[str, list[dict[str, Any]]] = defaultdict(list)
    unassigned: list[dict[str, Any]] = []
    for task in tasks:
        if task.get("owner"):
            by_owner[task["owner"]].append(task)
        else:
            unassigned.append(task)

    created: list[str] = []
    orchestrator_id = "otaman"
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    now_ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")

    for i, (owner, owner_tasks) in enumerate(sorted(by_owner.items())):
        pending_tasks = [t for t in owner_tasks if not t["done"]]
        if not pending_tasks:
            continue

        slug = feature_name.lower().replace(" ", "-")[:30]
        # Index suffix de-duplicates within THIS run when several agents are
        # assigned in the same second. It is in-process only: it cannot see a
        # second dispatcher, let alone a second workspace, which is exactly the
        # collision class JTBD-149 raises. Left as-is deliberately — widening
        # it is an identity decision (cofounder 20261001T210702: reserve the
        # field, defer the routing), not a local patch.
        ts = f"{now_ts}{i:02d}" if i > 0 else now_ts

        # Minted through core's single home, NOT hand-built. This was the last
        # writer bypassing `otaman_core.bus_stem.build_stem` — nine cli sites
        # and core already go through it. A uniqueness scheme added there would
        # silently have skipped dispatch assignments, so the single-home fix
        # would ship while the one writer that ignored it kept minting
        # colliding ids. Output is byte-identical to the previous hand-built
        # string, so this changes no filename anyone has already acked.
        stem = build_stem(
            timestamp=ts, sender=orchestrator_id, recipient=owner, slug=f"tasks-{slug}"
        )
        msg_id = f"{ts}-tasks-{slug}"
        filename = f"{stem}.md"

        task_lines = []
        for t in pending_tasks:
            repo_tag = f" ({t['repo']})" if t.get("repo") else ""
            task_lines.append(f"- [ ] {t['text']}{repo_tag}")

        content = f"""---
id: {msg_id}
from: {orchestrator_id}
to: {owner}
priority: normal
type: task-assignment
timestamp: {now_iso}
status: pending
{gate_waived_line}---

## Subject: Tasks assigned from "{feature_name}"

The following tasks from the feature "{feature_name}" are assigned to you:

{chr(10).join(task_lines)}

Please implement these in your owned repos and send a completion message when done.
{envelope_section}"""
        msg_path = active_dir / filename
        msg_path.write_text(content, encoding="utf-8")
        created.append(msg_path.relative_to(project_root).as_posix())

    return created


#: Prefix of the line emitted when a DECLARED gate could not be evaluated.
#: Exported so callers test the fact rather than re-deriving a substring.
GATE_NOT_EVALUATED = "[map-tasks] GATE NOT EVALUATED"


def check_dispatch_allowed(tasks_path: Path, config: dict[str, Any]) -> tuple[bool, list[str]]:
    """Consult the dispatch gate for the change owning *tasks_path*.

    Returns ``(may_dispatch, messages)``.

    spec-lifecycle-enforcement D5: dispatch requires stage >= ``spec-approved``;
    absent it, the configured enforcement MODE decides. This path never
    consulted the gate at all, so an authored change fanned out
    task-assignments the moment its folder was touched — spec-agent caught
    exactly that (20260922T194019) when PR #470 dispatched two authored
    changes.

    Worth being precise about cause: the gate was always missing here, but the
    path was DEAD until the root-resolution fix (#57) made hook-driven
    dispatch work. Fixing the dispatcher is what turned a latent ungated path
    into a live one.

    Honouring the mode rather than hard-refusing is deliberate. Under
    ``warn`` the dispatch proceeds and says so; hard-refusing would override a
    policy someone chose. Making refusal unconditional is a POLICY change
    (``enforcement: block``), not a conformance fix.

    Degrades to allow-with-no-message ONLY when the gate genuinely does not
    apply: core lacks the module (laggard bundle), or the change carries no
    ``.openspec.yaml``. A dispatcher must not be disarmed by either, and the
    read surfaces refuse loudly instead.

    A gate that is DECLARED but could not be evaluated is a third case, and
    conflating it with the two above cost real dispatches. On 2026-09-30 an
    unquoted colon in ``requested_by`` made ``.openspec.yaml`` unparseable;
    ``yaml.safe_load`` raised, one bare ``except`` swallowed it, and five
    agents received task-assignments for a change at stage ``authored`` with
    nothing printed.

    An unverifiable stage is treated as a VIOLATING one, honouring the mode:
    refused under ``block``, warned-and-proceeded under ``warn``. spec-agent
    named the asymmetry that settles the direction (20260930T084339) — the
    gate refused a READABLE ``authored`` stage while waving through an
    UNREADABLE one, which makes malforming the file a way past the gate. This
    is not the policy change I first took it for: under ``block`` a known-bad
    stage is already refused, so refusing an unknowable one changes no
    decision anybody configured. It only stops an unperformed check rendering
    as a passed one (no-silent-success clause 2).

    "No gate file" still means no gate is declared, and stays silent.
    """
    try:
        import yaml as _yaml  # noqa: F401 - kept for the laggard-bundle fallback below
        from otaman_core.spec_lifecycle import resolve_spec_policy
    except Exception:
        return True, []

    meta = tasks_path.parent / ".openspec.yaml"
    if not meta.is_file():
        return True, []

    try:
        program = config.get("spec_policy") if isinstance(config, dict) else None
        policy = resolve_spec_policy(program_block=program)
    except Exception:  # noqa: BLE001 - policy unreadable: cannot verify anything
        return False, [
            f"{GATE_NOT_EVALUATED} for {tasks_path.parent.name!r}: "
            "the enforcement policy itself could not be resolved.",
            "[map-tasks]   DISPATCH REFUSED: nothing about the stage can be verified.",
        ]

    # Single-home the read+gate in core (core #90). Its entry is the only place
    # that can tell an ABSENT .openspec.yaml from an UNPARSEABLE one — both
    # arrive as {} through the parsed-mapping form — and it hard-refuses the
    # unparseable case in EVERY mode.
    #
    # Mode-independence is the part I got wrong first time. I conditioned the
    # refusal on `block`, reasoning that refusing under `warn` would override a
    # policy someone chose. core-agent's correction (20260930T161820) settles
    # it: `warn` is the L1 DEFAULT, so a warn-mode consult that only fails
    # closed under block still waves an unreadable file through in the common
    # configuration — which is the sghc incident intact. And `warn` means
    # "tell me about a bad stage but proceed", not "proceed when the stage
    # cannot be read at all"; an inability to verify is not a policy violation
    # that a mode may downgrade (nss clause 2).
    try:
        from otaman_core.spec_lifecycle import check_dispatch_gate_at
    except ImportError:
        check_dispatch_gate_at = None  # type: ignore[assignment]

    unreadable = False
    stage = "<unset>"
    if check_dispatch_gate_at is not None:
        decision = check_dispatch_gate_at(meta, policy)
        try:
            from otaman_core.spec_lifecycle import openspec_is_unreadable, read_openspec

            unreadable = openspec_is_unreadable(meta)
            stage = (
                "<unreadable>" if unreadable else (read_openspec(meta).get("stage") or "<unset>")
            )
        except Exception:  # noqa: BLE001 - reporting detail only; the verdict stands
            stage = "<unknown>"
    else:
        # Laggard bundle: core predates #90. Reproduce its semantics locally
        # rather than degrading to the swallow this whole change removed.
        from otaman_core.spec_lifecycle import check_dispatch_gate

        try:
            change = _yaml.safe_load(meta.read_text(encoding="utf-8")) or {}
        except Exception as exc:  # noqa: BLE001 - unparseable: refuse, every mode
            return False, [
                f"{GATE_NOT_EVALUATED} for {tasks_path.parent.name!r}: {type(exc).__name__}: {exc}",
                "[map-tasks]   DISPATCH REFUSED: .openspec.yaml is present but could "
                "not be read, so the stage cannot be verified.",
                "[map-tasks]   Fix the file, or check the stage with "
                f"`otaman spec gate {tasks_path.parent.name} --at dispatch`.",
            ]
        decision = check_dispatch_gate(change, policy)
        stage = change.get("stage") or "<unset>"

    violations = list(getattr(decision, "violations", ()) or ())
    if not violations:
        return True, []

    # Loud either way: a gate that fires silently is the defect it exists to
    # prevent (no-silent-success clause 1 — say what was refused and why).
    verb = "DISPATCH REFUSED" if not decision.allowed else "DISPATCH WARNING"
    lines = [
        f"[map-tasks] {verb}: change {tasks_path.parent.name!r} is stage={stage}",
        *(f"[map-tasks]   - {v}" for v in violations),
    ]
    if unreadable:
        # An unverifiable stage is its own event, not just another violation:
        # say it could not be CHECKED, and name the command that answers it.
        lines.insert(
            0,
            f"{GATE_NOT_EVALUATED} for {tasks_path.parent.name!r}: "
            ".openspec.yaml is present but does not parse.",
        )
        lines.append(
            "[map-tasks]   Fix the file, or check the stage with "
            f"`otaman spec gate {tasks_path.parent.name} --at dispatch`."
        )
    if decision.allowed:
        lines.append(
            "[map-tasks]   dispatching anyway: spec_policy enforcement is "
            f"{getattr(decision, 'mode', 'warn')!r}. Set enforcement: block to refuse."
        )
    else:
        lines.append("[map-tasks]   no task-assignments were written.")
    return decision.allowed, lines


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: map-tasks.py <path-to-tasks.md or openspec-feature-dir>", file=sys.stderr)
        return 2

    target = Path(sys.argv[1]).resolve()

    # Determine tasks.md path
    if target.is_dir():
        tasks_path = target / "tasks.md"
        feature_name = target.name
    else:
        tasks_path = target
        feature_name = target.parent.name

    if not tasks_path.exists():
        print(f"ERROR: Tasks file not found: {tasks_path}", file=sys.stderr)
        return 2

    # Find project root
    project_root = find_project_root(tasks_path)
    if not project_root:
        # no-silent-success 1.2: "not found" and "found nothing to do" are
        # DISTINCT outcomes, with distinct exit codes. This also named the
        # wrong file — the resolver looks for the otaman root (platform.yaml
        # via the repo's .otaman marker), not ownership.json, and that
        # misdirection cost real debugging time on haulops.
        print(
            f"ERROR: no otaman root found from {tasks_path} — "
            "the repo needs an .otaman marker pointing at the otaman folder "
            "(the one holding platform.yaml). Nothing was dispatched.",
            file=sys.stderr,
        )
        return 3

    # Load data
    ownership = load_ownership(project_root)
    config = load_platform_config(project_root)

    # Dispatch gate (spec-lifecycle-enforcement D5) — BEFORE any bus write.
    may_dispatch, gate_lines = check_dispatch_allowed(tasks_path, config)
    for line in gate_lines:
        print(line, file=sys.stderr)
    if not may_dispatch:
        return 1
    # A dispatch that proceeded WITHOUT a stage check must be recoverable from
    # the report, not only from whoever was watching stderr at the time.
    gate_unevaluated = [ln for ln in gate_lines if ln.startswith(GATE_NOT_EVALUATED)]

    # Parse and map tasks
    tasks = parse_tasks_md(tasks_path)
    if not tasks:
        # Legitimate zero work — STATED, not disguised, and not an error:
        # a tasks.md with no checklist items is a valid thing to commit.
        print(f"0 dispatched: no checklist tasks in {tasks_path.name}", file=sys.stderr)
        print(
            json.dumps(
                {
                    "feature": feature_name,
                    "outcome": "no-tasks-in-file",
                    "total_tasks": 0,
                    "dispatched": 0,
                    "bus_messages_created": [],
                },
                indent=2,
            )
        )
        return 0

    tasks = map_tasks_to_owners(tasks, ownership)

    # Consult the bus BEFORE assigning: a task whose completion is already
    # filed is done for dispatch purposes, even though tasks.md has not been
    # swept yet. Never silent — the skipped ones are counted and named below,
    # and a consult that could not run at all reports itself as a problem.
    filed_complete, already_live, retracted, consult_problems = _consult_filed(
        tasks, tasks_path, project_root, feature_name, config
    )

    # A task ANNOTATED for a repo that did not resolve to an owner is a DROP,
    # not an absence: someone asked for it and nobody got it. An unannotated
    # line is legitimately nobody's and is not counted here. This is exactly
    # the haulops silence — @otaman-haulops-firmware resolved to nothing and
    # was skipped without a word.
    dropped = [
        t_["text"]
        for t_ in tasks
        if not t_.get("owner") and _ANNOTATION_RE.search(t_.get("text", ""))
    ]

    # Create bus messages
    envelope_section, envelope_problems = envelope_block(tasks_path)
    created = create_bus_messages(project_root, tasks, feature_name, config, envelope_section)

    # Build report
    report = {
        "feature": feature_name,
        "total_tasks": len(tasks),
        "assigned": sum(1 for t in tasks if t.get("owner")),
        "unassigned": sum(1 for t in tasks if not t.get("owner")),
        "done": sum(1 for t in tasks if t["done"]),
        "pending": sum(1 for t in tasks if not t["done"]),
        "by_owner": {},
        "unassigned_tasks": [t["text"] for t in tasks if not t.get("owner")],
        "bus_messages_created": created,
    }

    by_owner: dict[str, list[str]] = defaultdict(list)
    for t in tasks:
        if t.get("owner"):
            by_owner[t["owner"]].append(t["text"])
    report["by_owner"] = dict(by_owner)
    report["dispatched"] = len(created)
    report["dropped"] = len(dropped)
    report["dropped_tasks"] = dropped
    report["filed_complete"] = len(filed_complete)
    report["already_live"] = len(already_live)
    report["already_live_tasks"] = already_live
    report["filed_complete_tasks"] = filed_complete
    report["retracted"] = len(retracted)
    report["retracted_tasks"] = retracted
    report["envelope_carried"] = bool(envelope_section)
    report["envelope_problems"] = envelope_problems
    report["consult_problems"] = consult_problems
    report["gate_evaluated"] = not gate_unevaluated
    report["gate_problems"] = gate_unevaluated

    # Counts on every run, on stderr so they are visible even when stdout is
    # consumed as JSON. A verb that did work says what it did.
    print(
        f"{len(created)} dispatched to {len(report['by_owner'])} agent(s); "
        f"{report['assigned']} task(s) assigned, {report['dropped']} dropped, "
        f"{len(filed_complete)} filed-complete, skipped, "
        f"{len(already_live)} already live, skipped, "
        f"{len(retracted)} re-dispatched after retraction",
        file=sys.stderr,
    )
    # Named, not just counted: "3 skipped" leaves the reader unable to tell a
    # correct skip from a bug in the bus consult.
    for text in filed_complete:
        print(f"  filed-complete, not re-dispatched: {text[:90]}", file=sys.stderr)
    for text in already_live:
        print(
            f"  unresolved assignment already out, not re-dispatched: {text[:90]}",
            file=sys.stderr,
        )
    for text in retracted:
        print(f"  retracted since filing, re-dispatched: {text[:90]}", file=sys.stderr)
    # A refused envelope must never be silent: the assignment then carries no
    # authorization at all, and the delivering agent needs to know that is why.
    for problem in envelope_problems:
        print(f"  envelope: {problem}", file=sys.stderr)
    # A consult that could not run is NOT a run that found nothing filed. Both
    # dispatch every task; only one of them is correct, so the line has to say
    # which happened.
    for problem in consult_problems:
        print(f"  WARNING: {problem}", file=sys.stderr)
        print(
            "  Every task was re-dispatched without checking the bus — "
            "already-filed work may be assigned again.",
            file=sys.stderr,
        )

    if dropped:
        # A drop is an error, not a silent omission (delta, scenario 1).
        report["outcome"] = "drops"
        print(
            f"ERROR: {len(dropped)} task(s) carry an @otaman-<repo> annotation that "
            "resolved to no owner — they were NOT dispatched:",
            file=sys.stderr,
        )
        for text in dropped:
            print(f"  - {text}", file=sys.stderr)
        print(
            "Check that each annotated repo appears in platform.yaml repos[] with an owner.",
            file=sys.stderr,
        )
        print(json.dumps(report, indent=2))
        return 5

    if not created:
        # Tasks existed, none were for anyone here. Stated, not disguised.
        report["outcome"] = "nothing-to-dispatch"
        print(
            f"0 dispatched: none of the {len(tasks)} task(s) are annotated for a known repo",
            file=sys.stderr,
        )
        print(json.dumps(report, indent=2))
        return 0

    report["outcome"] = "dispatched"
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
