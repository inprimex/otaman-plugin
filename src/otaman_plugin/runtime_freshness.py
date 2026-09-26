"""Runtime freshness — is the thing actually RUNNING the thing on disk?

session-runtime-freshness 1.1 (checks 1-3). Check 4, installed-vs-source
skew, is 1.2 and lands alongside these under the same vocabulary.

Every doctor check before this one inspects files. That is why the fleet's
2026-09-17 incident was invisible: thirteen sessions booted at 15:5xZ, the
vendored plugin tree's `hooks.json` was rewritten five days later, and every
artifact on disk was correct the whole time. `otaman doctor` was green while
no running session had the heartbeat hook. Proving it required reading
process start times against file mtimes by hand.

This module is the SINGLE computation behind both the doctor section and
cli's console session view (task 1.3, single-home — there is deliberately no
second checker). It returns structured `Finding`s; the doctor wrapper maps
them to `DoctorWarning`s and the console renders the same verdicts.

DESIGN CONSTRAINTS, from the approved delta:

* **D1 — detection, never enforcement.** Restarting a stale session destroys
  conversation context and in-progress work. Every finding names a remedy;
  nothing here performs one.
* **D3 — the wiring-vs-script boundary is part of the truth.** Hook SCRIPT
  bodies are read by bash at invocation, so editing one never makes a session
  stale. Only inputs snapshotted at session start count: `hooks.json` wiring,
  argv, env, bootstrap config. A checker that flagged script edits would cry
  wolf within a day and teach operators to skip the section — the exact
  failure this change exists to remove.
* **D4 — argv comparison outranks timestamps.** A missing flag is definitive:
  no clock skew, no touch-without-change false positive, and it names what is
  absent. Timestamps are for inputs that never reach argv.
* **not-checked is loud** (nss clause 2). A subject the checker could not
  inspect never renders fresh and is never silently dropped.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

Verdict = Literal["fresh", "stale", "skewed", "halted", "not-checked"]

#: Only these inputs are snapshotted when a session starts. Hook SCRIPT bodies
#: are deliberately absent — see D3; they are read at invocation and are live.
SESSION_SNAPSHOT_INPUTS = ("platform.yaml", "hooks/hooks.json")

_PLUGIN_DIR_RE = re.compile(r"--plugin-dir[=\s]+(\S+)")
_CLAUDE_RE = re.compile(r"(^|/)claude(\s|$)")

#: Runner /status is a local read surface; a hung daemon must not hang doctor.
_HTTP_TIMEOUT_S = 2.0


@dataclass(frozen=True)
class Finding:
    """One freshness verdict about one runtime subject.

    `evidence` carries the raw values the verdict was computed from, so the
    console and a gate record can show the same numbers without recomputing
    them — and so a disputed verdict can be checked rather than re-derived.
    """

    subject: str
    check: str
    verdict: Verdict
    reason: str
    remedy: str | None = None
    evidence: dict[str, Any] | None = None

    @property
    def ok(self) -> bool:
        return self.verdict == "fresh"


# ---------------------------------------------------------------------------
# process inspection (Linux /proc fast path, ps fallback — cli acting_guard's
# idiom, kept identical so the two cannot drift on what counts as a session)


def _proc_start_epoch(pid: int) -> float | None:
    """Wall-clock start time of `pid`, or None if it cannot be determined."""
    try:
        st = os.stat(f"/proc/{pid}")
        return float(st.st_ctime)
    except (OSError, ValueError):
        pass
    if not shutil.which("ps"):
        return None
    try:
        r = subprocess.run(
            ["ps", "-o", "lstart=", "-p", str(pid)],
            capture_output=True,
            text=True,
            timeout=5,
        )
        raw = r.stdout.strip()
        if not raw:
            return None
        return datetime.strptime(raw, "%a %b %d %H:%M:%S %Y").timestamp()
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def _proc_argv(pid: int) -> str | None:
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as fh:
            return fh.read().replace(b"\0", b" ").decode("utf-8", "replace").strip()
    except OSError:
        pass
    if not shutil.which("ps"):
        return None
    try:
        r = subprocess.run(
            ["ps", "-o", "args=", "-p", str(pid)], capture_output=True, text=True, timeout=5
        )
        return r.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def _proc_cwd(pid: int) -> Path | None:
    try:
        return Path(os.readlink(f"/proc/{pid}/cwd"))
    except OSError:
        return None


def _program_repo_dirs(otaman_root: Path) -> list[Path]:
    """Resolved on-disk paths of the repos this otaman root declares.

    Used to scope session discovery to THIS program. A host can run several
    programs' fleets at once, and a doctor run for one must not report the
    other's sessions — it would name subjects the operator cannot act on from
    here, and would make the check's output depend on who else is logged in.
    """
    from otaman_plugin.doctor_checks import _load_yaml

    cfg = _load_yaml(otaman_root / "platform.yaml")
    out: list[Path] = []
    for repo in (cfg.get("repos") or []) if isinstance(cfg, dict) else []:
        path = (repo or {}).get("path") if isinstance(repo, dict) else None
        if not path:
            continue
        try:
            out.append((otaman_root / str(path)).resolve())
        except OSError:
            continue
    return out


def _agent_pids() -> list[int] | None:
    """PIDs of running `claude` sessions launched with a plugin dir.

    Returns None — not [] — when the platform cannot be enumerated at all.
    The distinction is the whole point: "no sessions running" and "I could not
    look" must not render the same.
    """
    if not shutil.which("pgrep"):
        return None
    try:
        r = subprocess.run(
            ["pgrep", "-u", str(os.getuid()), "-f", "claude"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    pids: list[int] = []
    for line in r.stdout.split():
        try:
            pid = int(line)
        except ValueError:
            continue
        argv = _proc_argv(pid) or ""
        if _CLAUDE_RE.search(argv) and "--plugin-dir" in argv:
            pids.append(pid)
    return pids


def _not_checked(subject: str, check: str, reason: str) -> Finding:
    return Finding(
        subject=subject,
        check=check,
        verdict="not-checked",
        reason=reason,
        remedy="This is 'could not check', not 'checked clean'.",
    )


def _iso(epoch: float | None) -> str | None:
    if epoch is None:
        return None
    return datetime.fromtimestamp(epoch, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# check 1 — session vs the inputs snapshotted at its start


def _snapshot_inputs(otaman_root: Path, plugin_dir: str | None) -> list[tuple[str, float]]:
    """(label, mtime) for each input a session captures when it starts.

    Deliberately NOT hook script bodies (D3). `hooks.json` is the wiring, and
    wiring is what Claude Code reads once at startup.
    """
    out: list[tuple[str, float]] = []
    pf = otaman_root / "platform.yaml"
    if pf.is_file():
        out.append((str(pf), pf.stat().st_mtime))
    if plugin_dir:
        hooks = Path(plugin_dir).expanduser() / "hooks" / "hooks.json"
        if hooks.is_file():
            out.append((str(hooks), hooks.stat().st_mtime))
    return out


def _sessions_for(otaman_root: Path) -> list[int] | None:
    """Agent sessions belonging to THIS program, or None if unenumerable."""
    pids = _agent_pids()
    if pids is None:
        return None
    repos = _program_repo_dirs(otaman_root)
    if not repos:
        return []
    scoped: list[int] = []
    for pid in pids:
        cwd = _proc_cwd(pid)
        if cwd is None:
            continue
        try:
            resolved = cwd.resolve()
        except OSError:
            continue
        if any(resolved == r or r in resolved.parents for r in repos):
            scoped.append(pid)
    return scoped


def check_sessions_vs_inputs(otaman_root: Path) -> list[Finding]:
    pids = _sessions_for(otaman_root)
    if pids is None:
        return [
            _not_checked(
                "agent sessions",
                "session-inputs",
                "cannot enumerate processes on this platform (no pgrep/ps)",
            )
        ]
    if not pids:
        return []

    out: list[Finding] = []
    for pid in sorted(pids):
        subject = f"session pid {pid}"
        started = _proc_start_epoch(pid)
        if started is None:
            out.append(
                _not_checked(subject, "session-inputs", f"could not read start time for pid {pid}")
            )
            continue
        argv = _proc_argv(pid) or ""
        m = _PLUGIN_DIR_RE.search(argv)
        inputs = _snapshot_inputs(otaman_root, m.group(1) if m else None)
        if not inputs:
            out.append(
                _not_checked(
                    subject, "session-inputs", "no snapshotted inputs found to compare against"
                )
            )
            continue

        newer = [(label, mt) for label, mt in inputs if mt > started]
        if not newer:
            out.append(
                Finding(
                    subject=subject,
                    check="session-inputs",
                    verdict="fresh",
                    reason="session started after every input it snapshotted",
                    evidence={"started_at": _iso(started)},
                )
            )
            continue
        label, mt = max(newer, key=lambda p: p[1])
        out.append(
            Finding(
                subject=subject,
                check="session-inputs",
                verdict="stale",
                reason=(
                    f"started {_iso(started)}, but {label} was modified {_iso(mt)} — "
                    f"this session is running a snapshot nobody can see"
                ),
                remedy="Relaunch the session (hook WIRING loads at start; script bodies are live).",
                evidence={
                    "started_at": _iso(started),
                    "input": label,
                    "input_mtime": _iso(mt),
                    "behind_seconds": int(mt - started),
                },
            )
        )
    return out


# ---------------------------------------------------------------------------
# check 2 — live argv vs what current config would produce (D4: outranks mtime)


def _expected_flags(otaman_root: Path) -> set[str]:
    """Flags today's launch config would put on a session's command line."""
    from otaman_plugin.doctor_checks import _load_yaml

    cfg = _load_yaml(otaman_root / "platform.yaml")
    boot = ((cfg.get("runner") or {}).get("agent_bootstrap") or {}) if isinstance(cfg, dict) else {}
    flags: set[str] = set()
    if boot.get("plugin_dir"):
        flags.add("--plugin-dir")
    for cmd in boot.get("launch_commands") or []:
        if "--continue" in str(cmd):
            flags.add("--continue")
        if "--mcp-config" in str(cmd):
            flags.add("--mcp-config")
    return flags


def check_session_argv(otaman_root: Path) -> list[Finding]:
    pids = _sessions_for(otaman_root)
    if pids is None:
        return [
            _not_checked(
                "agent sessions", "session-argv", "cannot enumerate processes (no pgrep/ps)"
            )
        ]
    if not pids:
        return []
    expected = _expected_flags(otaman_root)
    if not expected:
        return [
            _not_checked(
                "agent sessions",
                "session-argv",
                "platform.yaml declares no launch flags to compare argv against",
            )
        ]

    out: list[Finding] = []
    for pid in sorted(pids):
        subject = f"session pid {pid}"
        argv = _proc_argv(pid)
        if argv is None:
            out.append(_not_checked(subject, "session-argv", f"could not read argv for pid {pid}"))
            continue
        missing = sorted(f for f in expected if f not in argv)
        if not missing:
            out.append(
                Finding(
                    subject=subject,
                    check="session-argv",
                    verdict="fresh",
                    reason="live argv carries every flag current config would produce",
                )
            )
            continue
        out.append(
            Finding(
                subject=subject,
                check="session-argv",
                verdict="stale",
                reason=(
                    f"live argv is missing {', '.join(missing)} — current config would "
                    f"supply it, so this session predates that config"
                ),
                remedy="Relaunch the session to pick up the current launch flags.",
                evidence={"missing_flags": missing, "argv": argv[:400]},
            )
        )
    return out


# ---------------------------------------------------------------------------
# check 3 — daemon start time vs its config inputs (runner 1.4 read surface)


def _runner_endpoint() -> tuple[str, str] | None:
    path = Path.home() / ".otaman" / "runner.endpoint"
    try:
        fields = dict(
            line.split("=", 1)
            for line in path.read_text(encoding="utf-8").splitlines()
            if "=" in line
        )
    except OSError:
        return None
    host, port = fields.get("host"), fields.get("port")
    if not host or not port:
        return None
    return host.strip(), port.strip()


def check_daemon_vs_config(_otaman_root: Path) -> list[Finding]:
    """runner exposes `started_at` + `config_inputs[]` on GET /status (task 1.4)."""
    subject = "runner daemon"
    ep = _runner_endpoint()
    if ep is None:
        return [
            _not_checked(
                subject,
                "daemon-config",
                "no ~/.otaman/runner.endpoint — runner not configured here",
            )
        ]
    host, port = ep
    import urllib.error
    import urllib.request

    try:
        with urllib.request.urlopen(  # noqa: S310 - fixed localhost scheme, not user input
            f"http://{host}:{port}/status", timeout=_HTTP_TIMEOUT_S
        ) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, ValueError, json.JSONDecodeError) as exc:
        return [_not_checked(subject, "daemon-config", f"runner /status unreachable: {exc}")]

    started_raw = payload.get("started_at")
    if not started_raw:
        return [
            _not_checked(
                subject,
                "daemon-config",
                "runner /status carries no started_at (pre-1.4 runner build)",
            )
        ]
    try:
        started = datetime.fromisoformat(str(started_raw).replace("Z", "+00:00"))
    except ValueError:
        return [_not_checked(subject, "daemon-config", f"unparseable started_at: {started_raw!r}")]

    newer: list[tuple[str, str]] = []
    for item in payload.get("config_inputs") or []:
        if not isinstance(item, dict) or not item.get("exists") or not item.get("mtime"):
            continue
        try:
            mt = datetime.fromisoformat(str(item["mtime"]).replace("Z", "+00:00"))
        except ValueError:
            continue
        if mt > started:
            newer.append((str(item.get("path", "?")), mt.strftime("%Y-%m-%dT%H:%M:%SZ")))

    if not newer:
        return [
            Finding(
                subject=subject,
                check="daemon-config",
                verdict="fresh",
                reason="daemon started after every config input it reads",
                evidence={"started_at": str(started_raw)},
            )
        ]
    path, mtime = newer[0]
    return [
        Finding(
            subject=subject,
            check="daemon-config",
            verdict="stale",
            reason=f"started {started_raw}, but {path} was modified {mtime}",
            remedy="Restart the runner daemon so it reloads its config.",
            evidence={"started_at": str(started_raw), "input": path, "input_mtime": mtime},
        )
    ]


# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# check 4 — installed bundle vs the LATEST CUT RELEASE
#
# The comparand here was wrong twice before it was pinned, and both wrong
# answers were the same failure: a verdict that fires on a healthy workspace.
#
#   rejected  `otaman --version` vs a sibling's pyproject version. Deploy
#             stamps the RELEASE version onto components while each repo keeps
#             its own, so 0.5.14 vs 0.5.0 differ on a perfectly current
#             machine (cli-agent measured it, 20260923T222305).
#   rejected  installed_at vs commits-on-sibling-since. Sibling mains run
#             ahead of the last cut BY DESIGN — that is the cadence working,
#             not drift, so this fires on every dev workspace between
#             releases (spec-agent's pin, 20260925).
#
# What is actually actionable is a release that has been CUT but not ROLLED to
# this host. Siblings ahead of the latest cut render fresh, with a note.


_VERSION_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)")


def _parse_version(raw: str) -> tuple[int, int, int] | None:
    m = _VERSION_RE.match(str(raw).strip())
    if not m:
        return None
    return tuple(int(g) for g in m.groups())  # type: ignore[return-value]


def _installed_release() -> str | None:
    """The release this host actually has, from deploy's own manifest."""
    path = Path.home() / ".otaman" / "release.yaml"
    try:
        from otaman_plugin.doctor_checks import _load_yaml

        data = _load_yaml(path)
    except Exception:
        return None
    for key in ("release", "version"):
        val = data.get(key) if isinstance(data, dict) else None
        if val:
            return str(val)
    return None


