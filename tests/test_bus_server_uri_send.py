"""single-bus-per-program 2.1-2.3 MCP parity — otaman_send URI targets.

Mirrors otaman-cli's tests/test_bus_uri_send.py end-to-end matrix at the
MCP layer: the three input forms, cross-program delivery into the TARGET
program's bus, fail-closed `bus.boundaries` enforcement, cross-org
rejection, and schema-v2 envelope projections. The resolution layer
itself (derive_local_context / resolve_target_program_root /
check_boundaries) is unit-tested in otaman-cli, which owns it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from otaman_plugin.servers.bus_server import otaman_send

_send = otaman_send.fn


def _mk_program(org_root: Path, program: str, meta_name: str | None = None) -> Path:
    meta = org_root / "programs" / program / (meta_name or f"{program}-otaman")
    (meta / ".agents" / "bus" / "active" / "acks").mkdir(parents=True)
    (meta / "platform.yaml").write_text(f"project: {program}\nrepos: []\n", encoding="utf-8")
    return meta


def _grant(meta: Path, yaml_block: str) -> None:
    platform = meta / "platform.yaml"
    platform.write_text(platform.read_text(encoding="utf-8") + yaml_block, encoding="utf-8")


ALPHA_GRANT = "bus:\n  boundaries:\n    allow_from:\n      - program: alpha\n"


@pytest.fixture(autouse=True)
def _isolate_env(tmp_path, monkeypatch):
    # Root resolution is marker → env → walk-up; a developer shell's
    # OTAMAN_ROOT/MAESTRO_ROOT would silently redirect every send in these
    # tests to the real workspace bus. Strip them for isolation.
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("OTAMAN_ROOT", raising=False)
    monkeypatch.delenv("MAESTRO_ROOT", raising=False)


@pytest.fixture
def org(tmp_path: Path) -> Path:
    org_root = tmp_path / "orgs" / "acme"
    org_root.mkdir(parents=True)
    return org_root


@pytest.fixture
def sender_root(org: Path) -> Path:
    meta = _mk_program(org, "alpha")
    (meta / ".otaman").write_text("agent: plugin-agent\n", encoding="utf-8")
    return meta


@pytest.fixture
def legacy_root(tmp_path: Path) -> Path:
    """A project outside the orgs/<org>/programs/<program> layout."""
    meta = tmp_path / "legacy-meta"
    (meta / ".agents" / "bus" / "active" / "acks").mkdir(parents=True)
    (meta / "platform.yaml").write_text("project: legacy\nrepos: []\n", encoding="utf-8")
    (meta / ".otaman").write_text("agent: plugin-agent\n", encoding="utf-8")
    return meta


def _messages(meta: Path) -> list[Path]:
    return sorted((meta / ".agents" / "bus" / "active").glob("*.md"))


def _sole_message(meta: Path) -> str:
    msgs = _messages(meta)
    assert len(msgs) == 1, [m.name for m in msgs]
    return msgs[0].read_text(encoding="utf-8")


class TestBareNames:
    def test_bare_name_send_unchanged_plus_uri_fields(self, sender_root):
        result = _send(cwd=str(sender_root), to="spec-agent", subject="hello there", body="b")
        assert result.get("sent") is True
        assert result["to"] == "spec-agent"
        assert result["to_uri"] == "otaman://acme/alpha/spec-agent"
        body = _sole_message(sender_root)
        assert "to: spec-agent\n" in body
        assert "to-uri: otaman://acme/alpha/spec-agent\n" in body
        assert "from-uri: otaman://acme/alpha/plugin-agent\n" in body
        assert "from_org: acme\n" in body
        assert "to_org: acme\n" in body

    def test_bare_name_outside_layout_keeps_legacy_envelope(self, legacy_root):
        result = _send(cwd=str(legacy_root), to="spec-agent", subject="hello", body="b")
        assert result.get("sent") is True
        assert "to_uri" not in result
        body = _sole_message(legacy_root)
        assert "to: spec-agent\n" in body
        assert "to-uri:" not in body and "from_org:" not in body

    def test_slug_grammar_reject_falls_back_to_legacy(self, sender_root):
        # Historical comma-list recipient: not a valid segment, not an
        # addressed form — must keep exact legacy behavior, no URI fields.
        result = _send(cwd=str(sender_root), to="spec-agent,cli-agent", subject="hello", body="b")
        assert result.get("sent") is True
        assert "to_uri" not in result
        assert "to-uri:" not in _sole_message(sender_root)


class TestCrossProgram:
    def test_shorthand_delivers_into_target_bus(self, sender_root, org):
        target = _mk_program(org, "beta")
        _grant(target, ALPHA_GRANT)
        result = _send(cwd=str(sender_root), to="pm-agent@beta", subject="hello", body="b")
        assert result.get("sent") is True, result
        assert result["to"] == "pm-agent"
        assert result["to_uri"] == "otaman://acme/beta/pm-agent"
        assert result["delivered_program_root"] == str(target)
        # Nothing written locally; one copy in the target's own bus
        assert _messages(sender_root) == []
        body = _sole_message(target)
        assert "to: pm-agent\n" in body
        assert "to-uri: otaman://acme/beta/pm-agent\n" in body
        assert "from-uri: otaman://acme/alpha/plugin-agent\n" in body
        assert "to_org: acme\n" in body

    def test_full_uri_form_delivers(self, sender_root, org):
        target = _mk_program(org, "beta")
        _grant(target, ALPHA_GRANT)
        result = _send(
            cwd=str(sender_root), to="otaman://acme/beta/pm-agent", subject="hi", body="b"
        )
        assert result.get("sent") is True, result
        assert "to: pm-agent\n" in _sole_message(target)

    def test_refused_without_grant(self, sender_root, org):
        target = _mk_program(org, "beta")  # no boundaries declared
        result = _send(cwd=str(sender_root), to="pm-agent@beta", subject="hi", body="b")
        assert "error" in result
        assert "no bus.boundaries.allow_from grant" in result["error"]
        assert _messages(target) == [] and _messages(sender_root) == []

    def test_agent_narrowing_refuses_unlisted_sender(self, sender_root, org):
        target = _mk_program(org, "beta")
        _grant(
            target,
            "bus:\n  boundaries:\n    allow_from:\n"
            "      - program: alpha\n        agents: [spec-agent]\n",
        )
        result = _send(cwd=str(sender_root), to="pm-agent@beta", subject="hi", body="b")
        assert "error" in result
        assert "fall outside the grant" in result["error"]
        assert _messages(target) == []

    def test_unresolvable_program_refused_no_walkup(self, sender_root, org):
        # A program with a perfectly good .agents root under a
        # non-conventional meta name is unreachable: declarations only.
        _mk_program(org, "delta", meta_name="weird-name")
        result = _send(cwd=str(sender_root), to="pm-agent@delta", subject="hi", body="b")
        assert "error" in result
        assert "cannot resolve program 'delta'" in result["error"]

    def test_explicit_cc_written_in_target_bus(self, sender_root, org):
        target = _mk_program(org, "beta")
        _grant(target, ALPHA_GRANT)
        result = _send(
            cwd=str(sender_root),
            to="pm-agent@beta",
            subject="hello",
            body="b",
            cc=["qa-agent"],
        )
        assert result.get("sent") is True, result
        names = [p.name for p in _messages(target)]
        assert len(names) == 2
        assert any("-cc-qa-agent-" in n for n in names)
        assert _messages(sender_root) == []


class TestCrossOrgAndErrors:
    def test_cross_org_rejected_naming_foreign_org(self, sender_root):
        result = _send(
            cwd=str(sender_root), to="otaman://contoso/site/ops-agent", subject="hi", body="b"
        )
        assert "error" in result
        assert "cross-org routing not yet implemented" in result["error"]
        assert "contoso" in result["error"]
        assert _messages(sender_root) == []

    def test_cross_program_form_outside_layout_errors(self, legacy_root):
        result = _send(cwd=str(legacy_root), to="pm-agent@beta", subject="hi", body="b")
        assert "error" in result
        assert "declared org layout" in result["error"]
        assert _messages(legacy_root) == []

    def test_malformed_uri_errors(self, sender_root):
        result = _send(cwd=str(sender_root), to="otaman://acme/beta", subject="hi", body="b")
        assert "error" in result
        assert "Invalid target address" in result["error"]
