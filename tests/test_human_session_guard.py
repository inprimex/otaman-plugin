"""interactive-human-console 3.1: every generated agent's orchestration rules
(CLAUDE.local.md) MUST carry the mandatory prohibition on injecting input into
human sessions.

Spec: interactive-console — "human console sessions SHALL be isolated from
fleet input injection ... fleet agents SHALL NOT send input (`tmux send-keys`
or equivalent) to human sessions — a mandatory fleet policy propagated through
generated agent orchestration rules", with the scenario "agent rules carry the
prohibition" (for ANY fleet agent).

Pins the load-bearing lines so a future template edit can't silently drop the
policy — same convention as test_spec_authoring_guard_template.py.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
gen = importlib.import_module("otaman_plugin.generate_agent_config")

_REPO = {"name": "backend", "path": "./backend", "owner": "dev-agent"}


def _block() -> str:
    return gen._build_maestro_block(_REPO, [_REPO], ".agents/bus", {}, None)


def test_guard_constant_carries_load_bearing_lines():
    g = gen._HUMAN_SESSION_GUARD
    assert "### Human sessions — NEVER inject input (CRITICAL)" in g
    assert "tmux send-keys" in g
    # the "or equivalent" breadth must be stated so it isn't read as tmux-only
    assert "equivalent" in g
    assert "mandatory fleet policy" in g
    # interaction with humans is bus-only
    assert "ONLY through the bus" in g


def test_prohibition_is_rendered_for_any_agent():
    """Scenario 'agent rules carry the prohibition' — unconditional: it must
    appear even with an empty config and no project_root."""
    block = _block()
    assert "NEVER inject" in block
    assert "tmux send-keys" in block
    assert "private tmux server" in block


def test_guard_is_interpolated_in_the_template():
    """Guard against a silent drop: the constant must be wired into the block
    template, not just defined."""
    source = (
        Path(__file__).resolve().parent.parent
        / "src"
        / "otaman_plugin"
        / "generate_agent_config.py"
    ).read_text(encoding="utf-8")
    assert "{_HUMAN_SESSION_GUARD}" in source
