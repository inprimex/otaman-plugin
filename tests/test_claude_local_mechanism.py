"""The gitignored-import mechanism: orchestration rules go to CLAUDE.local.md.

External-audit remediation (spec-agent 20260818T143518, Roman-caught
ordering trap). The generator must NEVER write the private orchestration
block into the committed CLAUDE.md — it writes CLAUDE.local.md (gitignored,
auto-loaded by Claude Code after CLAUDE.md). Chosen over an @import of a
gitignored file because a missing @import target's behavior is unspecified,
while a missing CLAUDE.local.md degrades gracefully by construction.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
gen_config = importlib.import_module("otaman_plugin.generate_agent_config")

_REPO = {"name": "backend", "path": "./backend", "owner": "dev-agent"}


def _config(repo: dict) -> dict:
    return {
        "project": "mech-test",
        "repos": [repo],
        "communication": {"bus_path": ".agents/bus", "format": "markdown"},
    }


def _run(tmp_path: Path) -> Path:
    repo_dir = tmp_path / "backend"
    repo_dir.mkdir(parents=True, exist_ok=True)
    gen_config.generate_repo_claude_md(tmp_path, _config(_REPO))
    return repo_dir


class TestBlockGoesToLocalFile:
    def test_block_written_to_claude_local_md(self, tmp_path):
        repo_dir = _run(tmp_path)
        local = repo_dir / "CLAUDE.local.md"
        assert local.is_file()
        text = local.read_text(encoding="utf-8")
        assert "<!-- otaman:begin -->" in text
        assert "## Otaman Orchestration Rules" in text
        assert "**You are `dev-agent`**" in text

    def test_claude_md_not_created(self, tmp_path):
        """The generator no longer creates or touches a missing CLAUDE.md."""
        repo_dir = _run(tmp_path)
        assert not (repo_dir / "CLAUDE.md").exists()

    def test_local_block_carries_generated_marker_note(self, tmp_path):
        repo_dir = _run(tmp_path)
        text = (repo_dir / "CLAUDE.local.md").read_text(encoding="utf-8")
        assert "gitignored" in text.lower()
        assert "never committed" in text.lower()


class TestMigration:
    def test_inline_block_stripped_public_content_kept(self, tmp_path):
        """A CLAUDE.md that wraps public content around a legacy injected
        block: the block is stripped (now in CLAUDE.local.md), the public
        content survives."""
        repo_dir = tmp_path / "backend"
        repo_dir.mkdir(parents=True)
        (repo_dir / "CLAUDE.md").write_text(
            "# backend — developer guide\n\nPublic intro.\n\n"
            "<!-- otaman:begin -->\n## Otaman Orchestration Rules\nprivate\n<!-- otaman:end -->\n\n"
            "## Public footer\n",
            encoding="utf-8",
        )
        gen_config.generate_repo_claude_md(tmp_path, _config(_REPO))
        md = (repo_dir / "CLAUDE.md").read_text(encoding="utf-8")
        assert "<!-- otaman:begin -->" not in md
        assert "Public intro." in md
        assert "## Public footer" in md
        assert "<!-- otaman:begin -->" in (repo_dir / "CLAUDE.local.md").read_text(encoding="utf-8")

    def test_block_only_claude_md_left_for_owner_sanitize(self, tmp_path):
        """A not-yet-sanitized CLAUDE.md that is ONLY the block is left
        untouched — rules are already safe in CLAUDE.local.md, and the
        owner replaces CLAUDE.md in their separate sanitize commit."""
        repo_dir = tmp_path / "backend"
        repo_dir.mkdir(parents=True)
        block_only = (
            "<!-- otaman:begin -->\n## Otaman Orchestration Rules\nprivate\n<!-- otaman:end -->\n"
        )
        (repo_dir / "CLAUDE.md").write_text(block_only, encoding="utf-8")
        gen_config.generate_repo_claude_md(tmp_path, _config(_REPO))
        assert (repo_dir / "CLAUDE.md").read_text(encoding="utf-8") == block_only
        assert (repo_dir / "CLAUDE.local.md").is_file()

    def test_legacy_maestro_markers_migrated(self, tmp_path):
        repo_dir = tmp_path / "backend"
        repo_dir.mkdir(parents=True)
        (repo_dir / "CLAUDE.md").write_text(
            "# guide\n\nkeep me\n\n<!-- maestro:begin -->\nold\n<!-- maestro:end -->\n",
            encoding="utf-8",
        )
        gen_config.generate_repo_claude_md(tmp_path, _config(_REPO))
        md = (repo_dir / "CLAUDE.md").read_text(encoding="utf-8")
        assert "maestro:begin" not in md
        assert "keep me" in md


class TestIdempotencyAndCoexistence:
    def test_two_runs_do_not_duplicate_block(self, tmp_path):
        _run(tmp_path)
        repo_dir = _run(tmp_path)
        text = (repo_dir / "CLAUDE.local.md").read_text(encoding="utf-8")
        assert text.count("<!-- otaman:begin -->") == 1

    def test_human_notes_in_local_file_survive(self, tmp_path):
        repo_dir = tmp_path / "backend"
        repo_dir.mkdir(parents=True)
        (repo_dir / "CLAUDE.local.md").write_text(
            "# my personal notes\n\nremember the thing\n", encoding="utf-8"
        )
        gen_config.generate_repo_claude_md(tmp_path, _config(_REPO))
        text = (repo_dir / "CLAUDE.local.md").read_text(encoding="utf-8")
        assert "remember the thing" in text  # human content preserved
        assert "<!-- otaman:begin -->" in text  # block appended
        # second run still doesn't duplicate
        gen_config.generate_repo_claude_md(tmp_path, _config(_REPO))
        text2 = (repo_dir / "CLAUDE.local.md").read_text(encoding="utf-8")
        assert text2.count("<!-- otaman:begin -->") == 1
        assert "remember the thing" in text2
