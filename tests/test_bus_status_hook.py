"""Tests for scripts/bus-status-hook.sh.

Covers correctness (pending/urgent counting, ack-resolved exclusion,
recipient filtering, CRLF handling, and a frontmatter-vs-body `to:` false
positive) and a performance regression guard for the bug this hook actually
hit in production: bus/active/ accumulates every message ever sent (acking
a message writes a .ack file; the underlying .md is never moved or pruned),
so at 1000+ accumulated messages the original per-file sed|head|tr pipeline
(~8 subprocess forks per file) blew the 5s UserPromptSubmit timeout. The
fix rewrote the hot loop with pure-bash builtins (zero forks per file).
"""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

REPO = Path(__file__).parent.parent
HOOK = REPO / "scripts" / "bus-status-hook.sh"


def _make_bus(root: Path) -> Path:
    """A minimal otaman project root: .otaman marker (self-pointing),
    .agents/current-agent, and an empty bus/active/acks tree."""
    (root / ".agents" / "bus" / "active" / "acks").mkdir(parents=True)
    (root / ".agents" / "current-agent").write_text("plugin-agent\n", encoding="utf-8")
    (root / ".otaman").write_text(".\n", encoding="utf-8")
    return root / ".agents" / "bus" / "active"


def _run_hook(root: Path, timeout: float = 10) -> tuple[dict | None, float]:
    payload = json.dumps({"cwd": str(root)})
    start = time.monotonic()
    proc = subprocess.run(
        ["bash", str(HOOK)],
        input=payload,
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=str(root),
    )
    elapsed = time.monotonic() - start
    assert proc.returncode == 0, f"hook exited {proc.returncode}: stderr={proc.stderr}"
    out = proc.stdout.strip()
    if not out:
        return None, elapsed
    return json.loads(out), elapsed


