"""`otaman_blocked`'s resume note must be about the entry's OWN change.

Found by auditing my own repo after cli-agent reported that my filename-glob
warning had found two instances of the same class in theirs (20260926T121819).
Their gap produced phantom approvals — one of which could CLEAR a blocked
entry on evidence that did not exist. Checking mine for the mirror case found
this: the `spec-change` arm of the cross-reference loop carried no ref check,
so ANY pending spec-change marked EVERY blocked entry resumable.

Not a cosmetic note. "READY TO RESUME — specs updated" is an instruction, and
the standing rule is that an agent does not resume a blocked task until BOTH
`spec-change-approved` AND `spec-change` arrive FOR THAT CHANGE. An unscoped
note tells them the second one has landed when it has not.

Live at the time of the fix: 723 pending `spec-change` messages on this
fleet's bus, 13 agents with blocked files — so in practice every entry read
READY TO RESUME regardless of its own state.
"""

from __future__ import annotations

import pathlib
import re

BUS_SERVER = (
    pathlib.Path(__file__).resolve().parent.parent
    / "src"
    / "otaman_plugin"
    / "servers"
    / "bus_server.py"
)


def _status_for():
    """Compile the real cross-reference loop out of bus_server, so the test
    exercises the shipped logic rather than a paraphrase of it."""
    src = BUS_SERVER.read_text(encoding="utf-8")
    start = src.index("            for msg in messages:")
    end = src.index("            blocked.append(")
    body = "\n".join(line[8:] for line in src[start:end].split("\n"))
    code = (
        "def status_for(entry, messages):\n"
        "    ref = entry.get('ref') or entry.get('proposal') or ''\n"
        "    status_note = 'waiting for approval'\n" + body + "\n    return status_note\n"
    )
    ns: dict = {}
    exec(compile(code, str(BUS_SERVER), "exec"), ns)  # noqa: S102 - the shipped loop, by design
    return ns["status_for"]


ENTRY = {"ref": "my-own-change", "proposal": "my-own-change"}


def _msg(type_: str, stem: str, status: str = "pending") -> dict:
    return {"type": type_, "status": status, "stem": stem}


class TestResumeNoteIsRefScoped:
    def test_an_unrelated_spec_change_does_not_say_resume(self):
        """The bug. An agent blocked on X told to resume because Y shipped."""
        note = _status_for()(ENTRY, [_msg("spec-change", "2026-specs-to-a-OTHER-spec-change")])
        assert "RESUME" not in note, (
            "an unrelated spec-change marked this entry resumable — that is an "
            "instruction to unblock work on evidence about a different change"
        )
        assert note == "waiting for approval"

    def test_my_own_spec_change_does_say_resume(self):
        """The fix must not silence the real signal."""
        note = _status_for()(
            ENTRY, [_msg("spec-change", "2026-specs-to-a-my-own-change-spec-change")]
        )
        assert note == "READY TO RESUME — specs updated"

    def test_a_generic_specs_changed_notification_matches_nothing(self):
        """`20260925T083520-specs-spec-change` names no change, so it is not
        evidence about any particular entry. Matching it would reinstate the
        bug for the most common message on the bus."""
        note = _status_for()(ENTRY, [_msg("spec-change", "20260925T083520-specs-spec-change")])
        assert "RESUME" not in note

    def test_approval_arm_stays_ref_scoped_too(self):
        f = _status_for()
        assert f(ENTRY, [_msg("spec-change-approved", "h-to-all-my-own-change-approved")]) == (
            "approved — waiting for spec commit"
        )
        assert "approved" not in f(
            ENTRY, [_msg("spec-change-approved", "h-to-all-someone-elses-change-approved")]
        )

    def test_an_entry_with_no_ref_is_never_auto_resumed(self):
        """A malformed entry carries no ref. It must not inherit somebody
        else's evidence — it should stay visible and unresolved."""
        note = _status_for()(
            {"ref": "", "proposal": ""},
            [_msg("spec-change", "2026-specs-to-a-my-own-change-spec-change")],
        )
        assert note == "waiting for approval"


def test_both_arms_carry_a_ref_check():
    """Structural guard. The two arms drifted once — one scoped, one not — and
    the unscoped one shipped. This fails if either loses its ref test."""
    src = BUS_SERVER.read_text(encoding="utf-8")
    start = src.index("            for msg in messages:")
    end = src.index("            blocked.append(")
    loop = src[start:end]
    arms = re.findall(r'if msg\["type"\] == "(spec-change(?:-approved)?)"[^\n]*', loop)
    assert len(arms) == 2, f"expected two cross-reference arms, found {arms}"
    for line in re.findall(r'\s+if msg\["type"\] == "spec-change[^\n]*', loop):
        assert "ref in stem" in line or "ref in msg" in line, (
            f"this arm is not ref-scoped, so it matches messages about other changes:\n{line}"
        )
