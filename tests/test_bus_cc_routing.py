"""Tests for bus-cc-routing — CC field parsing, routing rule evaluator,
and CC fan-out in ``otaman_send`` (bus-cc-routing tasks 1.1-1.6).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml


from otaman_plugin.servers.bus_server import (  # noqa: E402
    _compute_effective_cc,
    _inject_x_cc,
    _parse_cc_field,
    _parse_frontmatter,
    evaluate_routing_rules,
    otaman_send,
)


# ---------------------------------------------------------------------------
# Task 1.1 — cc field parsing
# ---------------------------------------------------------------------------

class TestParseCcField:
    def test_inline_list(self):
        text = "---\nfrom: x\ncc: [a, b, c]\nto: y\n---\n\nbody"
        assert _parse_cc_field(text) == ["a", "b", "c"]

    def test_block_list(self):
        text = "---\nfrom: x\ncc:\n  - a\n  - b\nto: y\n---\n\nbody"
        assert _parse_cc_field(text) == ["a", "b"]

    def test_absent_returns_empty(self):
        text = "---\nfrom: x\nto: y\n---\n\nbody"
        assert _parse_cc_field(text) == []

    def test_inline_empty_returns_empty(self):
        text = "---\nfrom: x\ncc: []\nto: y\n---\n\nbody"
        assert _parse_cc_field(text) == []

    def test_quoted_values_unquoted(self):
        text = '---\nfrom: x\ncc: ["a", "b"]\nto: y\n---\n\nbody'
        assert _parse_cc_field(text) == ["a", "b"]


# ---------------------------------------------------------------------------
# Task 1.3 — routing rule evaluator
# ---------------------------------------------------------------------------

class TestEvaluateRoutingRules:
    def test_no_rules_returns_empty(self):
        assert evaluate_routing_rules([], "human", "normal") == set()

    def test_single_matching_rule(self):
        rules = [{"when": {"to": "human"}, "cc": ["spec-agent"]}]
        assert evaluate_routing_rules(rules, "human", "normal") == {"spec-agent"}

    def test_no_match_returns_empty(self):
        rules = [{"when": {"to": "human"}, "cc": ["spec-agent"]}]
        assert evaluate_routing_rules(rules, "runner-agent", "normal") == set()

    def test_multiple_matching_rules_union(self):
        rules = [
            {"when": {"to": "human"}, "cc": ["spec-agent"]},
            {"when": {"to": "human"}, "cc": ["cpo-agent"]},
        ]
        assert evaluate_routing_rules(rules, "human", "normal") == {
            "spec-agent",
            "cpo-agent",
        }

    def test_priority_exact_match(self):
        rules = [
            {"when": {"to": "human", "priority": "urgent"}, "cc": ["cpo-agent"]},
        ]
        assert evaluate_routing_rules(rules, "human", "urgent") == {"cpo-agent"}
        assert evaluate_routing_rules(rules, "human", "normal") == set()

    def test_priority_list_or(self):
        rules = [
            {
                "when": {"to": "human", "priority": ["high", "urgent"]},
                "cc": ["cpo-agent"],
            }
        ]
        assert evaluate_routing_rules(rules, "human", "high") == {"cpo-agent"}
        assert evaluate_routing_rules(rules, "human", "urgent") == {"cpo-agent"}
        assert evaluate_routing_rules(rules, "human", "normal") == set()

    def test_all_matching_contribute(self):
        # Two rules both matching to: human; one priority-gated, one not.
        # Both contribute (not first-match-wins).
        rules = [
            {"when": {"to": "human"}, "cc": ["spec-agent"]},
            {"when": {"to": "human", "priority": ["high", "urgent"]}, "cc": ["cpo-agent"]},
        ]
        assert evaluate_routing_rules(rules, "human", "high") == {
            "spec-agent",
            "cpo-agent",
        }
        # When priority doesn't match the gated rule, only the unconditional one fires.
        assert evaluate_routing_rules(rules, "human", "normal") == {"spec-agent"}

    def test_unknown_when_key_skips_rule(self):
        # Forward-compat: unknown `when` keys cause the rule to be ignored.
        rules = [
            {"when": {"to": "human", "from": "runner-agent"}, "cc": ["spec-agent"]},
        ]
        assert evaluate_routing_rules(rules, "human", "normal") == set()


# ---------------------------------------------------------------------------
# Task 1.3 cont. — primary recipient excluded from CC (via _compute_effective_cc)
# ---------------------------------------------------------------------------

class TestComputeEffectiveCc:
    def test_primary_excluded_even_when_in_rule(self):
        rules = [{"when": {"to": "human"}, "cc": ["spec-agent", "human"]}]
        result = _compute_effective_cc("human", "normal", None, rules)
        assert "human" not in result
        assert "spec-agent" in result

    def test_primary_excluded_when_in_explicit_cc(self):
        result = _compute_effective_cc(
            "human", "normal", ["spec-agent", "human"], []
        )
        assert result == ["spec-agent"]

    def test_explicit_and_rule_unioned_and_deduped(self):
        rules = [{"when": {"to": "human"}, "cc": ["spec-agent", "cpo-agent"]}]
        result = _compute_effective_cc(
            "human", "normal", ["spec-agent", "deploy-agent"], rules
        )
        assert sorted(result) == ["cpo-agent", "deploy-agent", "spec-agent"]
        # Explicit recipients are listed first so the on-disk shape is
        # deterministic — explicit ordering, then rule-derived in sorted order
        assert result.index("deploy-agent") < result.index("cpo-agent")

    def test_no_cc_anywhere_returns_empty(self):
        assert _compute_effective_cc("human", "normal", None, []) == []
        assert _compute_effective_cc("human", "normal", [], []) == []


# ---------------------------------------------------------------------------
# Task 1.4 — x-cc injection
# ---------------------------------------------------------------------------

class TestInjectXCc:
    def test_x_cc_appended_to_frontmatter(self):
        content = "---\nfrom: x\nto: y\n---\n\nbody\n"
        out = _inject_x_cc(content)
        assert "x-cc: true" in out
        # The body is untouched
        assert out.endswith("body\n")
        # Frontmatter is still well-formed
        m = _parse_frontmatter(out)
        assert m["x-cc"] == "true"
        assert m["from"] == "x"
        assert m["to"] == "y"

    def test_original_string_not_mutated(self):
        content = "---\nfrom: x\nto: y\n---\n\nbody\n"
        _inject_x_cc(content)
        assert "x-cc" not in content


# ---------------------------------------------------------------------------
# Task 1.6 — integration test: full otaman_send fan-out path
# ---------------------------------------------------------------------------

@pytest.fixture
def workspace(tmp_path, monkeypatch):
    """Build a sibling-layout project: otaman folder + a repo with .otaman marker.

    Patches HOME so the .otaman marker passes the safe-path check in
    ``otaman_core._resolve``.
    """
    monkeypatch.setenv("HOME", str(tmp_path))

    otaman = tmp_path / "my-otaman"
    otaman.mkdir()
    agents_dir = otaman / ".agents"
    agents_dir.mkdir()

    # platform.yaml carries the routing rules under test
    platform_data = {
        "project": "test",
        "version": "1.0",
        "bus": {
            "routing_rules": [
                {"when": {"to": "human"}, "cc": ["spec-agent"]},
                {
                    "when": {"to": "human", "priority": ["high", "urgent"]},
                    "cc": ["cpo-agent"],
                },
            ]
        },
    }
    (otaman / "platform.yaml").write_text(yaml.dump(platform_data), encoding="utf-8")

    # Sender repo with explicit agent: identity
    repo = tmp_path / "repo-runner"
    repo.mkdir()
    (repo / ".otaman").write_text(
        "otaman_root: ../my-otaman\nagent: runner-agent\n", encoding="utf-8"
    )

    return {"root": tmp_path, "otaman": otaman, "repo": repo}


def _read_msg(path: Path) -> dict[str, str]:
    return _parse_frontmatter(path.read_text(encoding="utf-8"))


class TestIntegrationFanOut:
    def test_primary_recipient_no_x_cc_cc_copies_have_it(self, workspace):
        result = otaman_send.fn(
            cwd=str(workspace["repo"]),
            to="human",
            subject="urgent thing",
            body="see me",
            priority="urgent",
        )
        assert result["sent"] is True
        bus = workspace["otaman"] / ".agents" / "bus" / "active"
        files = list(bus.glob("*.md"))
        # 1 primary + 2 CC copies (spec-agent + cpo-agent both match the rules)
        assert len(files) == 3

        primary = next(f for f in files if "-cc-" not in f.name)
        cc_spec = next(f for f in files if "-cc-spec-agent-" in f.name)
        cc_cpo = next(f for f in files if "-cc-cpo-agent-" in f.name)

        primary_fm = _read_msg(primary)
        assert primary_fm["to"] == "human"
        assert primary_fm.get("x-cc", "") != "true"
        # Primary still carries the cc: list so the human can see who else got copies
        assert _parse_cc_field(primary.read_text(encoding="utf-8")) in (
            ["spec-agent", "cpo-agent"],
            ["cpo-agent", "spec-agent"],
        )

        for cc_file in (cc_spec, cc_cpo):
            fm = _read_msg(cc_file)
            assert fm["to"] == "human"
            assert fm["x-cc"] == "true"

    def test_no_routing_rule_match_no_cc_copies(self, workspace):
        result = otaman_send.fn(
            cwd=str(workspace["repo"]),
            to="cli-agent",     # rules target "human" only — no match here
            subject="hello",
            body="hi",
            priority="normal",
        )
        assert result["sent"] is True
        assert "cc" not in result
        bus = workspace["otaman"] / ".agents" / "bus" / "active"
        files = list(bus.glob("*.md"))
        assert len(files) == 1
        assert "-cc-" not in files[0].name
        # Primary carries no cc: field at all
        assert _parse_cc_field(files[0].read_text(encoding="utf-8")) == []

    def test_priority_rule_only_fires_when_priority_matches(self, workspace):
        # Normal-priority to:human → only the unconditional rule (spec-agent) fires
        result = otaman_send.fn(
            cwd=str(workspace["repo"]),
            to="human",
            subject="routine",
            body=".",
            priority="normal",
        )
        assert result["cc"] == ["spec-agent"]
        bus = workspace["otaman"] / ".agents" / "bus" / "active"
        files = list(bus.glob("*.md"))
        assert len(files) == 2  # primary + 1 CC
        cc_file = next(f for f in files if "-cc-" in f.name)
        assert "-cc-spec-agent-" in cc_file.name

    def test_explicit_cc_unioned_with_rule_cc(self, workspace):
        result = otaman_send.fn(
            cwd=str(workspace["repo"]),
            to="human",
            subject="combined",
            body=".",
            priority="urgent",
            cc=["deploy-agent"],
        )
        assert set(result["cc"]) == {"deploy-agent", "spec-agent", "cpo-agent"}
        bus = workspace["otaman"] / ".agents" / "bus" / "active"
        files = list(bus.glob("*.md"))
        assert len(files) == 4  # primary + 3 CC

    def test_primary_excluded_when_listed_in_routing_rule(self, tmp_path, monkeypatch):
        """If a routing rule names the primary `to` recipient, they must not
        receive a CC copy of their own message."""
        monkeypatch.setenv("HOME", str(tmp_path))
        otaman = tmp_path / "om"
        otaman.mkdir()
        (otaman / ".agents").mkdir()
        platform_data = {
            "project": "test",
            "version": "1.0",
            "bus": {
                "routing_rules": [
                    # Rule includes human, which is also the primary recipient
                    {"when": {"to": "human"}, "cc": ["spec-agent", "human"]}
                ]
            },
        }
        (otaman / "platform.yaml").write_text(yaml.dump(platform_data), encoding="utf-8")
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / ".otaman").write_text(
            "otaman_root: ../om\nagent: runner-agent\n", encoding="utf-8"
        )

        result = otaman_send.fn(
            cwd=str(repo),
            to="human",
            subject="x",
            body=".",
            priority="normal",
        )
        # Only spec-agent in effective CC — human (== primary) was excluded
        assert result["cc"] == ["spec-agent"]
        bus = otaman / ".agents" / "bus" / "active"
        files = list(bus.glob("*.md"))
        # Exactly 2 files: primary + CC to spec-agent, NOT a CC to human
        assert len(files) == 2
        assert not any("-cc-human-" in f.name for f in files)
