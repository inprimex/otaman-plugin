"""Tests for scripts/_models_resolve.py — session tier resolution chain."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
import yaml


def _load_module():
    scripts_dir = Path(__file__).parent.parent / "scripts"
    sys.path.insert(0, str(scripts_dir))
    spec = importlib.util.spec_from_file_location(
        "models_resolve",
        scripts_dir / "_models_resolve.py",
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["models_resolve"] = module
    spec.loader.exec_module(module)
    return module


mr = _load_module()


@pytest.fixture
def maestro_folder(tmp_path):
    root = tmp_path / "my-maestro"
    root.mkdir()
    return root


def _write_platform(root, models=None, repos=None):
    data: dict = {"project": "test", "version": "1.0", "repos": repos or []}
    if models is not None:
        data["models"] = models
    (root / "platform.yaml").write_text(yaml.dump(data), encoding="utf-8")


# ---------------------------------------------------------------------------
# No config at all


class TestEmpty:
    def test_no_platform_yaml_returns_empty(self, maestro_folder):
        result = mr.resolve_tier(maestro_folder)
        assert result.is_empty()
        assert result.model_source == ""
        assert result.effort_source == ""

    def test_platform_yaml_without_models_block(self, maestro_folder):
        _write_platform(maestro_folder)
        result = mr.resolve_tier(maestro_folder)
        assert result.is_empty()


# ---------------------------------------------------------------------------
# Project default


class TestProjectDefault:
    def test_default_applied(self, maestro_folder):
        _write_platform(
            maestro_folder,
            models={
                "default": "sonnet",
                "default_effort": "medium",
            },
        )
        result = mr.resolve_tier(maestro_folder)
        assert result.model == "sonnet"
        assert result.effort == "medium"
        assert result.model_source == "default"
        assert result.effort_source == "default"

    def test_default_only_model(self, maestro_folder):
        _write_platform(maestro_folder, models={"default": "haiku"})
        result = mr.resolve_tier(maestro_folder)
        assert result.model == "haiku"
        assert result.effort == ""

    def test_inherit_treated_as_unset(self, maestro_folder):
        """`inherit` in platform.yaml is a no-op — lets user say 'don't
        override at this layer, fall through'."""
        _write_platform(
            maestro_folder,
            models={
                "default": "inherit",
                "default_effort": "inherit",
            },
        )
        result = mr.resolve_tier(maestro_folder)
        assert result.is_empty()


# ---------------------------------------------------------------------------
# Per-repo


class TestByRepo:
    def test_by_repo_wins_over_default(self, maestro_folder):
        _write_platform(
            maestro_folder,
            models={
                "default": "sonnet",
                "by_repo": {
                    "train": {"model": "opus", "effort": "high"},
                },
            },
        )
        result = mr.resolve_tier(maestro_folder, repo="train")
        assert result.model == "opus"
        assert result.effort == "high"
        assert result.model_source == "by_repo"

    def test_unmatched_repo_falls_to_default(self, maestro_folder):
        _write_platform(
            maestro_folder,
            models={
                "default": "sonnet",
                "by_repo": {"train": {"model": "opus"}},
            },
        )
        result = mr.resolve_tier(maestro_folder, repo="other")
        assert result.model == "sonnet"
        assert result.model_source == "default"

    def test_by_repo_partial_fills_from_default(self, maestro_folder):
        """Per-repo sets only model; effort falls through to default."""
        _write_platform(
            maestro_folder,
            models={
                "default": "sonnet",
                "default_effort": "medium",
                "by_repo": {"train": {"model": "opus"}},  # no effort
            },
        )
        result = mr.resolve_tier(maestro_folder, repo="train")
        assert result.model == "opus"
        assert result.model_source == "by_repo"
        assert result.effort == "medium"
        assert result.effort_source == "default"


# ---------------------------------------------------------------------------
# Per-agent (explicit + via repo owner)