def _deploy_checkout(otaman_root: Path) -> Path | None:
    for repo in _program_repo_dirs(otaman_root):
        if (repo / "release-manifests").is_dir() or repo.name.endswith("otaman-deploy"):
            return repo
    return None


def _latest_cut_release(deploy: Path) -> str | None:
    """Newest release that has been CUT, from the manifests deploy commits.

    Manifests are preferred over git tags: a tag can exist in a local clone
    that was never pushed, while a committed manifest is the cut's own record.
    """
    best: tuple[tuple[int, int, int], str] | None = None
    for f in (deploy / "release-manifests").glob("*.json"):
        parsed = _parse_version(f.stem)
        if parsed and (best is None or parsed > best[0]):
            best = (parsed, f.stem)
    return best[1] if best else None


def check_bundle_vs_latest_release(otaman_root: Path) -> list[Finding]:
    subject = "installed bundle"
    installed = _installed_release()
    if not installed:
        return [
            _not_checked(
                subject, "bundle-skew", "no ~/.otaman/release.yaml — cannot tell what is installed"
            )
        ]
    deploy = _deploy_checkout(otaman_root)
    if deploy is None:
        return [
            _not_checked(
                subject,
                "bundle-skew",
                f"installed {installed}, but no otaman-deploy checkout here to "
                f"learn the latest cut from",
            )
        ]
    latest = _latest_cut_release(deploy)
    if not latest:
        return [_not_checked(subject, "bundle-skew", f"no release manifests found in {deploy}")]

    got, want = _parse_version(installed), _parse_version(latest)
    if got is None or want is None:
        return [
            _not_checked(
                subject, "bundle-skew", f"unparseable release version: {installed!r} / {latest!r}"
            )
        ]
    if got >= want:
        # Siblings run ahead of the latest cut between releases. That is the
        # cadence's designed steady state, NOT drift — reporting it as skew is
        # the cry-wolf failure the pin exists to prevent.
        return [
            Finding(
                subject=subject,
                check="bundle-skew",
                verdict="fresh",
                reason=(
                    f"on the latest cut release {installed}; sibling mains running ahead of it "
                    f"is the release cadence's normal state, not drift"
                ),
                evidence={"installed": installed, "latest_cut": latest},
            )
        ]
    return [
        Finding(
            subject=subject,
            check="bundle-skew",
            verdict="skewed",
            reason=(
                f"installed release {installed}, but {latest} has been cut — this host has "
                f"not been rolled, so fixes shipped in {latest} are not running here"
            ),
            remedy=f"Roll this host to {latest} (see otaman-deploy RELEASING.md).",
            evidence={"installed": installed, "latest_cut": latest},
        )
    ]


