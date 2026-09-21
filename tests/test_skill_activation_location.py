"""skill-activation-config-split 1.1 — activation config moves to `program.skills`.

Canon (shared-contracts delta): `program.processes.<name>` denotes a
REGISTRY-BACKED process — rows with ids, status, transitions, an audit trail,
addressed by a `path:`. Activation config is one object with no rows and
nothing to audit, so it does not belong there, and
`program.processes.skills` is RESERVED for the per-project skills registry.

Design D1 rules a one-time migration window: the retired location WORKS with
a warning naming the new key, then refuses. "No silent dual-read" is explicit
— silence is how the wizard-writes-here/resolver-reads-there defect survived
in the first place, so the warning is a tested requirement, not a nicety.

Design D3 is the reason this file is thorough: `resolve_active_skills()` is
unexercised in production with passing unit tests, and the first wizard-created
program would have been its first real execution — on a customer. These tests
cover the location logic; the gate (2.1) proves a real activation on dogfood.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from otaman_plugin import skill_packs  # noqa: E402
from otaman_plugin.skill_packs import (  # noqa: E402
    ACTIVATION_PATH,
    RETIRED_ACTIVATION_PATH,
    _is_activation_shape,
    _read_activation_config,
)


def _canonical(**cfg):
    return {"program": {"skills": cfg}}


def _retired(**cfg):
    return {"program": {"processes": {"skills": cfg}}}


class TestCanonicalLocation:
    def test_reads_program_skills(self):
        cfg, warnings, error = _read_activation_config(_canonical(profile="tech-startup-cofounder"))
        assert cfg["profile"] == "tech-startup-cofounder"
        assert warnings == []
        assert error is None

    def test_canonical_does_not_warn(self):
        """The whole point of moving is that the correct location is quiet."""
        _, warnings, _ = _read_activation_config(_canonical(profile="x"))
        assert warnings == []

    def test_canonical_wins_over_retired(self):
        """Both present: canonical is authoritative, and there is nothing to
        warn about because the program already has it right."""
        platform = {
            "program": {
                "skills": {"profile": "canonical-wins"},
                "processes": {"skills": {"profile": "retired-loses"}},
            }
        }
        cfg, warnings, error = _read_activation_config(platform)
        assert cfg["profile"] == "canonical-wins"
        assert warnings == []
        assert error is None


class TestRetiredLocationDuringWindow:
    def test_retired_still_works(self):
        cfg, _, error = _read_activation_config(_retired(profile="tech-startup-cofounder"))
        assert cfg["profile"] == "tech-startup-cofounder"
        assert error is None

    def test_retired_warns_and_names_the_new_key(self):
        """D1: "no silent dual-read". The warning must name where to move it —
        a warning that says only "deprecated" leaves the reader to guess."""
        _, warnings, _ = _read_activation_config(_retired(profile="x"))
        assert len(warnings) == 1
        assert ACTIVATION_PATH in warnings[0]
        assert RETIRED_ACTIVATION_PATH in warnings[0]

    def test_warning_reaches_the_caller_through_resolve(self):
        """The notice is useless if it dies inside the resolver."""
        result = skill_packs.resolve_active_skills(
            _retired(profile="tech-startup-cofounder"), Path("/nonexistent")
        )
        assert result.warnings
        assert ACTIVATION_PATH in result.warnings[0]


class TestRetiredLocationAfterWindowCloses:
    def test_refuses_when_window_closed(self, monkeypatch):
        """Closing the window is a one-line flip, so the refusal path is
        implemented and tested NOW rather than written later under pressure."""
        monkeypatch.setattr(skill_packs, "RETIRED_ACTIVATION_SUPPORTED", False)
        cfg, _, error = _read_activation_config(_retired(profile="x"))
        assert cfg == {}
        assert error is not None
        assert ACTIVATION_PATH in error

    def test_refusal_surfaces_as_error_not_empty_success(self, monkeypatch):
        """A refusal must be distinguishable from "no config configured".
        Both yield zero skills; only one means the program is misconfigured,
        and a caller that cannot tell them apart will silently activate
        nothing and report success."""
        monkeypatch.setattr(skill_packs, "RETIRED_ACTIVATION_SUPPORTED", False)
        refused = skill_packs.resolve_active_skills(
            _retired(profile="tech-startup-cofounder"), Path("/nonexistent")
        )
        absent = skill_packs.resolve_active_skills({"program": {}}, Path("/nonexistent"))
        assert refused.skills == [] and absent.skills == []
        assert refused.error is not None
        assert absent.error is None

    def test_canonical_unaffected_by_the_window_closing(self, monkeypatch):
        monkeypatch.setattr(skill_packs, "RETIRED_ACTIVATION_SUPPORTED", False)
        cfg, warnings, error = _read_activation_config(_canonical(profile="x"))
        assert cfg["profile"] == "x"
        assert error is None and warnings == []


class TestRegistryIsNotMistakenForActivation:
    """`program.processes.skills` is RESERVED for the real skills registry.
    Warning at a program that legitimately has one there would be nagging
    about correct config — the failure NON_REGISTRY_PROCESSES existed to
    paper over, pointed the other way."""

    def test_a_path_addressed_registry_is_not_activation(self):
        cfg, warnings, error = _read_activation_config(_retired(path="registries/skills.yaml"))
        assert cfg == {}
        assert warnings == []
        assert error is None

    def test_registry_does_not_refuse_even_after_window_closes(self, monkeypatch):
        monkeypatch.setattr(skill_packs, "RETIRED_ACTIVATION_SUPPORTED", False)
        _, _, error = _read_activation_config(_retired(path="registries/skills.yaml"))
        assert error is None, "a legitimate registry must never be refused"

    @pytest.mark.parametrize(
        "cfg,expected",
        [
            ({"profile": "x"}, True),
            ({"active_skills": []}, True),
            ({"extra": []}, True),
            ({"path": "p"}, False),
            ({"path": "p", "profile": "x"}, False),  # path wins — it's a registry
            ({}, False),
            (None, False),
            ("not-a-mapping", False),
        ],
    )
    def test_activation_shape_detection(self, cfg, expected):
        assert _is_activation_shape(cfg) is expected


class TestExtraAlias:
    """The proposal names the schema as `profile`, `extra`/`active_skills`."""

    def test_extra_is_accepted_as_the_override_list(self, tmp_path):
        cfg, _, _ = _read_activation_config(_canonical(profile="p", extra=["a:b"]))
        assert cfg.get("extra") == ["a:b"]

    def test_active_skills_wins_when_both_present(self):
        """Explicit beats alias, and neither is silently merged — merging two
        override lists would activate a set the author never wrote."""
        platform = _canonical(profile="p", active_skills=["wins"], extra=["loses"])
        cfg, _, _ = _read_activation_config(platform)
        assert cfg["active_skills"] == ["wins"]


class TestMalformedPlatform:
    @pytest.mark.parametrize(
        "platform",
        [
            {},
            {"program": None},
            {"program": "not-a-mapping"},
            {"program": {"skills": None}},
            {"program": {"skills": "not-a-mapping"}},
            {"program": {"processes": None}},
            {"program": {"processes": "not-a-mapping"}},
        ],
    )
    def test_degrades_to_no_config_without_raising(self, platform):
        """A resolver that raises on a malformed platform.yaml turns a config
        typo into a crashed session."""
        cfg, warnings, error = _read_activation_config(platform)
        assert cfg == {}
        assert warnings == [] and error is None


class TestNoRetiredLocationInTheDocstring:
    def test_module_docstring_shows_the_canonical_shape(self):
        """The docstring is the first thing a reader copies from; leaving the
        retired shape there would keep minting programs that need migrating."""
        doc = skill_packs.__doc__ or ""
        assert "program:\n      skills:" in doc
        assert "processes:\n        skills:" not in doc
