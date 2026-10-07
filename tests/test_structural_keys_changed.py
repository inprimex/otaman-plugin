"""`structural_keys_changed` — the single home for "what counts as structural".

otaman-meta-merge-gate 1.1. Two callers share it and must never disagree:

  - the PreToolUse commit guard, comparing staged vs HEAD on an agent's machine;
  - the server-side meta-gate workflow, re-checking the same thing on a PR
    where no client hook ran at all.

The second exists because the first is bypassable: a `gh pr merge` never
reaches a PreToolUse hook, which is the hole omg closes. A backstop that
computes "structural" differently from the thing it backs up would pass what
the hook refuses or refuse what it allows — and each would be defensible
according to its own code, which is the worst version of this bug.

THE CALLERS DISAGREE ON DEFAULTS, DELIBERATELY, AND THAT IS NOT THIS
FUNCTION'S JOB. An unparseable side yields () here; the guard renders that as
allow (a speed bump that blocks on unreadable YAML blocks the commit that
fixes it) and the gate must render it as refuse (a server check that passes
what it could not read certifies nothing). Same comparison, opposite
defaults, one implementation.
"""

from __future__ import annotations

import pytest

from otaman_plugin.generate_agent_config import (
    STRUCTURAL_PLATFORM_KEYS,
    structural_keys_changed,
)

BASE = {
    "project": "acme",
    "repos": [{"name": "a", "owner": "a-agent"}],
    "ownership": {"otaman-folder": "plugin-agent"},
    "bus": {"routing_rules": {}},
    "communication": {"bus_path": ".agents/bus"},
    "program": {"registries": {}},
    "knowledge": {"ttl": 30},
    "terminal": {"kind": "tmux"},
}


def _with(**over):
    out = dict(BASE)
    out.update(over)
    return out


class TestItDetectsEveryStructuralKey:
    @pytest.mark.parametrize("key", STRUCTURAL_PLATFORM_KEYS)
    def test_each_declared_key_is_actually_compared(self, key):
        """A key in the list that the function never compares is a key the
        gate silently permits — the list would advertise protection it does
        not provide."""
        changed = structural_keys_changed(BASE, _with(**{key: {"MUTATED": True}}))
        assert key in changed, f"{key} is in the list but changes to it go undetected"

    def test_several_at_once_are_all_named(self):
        """One name would let the committer fix that key and be refused again
        for the next, with no idea how many remain."""
        after = _with(repos=[{"name": "b"}], ownership={"otaman-folder": "x"})
        assert set(structural_keys_changed(BASE, after)) == {"repos", "ownership"}

    def test_order_is_stable_for_diffing(self):
        after = _with(ownership={"x": 1}, repos=[], bus={})
        once = structural_keys_changed(BASE, after)
        assert once == structural_keys_changed(BASE, after)
        assert list(once) == [k for k in STRUCTURAL_PLATFORM_KEYS if k in once]


class TestItLeavesOrdinaryChangesAlone:
    """A gate that fires on normal edits gets routed around within a day."""

    def test_a_non_structural_key_is_not_structural(self):
        assert structural_keys_changed(BASE, _with(knowledge={"ttl": 90})) == ()

    def test_an_identical_document_changes_nothing(self):
        assert structural_keys_changed(BASE, dict(BASE)) == ()

    def test_adding_an_unrelated_key_is_not_structural(self):
        assert structural_keys_changed(BASE, _with(standards={"lint": "ruff"})) == ()

    def test_key_reordering_is_not_a_change(self):
        """YAML round-trips and formatting passes reorder top-level keys; a
        gate that called that structural would fire on cosmetics."""
        reordered = {k: BASE[k] for k in reversed(list(BASE))}
        assert structural_keys_changed(BASE, reordered) == ()


class TestRemovalAndAdditionBothCount:
    def test_DELETING_a_structural_key_is_a_change(self):
        """The dangerous direction. Dropping `ownership:` un-declares who owns
        the coordination repo, and `before.get(k) != after.get(k)` must catch
        absence as readily as mutation."""
        after = {k: v for k, v in BASE.items() if k != "ownership"}
        assert "ownership" in structural_keys_changed(BASE, after)

    def test_ADDING_a_structural_key_is_a_change(self):
        """How `ownership:` itself arrived — and the case the gate would have
        had to refuse, which is why core 1.4 had to ship first."""
        without = {k: v for k, v in BASE.items() if k != "ownership"}
        assert "ownership" in structural_keys_changed(without, BASE)


class TestUnparseableYieldsNothingAndTheCallerDecides:
    """nss: the function reports "no differences found", NOT "no differences
    exist". Rendering that as clean is the caller's error to make, and the
    guard and the gate make opposite choices about it on purpose."""

    @pytest.mark.parametrize(
        ("before", "after"),
        [(None, BASE), (BASE, None), (None, None)],
    )
    def test_an_unparseable_side_returns_empty(self, before, after):
        assert structural_keys_changed(before, after) == ()

    def test_empty_is_therefore_AMBIGUOUS_by_construction(self):
        """() means either "nothing structural changed" or "I could not
        compare". The docstring says so, and both callers must disambiguate
        from their own context — the guard fails open, the gate fails closed."""
        clean = structural_keys_changed(BASE, dict(BASE))
        unreadable = structural_keys_changed(None, BASE)
        assert clean == unreadable == ()
