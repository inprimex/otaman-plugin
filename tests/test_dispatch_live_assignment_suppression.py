"""A live, unresolved assignment suppresses re-dispatch (pmeets via deploy).

Until now a FILED COMPLETION was the only thing that stopped a re-dispatch.
So a task that had been dispatched but not yet completed — the normal state of
in-flight work — went out again on every subsequent tasks.md commit.

MEASURED ON otaman-dev, 20261008T091419:

    357 dispatches across 172 distinct (change, recipient) pairs
    185 re-emissions = 52% of all dispatch traffic
    worst cases 7x

Twenty dispatches exist for otaman-meta-merge-gate alone, seven rounds to
three recipients, for work that was in flight the whole time.

WHAT COUNTS AS LIVE — and the line matters:

    unacked        LIVE     just sent, recipient has not looked
    acked `read`   LIVE     "seen, queued" — exactly what must not duplicate
    acked `resolved`  NOT   recipient says done; if nothing was filed, the
                            MISSING FILING is the defect and re-dispatch is
                            how the fleet notices. Suppressing here would
                            hide it.

That last row is deliberate. deploy's analysis showed spec-agent takes 38% of
all dispatch traffic at a 2.7x dispatch-to-filing ratio precisely because
they tick their own tasks.md and file nothing — and a tick is invisible to a
consult that reads filings. The fix for that is filing, not a wider
suppression here.
"""

from __future__ import annotations

import pathlib

import pytest

from otaman_plugin.map_tasks import _consult_filed, _live_assignment_task_ids

FEATURE = "acme-change"


def _bus(tmp_path: pathlib.Path) -> pathlib.Path:
    active = tmp_path / ".agents" / "bus" / "active"
    (active / "acks").mkdir(parents=True)
    return active


def _dispatch(
    active: pathlib.Path,
    owner: str,
    *task_lines: str,
    stem: str = "20261008T120000",
    ack: str | None = None,
) -> None:
    name = f"{stem}-otaman-to-{owner}-tasks-{FEATURE}"
    body = ["---", "type: task-assignment", f"to: {owner}", "---", ""]
    body += [f"- [ ] {line}" for line in task_lines]
    (active / f"{name}.md").write_text("\n".join(body) + "\n", encoding="utf-8")
    if ack is not None:
        (active / "acks" / f"{name}.{owner}.ack").write_text(ack, encoding="utf-8")


class TestWhatCountsAsLive:
    def test_an_unacked_assignment_is_live(self, tmp_path):
        _dispatch(_bus(tmp_path), "plugin-agent", "1.1 @otaman-plugin do a thing")
        live, problems = _live_assignment_task_ids(tmp_path, FEATURE, {})
        assert live == {"plugin-agent": {"1.1"}}
        assert problems == []

    def test_an_assignment_acked_READ_is_still_live(self, tmp_path):
        """ "Seen, queued, in flight" is the case that must not duplicate."""
        _dispatch(_bus(tmp_path), "cli-agent", "2.1 @otaman-cli a thing", ack="read")
        live, _ = _live_assignment_task_ids(tmp_path, FEATURE, {})
        assert live == {"cli-agent": {"2.1"}}

    def test_an_assignment_acked_RESOLVED_is_NOT_live(self, tmp_path):
        """The recipient says done. If no completion was filed, the missing
        filing is the defect — suppressing here would hide it."""
        _dispatch(_bus(tmp_path), "core-agent", "3.1 @otaman-core a thing", ack="resolved")
        live, _ = _live_assignment_task_ids(tmp_path, FEATURE, {})
        assert live == {}

    def test_a_double_appended_ack_is_read_correctly(self, tmp_path):
        """51 ack files on this tenant contain `readread` / `resolvedresolved`
        from a double-append somewhere. Not my bug, but a substring match has
        to get both right or suppression flips on corrupt data."""
        active = _bus(tmp_path)
        _dispatch(active, "a-agent", "1.1 @otaman-a x", stem="20261008T120001", ack="readread")
        _dispatch(
            active, "b-agent", "1.2 @otaman-b y", stem="20261008T120002", ack="resolvedresolved"
        )
        live, _ = _live_assignment_task_ids(tmp_path, FEATURE, {})
        assert live == {"a-agent": {"1.1"}}, "readread must stay live, resolvedresolved must not"

    def test_only_THIS_feature_is_consulted(self, tmp_path):
        """A live assignment for another change must not suppress this one."""
        active = _bus(tmp_path)
        other = "20261008T120003-otaman-to-plugin-agent-tasks-some-other-change.md"
        (active / other).write_text(
            "---\ntype: task-assignment\n---\n\n- [ ] 1.1 @otaman-plugin elsewhere\n",
            encoding="utf-8",
        )
        live, _ = _live_assignment_task_ids(tmp_path, FEATURE, {})
        assert live == {}

    def test_several_task_ids_in_one_assignment_all_count(self, tmp_path):
        _dispatch(
            _bus(tmp_path),
            "plugin-agent",
            "1.1 @otaman-plugin first",
            "1.3 @otaman-plugin second",
        )
        live, _ = _live_assignment_task_ids(tmp_path, FEATURE, {})
        assert live == {"plugin-agent": {"1.1", "1.3"}}