# ---------------------------------------------------------------------------
# check 5 — HALTED: alive, claiming work, and silent
#
# Amendment, approved SCR 20260925T145238. A session frozen on an unanswered
# interactive prompt is ALIVE and still claims `working` — so a liveness check
# says fine and a staleness check says STALE, which reads as "it died". Neither
# is true, and the difference matters: a dead session needs nothing, a halted
# one needs a human to answer a prompt nobody knows is open.
#
# This cost ~11h of fleet delivery on 2026-09-25 across five halts. Every one
# was found by a person reading a tmux pane.
#
# The discriminator vs STALE is process liveness, which is why this lives here
# rather than in cli's record-only staleness view: STALE is computable from the
# status file alone, HALTED is not.

#: Default silence window. Deliberately the SAME key cli's staleness rule reads
#: (`agent_presence_ttl_seconds`), so a program has ONE notion of "too quiet"
#: rather than two knobs that can disagree. Mirrored rather than imported:
#: otaman-cli declares otaman-plugin as a dependency, so importing it back is
#: circular and absent from wheel installs.
HALT_WINDOW_DEFAULT_S = 1800

_HALT_STATES = ("working", "waiting")


def _halt_window_seconds(otaman_root: Path) -> int:
    from otaman_plugin.doctor_checks import _load_yaml

    doc = _load_yaml(otaman_root / "platform.yaml")
    if not isinstance(doc, dict):
        return HALT_WINDOW_DEFAULT_S
    val = doc.get("agent_presence_ttl_seconds")
    if val is None:
        plat = doc.get("platform")
        val = plat.get("agent_presence_ttl_seconds") if isinstance(plat, dict) else None
    try:
        ttl = int(val)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return HALT_WINDOW_DEFAULT_S
    return ttl if ttl > 0 else HALT_WINDOW_DEFAULT_S


