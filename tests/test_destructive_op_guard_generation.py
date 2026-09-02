"""destructive-op-guard 2.1: generated CLAUDE.local.md carries a paragraph
stating the guard exists, its two classes, and that confirmation is
per-turn (so agents don't misread the "ask" prompt as an error).

Drop-guard convention (matches test_policy_generation.py's
test_policy_section_is_wired_into_the_template): the paragraph is static
and unconditional — every repo gets it, no policy resolution involved — so
a source-text presence check is proportionate; it protects against a
future template edit silently dropping the note.
"""

from __future__ import annotations

from pathlib import Path

GENERATOR = (
    Path(__file__).resolve().parent.parent / "src" / "otaman_plugin" / "generate_agent_config.py"
)


def test_destructive_op_guard_note_is_present_in_the_template():
    source = GENERATOR.read_text(encoding="utf-8")
    assert "### Destructive-operation guard" in source
    assert "PreToolUse" in source
    assert "fresh, explicit confirmation" in source
    assert "publish/merge" in source
    assert "working-tree-destructive" in source
    assert "not an error" in source
    assert "destructive-op-patterns.local" in source
