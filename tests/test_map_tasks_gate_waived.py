"""spec-gate-hardening 1.3(c): map_tasks stamps x-gate-waived on dispatched
task-assignments when the dispatching `otaman assign` ran under an active
gate waiver.

Seam agreed with cli-agent (bus msg 20260911T124540): cli's dispatch flow
calls `otaman_plugin.map_tasks.main(...)` in-process (via SCRIPT_MAP —
this module, NOT scripts/map-tasks.py, is the actual frontmatter emitter
for `otaman assign` dispatch). cli sets OTAMAN_GATE_WAIVED=<violation-slug>
before calling in when a waiver is active; absent/empty means no waiver,
the normal case.
"""

from __future__ import annotations

from pathlib import Path

from otaman_plugin.map_tasks import create_bus_messages


def _config():
    return {"communication": {"bus_path": ".agents/bus"}}


def _tasks():
    return [
        {"text": "1.1 do the thing", "owner": "backend-agent", "repo": "api", "done": False},
    ]


def _read_created(project_root: Path, created: list[str]) -> str:
    assert len(created) == 1
    return (project_root / created[0]).read_text(encoding="utf-8")


class TestNoWaiver:
    def test_absent_env_no_stamp(self, tmp_path, monkeypatch):
        monkeypatch.delenv("OTAMAN_GATE_WAIVED", raising=False)
        created = create_bus_messages(tmp_path, _tasks(), "demo-change", _config())
        content = _read_created(tmp_path, created)
        assert "x-gate-waived" not in content

    def test_empty_env_no_stamp(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OTAMAN_GATE_WAIVED", "")
        created = create_bus_messages(tmp_path, _tasks(), "demo-change", _config())
        content = _read_created(tmp_path, created)
        assert "x-gate-waived" not in content


class TestActiveWaiver:
    def test_stamps_slug_in_frontmatter(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OTAMAN_GATE_WAIVED", "not-spec-approved")
        created = create_bus_messages(tmp_path, _tasks(), "demo-change", _config())
        content = _read_created(tmp_path, created)
        assert "x-gate-waived: not-spec-approved" in content
        # Frontmatter, not body — must land between the --- markers.
        frontmatter = content.split("---")[1]
        assert "x-gate-waived: not-spec-approved" in frontmatter

    def test_valid_slug_shape_matches_core_validator(self, tmp_path, monkeypatch):
        """Same slug regex otaman-core's validate_message enforces
        (^[a-z][a-z0-9-]*[a-z0-9]$) — multi-hyphen slugs pass through."""
        monkeypatch.setenv("OTAMAN_GATE_WAIVED", "no-valid-approval")
        created = create_bus_messages(tmp_path, _tasks(), "demo-change", _config())
        content = _read_created(tmp_path, created)
        assert "x-gate-waived: no-valid-approval" in content


class TestMalformedEnvDropped:
    def test_uppercase_rejected(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OTAMAN_GATE_WAIVED", "Not-Spec-Approved")
        created = create_bus_messages(tmp_path, _tasks(), "demo-change", _config())
        content = _read_created(tmp_path, created)
        assert "x-gate-waived" not in content

    def test_leading_digit_rejected(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OTAMAN_GATE_WAIVED", "1-bad-slug")
        created = create_bus_messages(tmp_path, _tasks(), "demo-change", _config())
        content = _read_created(tmp_path, created)
        assert "x-gate-waived" not in content

    def test_trailing_hyphen_rejected(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OTAMAN_GATE_WAIVED", "bad-slug-")
        created = create_bus_messages(tmp_path, _tasks(), "demo-change", _config())
        content = _read_created(tmp_path, created)
        assert "x-gate-waived" not in content

    def test_whitespace_only_treated_as_absent(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OTAMAN_GATE_WAIVED", "   ")
        created = create_bus_messages(tmp_path, _tasks(), "demo-change", _config())
        content = _read_created(tmp_path, created)
        assert "x-gate-waived" not in content
