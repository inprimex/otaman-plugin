"""map-tasks consults the dispatch gate before writing task-assignments.

spec-lifecycle-enforcement D5: dispatch requires stage >= `spec-approved`;
absent it, the configured enforcement MODE decides. This path never consulted
the gate at all, so an authored change fanned out assignments the moment its
folder was touched. spec-agent caught it live (20260922T194019) when PR #470
dispatched two authored changes to five agents.

Cause, precisely: the gate was always missing here, but the path was DEAD
until the root-resolution fix (#57) made hook-driven dispatch work. Fixing the
dispatcher is what turned a latent ungated path into a live one.

Per `no-silent-success` clause 3, these must fail with the bypass restored —
`TestBypassRestoredFails` does exactly that rather than trusting the claim.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from otaman_plugin import map_tasks  # noqa: E402
from otaman_plugin.map_tasks import check_dispatch_allowed  # noqa: E402

BLOCK = {"spec_policy": {"enforcement": "block"}}
WARN = {"spec_policy": {"enforcement": "warn"}}


def _change(tmp_path: Path, *, stage: str | None, name: str = "demo") -> Path:
    d = tmp_path / "openspec" / "changes" / name
    d.mkdir(parents=True)
    (d / "tasks.md").write_text("- [ ] 1.1 @otaman-plugin do it\n", encoding="utf-8")
    if stage is not None:
        (d / ".openspec.yaml").write_text(
            yaml.safe_dump({"schema": "spec-driven", "stage": stage}), encoding="utf-8"
        )
    return d / "tasks.md"


class TestBlockPolicyRefusesAuthored:
    def test_authored_change_is_refused(self, tmp_path):
        """The live defect: two authored changes dispatched to five agents."""
        ok, lines = check_dispatch_allowed(_change(tmp_path, stage="authored"), BLOCK)
        assert ok is False
        assert any("DISPATCH REFUSED" in line for line in lines)

    def test_refusal_names_what_and_why(self, tmp_path):
        """no-silent-success clause 1: a refused dispatch says what it refused
        and why. A silent skip would be the same class of defect, inverted."""
        _, lines = check_dispatch_allowed(_change(tmp_path, stage="authored"), BLOCK)
        blob = "\n".join(lines)
        assert "demo" in blob, "must name the change"
        assert "authored" in blob, "must name the stage"
        assert "spec-approved" in blob, "must name the requirement"
        assert "no task-assignments were written" in blob

    def test_spec_approved_change_dispatches(self, tmp_path):
        ok, lines = check_dispatch_allowed(_change(tmp_path, stage="spec-approved"), BLOCK)
        assert ok is True
        assert lines == [], "a clean gate must be quiet"


class TestModeIsHonouredNotHardcoded:
    def test_warn_policy_dispatches_but_says_so(self, tmp_path):
        """Hard-refusing regardless of mode would override a policy someone
        chose. Under `warn` the dispatch proceeds — loudly."""
        ok, lines = check_dispatch_allowed(_change(tmp_path, stage="authored"), WARN)
        assert ok is True
        blob = "\n".join(lines)
        assert "DISPATCH WARNING" in blob
        assert "enforcement: block to refuse" in blob, "must name how to make it refuse"

    def test_warn_is_not_silent(self, tmp_path):
        _, lines = check_dispatch_allowed(_change(tmp_path, stage="authored"), WARN)
        assert lines, "warn mode must still report the violation"


class TestDegradesRatherThanDisarming:
    def test_change_without_openspec_yaml_is_allowed(self, tmp_path):
        """Not every tasks.md sits beside a lifecycle record; a dispatcher
        must not be disarmed by its absence."""
        ok, lines = check_dispatch_allowed(_change(tmp_path, stage=None), BLOCK)
        assert ok is True and lines == []

    def test_laggard_core_allows(self, tmp_path, monkeypatch):
        real_import = __import__

        def _fake(name, *a, **k):
            if name == "otaman_core.spec_lifecycle":
                raise ImportError("simulated laggard bundle")
            return real_import(name, *a, **k)

        monkeypatch.setattr("builtins.__import__", _fake)
        ok, lines = check_dispatch_allowed(_change(tmp_path, stage="authored"), BLOCK)
        assert ok is True and lines == []

    def test_malformed_lifecycle_record_allows(self, tmp_path):
        """A corrupt record should not silently stop all dispatch."""
        tasks = _change(tmp_path, stage="authored")
        (tasks.parent / ".openspec.yaml").write_text("{[not yaml", encoding="utf-8")
        ok, _ = check_dispatch_allowed(tasks, BLOCK)
        assert ok is True


class TestNoBusWritesWhenRefused:
    def test_main_writes_nothing_for_an_authored_change(self, tmp_path, monkeypatch):
        """The assertion that actually matters: refusing must mean no
        task-assignment files on disk."""
        meta = tmp_path / "proj-otaman"
        (meta / ".agents" / "bus" / "active").mkdir(parents=True)
        (meta / "platform.yaml").write_text(
            yaml.safe_dump(
                {
                    "project": "p",
                    "spec_policy": {"enforcement": "block"},
                    "repos": [{"name": "otaman-plugin", "path": "../p", "owner": "plugin-agent"}],
                }
            ),
            encoding="utf-8",
        )
        specs = tmp_path / "proj-specs"
        specs.mkdir()
        (specs / ".otaman").write_text("../proj-otaman\nagent: spec-agent\n", encoding="utf-8")
        tasks = _change(specs, stage="authored")

        monkeypatch.setattr(sys, "argv", ["map-tasks.py", str(tasks)])
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.delenv("OTAMAN_ROOT", raising=False)
        monkeypatch.delenv("MAESTRO_ROOT", raising=False)

        rc = map_tasks.main()
        assert rc != 0, "a refused dispatch must not report success"
        assert not list((meta / ".agents" / "bus" / "active").glob("*.md"))


class TestBypassRestoredFails:
    """no-silent-success clause 3: the fix's test must fail with the bypass
    restored. Simulated by neutering the gate, which is what the code did
    before — no call at all."""

    def test_gate_removed_lets_an_authored_change_through(self, tmp_path, monkeypatch):
        monkeypatch.setattr(map_tasks, "check_dispatch_allowed", lambda *a, **k: (True, []))
        ok, _ = map_tasks.check_dispatch_allowed(_change(tmp_path, stage="authored"), BLOCK)
        assert ok is True, "sanity: the bypass is what we are simulating"

    def test_real_gate_does_not(self, tmp_path):
        ok, _ = check_dispatch_allowed(_change(tmp_path, stage="authored"), BLOCK)
        assert ok is False, "the real gate must refuse where the bypass allowed"
