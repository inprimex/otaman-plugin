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

import pytest
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

    def test_malformed_lifecycle_record_refuses_loudly(self, tmp_path):
        """REVERSED 2026-09-30. This asserted `ok is True` — "a corrupt record
        should not silently stop all dispatch" — and that allowance is what
        let five agents be assigned an unapproved change.

        The original concern was the word SILENTLY, and it still holds: the
        refusal names the parse error and the command that resolves it. What
        does not hold is allowing the dispatch, because under `block` a
        readable bad stage is already refused and an unreadable one must not
        be the softer path (spec-agent 20260930T084339).
        """
        tasks = _change(tmp_path, stage="authored")
        (tasks.parent / ".openspec.yaml").write_text("{[not yaml", encoding="utf-8")
        ok, lines = check_dispatch_allowed(tasks, BLOCK)
        assert ok is False
        assert lines, "refusing silently would be the other half of the same defect"


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


class TestUnevaluableGateIsNeverSilent:
    """The 2026-09-30 incident, reproduced.

    `requested_by` in security-gates-hook-c's `.openspec.yaml` carried an
    unquoted colon inside its value. `yaml.safe_load` raised ScannerError, one
    bare `except Exception: return True, []` swallowed it, and FIVE agents
    (core, cli, deploy, plugin, spec) received task-assignments for a change at
    stage `authored` — with nothing printed. core-agent's fix quoted the value
    2m13s later; the assignments were already out.

    Three cases that must stay apart:
      - no `.openspec.yaml`        -> no gate is declared; allow, say nothing
      - core lacks the module      -> laggard bundle; allow, say nothing
      - declared but unparseable   -> a gate EXISTS and was not evaluated;
                                      allow (a bad file must not disarm the
                                      dispatcher) but SAY SO

    The third collapsing into the first two is what made the dispatch silent.
    """

    #: Verbatim from security-gates-hook-c before ce8c410 quoted it.
    REAL_BAD_LINE = (
        "requested_by: cofounder-agent (SCR 20260622T210418, "
        "research-grounded: verification-gates-research.md)\n"
    )

    def _broken(self, tmp_path: Path, name: str = "sghc") -> Path:
        d = tmp_path / "openspec" / "changes" / name
        d.mkdir(parents=True)
        (d / "tasks.md").write_text("- [ ] 1.4 @otaman-plugin do it\n", encoding="utf-8")
        (d / ".openspec.yaml").write_text(
            "schema: spec-driven\n" + self.REAL_BAD_LINE + "stage: authored\n",
            encoding="utf-8",
        )
        return d / "tasks.md"

    def test_the_real_file_is_genuinely_unparseable(self, tmp_path):
        """Guard the fixture itself: if this ever parses, the test below is
        vacuous and would pass while proving nothing."""
        with pytest.raises(yaml.YAMLError):
            yaml.safe_load("schema: spec-driven\n" + self.REAL_BAD_LINE)

    def test_unparseable_gate_REFUSES_under_block(self, tmp_path):
        """spec-agent's asymmetry argument (20260930T084339), which settles it:
        the gate refused a READABLE `authored` stage while waving through an
        UNREADABLE one — making a malformed file a way PAST the gate.

        Refusing here is not a policy change. Under `block` a known-bad stage
        is already refused, so refusing an unknowable one changes no decision
        anyone configured; it only stops an unperformed check rendering as a
        passed one (no-silent-success clause 2).
        """
        ok, lines = check_dispatch_allowed(self._broken(tmp_path), BLOCK)
        assert ok is False, "an unverifiable stage was dispatched under enforcement=block"
        assert lines

    def test_a_malformed_file_is_no_softer_than_a_readable_bad_stage(self, tmp_path):
        """The asymmetry itself, asserted directly: both must refuse."""
        readable_bad, _ = check_dispatch_allowed(
            _change(tmp_path, stage="authored", name="readable"), BLOCK
        )
        unreadable, _ = check_dispatch_allowed(self._broken(tmp_path, name="unreadable"), BLOCK)
        assert readable_bad is False
        assert unreadable is False, "malforming the file is a way past the gate"

    def test_warn_mode_still_proceeds_and_says_so(self, tmp_path):
        """Refusing under `warn` would override a policy someone chose — the
        mode is honoured in both directions."""
        ok, lines = check_dispatch_allowed(self._broken(tmp_path), WARN)
        assert ok is True
        assert "WITHOUT a stage check" in "\n".join(lines)

    def test_unreadable_policy_takes_the_safe_side(self, tmp_path, monkeypatch):
        """If even the enforcement mode cannot be resolved, refuse.

        Patched at `otaman_core.spec_lifecycle`, NOT on map_tasks: the function
        imports the symbol locally inside its try block, so a module-attribute
        patch is shadowed and the test passes without exercising anything. It
        did exactly that until a sabotage run scored 22/22 against an inverted
        fallback and exposed it.
        """
        import otaman_core.spec_lifecycle as sl

        def boom(**kwargs):
            raise RuntimeError("policy unreadable")

        monkeypatch.setattr(sl, "resolve_spec_policy", boom)
        ok, _ = check_dispatch_allowed(self._broken(tmp_path), BLOCK)
        assert ok is False

    def test_the_report_names_the_parse_failure(self, tmp_path):
        _, lines = check_dispatch_allowed(self._broken(tmp_path), BLOCK)
        blob = "\n".join(lines)
        assert "ScannerError" in blob, "the reason must be named, not just 'failed'"
        assert "cannot be verified" in blob

    def test_it_points_at_the_command_that_gives_the_real_answer(self, tmp_path):
        """A warning an agent cannot act on is nearly as bad as silence."""
        _, lines = check_dispatch_allowed(self._broken(tmp_path), BLOCK)
        assert "otaman spec gate" in "\n".join(lines)

    def test_uses_the_exported_marker(self, tmp_path):
        from otaman_plugin.map_tasks import GATE_NOT_EVALUATED

        _, lines = check_dispatch_allowed(self._broken(tmp_path), BLOCK)
        assert any(ln.startswith(GATE_NOT_EVALUATED) for ln in lines)

    def test_a_missing_openspec_yaml_stays_silent(self, tmp_path):
        """The case the old handler was WRITTEN for must not become noisy —
        a change with no gate file has no gate, and saying so on every
        dispatch would train everyone to ignore the line."""
        ok, lines = check_dispatch_allowed(_change(tmp_path, stage=None), BLOCK)
        assert ok is True and lines == []

    def test_a_valid_gate_says_nothing_about_evaluation(self, tmp_path):
        ok, lines = check_dispatch_allowed(_change(tmp_path, stage="spec-approved"), BLOCK)
        assert ok is True and lines == []

    def test_unevaluable_differs_from_no_gate_at_all(self, tmp_path):
        """Both allow the dispatch. Only one of them checked anything."""
        _, no_gate = check_dispatch_allowed(_change(tmp_path, stage=None, name="a"), BLOCK)
        _, broken = check_dispatch_allowed(self._broken(tmp_path, name="b"), BLOCK)
        assert no_gate == []
        assert broken != no_gate
