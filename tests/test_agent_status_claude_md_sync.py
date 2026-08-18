"""Regression test for `agent-status-presence` task 2.4.

The `### Agent Status (REQUIRED)` block must be present in the CLAUDE.md
scaffold TEMPLATE — `src/otaman_plugin/generate_agent_config.py` — so that
every otaman-managed repo's locally-generated `CLAUDE.local.md` carries the
rule. This guards the failure mode `core-agent` warned about in
`20260609T145334-core-agent-to-plugin-agent-fyi-agent-status-presence-generator-temp`:
if the block ever leaves the template, `otaman init` silently drops it.

History note: this test previously also pinned the block in this repo's
committed `CLAUDE.md`. That coupling was removed by the 2026-08-18
external-audit sanitize (spec-agent 20260818T142208 / 143518) — the
committed CLAUDE.md is now the public-safe developer guide and carries NO
orchestration block; the full block is generated into a gitignored
`CLAUDE.local.md` (auto-loaded by Claude Code after CLAUDE.md). So the
invariant now lives on the template alone.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CLAUDE_MD = REPO_ROOT / "CLAUDE.md"
GENERATOR = REPO_ROOT / "src" / "otaman_plugin" / "generate_agent_config.py"

# Load-bearing lines: the section heading + the three CLI signatures.
_REQUIRED_LINES = [
    "### Agent Status (REQUIRED)",
    'otaman set-status working --task "<N.M task description>" --change <change-name>',
    'otaman set-status waiting --task "<N.M ...>" --change <change-name>',
    "otaman set-status idle",
]


def test_agent_status_block_present_in_template():
    """The generator template carries the Agent Status rule."""
    text = GENERATOR.read_text(encoding="utf-8")
    for line in _REQUIRED_LINES:
        assert line in text, (
            f"'{line}' missing from the Agent Status block in the generator "
            "template. If you intentionally moved the section, update "
            "_REQUIRED_LINES in this test."
        )


def test_required_lines_appear_in_canonical_order_in_template():
    """The working / waiting / idle signatures stay in intent order."""
    gen = GENERATOR.read_text(encoding="utf-8")
    positions = [gen.index(line) for line in _REQUIRED_LINES]
    assert positions == sorted(positions), (
        "Generator template Agent Status lines out of canonical order"
    )


def test_committed_claude_md_is_sanitized():
    """The committed CLAUDE.md must NOT carry the private orchestration
    block (external-audit P0). The full block is generated into a gitignored
    CLAUDE.local.md and auto-loaded locally."""
    text = CLAUDE_MD.read_text(encoding="utf-8")
    assert "<!-- otaman:begin -->" not in text
    assert "## Otaman Orchestration Rules" not in text
    assert "### Agent Status (REQUIRED)" not in text
