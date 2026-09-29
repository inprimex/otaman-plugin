"""delivery-authorization-envelope 2.3 — dispatch carries the envelope into
task-assignments, so a delivering agent knows its action classes without
reading specs repo state.

HONESTY IS THE HARD PART, not plumbing. Every class in core's registry is
`runtime-honored: limited` until cli 2.2 records a measured value, and a
limited class AUTHORIZES NOTHING (design D6) — the runtime still prompts.

An assignment that listed a declared class without that marker would tell an
agent it may proceed unprompted when the runtime will stop it anyway. The
envelope must never promise autonomy the runtime refuses; a carried envelope
that over-promises is worse than none, because the agent stops checking.

FAIL-SAFE: a malformed or floor-violating envelope carries NOTHING and says
why. Carrying nothing authorizes nothing, which is the safe direction — and
the problem is surfaced rather than swallowed, because an assignment silently
missing its envelope looks identical to a change that never had one.
"""

from __future__ import annotations

from pathlib import Path

from otaman_plugin.map_tasks import envelope_block


def _change(tmp_path: Path, authorizes: str | None) -> Path:
    d = tmp_path / "c"
    d.mkdir(exist_ok=True)
    body = "stage: spec-approved\n" + (authorizes or "")
    (d / ".openspec.yaml").write_text(body, encoding="utf-8")
    tasks = d / "tasks.md"
    tasks.write_text("# t\n\n- [ ] 1.1 @otaman-plugin x\n", encoding="utf-8")
    return tasks


class TestTheEnvelopeIsCarried:
    def test_declared_classes_appear_with_scope(self, tmp_path):
        tasks = _change(
            tmp_path, "authorizes:\n  - hooks-wiring\n  - release-publish: [otaman-deploy]\n"
        )
        section, problems = envelope_block(tasks)
        assert problems == []
        assert "`hooks-wiring`" in section
        assert "`release-publish`" in section
        assert "otaman-deploy" in section, "a scoped class must carry its scope"
        assert "(every target)" in section, "an unscoped class must say it is unscoped"

    def test_it_says_what_is_outside_the_envelope(self, tmp_path):
        """The envelope is an allowlist. An agent needs the negative rule as
        much as the positive one, or it reads absence as permission."""
        tasks = _change(tmp_path, "authorizes:\n  - hooks-wiring\n")
        section, _ = envelope_block(tasks)
        assert "outside every envelope" in section
        assert "decision-required" in section

    def test_a_change_with_no_envelope_adds_nothing(self, tmp_path):
        """Most changes have no envelope. They must not grow a section
        explaining one."""
        assert envelope_block(_change(tmp_path, None)) == ("", [])

    def test_no_openspec_yaml_is_silent(self, tmp_path):
        d = tmp_path / "bare"
        d.mkdir()
        tasks = d / "tasks.md"
        tasks.write_text("- [ ] 1.1 x\n", encoding="utf-8")
        assert envelope_block(tasks) == ("", [])


class TestItNeverPromisesAutonomyTheRuntimeRefuses:
    def test_a_limited_class_is_marked_as_not_proceeding(self, tmp_path):
        """D6. Today every registry class is `limited`, so a declared class
        authorizes nothing — and the assignment has to say so, or an agent
        proceeds into a prompt believing it was authorized."""
        tasks = _change(tmp_path, "authorizes:\n  - hooks-wiring\n")
        section, _ = envelope_block(tasks)
        assert "limited" in section
        assert "**no**" in section, "a limited class was not marked as not-proceeding"
        assert "authorizes nothing by declaration" in section

    def test_the_runtime_honored_marker_is_shown_per_class(self, tmp_path):
        tasks = _change(tmp_path, "authorizes:\n  - schema-migration\n")
        section, _ = envelope_block(tasks)
        assert "runtime-honored" in section

    def test_it_still_tells_the_agent_to_emit_before_blocking(self, tmp_path):
        """The envelope and the decision-required duty are one story: if
        nothing proceeds unprompted, the duty is the whole answer."""
        tasks = _change(tmp_path, "authorizes:\n  - hooks-wiring\n")
        section, _ = envelope_block(tasks)
        assert "Emit before you block" in section


class TestFailSafe:
    def test_a_floor_action_refuses_and_carries_nothing(self, tmp_path):
        """The floor is never pre-authorizable. A change naming one must not
        get a partial envelope — it gets none, loudly."""
        tasks = _change(tmp_path, "authorizes:\n  - history-rewrite\n")
        section, problems = envelope_block(tasks)
        assert section == "", "a floor-violating envelope was partially carried"
        assert problems and "floor" in problems[0]

    def test_a_malformed_envelope_refuses_and_says_so(self, tmp_path):
        tasks = _change(tmp_path, "authorizes: {not: a-list}\n")
        section, problems = envelope_block(tasks)
        assert section == ""
        assert problems and "NOT carried" in problems[0]

    def test_the_refusal_is_never_silent(self, tmp_path):
        """An assignment silently missing its envelope is indistinguishable
        from a change that never had one — so the reason must travel."""
        tasks = _change(tmp_path, "authorizes:\n  - not-a-real-class\n")
        section, problems = envelope_block(tasks)
        assert section == ""
        assert problems, "an unknown class was dropped without a word"

    def test_older_core_without_the_module_says_so(self, tmp_path, monkeypatch):
        import builtins

        real = builtins.__import__

        def boom(name, *a, **k):
            if name == "otaman_core.delivery_envelope":
                raise ImportError("no envelope module")
            return real(name, *a, **k)

        monkeypatch.setattr(builtins, "__import__", boom)
        tasks = _change(tmp_path, "authorizes:\n  - hooks-wiring\n")
        section, problems = envelope_block(tasks)
        assert section == ""
        assert problems and "NOT carried" in problems[0]


class TestEndToEnd:
    def test_the_assignment_message_contains_the_envelope(self, tmp_path):
        from otaman_plugin.map_tasks import create_bus_messages

        root = tmp_path / "meta"
        (root / ".agents" / "bus" / "active" / "acks").mkdir(parents=True)
        tasks = _change(tmp_path, "authorizes:\n  - hooks-wiring\n")
        section, _ = envelope_block(tasks)
        created = create_bus_messages(
            root,
            [{"text": "1.1 do it", "done": False, "owner": "plugin-agent"}],
            "c",
            {},
            section,
        )
        assert created
        body = (root / created[0]).read_text(encoding="utf-8")
        assert "Delivery authorization envelope" in body
        assert "`hooks-wiring`" in body