class TestByAgent:
    def test_explicit_agent(self, maestro_folder):
        _write_platform(
            maestro_folder,
            models={
                "by_agent": {"train-agent": {"model": "opus"}},
            },
        )
        result = mr.resolve_tier(maestro_folder, agent="train-agent")
        assert result.model == "opus"
        assert result.model_source == "by_agent"

    def test_agent_via_repo_owner(self, maestro_folder):
        """When no agent is passed but repo is, look up the repo's owner
        and apply the agent rule."""
        _write_platform(
            maestro_folder,
            models={"by_agent": {"train-agent": {"model": "opus"}}},
            repos=[
                {"name": "train", "path": "../train", "owner": "train-agent"},
            ],
        )
        result = mr.resolve_tier(maestro_folder, repo="train")
        assert result.model == "opus"
        assert result.model_source == "by_agent"

    def test_by_repo_beats_by_agent(self, maestro_folder):
        _write_platform(
            maestro_folder,
            models={
                "by_repo": {"train": {"model": "haiku"}},
                "by_agent": {"train-agent": {"model": "opus"}},
            },
            repos=[
                {"name": "train", "path": "../train", "owner": "train-agent"},
            ],
        )
        result = mr.resolve_tier(maestro_folder, repo="train")
        assert result.model == "haiku"
        assert result.model_source == "by_repo"

    def test_explicit_agent_overrides_repo_owner_lookup(self, maestro_folder):
        _write_platform(
            maestro_folder,
            models={
                "by_agent": {
                    "train-agent": {"model": "opus"},
                    "other-agent": {"model": "haiku"},
                }
            },
            repos=[
                {"name": "train", "path": "../train", "owner": "train-agent"},
            ],
        )
        # repo=train would look up train-agent. But we pass agent=other-agent
        # explicitly; that should win the lookup step.
        result = mr.resolve_tier(
            maestro_folder,
            repo="train",
            agent="other-agent",
        )
        assert result.model == "haiku"


# ---------------------------------------------------------------------------
# CLI override


class TestCliOverride:
    def test_cli_wins_over_all(self, maestro_folder):
        _write_platform(
            maestro_folder,
            models={
                "default": "sonnet",
                "by_repo": {"train": {"model": "opus"}},
            },
        )
        result = mr.resolve_tier(
            maestro_folder,
            repo="train",
            cli_model="haiku",
        )
        assert result.model == "haiku"
        assert result.model_source == "cli"

    def test_invalid_cli_falls_through(self, maestro_folder):
        """Typo in CLI model doesn't crash — just falls to next rule."""
        _write_platform(maestro_folder, models={"default": "sonnet"})
        result = mr.resolve_tier(maestro_folder, cli_model="octopus")
        assert result.model == "sonnet"
        assert result.model_source == "default"

    def test_effort_cli_independent_of_model(self, maestro_folder):
        _write_platform(
            maestro_folder,
            models={
                "default": "sonnet",
                "default_effort": "low",
            },
        )
        result = mr.resolve_tier(maestro_folder, cli_effort="xhigh")
        assert result.model == "sonnet"
        assert result.model_source == "default"
        assert result.effort == "xhigh"
        assert result.effort_source == "cli"


# ---------------------------------------------------------------------------
# Validation


class TestValidation:
    def test_invalid_model_silently_dropped(self, maestro_folder):
        _write_platform(maestro_folder, models={"default": "sooopus"})
        result = mr.resolve_tier(maestro_folder)
        assert result.model == ""

    def test_valid_aliases(self, maestro_folder):
        for alias in ("opus", "sonnet", "haiku"):
            _write_platform(maestro_folder, models={"default": alias})
            result = mr.resolve_tier(maestro_folder)
            assert result.model == alias

    def test_valid_effort_levels(self, maestro_folder):
        for level in ("low", "medium", "high", "xhigh", "max"):
            _write_platform(maestro_folder, models={"default_effort": level})
            result = mr.resolve_tier(maestro_folder)
            assert result.effort == level

    def test_case_normalized(self, maestro_folder):
        _write_platform(maestro_folder, models={"default": "OPUS"})
        result = mr.resolve_tier(maestro_folder)
        assert result.model == "opus"


# ---------------------------------------------------------------------------
# explain_chain output