def _repo_owner_for_cwd(otaman_root: Path, cwd: Path) -> str | None:
    """The agent owning the repo a session is sitting in."""
    from otaman_plugin.doctor_checks import _load_yaml

    cfg = _load_yaml(otaman_root / "platform.yaml")
    try:
        target = cwd.resolve()
    except OSError:
        return None
    for repo in (cfg.get("repos") or []) if isinstance(cfg, dict) else []:
        if not isinstance(repo, dict) or not repo.get("path"):
            continue
        try:
            base = (otaman_root / str(repo["path"])).resolve()
        except OSError:
            continue
        if target == base or base in target.parents:
            owner = repo.get("owner") or repo.get("name")
            return str(owner) if owner else None
    return None


def _status_record(otaman_root: Path, agent: str) -> dict[str, str]:
    out: dict[str, str] = {}
    path = otaman_root / ".agents" / "status" / f"{agent}.yaml"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return out
    for line in text.splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            out[k.strip()] = v.strip().strip("'\"")
    return out


def check_halted_sessions(otaman_root: Path) -> list[Finding]:
    pids = _sessions_for(otaman_root)
    if pids is None:
        return [
            _not_checked("agent sessions", "halted", "cannot enumerate processes (no pgrep/ps)")
        ]
    if not pids:
        return []

    window = _halt_window_seconds(otaman_root)
    now = datetime.now(tz=timezone.utc)

    # A session whose snapshotted inputs are stale has no heartbeat hook
    # loaded, so its silence is already explained — and already reported by
    # check 1. Calling that HALTED would name the wrong cause ("an unanswered
    # prompt") for a session that is working fine, which is the false-positive
    # class this whole change exists to remove. Reported once, correctly.
    stale_pids = {f.subject for f in check_sessions_vs_inputs(otaman_root) if f.verdict == "stale"}

    out: list[Finding] = []
    for pid in sorted(pids):
        subject = f"session pid {pid}"
        if subject in stale_pids:
            continue
        cwd = _proc_cwd(pid)
        agent = _repo_owner_for_cwd(otaman_root, cwd) if cwd else None
        if agent is None:
            continue
        rec = _status_record(otaman_root, agent)
        state = rec.get("state", "")
        if state not in _HALT_STATES:
            continue
        stamp = rec.get("updated_at") or rec.get("since")
        if not stamp:
            out.append(
                _not_checked(
                    f"{agent} ({subject})", "halted", "status record carries no updated_at"
                )
            )
            continue
        try:
            last = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
        except ValueError:
            out.append(
                _not_checked(f"{agent} ({subject})", "halted", f"unparseable updated_at: {stamp!r}")
            )
            continue
        silent = (now - last).total_seconds()
        if silent <= window:
            continue
        # Name what the agent was doing. cli-agent's point (20260926T094501):
        # a halt report that cannot say what is stuck loses most of its value —
        # "spec-agent is halted" sends someone to a pane, "halted on srf 2.1"
        # tells them what they are interrupting.
        #
        # `task: null` is itself diagnostic rather than merely missing. Before
        # cli #209, acking ANY task-assignment (including a CC copy addressed
        # to someone else) wrote a bare `working` with no task, so a record in
        # that shape may be describing a state its agent never declared.
        raw_task = rec.get("task", "")
        # YAML `task: null` arrives as the STRING "null" through this reader.
        # Evidence must not hand a consumer "null" as if it were a task name —
        # the reason and the structured field have to agree on what is unnamed.
        task = raw_task if raw_task and raw_task != "null" else None
        doing = f" on '{task}'" if task else " (no task named)"
        out.append(
            Finding(
                subject=f"{agent} ({subject})",
                check="halted",
                verdict="halted",
                reason=(
                    f"alive and claiming {state}{doing}, but has written no status update "
                    f"for {int(silent // 60)}m (window {window // 60}m). Not dead, not stale. "
                    f"Most likely an unanswered interactive prompt nobody knows is open"
                    + (
                        ""
                        if task
                        else " — and a record with no task may predate cli #209, which "
                        "stopped an ack from writing a bare working state, so the claim "
                        "itself may be one the agent never made"
                    )
                    + "."
                ),
                remedy=(
                    f"Look at {agent}'s pane and answer the prompt; it cannot time out, "
                    f"self-resolve, or be reached by a bus message. If the pane is idle "
                    f"and the agent is demonstrably active elsewhere, the heartbeat hook "
                    f"is not refreshing this record — a different fault, same symptom."
                ),
                evidence={
                    "agent": agent,
                    "pid": pid,
                    "state": state,
                    "task": task,
                    "last_status_write": str(stamp),
                    "silent_seconds": int(silent),
                    "window_seconds": window,
                },
            )
        )
    return out


def assess(otaman_root: Path) -> list[Finding]:
    """Checks 1-5 in a stable order. The single computation behind both the
    doctor section and the console session view (1.3)."""
    if not (otaman_root / "platform.yaml").is_file():
        # Not a program root — there is nothing for a runtime to be fresh
        # RELATIVE TO. Every other plugin check treats this as [] rather than
        # a finding, and inventing one here would make doctor's output depend
        # on the host's unrelated processes.
        return []
    out: list[Finding] = []
    out.extend(check_sessions_vs_inputs(otaman_root))
    out.extend(check_session_argv(otaman_root))
    out.extend(check_daemon_vs_config(otaman_root))
    out.extend(check_bundle_vs_latest_release(otaman_root))
    out.extend(check_halted_sessions(otaman_root))
    return out
