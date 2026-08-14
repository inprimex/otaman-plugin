"""Tests for outcome-proposal-routing — type-aware routing rule evaluator
and CC fan-out by ``msg_type`` (tasks 1.1 + 1.2 + 5.1).

Task 1.2 enumerates six required cases:

(a) type-only rule fires for a matching type
(b) type-only rule does not fire for a non-matching type
(c) type + priority rule requires both conditions (AND semantics)
(d) existing to-based rules (no ``type:``) are unaffected
(e) type rule with cc list writes copies to all cc recipients
(f) no cc duplication when multiple rules fire for the same message

Task 5.1 is the full ``otaman init``-seeded → ``otaman_send`` integration
test. Cli-agent's 3.3 / 3.4 (init seeding) is not yet shipped, so the
integration test materialises the seeded ``platform.yaml`` directly — that
mirrors exactly what the seeder will write and keeps this test independent
of cli-agent's land order.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from otaman_plugin.servers.bus_server import (
    _compute_effective_cc,
    _parse_cc_field,
    _parse_frontmatter,
    evaluate_routing_rules,
    otaman_send,
)

# ---------------------------------------------------------------------------
# Task 1.2 (a)-(d) — pure evaluator tests, no filesystem
# ---------------------------------------------------------------------------


class TestTypeAwareRoutingEvaluator:
    def test_a_type_only_rule_fires_for_matching_type(self):
        rules = [
            {"when": {"type": "outcome-proposal"}, "cc": ["cofounder-agent", "cpo-agent"]},
        ]
        assert evaluate_routing_rules(rules, "human", "normal", "outcome-proposal") == {
            "cofounder-agent",
            "cpo-agent",
        }

    def test_b_type_only_rule_does_not_fire_for_non_matching_type(self):
        rules = [
            {"when": {"type": "outcome-proposal"}, "cc": ["cofounder-agent"]},
        ]
        assert evaluate_routing_rules(rules, "human", "normal", "info") == set()
        # And explicitly: no msg_type at all → type-gated rule never fires
        assert evaluate_routing_rules(rules, "human", "normal", None) == set()

    def test_c_type_plus_priority_requires_both(self):
        rules = [
            {
                "when": {"type": "outcome-proposal", "priority": "high"},
                "cc": ["cofounder-agent"],
            },
        ]
        # Both match
        assert evaluate_routing_rules(rules, "human", "high", "outcome-proposal") == {
            "cofounder-agent"
        }
        # Type matches but priority doesn't
        assert evaluate_routing_rules(rules, "human", "normal", "outcome-proposal") == set()
        # Priority matches but type doesn't
        assert evaluate_routing_rules(rules, "human", "high", "info") == set()

    def test_d_existing_to_based_rules_unaffected(self):
        # The legacy bus-cc-routing rule shape — no `type:` in `when:`. With
        # the type-aware evaluator extension these must still fire exactly
        # as they did before. No regression.
        rules = [
            {"when": {"to": "human"}, "cc": ["spec-agent"]},
            {"when": {"to": "human", "priority": "high"}, "cc": ["cpo-agent"]},
        ]
        # No msg_type passed — same call shape callers had before 1.1
        assert evaluate_routing_rules(rules, "human", "normal") == {"spec-agent"}
        assert evaluate_routing_rules(rules, "human", "high") == {
            "spec-agent",
            "cpo-agent",
        }
        # And: passing msg_type alongside still doesn't break legacy rules
        assert evaluate_routing_rules(rules, "human", "high", "outcome-proposal") == {
            "spec-agent",
            "cpo-agent",
        }

    def test_type_list_or_semantics(self):
        # Mirrors the existing priority-list shape — list form means OR
        rules = [
            {
                "when": {"type": ["outcome-proposal", "proposal"]},
                "cc": ["cofounder-agent"],
            },
        ]
        assert evaluate_routing_rules(rules, "human", "normal", "outcome-proposal") == {
            "cofounder-agent"
        }
        assert evaluate_routing_rules(rules, "human", "normal", "proposal") == {"cofounder-agent"}
        assert evaluate_routing_rules(rules, "human", "normal", "info") == set()


# ---------------------------------------------------------------------------
# Task 1.2 (e)-(f) — full otaman_send round-trip
# ---------------------------------------------------------------------------


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    """Sibling-layout project with type-aware routing rules.

    The platform.yaml below is the shape cli-agent's `otaman init` 3.3/3.4
    will seed once a `-business` or `-strategy` repo is detected. Writing
    it directly here keeps the test independent of cli-agent's land order.
    """
    monkeypatch.setenv("HOME", str(tmp_path))

    otaman = tmp_path / "my-otaman"
    otaman.mkdir()
    (otaman / ".agents").mkdir()

    platform_data = {
        "project": "test",
        "version": "1.0",
        "bus": {
            "routing_rules": [
                # The seeded outcome-proposal rule
                {
                    "when": {"type": "outcome-proposal"},
                    "cc": ["cofounder-agent", "cpo-agent"],
                },
                # A pre-existing to-based rule — to verify (d) under fan-out
                {"when": {"to": "human"}, "cc": ["spec-agent"]},
            ]
        },
    }
    (otaman / "platform.yaml").write_text(yaml.dump(platform_data), encoding="utf-8")

    repo = tmp_path / "repo-runner"
    repo.mkdir()
    (repo / ".otaman").write_text(
        "otaman_root: ../my-otaman\nagent: runner-agent\n", encoding="utf-8"
    )

    return {"root": tmp_path, "otaman": otaman, "repo": repo}


def _read_msg(path: Path) -> dict[str, str]:
    return _parse_frontmatter(path.read_text(encoding="utf-8"))


class TestTypeRuleFanOut:
    def test_e_type_rule_with_cc_list_writes_copies_to_all_recipients(self, workspace):
        result = otaman_send.fn(
            cwd=str(workspace["repo"]),
            to="human",
            subject="raise prices 10pct",
            body="see model",
            msg_type="outcome-proposal",
            priority="normal",
        )
        assert result["sent"] is True

        bus = workspace["otaman"] / ".agents" / "bus" / "active"
        files = list(bus.glob("*.md"))
        # Primary + cofounder cc + cpo cc + spec-agent (to-rule still fires)
        # = 1 primary + 3 cc copies
        assert len(files) == 4

        primary = next(f for f in files if "-cc-" not in f.name)
        cc_cofounder = next(f for f in files if "-cc-cofounder-agent-" in f.name)
        cc_cpo = next(f for f in files if "-cc-cpo-agent-" in f.name)
        cc_spec = next(f for f in files if "-cc-spec-agent-" in f.name)

        primary_fm = _read_msg(primary)
        assert primary_fm["to"] == "human"
        assert primary_fm["type"] == "outcome-proposal"
        assert primary_fm.get("x-cc", "") != "true"
        # Primary carries the cc list so the recipient sees who else got copies
        primary_cc = _parse_cc_field(primary.read_text(encoding="utf-8"))
        assert set(primary_cc) == {"cofounder-agent", "cpo-agent", "spec-agent"}

        for cc_file in (cc_cofounder, cc_cpo, cc_spec):
            fm = _read_msg(cc_file)
            assert fm["to"] == "human"
            assert fm["type"] == "outcome-proposal"
            assert fm["x-cc"] == "true"

    def test_f_no_cc_duplication_when_multiple_rules_fire(self, workspace):
        # Two distinct rules both naming the same agent must produce exactly
        # one copy for that agent. We layer a redundant rule onto the
        # workspace's platform.yaml to force the overlap.
        platform = workspace["otaman"] / "platform.yaml"
        data = yaml.safe_load(platform.read_text(encoding="utf-8"))
        data["bus"]["routing_rules"].append(
            # A second outcome-proposal rule that also names cofounder-agent
            {
                "when": {"type": "outcome-proposal", "priority": ["normal", "high"]},
                "cc": ["cofounder-agent", "auditor-agent"],
            }
        )
        platform.write_text(yaml.dump(data), encoding="utf-8")

        result = otaman_send.fn(
            cwd=str(workspace["repo"]),
            to="human",
            subject="another outcome",
            body="dedup me",
            msg_type="outcome-proposal",
            priority="normal",
        )
        assert result["sent"] is True

        bus = workspace["otaman"] / ".agents" / "bus" / "active"
        files = list(bus.glob("*.md"))
        # Unique cc set: cofounder-agent + cpo-agent (rule 1) + spec-agent
        # (rule 2, to-based) + auditor-agent (rule 3). cofounder-agent
        # appears in both rule 1 and rule 3 — must produce exactly one copy.
        # Each file's frontmatter `to:` is the primary, so the
        # disambiguating signal is the filename containing `-cc-<agent>-`.
        # Count occurrences:
        for agent in ("cofounder-agent", "cpo-agent", "spec-agent", "auditor-agent"):
            n = sum(1 for f in files if f"-cc-{agent}-" in f.name)
            assert n == 1, f"{agent} got {n} copies, expected exactly 1"
        assert len([f for f in files if "-cc-" in f.name]) == 4


# ---------------------------------------------------------------------------
# Task 5.1 — integration test: full flow
# ---------------------------------------------------------------------------


class TestOutcomeProposalIntegration:
    def test_full_flow_outcome_proposal_fan_out(self, workspace):
        """End-to-end: with the seeded routing rule in place, sending an
        ``outcome-proposal`` message addressed to ``human`` results in
        copies for the cofounder + cpo agents, and the primary delivery to
        ``human`` is unchanged.
        """
        result = otaman_send.fn(
            cwd=str(workspace["repo"]),
            to="human",
            subject="pivot to vertical X",
            body="business impact: ...",
            msg_type="outcome-proposal",
            priority="normal",
        )
        assert result["sent"] is True

        bus = workspace["otaman"] / ".agents" / "bus" / "active"
        files = sorted(bus.glob("*.md"))

        # Exactly 1 primary
        primaries = [f for f in files if "-cc-" not in f.name]
        assert len(primaries) == 1
        primary = primaries[0]
        primary_fm = _read_msg(primary)
        assert primary_fm["to"] == "human"
        assert primary_fm["from"] == "runner-agent"
        assert primary_fm["type"] == "outcome-proposal"

        # cofounder-agent and cpo-agent each receive a CC copy
        assert any("-cc-cofounder-agent-" in f.name for f in files)
        assert any("-cc-cpo-agent-" in f.name for f in files)

    def test_outcome_proposal_does_not_fan_out_when_no_rule(self, tmp_path, monkeypatch):
        """A workspace without the seeded rule emits only the primary —
        regression guard against accidental fan-out from a hardcoded path.
        """
        monkeypatch.setenv("HOME", str(tmp_path))
        otaman = tmp_path / "my-otaman"
        otaman.mkdir()
        (otaman / ".agents").mkdir()
        (otaman / "platform.yaml").write_text(
            yaml.dump({"project": "x", "version": "1.0"}), encoding="utf-8"
        )
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / ".otaman").write_text(
            "otaman_root: ../my-otaman\nagent: cli-agent\n", encoding="utf-8"
        )

        result = otaman_send.fn(
            cwd=str(repo),
            to="human",
            subject="no rule here",
            body="...",
            msg_type="outcome-proposal",
        )
        assert result["sent"] is True

        bus = otaman / ".agents" / "bus" / "active"
        files = list(bus.glob("*.md"))
        assert len(files) == 1
        assert "-cc-" not in files[0].name


# ---------------------------------------------------------------------------
# Cross-check — pure _compute_effective_cc behavior with msg_type
# ---------------------------------------------------------------------------


class TestComputeEffectiveCcWithType:
    def test_msg_type_plumbed_through(self):
        rules = [
            {"when": {"type": "outcome-proposal"}, "cc": ["cofounder-agent"]},
            {"when": {"to": "human"}, "cc": ["spec-agent"]},
        ]
        # outcome-proposal: both rules fire
        result = _compute_effective_cc("human", "normal", None, rules, msg_type="outcome-proposal")
        assert set(result) == {"cofounder-agent", "spec-agent"}
        # info: only the to-based rule fires
        result = _compute_effective_cc("human", "normal", None, rules, msg_type="info")
        assert result == ["spec-agent"]

    def test_msg_type_none_skips_type_rules(self):
        rules = [
            {"when": {"type": "outcome-proposal"}, "cc": ["cofounder-agent"]},
        ]
        assert _compute_effective_cc("human", "normal", None, rules) == []