class TestMergeFromTwoFiles:
    """launch-settings.yaml models: block overlays platform.yaml's."""

    def test_launch_settings_overrides_platform_default(self, maestro_folder):
        (maestro_folder / "platform.yaml").write_text(
            yaml.dump(
                {"project": "t", "version": "1.0", "repos": [], "models": {"default": "sonnet"}}
            ),
            encoding="utf-8",
        )
        (maestro_folder / "launch-settings.yaml").write_text(
            yaml.dump({"models": {"default": "haiku"}}),
            encoding="utf-8",
        )
        result = mr.resolve_tier(maestro_folder)
        assert result.model == "haiku"  # launch-settings wins

    def test_platform_fills_in_what_launch_settings_omits(self, maestro_folder):
        """platform.yaml: default=sonnet + by_repo. launch-settings.yaml:
        only default=haiku. by_repo survives from platform.yaml."""
        (maestro_folder / "platform.yaml").write_text(
            yaml.dump(
                {
                    "project": "t",
                    "version": "1.0",
                    "repos": [],
                    "models": {
                        "default": "sonnet",
                        "by_repo": {"train": {"model": "opus"}},
                    },
                }
            ),
            encoding="utf-8",
        )
        (maestro_folder / "launch-settings.yaml").write_text(
            yaml.dump({"models": {"default": "haiku"}}),
            encoding="utf-8",
        )
        # Unmatched repo → falls to default → haiku from launch-settings
        assert mr.resolve_tier(maestro_folder).model == "haiku"
        # Matching repo → by_repo from platform.yaml survives
        assert mr.resolve_tier(maestro_folder, repo="train").model == "opus"

    def test_deep_merge_by_repo(self, maestro_folder):
        """Same repo in both files: launch-settings keys overlay."""
        (maestro_folder / "platform.yaml").write_text(
            yaml.dump(
                {
                    "project": "t",
                    "version": "1.0",
                    "repos": [],
                    "models": {
                        "by_repo": {
                            "train": {
                                "model": "sonnet",
                                "effort": "medium",
                            }
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        (maestro_folder / "launch-settings.yaml").write_text(
            yaml.dump(
                {
                    "models": {
                        "by_repo": {
                            "train": {
                                "model": "opus",  # overrides platform's sonnet
                                # effort not specified → inherits 'medium'
                            }
                        }
                    }
                }
            ),
            encoding="utf-8",
        )
        result = mr.resolve_tier(maestro_folder, repo="train")
        assert result.model == "opus"
        assert result.effort == "medium"

    def test_only_launch_settings_works(self, maestro_folder):
        """No platform.yaml models block — launch-settings.yaml alone suffices."""
        (maestro_folder / "platform.yaml").write_text(
            yaml.dump({"project": "t", "version": "1.0", "repos": []}),
            encoding="utf-8",
        )
        (maestro_folder / "launch-settings.yaml").write_text(
            yaml.dump({"models": {"default": "sonnet"}}),
            encoding="utf-8",
        )
        assert mr.resolve_tier(maestro_folder).model == "sonnet"

    def test_no_platform_yaml_at_all(self, maestro_folder):
        """launch-settings.yaml ONLY (no platform.yaml) — launcher-folder
        case where user might not have a local platform.yaml."""
        (maestro_folder / "launch-settings.yaml").write_text(
            yaml.dump(
                {
                    "accounts": {"personal": {"config_dir": "~/.claude-personal"}},
                    "models": {
                        "default": "haiku",
                        "by_repo": {
                            "train": {"model": "opus"},
                        },
                    },
                }
            ),
            encoding="utf-8",
        )
        assert mr.resolve_tier(maestro_folder).model == "haiku"
        assert mr.resolve_tier(maestro_folder, repo="train").model == "opus"


class TestExplain:
    def test_shows_which_rule_fired(self, maestro_folder):
        _write_platform(
            maestro_folder,
            models={
                "default": "sonnet",
                "by_repo": {"train": {"model": "opus", "effort": "high"}},
            },
        )
        lines = mr.explain_chain(maestro_folder, repo="train")
        joined = "\n".join(lines)
        # Marker "->" on the rule that won
        assert "->" in joined
        # All four ranks should appear
        assert "1. CLI override" in joined
        assert "2. by_repo[train]" in joined
        assert "3. by_agent" in joined
        assert "4. project default" in joined
        # Effective line
        assert "Effective:" in lines[-1]
        assert "opus" in lines[-1]
        assert "high" in lines[-1]
