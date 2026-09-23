"""status-heartbeat identity resolution — the CLAUDE.md sniff was dead on every
operator-mode repo, and an unresolvable identity must not look like "no otaman
root here".

Found while running the gate 2.1 clean test; spec-agent gave GO as a
conformance defect fix (msg 20260922T224906), no SCR — approved canon covers it
twice over.

THE DEAD BRANCH. The hook resolved identity by sniffing ``You are `<agent>` ``
out of **CLAUDE.md**. But `otaman init` writes that line to the **gitignored
CLAUDE.local.md**, and the committed CLAUDE.md never carries it. So on this
fleet — and every operator-mode repo — the branch matched nothing, and identity
survived purely on the `OTAMAN_AGENT` env fallback. The hook was one unset
variable away from exiting 0 silently, which is indistinguishable from "this
isn't an otaman workspace".

THE REPLACEMENT is the `.otaman` marker's `agent:` field, which is the
per-directory source `resolve_enforcement_identity` already treats as
authoritative and the only identity source that is not agent-writable
(`OTAMAN_AGENT` and the retired `.agents/current-agent` both are). Mirroring
that order rather than inventing a third identity path was spec-agent's
explicit condition. It is also pure bash — `resolve_agent_identity()` would
spawn python3 on every tool call, which the per-tool-call path cannot afford.

THE SILENCE SPLIT (no-silent-success clause 1). "No otaman root here" is a
legitimate quiet no-op — most repos on a machine are not otaman workspaces.
"Root resolved but identity did not" is a real defect in that workspace's
setup, and the two must not present identically. The second now writes to
stderr and still exits 0: a heartbeat may never block a tool call or inject
text into a transcript, but it may leave a trace where someone debugging a
status record that will not refresh would actually look.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).parent.parent
HOOK = REPO / "hooks" / "status-heartbeat.sh"
RESOLVE = REPO / "scripts" / "_resolve.sh"

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="bash not on PATH")

SINCE = "2026-09-22T22:28:23Z"
BASELINE = "2026-09-22T22:28:24Z"


@pytest.fixture(autouse=True)
def _unpin_root(monkeypatch):
    monkeypatch.delenv("OTAMAN_ROOT", raising=False)
    monkeypatch.delenv("MAESTRO_ROOT", raising=False)
    monkeypatch.delenv("OTAMAN_AGENT", raising=False)


def _fleet(
    tmp_path: Path,
    *,
    agents: tuple[str, ...] = ("plugin-agent",),
    marker_agent: str | None = "plugin-agent",
    claude_md_agent: str | None = None,
    marker_agent_first: bool = False,
) -> tuple[Path, Path]:
    meta = tmp_path / "meta"
    (meta / ".agents" / "status").mkdir(parents=True)
    for a in agents:
        (meta / ".agents" / "status" / f"{a}.yaml").write_text(
            f"agent: {a}\nstate: working\ntask: null\nsince: '{SINCE}'\nupdated_at: '{BASELINE}'\n",
            encoding="utf-8",
        )

    repo = tmp_path / "repo"
    repo.mkdir()
    lines = ["../meta"]
    if marker_agent:
        lines = (
            [f"agent: {marker_agent}", "../meta"]
            if marker_agent_first
            else ["../meta", f"agent: {marker_agent}"]
        )
    (repo / ".otaman").write_text("\n".join(lines) + "\n", encoding="utf-8")

    if claude_md_agent:
        (repo / "CLAUDE.md").write_text(
            f"You are `{claude_md_agent}`. You own this repo.\n", encoding="utf-8"
        )
    return meta, repo


def _fire(repo: Path, home: Path, *, agent_env: str | None = None, interval: str = "0"):
    # interval 0 defeats the throttle deterministically. With any positive
    # value a fixture written microseconds earlier is still inside its own
    # throttle window, and the test measures the clock rather than the code.
    env = {**os.environ, "HOME": str(home), "OTAMAN_HEARTBEAT_INTERVAL": interval}
    for k in ("OTAMAN_ROOT", "MAESTRO_ROOT", "OTAMAN_AGENT"):
        env.pop(k, None)
    if agent_env:
        env["OTAMAN_AGENT"] = agent_env
    return subprocess.run(
        ["bash", str(HOOK)],
        input=f'{{"cwd": "{repo}", "tool_name": "Bash"}}',
        cwd=repo,
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
    )


def _updated_at(meta: Path, agent: str) -> str:
    for line in (meta / ".agents" / "status" / f"{agent}.yaml").read_text().splitlines():
        if line.startswith("updated_at:"):
            return line.split(":", 1)[1].strip().strip("'\"")
    raise AssertionError("no updated_at")


class TestMarkerAgentIsTheIdentitySource:
    def test_marker_agent_resolves_and_refreshes(self, tmp_path):
        meta, repo = _fleet(tmp_path)
        r = _fire(repo, tmp_path)
        assert r.returncode == 0, r.stderr
        assert _updated_at(meta, "plugin-agent") != BASELINE, r.stderr

    def test_claude_md_sniff_is_gone_and_does_not_win(self, tmp_path):
        """The regression guard. With the dead branch restored AHEAD of the
        marker, the wrong agent's record moves — which is not merely wrong, it
        is a hook writing to another agent's status on the strength of a line
        in a file anyone can edit."""
        meta, repo = _fleet(
            tmp_path,
            agents=("plugin-agent", "impostor-agent"),
            marker_agent="plugin-agent",
            claude_md_agent="impostor-agent",
        )
        _fire(repo, tmp_path)

        assert _updated_at(meta, "plugin-agent") != BASELINE, "the marker's agent must win"
        assert _updated_at(meta, "impostor-agent") == BASELINE, (
            "CLAUDE.md decided identity — the dead branch is back"
        )

    def test_env_still_works_when_the_marker_carries_no_agent(self, tmp_path):
        """The documented fallback stays; it is just no longer load-bearing."""
        meta, repo = _fleet(tmp_path, marker_agent=None)
        r = _fire(repo, tmp_path, agent_env="plugin-agent")
        assert r.returncode == 0, r.stderr
        assert _updated_at(meta, "plugin-agent") != BASELINE


class TestTheTwoSilencesAreDistinguishable:
    """no-silent-success clause 1."""

    def test_no_root_stays_quiet(self, tmp_path):
        """Most directories on a machine are not otaman workspaces. Saying
        something here would make the hook noise on every tool call everywhere."""
        plain = tmp_path / "somewhere"
        plain.mkdir()
        r = _fire(plain, tmp_path)
        assert r.returncode == 0
        assert r.stderr.strip() == "", f"a non-otaman directory must be silent: {r.stderr!r}"

    def test_root_without_identity_speaks(self, tmp_path):
        """A root resolved but no identity is a real defect in this workspace,
        and must not present as the quiet case above."""
        _, repo = _fleet(tmp_path, marker_agent=None)
        r = _fire(repo, tmp_path)  # no OTAMAN_AGENT either
        assert r.returncode == 0, "a heartbeat must never block a tool call"
        assert "identity" in r.stderr.lower(), f"stayed silent on a real defect: {r.stderr!r}"
        assert "OTAMAN_AGENT" in r.stderr, "should name what is missing"

    def test_it_never_writes_to_stdout(self, tmp_path):
        """stdout on a PreToolUse hook can reach the transcript. Diagnostics
        belong on stderr."""
        _, repo = _fleet(tmp_path, marker_agent=None)
        assert _fire(repo, tmp_path).stdout == ""


class TestResolveShMarkerAgentField:
    def _call(self, fn: str, arg: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["bash", "-c", f'source "{RESOLVE}"; {fn} "{arg}"'],
            capture_output=True,
            text=True,
            timeout=30,
        )

    def test_read_marker_agent_reads_the_field(self, tmp_path):
        _, repo = _fleet(tmp_path)
        assert self._call("read_marker_agent", str(repo)).stdout.strip() == "plugin-agent"

    def test_absent_agent_field_returns_failure_not_a_stray_line(self, tmp_path):
        _, repo = _fleet(tmp_path, marker_agent=None)
        r = self._call("read_marker_agent", str(repo))
        assert r.returncode != 0
        assert r.stdout.strip() == ""

    def test_agent_line_before_the_bare_path_does_not_poison_root_lookup(self, tmp_path):
        """The latent bug this fix also closes: `agent` was not a recognised
        key, so an `agent:` line reaching the bare-path branch FIRST would be
        returned as the otaman root — a marker ordering nothing forbids."""
        _, repo = _fleet(tmp_path, marker_agent_first=True)
        r = subprocess.run(
            [
                "bash",
                "-c",
                f'source "{RESOLVE}"; _parse_marker_field "{repo}/.otaman" maestro_root',
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert r.stdout.strip() == "../meta", (
            f"root lookup returned {r.stdout.strip()!r} — an `agent:` line was "
            f"mistaken for the bare path"
        )
