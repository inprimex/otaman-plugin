"""Regression test: the spec-authoring guard lives in the scaffold TEMPLATE.

History (cofounder-agent task 20260816T202237): the guard was originally
hand-added to bridge's CLAUDE.md (their PR #14) INSIDE the otaman:begin/end
scaffold-managed block. The July scaffold re-sync regenerated that block
from the template — which never contained the guard — and silently dropped
it (re-landed by bridge PR #44). Until the guard is part of the template
itself, every re-sync destroys it again in every repo that received it.

This test pins the guard text into generate_agent_config.py so template
drift fails loudly in CI — same pattern as
test_agent_status_claude_md_sync.py.
"""

from __future__ import annotations

from pathlib import Path

from otaman_plugin.generate_agent_config import _SPEC_AUTHORING_GUARD

REPO_ROOT = Path(__file__).resolve().parent.parent
GENERATOR = REPO_ROOT / "src" / "otaman_plugin" / "generate_agent_config.py"

# Load-bearing lines; small wording tweaks elsewhere are fine.
_REQUIRED_LINES = [
    "### Spec Authoring — NOT your job (CRITICAL)",
    "**spec-agent authors ALL spec artifacts**",
    "**Your only spec action is `/otaman:propose`**",
]


def test_guard_constant_carries_required_lines():
    for line in _REQUIRED_LINES:
        assert line in _SPEC_AUTHORING_GUARD, f"guard constant missing: {line!r}"


def test_guard_is_interpolated_into_both_specs_section_variants():
    """Both specs_section template variants (openspec and plain) must embed
    the guard — a re-sync of ANY managed repo's CLAUDE.md regenerates from
    one of these two f-strings."""
    source = GENERATOR.read_text(encoding="utf-8")
    assert source.count("{_SPEC_AUTHORING_GUARD}") >= 2, (
        "the guard must be interpolated into both specs_section variants; "
        "found fewer than 2 interpolation sites"
    )
