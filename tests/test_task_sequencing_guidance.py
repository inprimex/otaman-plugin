"""task-sequencing-contract 2.1: the generated orchestration block (written
to CLAUDE.local.md) must teach the coordination contract — the five
sections, the mandatory four-field frontmatter, and STOP-AT discipline —
matching otaman-cli's validation grammar (sequence step 5/5, spec-agent
20260819T204810). Pinning the load-bearing elements so the guidance can't
silently drop on a future template edit.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
gen_config = importlib.import_module("otaman_plugin.generate_agent_config")

_REPO = {"name": "backend", "path": "./backend", "owner": "dev-agent"}


def _block() -> str:
    return gen_config._build_maestro_block(_REPO, [_REPO], ".agents/bus", {}, None)


def test_teaches_all_five_coordination_sections():
    blk = _block()
    for section in ("## Sequence", "## Your step", "## Handoff", "## Context", "## Artifacts"):
        assert section in blk, f"guidance missing section: {section}"


def test_teaches_all_four_frontmatter_fields():
    blk = _block()
    # Field names must match otaman_cli.sequencing.SEQ_FIELDS exactly.
    for field in ("sequence-id", "step: <n>/<m>", "depends-on", "stop-at"):
        assert field in blk, f"guidance missing frontmatter field: {field}"


def test_teaches_sections_and_frontmatter_travel_together():
    blk = _block()
    assert "MUST carry BOTH" in blk
    assert "malformed" in blk


def test_teaches_stop_at_discipline_and_exemption():
    blk = _block()
    assert "STOP-AT discipline" in blk
    assert "do NOT begin a later step" in blk
    # The single-task exemption must be stated so the contract doesn't tax
    # the common case.
    assert "Single-task assignments" in blk


def test_teaches_check_waiting_annotation():
    blk = _block()
    assert "waiting on step N (owner)" in blk


def test_send_form_names_the_sequencing_flags():
    blk = _block()
    for flag in ("--sequence-id", "--step", "--depends-on", "--stop-at"):
        assert flag in blk, f"send-form guidance missing flag: {flag}"
