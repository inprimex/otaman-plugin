"""Regression test for `agent-status-presence` task 2.4.

The `## Agent Status (REQUIRED)` block must be present in BOTH:

- `otaman-plugin/CLAUDE.md` (this repo's own canonical doc)
- `otaman-plugin/src/otaman_plugin/generate_agent_config.py` (the
  template used to scaffold every otaman-managed repo's CLAUDE.md)

If the block lives in one but not the other, the next time
`otaman init` regenerates CLAUDE.md the rule will silently disappear —
exactly the failure mode `core-agent` warned about in
`20260609T145334-core-agent-to-plugin-agent-fyi-agent-status-presence-generator-temp`.

This test pins the two copies together so any future drift fails
loudly during CI.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
CLAUDE_MD = REPO_ROOT / "CLAUDE.md"
GENERATOR = REPO_ROOT / "src" / "otaman_plugin" / "generate_agent_config.py"

# The literal lines we require to appear in both files. We do NOT pin the
# full block — small wording tweaks to the explanatory line are fine —
# but the load-bearing CLI signatures and section heading must match.
_REQUIRED_LINES = [
    "### Agent Status (REQUIRED)",
    'otaman set-status working --task "<N.M task description>" --change <change-name>',
    'otaman set-status waiting --task "<N.M ...>" --change <change-name>',
    "otaman set-status idle",
]


@pytest.mark.parametrize(
    "path",
    [CLAUDE_MD, GENERATOR],
    ids=["claude_md", "generator_template"],
)
def test_agent_status_block_present(path: Path):
    """Both the live CLAUDE.md and the generator template carry the rule."""
    assert path.is_file(), f"{path} missing"
    text = path.read_text(encoding="utf-8")
    for line in _REQUIRED_LINES:
        assert line in text, (
            f"{path.name}: '{line}' missing from the Agent Status block. "
            "If you intentionally moved the section, update _REQUIRED_LINES "
            "in this test."
        )


def test_required_lines_appear_in_same_order_in_both():
    """The CLI signatures appear in the same intent order in both copies.

    Catches the case where the block is present in both files but the
    order of working / waiting / idle has been shuffled out of sync —
    a subtle drift that the per-file test above can't see.
    """
    claude = CLAUDE_MD.read_text(encoding="utf-8")
    gen = GENERATOR.read_text(encoding="utf-8")
    for line in _REQUIRED_LINES:
        claude_idx = claude.index(line)
        gen_idx = gen.index(line)
        assert claude_idx >= 0 and gen_idx >= 0
    # Walk the four required lines in CLAUDE.md and ensure their relative
    # order matches the order in the generator template.
    claude_positions = [claude.index(line) for line in _REQUIRED_LINES]
    gen_positions = [gen.index(line) for line in _REQUIRED_LINES]
    assert claude_positions == sorted(claude_positions), (
        "CLAUDE.md Agent Status lines out of canonical order"
    )
    assert gen_positions == sorted(gen_positions), (
        "Generator template Agent Status lines out of canonical order"
    )