class TestBusStatusHookCorrectness:
    def test_no_messages_emits_nothing(self, tmp_path):
        _make_bus(tmp_path)
        result, _ = _run_hook(tmp_path)
        assert result is None

    def test_counts_pending_addressed_to_agent_and_all(self, tmp_path):
        bus = _make_bus(tmp_path)
        (bus / "m1.md").write_text(
            "id: m1\nto: plugin-agent\nfrom: spec-agent\npriority: normal\n---\nbody\n",
            encoding="utf-8",
        )
        (bus / "m2.md").write_text(
            "id: m2\nto: all\nfrom: cli-agent\npriority: normal\n---\nbody\n", encoding="utf-8"
        )
        result, _ = _run_hook(tmp_path)
        assert result is not None
        assert "2 pending" in result["systemMessage"]

    def test_excludes_messages_addressed_to_other_agents(self, tmp_path):
        bus = _make_bus(tmp_path)
        (bus / "m1.md").write_text(
            "id: m1\nto: cli-agent\nfrom: spec-agent\npriority: normal\n---\nbody\n",
            encoding="utf-8",
        )
        result, _ = _run_hook(tmp_path)
        assert result is None

    def test_resolved_ack_excludes_message(self, tmp_path):
        bus = _make_bus(tmp_path)
        (bus / "m1.md").write_text(
            "id: m1\nto: plugin-agent\nfrom: spec-agent\npriority: urgent\n---\nbody\n",
            encoding="utf-8",
        )
        (bus / "acks" / "m1.plugin-agent.ack").write_text("resolved 2026-01-01\n", encoding="utf-8")
        result, _ = _run_hook(tmp_path)
        assert result is None

    def test_read_ack_still_counts_as_pending(self, tmp_path):
        bus = _make_bus(tmp_path)
        (bus / "m1.md").write_text(
            "id: m1\nto: plugin-agent\nfrom: spec-agent\npriority: normal\n---\nbody\n",
            encoding="utf-8",
        )
        (bus / "acks" / "m1.plugin-agent.ack").write_text("read 2026-01-01\n", encoding="utf-8")
        result, _ = _run_hook(tmp_path)
        assert result is not None
        assert "1 pending" in result["systemMessage"]

    def test_high_and_urgent_priority_both_count_as_urgent(self, tmp_path):
        bus = _make_bus(tmp_path)
        (bus / "m1.md").write_text(
            "id: m1\nto: plugin-agent\nfrom: spec-agent\npriority: high\n---\nbody\n",
            encoding="utf-8",
        )
        (bus / "m2.md").write_text(
            "id: m2\nto: plugin-agent\nfrom: spec-agent\npriority: urgent\n---\nbody\n",
            encoding="utf-8",
        )
        (bus / "m3.md").write_text(
            "id: m3\nto: plugin-agent\nfrom: spec-agent\npriority: normal\n---\nbody\n",
            encoding="utf-8",
        )
        result, _ = _run_hook(tmp_path)
        assert "3 pending" in result["systemMessage"]
        assert "2 urgent" in result["systemMessage"]

    def test_crlf_line_endings_parse_correctly(self, tmp_path):
        bus = _make_bus(tmp_path)
        (bus / "m1.md").write_bytes(
            b"id: m1\r\nto: plugin-agent\r\nfrom: spec-agent\r\npriority: high\r\n---\r\nbody\r\n"
        )
        result, _ = _run_hook(tmp_path)
        assert result is not None
        assert "1 pending" in result["systemMessage"]
        assert "1 urgent" in result["systemMessage"]

    def test_frontmatter_to_field_wins_over_body_mentions(self, tmp_path):
        # A body line that happens to start with "to:" past the frontmatter
        # must not confuse the "first to: line wins" extraction.
        bus = _make_bus(tmp_path)
        body_lines = "\n".join(f"to: not-a-real-field line {i}" for i in range(20))
        (bus / "m1.md").write_text(
            f"id: m1\nto: plugin-agent\nfrom: spec-agent\npriority: normal\n---\n{body_lines}\n",
            encoding="utf-8",
        )
        result, _ = _run_hook(tmp_path)
        assert result is not None
        assert "1 pending" in result["systemMessage"]

    def test_blocked_tasks_file_with_zero_matches_does_not_crash(self, tmp_path):
        # Regression guard: `grep -c '^## Blocked:' file || echo 0` used to
        # concatenate grep's own "0" stdout with the fallback "0" into
        # "0\n0" whenever the blocked file existed with zero matching
        # lines, breaking the `-gt` comparison with a bash syntax error.
        # A message must still be present so the hook doesn't early-exit
        # before reaching the BLOCKED check.
        bus = _make_bus(tmp_path)
        (bus / "m1.md").write_text(
            "id: m1\nto: plugin-agent\nfrom: spec-agent\npriority: normal\n---\nbody\n",
            encoding="utf-8",
        )
        (tmp_path / ".agents" / "blocked").mkdir()
        (tmp_path / ".agents" / "blocked" / "plugin-agent.md").write_text(
            "# no blocked entries here, just prose\n", encoding="utf-8"
        )
        payload = json.dumps({"cwd": str(tmp_path)})
        proc = subprocess.run(
            ["bash", str(HOOK)], input=payload, capture_output=True, text=True, timeout=10
        )
        assert proc.returncode == 0
        assert "syntax error" not in proc.stderr
        result = json.loads(proc.stdout.strip())
        assert "1 pending" in result["systemMessage"]

    def test_blocked_tasks_counted_when_present(self, tmp_path):
        bus = _make_bus(tmp_path)
        (bus / "m1.md").write_text(
            "id: m1\nto: plugin-agent\nfrom: spec-agent\npriority: normal\n---\nbody\n",
            encoding="utf-8",
        )
        (tmp_path / ".agents" / "blocked").mkdir()
        (tmp_path / ".agents" / "blocked" / "plugin-agent.md").write_text(
            "## Blocked: something\n## Blocked: something else\n", encoding="utf-8"
        )
        result, _ = _run_hook(tmp_path)
        assert "2 blocked" in result["systemMessage"]


class TestBusStatusHookPerformance:
    def test_stays_well_under_timeout_at_production_scale(self, tmp_path):
        # Reproduces the reported bug's scale: bus/active/ never prunes
        # resolved messages, so a lived-in project accumulates thousands
        # of .md files. 1500 messages (mostly already-resolved, a handful
        # genuinely pending) mirrors the real otaman-meta bus that blew
        # the 5s hook timeout (~6s measured) before this fix.
        bus = _make_bus(tmp_path)
        for i in range(1500):
            msg = bus / f"m{i}.md"
            if i % 50 == 0:
                # A handful of genuinely pending, high-priority messages.
                msg.write_text(
                    f"id: m{i}\nto: plugin-agent\nfrom: spec-agent\npriority: high\n---\nbody\n",
                    encoding="utf-8",
                )
            else:
                msg.write_text(
                    f"id: m{i}\nto: plugin-agent\nfrom: spec-agent\npriority: normal\n---\nbody\n",
                    encoding="utf-8",
                )
                (bus / "acks" / f"m{i}.plugin-agent.ack").write_text(
                    "resolved 2026-01-01\n", encoding="utf-8"
                )

        result, elapsed = _run_hook(tmp_path, timeout=10)
        assert result is not None
        assert "30 pending" in result["systemMessage"]
        # Generous ceiling (the original blew 5s; the fix measured ~0.4s
        # against 1373 real messages) -- catches a fork-per-file regression
        # without being flaky on a loaded CI box.
        assert elapsed < 3.0, (
            f"hook took {elapsed:.2f}s against 1500 messages -- a per-file "
            f"subprocess-fork regression would reproduce the original "
            f"5s-timeout bug at this scale"
        )
