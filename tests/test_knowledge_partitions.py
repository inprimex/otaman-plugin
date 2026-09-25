"""knowledge-v2 3.1 — partition scoping in generated instructions, and the
ownership guard on partition writes.

The feature this defends is that **context cost stays flat as the corpus
grows**. An agent bound to `development` carries that partition's index lines
and nothing else, so a hundred new strategy entries cost it nothing (SOL-902).
An unscoped index would grow without bound and quietly become the largest
thing in every agent's context.

Two things here are easy to get wrong in the same direction — by omission:

* a partition with no owner must be carried EXPLICITLY as unowned, not left
  out of the table. A missing row reads as "that partition does not exist",
  and the next agent re-derives that `support` is unowned instead of being
  told. The spec names `support` for exactly this reason.
* an index truncated to its budget must SAY it was truncated. A silently cut
  index is indistinguishable from a small one, which is the failure this
  program keeps finding.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from otaman_plugin.generate_agent_config import (
    KNOWLEDGE_INDEX_LINE_BUDGET,
    _knowledge_partitions,
    _render_knowledge_partitions_section,
)

REPO = Path(__file__).parent.parent
HOOK = REPO / "scripts" / "check-ownership.sh"


def _cfg(partitions: dict[str, str] | None) -> dict:
    if partitions is None:
        return {"project": "t"}
    return {"program": {"processes": {"knowledge": {"partitions": partitions}}}}


def _entry(root: Path, *, title: str, function: str, state: str = "active") -> None:
    from otaman_core.knowledge import KNOWLEDGE_DIRNAME, KnowledgeEntry, write_entry

    d = root / ".agents" / KNOWLEDGE_DIRNAME
    d.mkdir(parents=True, exist_ok=True)
    write_entry(
        d,
        KnowledgeEntry(
            type="lesson",
            author="someone",
            created="2026-09-01",
            review_by="2026-12-01",
            anchor="file.py:1",
            title=title,
            body="b",
            state=state,
            function=function,
        ),
    )


class TestPartitionsMap:
    def test_absent_declaration_renders_nothing(self, tmp_path):
        """A program that has not adopted knowledge-v2 must not grow a section
        explaining a feature it does not use."""
        assert _render_knowledge_partitions_section(tmp_path, _cfg(None), "a") == ""

    def test_owner_is_named_and_marked(self, tmp_path):
        out = _render_knowledge_partitions_section(
            tmp_path, _cfg({"development": "plugin-agent", "design": "web-agent"}), "plugin-agent"
        )
        assert "You **own** `development`" in out
        assert "| `development` | plugin-agent **(you)** |" in out
        assert "| `design` | web-agent |" in out

    def test_support_is_carried_explicitly_unowned(self, tmp_path):
        """The spec names `support` because omission is the tempting bug: a
        partition absent from the table reads as nonexistent."""
        out = _render_knowledge_partitions_section(
            tmp_path, _cfg({"development": "plugin-agent"}), "plugin-agent"
        )
        assert "`support`" in out, "an undeclared partition was omitted rather than carried"
        assert "unowned" in out

    def test_every_platform_function_appears(self, tmp_path):
        from otaman_core.knowledge import FUNCTIONS

        out = _render_knowledge_partitions_section(
            tmp_path, _cfg({"development": "plugin-agent"}), "plugin-agent"
        )
        for fn in FUNCTIONS:
            assert f"`{fn}`" in out, f"{fn} missing from the partitions table"

    def test_agent_owning_nothing_is_told_how_to_contribute(self, tmp_path):
        out = _render_knowledge_partitions_section(
            tmp_path, _cfg({"development": "other-agent"}), "plugin-agent"
        )
        assert "own **no** knowledge partition" in out
        assert "bus" in out

    def test_reader_is_never_told_they_cannot_read(self, tmp_path):
        """Ownership is about WRITES. 'any agent reads' is the spec's wording
        and the instructions must not imply otherwise."""
        out = _render_knowledge_partitions_section(
            tmp_path, _cfg({"development": "other-agent"}), "plugin-agent"
        )
        assert "read" in out.lower()


class TestScopedIndex:
    def test_index_carries_only_owned_partitions(self, tmp_path):
        _entry(tmp_path, title="Mine one", function="development")
        _entry(tmp_path, title="Theirs one", function="design")
        out = _render_knowledge_partitions_section(
            tmp_path, _cfg({"development": "me", "design": "them"}), "me"
        )
        assert "Mine one" in out
        assert "Theirs one" not in out, (
            "an entry from a partition this agent does not own leaked into its index — "
            "scoping is the whole feature"
        )

    def test_dormant_and_retired_are_excluded(self, tmp_path):
        _entry(tmp_path, title="Still true", function="development")
        _entry(tmp_path, title="Decayed", function="development", state="dormant")
        _entry(tmp_path, title="Gone", function="development", state="retired")
        out = _render_knowledge_partitions_section(tmp_path, _cfg({"development": "me"}), "me")
        assert "Still true" in out
        assert "Decayed" not in out and "Gone" not in out

    def test_overflow_is_stated_never_silent(self, tmp_path):
        over = KNOWLEDGE_INDEX_LINE_BUDGET + 5
        for i in range(over):
            _entry(tmp_path, title=f"Entry number {i:03d}", function="development")
        out = _render_knowledge_partitions_section(tmp_path, _cfg({"development": "me"}), "me")
        assert f"({over} active" in out, "the true total must be stated"
        assert "more not shown" in out, "a truncated index that does not say so is a silent lie"
        assert "truncated, not complete" in out

    def test_empty_index_says_empty_not_missing(self, tmp_path):
        out = _render_knowledge_partitions_section(tmp_path, _cfg({"development": "me"}), "me")
        assert "empty index, not a missing one" in out

    def test_older_core_says_not_rendered(self, tmp_path, monkeypatch):
        """An installed core without the v2 reader must produce 'not shown',
        never an empty index that reads as 'nothing recorded'."""
        import builtins

        real = builtins.__import__

        def boom(name, *a, **k):
            if name == "otaman_core.knowledge":
                raise ImportError("no knowledge-v2")
            return real(name, *a, **k)

        monkeypatch.setattr(builtins, "__import__", boom)
        out = _render_knowledge_partitions_section(tmp_path, _cfg({"development": "me"}), "me")
        assert "not rendered" in out
        assert "not 'nothing recorded'" in out


class TestHelper:
    def test_missing_and_malformed_declarations_are_empty(self):
        assert _knowledge_partitions({}) == {}
        assert _knowledge_partitions({"program": {"processes": {"knowledge": {}}}}) == {}
        assert (
            _knowledge_partitions({"program": {"processes": {"knowledge": {"partitions": []}}}})
            == {}
        )

    def test_blank_owner_is_treated_as_unowned(self):
        parts = _knowledge_partitions(_cfg({"development": "me", "support": ""}))
        assert parts == {"development": "me"}


HAVE_BASH = shutil.which("bash") is not None


@pytest.mark.skipif(not HAVE_BASH, reason="bash not on PATH")
class TestOwnershipHookGuardsPartitionWrites:
    """`.agents/` is otherwise open to every agent — knowledge entries are the
    exception, and until now nothing enforced it."""

    def _project(self, tmp_path: Path, *, partitions: dict[str, str]) -> Path:
        root = tmp_path / "meta"
        (root / ".agents" / "knowledge").mkdir(parents=True)
        (root / ".agents").joinpath("ownership.json").write_text(
            json.dumps({"repos": [{"name": "r", "path": "../r", "owner": "other-agent"}]}),
            encoding="utf-8",
        )
        import yaml

        (root / "platform.yaml").write_text(
            yaml.safe_dump(
                {
                    "project": "t",
                    "program": {"processes": {"knowledge": {"partitions": partitions}}},
                }
            ),
            encoding="utf-8",
        )
        repo = tmp_path / "r"
        repo.mkdir()
        (repo / ".otaman").write_text("../meta\nagent: plugin-agent\n", encoding="utf-8")
        return root, repo

    def _write_entry_file(self, root: Path, name: str, function: str) -> Path:
        f = root / ".agents" / "knowledge" / name
        f.write_text(
            f"---\ntype: lesson\nauthor: x\ncreated: 2026-09-01\nreview_by: 2026-12-01\n"
            f"anchor: a.py:1\ntitle: T\nfunction: {function}\nstate: active\n---\n\nbody\n",
            encoding="utf-8",
        )
        return f

    def _run(self, repo: Path, target: Path, home: Path, stub_bin: Path):
        # `otaman_stub_bin` (conftest) puts a fake `otaman whoami --resolve-only`
        # on PATH. Without it `resolve_enforcement_identity` finds no CLI, the
        # hook bails before any check, and every deny test here passes
        # vacuously — which is what CI caught on this file's first run.
        payload = json.dumps({"tool_name": "Edit", "file_path": str(target)})
        env = {**os.environ, "HOME": str(home), "PATH": f"{stub_bin}:/usr/bin:/bin"}
        for k in ("OTAMAN_ROOT", "MAESTRO_ROOT", "OTAMAN_AGENT"):
            env.pop(k, None)
        r = subprocess.run(
            ["bash", str(HOOK)],
            input=payload,
            capture_output=True,
            text=True,
            timeout=60,
            cwd=repo,
            env=env,
        )
        parsed = json.loads(r.stdout) if r.stdout.strip() else None
        return r.returncode, parsed

    def test_enforcement_identity_resolves_here(self, tmp_path, otaman_stub_bin):
        """The precondition, asserted on its own.

        The partition test below cannot distinguish 'the guard is gone' from
        'identity never resolved, so the hook bailed at line 42' — both produce
        no deny. Skipping on a missing deny would make the guard test unable to
        fail, which is the vacuous-guard shape this repo has been removing. So
        the precondition gets its own check, against the PRE-EXISTING ownership
        rule rather than the new one.
        """
        root, repo = self._project(tmp_path, partitions={})
        foreign = tmp_path / "r" / "src"
        foreign.mkdir(parents=True, exist_ok=True)
        # `r` is owned by other-agent in ownership.json; this marker says we are
        # plugin-agent, so the long-standing repo-ownership check must deny.
        rc, parsed = self._run(repo, foreign / "x.py", tmp_path, otaman_stub_bin)
        assert rc == 0
        assert parsed is not None, (
            "the hook denied nothing even for a foreign-repo write — enforcement "
            "identity is not resolving, so every deny test here would pass vacuously"
        )

    def test_writing_another_agents_partition_is_denied(self, tmp_path, otaman_stub_bin):
        root, repo = self._project(tmp_path, partitions={"design": "web-agent"})
        target = self._write_entry_file(root, "e.md", "design")
        rc, parsed = self._run(repo, target, tmp_path, otaman_stub_bin)
        assert rc == 0, "deny must exit 0 so the stdout JSON is honoured"
        assert parsed is not None, "the partition guard did not deny a foreign-partition write"
        reason = parsed["hookSpecificOutput"]["permissionDecisionReason"]
        assert "design" in reason and "web-agent" in reason
        assert "bus" in reason, "the deny must name the sanctioned route, not just refuse"

    def test_writing_your_own_partition_is_allowed(self, tmp_path, otaman_stub_bin):
        root, repo = self._project(tmp_path, partitions={"development": "plugin-agent"})
        target = self._write_entry_file(root, "e.md", "development")
        rc, parsed = self._run(repo, target, tmp_path, otaman_stub_bin)
        assert rc == 0
        assert parsed is None, f"owner was denied their own partition: {parsed}"

    def test_unowned_partition_is_allowed(self, tmp_path, otaman_stub_bin):
        """`support` has no owner, so nobody can be trespassing on it."""
        root, repo = self._project(tmp_path, partitions={"development": "plugin-agent"})
        target = self._write_entry_file(root, "e.md", "support")
        rc, parsed = self._run(repo, target, tmp_path, otaman_stub_bin)
        assert rc == 0 and parsed is None

    def test_non_knowledge_agents_file_is_untouched(self, tmp_path, otaman_stub_bin):
        """The guard must not make the rest of `.agents/` suddenly ownable."""
        root, repo = self._project(tmp_path, partitions={"design": "web-agent"})
        other = root / ".agents" / "queue"
        other.mkdir()
        target = other / "plugin-agent.md"
        target.write_text("queue\n", encoding="utf-8")
        rc, parsed = self._run(repo, target, tmp_path, otaman_stub_bin)
        assert rc == 0 and parsed is None