class TestAbsentBusIsAnAnswerUnreadableBusIsNot:
    """The distinction the existing suite caught me getting wrong.

    My first version reported "SKIPPED — no bus" as a problem, which made the
    could-not-consult warning fire on every first-ever dispatch.
    `test_available_reader_reports_no_problem` refused it, on the grounds that
    "a warning that is always on is a warning nobody reads" — and it was
    right: an ABSENT bus is a determinate answer (nothing dispatched, so
    nothing live), whereas an UNREADABLE one is genuinely indeterminate.
    """

    def test_an_absent_bus_is_not_a_problem(self, tmp_path):
        live, problems = _live_assignment_task_ids(tmp_path, FEATURE, {})
        assert live == {}
        assert problems == [], "the always-on warning is back"

    def test_an_unreadable_bus_IS_a_problem(self, tmp_path, monkeypatch):
        """Indeterminate, so it must say so rather than suppressing nothing
        silently — which is indistinguishable from a clean scan."""
        _bus(tmp_path)

        def _boom(self, pattern):
            raise OSError("permission denied")

        monkeypatch.setattr(pathlib.Path, "glob", _boom)
        live, problems = _live_assignment_task_ids(tmp_path, FEATURE, {})
        assert live == {}
        assert problems and "SKIPPED" in problems[0]
        assert "OSError" in problems[0]


class TestTheFourOutcomesStayDistinct:
    """nss clause 1. "skipped" collapsing filed-complete and already-live
    would leave an operator unable to tell a correct skip from a stuck
    assignment nobody is acting on."""

    def _tasks(self, owner="plugin-agent"):
        return [
            {"text": "1.1 @otaman-plugin a thing", "done": False, "owner": owner},
            {"text": "1.2 @otaman-plugin another", "done": False, "owner": owner},
        ]

    def test_already_live_is_reported_separately_from_filed_complete(self, tmp_path):
        _dispatch(_bus(tmp_path), "plugin-agent", "1.1 @otaman-plugin a thing")
        tasks = self._tasks()
        filed, already_live, retracted, problems = _consult_filed(
            tasks, tmp_path / "tasks.md", tmp_path, FEATURE, {}
        )
        assert [t[:3] for t in already_live] == ["1.1"]
        assert filed == []
        assert retracted == []
        assert problems == []

    def test_a_suppressed_task_is_marked_done_for_dispatch(self, tmp_path):
        _dispatch(_bus(tmp_path), "plugin-agent", "1.1 @otaman-plugin a thing")
        tasks = self._tasks()
        _consult_filed(tasks, tmp_path / "tasks.md", tmp_path, FEATURE, {})
        assert tasks[0]["done"] is True
        assert tasks[0].get("already_live") is True
        assert tasks[1]["done"] is False, "an unrelated task must still dispatch"

    def test_it_does_not_claim_the_task_was_FILED(self, tmp_path):
        """The flags are different facts: one says evidence of completion
        exists, the other says nobody has answered yet."""
        _dispatch(_bus(tmp_path), "plugin-agent", "1.1 @otaman-plugin a thing")
        tasks = self._tasks()
        _consult_filed(tasks, tmp_path / "tasks.md", tmp_path, FEATURE, {})
        assert tasks[0].get("filed_complete") is not True

    def test_a_task_with_no_owner_is_never_suppressed(self, tmp_path):
        """Suppression is per (owner, task). An unowned task has nobody who
        could already be holding it."""
        _dispatch(_bus(tmp_path), "plugin-agent", "1.1 @otaman-plugin a thing")
        tasks = [{"text": "1.1 @otaman-plugin a thing", "done": False, "owner": None}]
        _, already_live, _, _ = _consult_filed(tasks, tmp_path / "tasks.md", tmp_path, FEATURE, {})
        assert already_live == []


class TestTheRealCorpus:
    """The live tenant, which is why this exists at all."""

    @pytest.mark.skipif(
        not (pathlib.Path(__file__).resolve().parents[2] / "otaman-meta" / ".agents").is_dir(),
        reason="otaman-meta checkout not present",
    )
    def test_omg_has_live_assignments_that_would_have_been_re_dispatched(self):
        meta = pathlib.Path(__file__).resolve().parents[2] / "otaman-meta"
        live, problems = _live_assignment_task_ids(meta, "otaman-meta-merge-gate", {})
        assert problems == []
        assert live, (
            "no live assignments found for a change with 20 dispatches on disk — "
            "the consult is not reading the corpus"
        )
