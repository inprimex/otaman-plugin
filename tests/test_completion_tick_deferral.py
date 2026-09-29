"""task-complete-reconciler 2.3 — the generated completion instructions must
retract the async-tick promise.

The old wording told every agent that the specs owner "applies the `tasks.md`
tick asynchronously on next session start" and named

    spec-agent will tick tasks.md on next session start

as the success signal. cli-agent removes that line (contract-change
20260929T113055); it is replaced by an output that states the tick is DEFERRED
and claims nothing about when it lands.

Two failure modes these tests exist to prevent:

1. Every agent is told to watch for a success signal that no longer prints,
   with the instruction framing its absence as possibly-an-error — so the new,
   honest output reads as a failure and the agent re-files.
2. The schedule itself was never real. The reconciler proposal measured the
   cost of believing it: ~2 weeks of unapplied completes on pmeets, the lens
   reporting 5/11 against a real 11/11, nothing warning.
"""

from pathlib import Path

import otaman_plugin.generate_agent_config as gen

GENERATOR = Path(gen.__file__)

BUS = ".agents/bus"


def _config(specs_path="../specs", specs_owner="spec-agent", with_specs=True):
    repos = [
        {"name": "backend", "path": "./backend", "owner": "dev-agent"},
        {"name": "specs", "path": specs_path, "owner": specs_owner},
    ]
    config = {"project": "myproj", "repos": repos}
    if with_specs:
        config["specs"] = {"path": specs_path, "format": "openspec"}
    return config, repos


def _section(repo, config, repos, tmp_path):
    block = gen._build_maestro_block(repo, repos, BUS, config, tmp_path)
    start = block.index("### Task Completion Reporting")
    return block[start:].split("### Sequenced")[0]


def _non_owner(tmp_path, **kw):
    config, repos = _config(**kw)
    return _section(repos[0], config, repos, tmp_path)


def _owner(tmp_path, **kw):
    config, repos = _config(**kw)
    return _section(repos[1], config, repos, tmp_path)


# --- the retraction itself ------------------------------------------------


def test_retracted_promise_is_gone_for_non_owners(tmp_path):
    """No agent is told the tick lands on a schedule."""
    section = _non_owner(tmp_path)
    assert "next session start" not in section
    assert "asynchronously" not in section


def test_retracted_promise_is_gone_from_the_whole_block(tmp_path):
    """Not merely relocated to another section of the same file."""
    config, repos = _config()
    block = gen._build_maestro_block(repos[0], repos, BUS, config, tmp_path)
    assert "will tick tasks.md on next session start" not in block
    assert "tick asynchronously" not in block


def test_non_owner_is_told_the_tick_is_deferred(tmp_path):
    section = _non_owner(tmp_path)
    assert "DEFERRED" in section


def test_success_signal_matches_the_cli_output(tmp_path):
    """The named signal must be the string `otaman complete` actually prints.

    An instruction naming a signal the CLI does not emit is how this broke the
    first time — the test pins the two together.
    """
    section = _non_owner(tmp_path)
    assert "`Durable tick DEFERRED to spec-agent` is the success signal" in section


def test_tasks_md_is_stated_unchanged(tmp_path):
    """The agent must know the file on disk is untouched, not just 'pending'."""
    section = _non_owner(tmp_path)
    assert "unchanged" in section


def test_no_schedule_is_asserted_by_any_other_wording(tmp_path):
    """Guard the intent, not one phrasing: nothing may name a time or trigger.

    `otaman spec sweep` is deliberately included — it does not exist yet (cli
    1.2), and pointing at it would be the same unfounded promise wearing a
    different command name.
    """
    section = _non_owner(tmp_path).lower()
    for banned in (
        "next session",
        "asynchronous",
        "shortly",
        "will be applied within",
        "spec sweep",
        "automatically ticks",
    ):
        assert banned not in section, f"section re-asserts a schedule: {banned!r}"


def test_agent_is_told_not_to_re_file(tmp_path):
    """The measured failure was agents re-running complete to force a tick."""
    section = _non_owner(tmp_path)
    assert "re-file" in section or "re-running `otaman complete`" in section


def test_unticked_state_is_named_expected_not_failure(tmp_path):
    section = _non_owner(tmp_path)
    assert "expected state, not" in section


# --- owner resolution -----------------------------------------------------


def test_owner_is_derived_from_config_not_hardcoded(tmp_path):
    """A program whose specs live elsewhere must name ITS owner.

    Hardcoding `spec-agent` sends that program's agents to an agent that does
    not exist in their fleet.
    """
    section = _non_owner(tmp_path, specs_path="../rules", specs_owner="rules-agent")
    assert "DEFERRED to rules-agent" in section
    assert "spec-agent" not in section


def test_specs_path_is_derived_too(tmp_path):
    section = _non_owner(tmp_path, specs_path="../rules", specs_owner="rules-agent")
    assert "`../rules`" in section


def test_unknown_owner_falls_back_without_naming_anyone(tmp_path):
    """specs configured but no repo entry claims it — say 'the specs owner',
    never invent a name."""
    config = {
        "project": "myproj",
        "repos": [{"name": "backend", "path": "./backend", "owner": "dev-agent"}],
        "specs": {"path": "../rules", "format": "openspec"},
    }
    section = _section(config["repos"][0], config, config["repos"], tmp_path)
    assert "the specs owner" in section
    assert "spec-agent" not in section


def test_section_renders_with_no_specs_block_at_all(tmp_path):
    """A config with no `specs` key still generates — the fallback literals
    stand in rather than the generator raising NameError."""
    config, repos = _config(with_specs=False)
    section = _section(repos[0], config, repos, tmp_path)
    assert "DEFERRED to the specs owner" in section
    assert "the specs repo" in section


# --- the owner's own copy -------------------------------------------------


def test_specs_owner_is_told_they_apply_the_tick(tmp_path):
    """spec-agent reading 'deferred to spec-agent' would be told to wait on
    itself. Its copy must say the work is its own."""
    section = _owner(tmp_path)
    assert "DEFERRED" not in section
    assert "you are the one who applies" in section


def test_specs_owner_is_told_nobody_else_will(tmp_path):
    section = _owner(tmp_path)
    assert "Nobody else will" in section


# --- wiring ---------------------------------------------------------------


def test_note_is_interpolated_into_the_template(tmp_path):
    """Guard against a future edit silently dropping the placeholder, which
    would restore the section to a hardcoded paragraph."""
    source = GENERATOR.read_text(encoding="utf-8")
    assert "{tick_deferral_note}" in source
