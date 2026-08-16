"""Tests for scripts/_resolve.py — maestro root resolution."""

# Add scripts/ to path so we can import _resolve
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from _resolve import (
    expand_config_dir,
    find_maestro_root,
    find_marker,
    parse_marker_fields,
    read_expected_account,
)


@pytest.fixture
def workspace(tmp_path):
    """Create a workspace with maestro folder and managed repos."""
    maestro = tmp_path / "my-maestro"
    maestro.mkdir()
    (maestro / "platform.yaml").write_text("project: test\n")
    (maestro / ".agents").mkdir()
    (maestro / ".agents" / "ownership.json").write_text("{}")

    repo = tmp_path / "my-repo"
    repo.mkdir()
    (repo / ".git").mkdir()

    return {"root": tmp_path, "maestro": maestro, "repo": repo}


class TestMarkerFile:
    """Resolution via .maestro marker file."""

    def test_marker_in_repo_root(self, workspace):
        repo = workspace["repo"]
        maestro = workspace["maestro"]
        (repo / ".maestro").write_text("../my-maestro\n")
        assert find_maestro_root(repo) == maestro.resolve()

    def test_marker_in_subdirectory(self, workspace):
        repo = workspace["repo"]
        maestro = workspace["maestro"]
        (repo / ".maestro").write_text("../my-maestro\n")
        subdir = repo / "src" / "components"
        subdir.mkdir(parents=True)
        assert find_maestro_root(subdir) == maestro.resolve()

    def test_marker_with_comments(self, workspace):
        repo = workspace["repo"]
        maestro = workspace["maestro"]
        (repo / ".maestro").write_text(
            "# Path to maestro folder\n# Written by maestro init\n../my-maestro\n"
        )
        assert find_maestro_root(repo) == maestro.resolve()

    def test_marker_invalid_path(self, workspace):
        """If marker points to non-existent dir, falls through to next method."""
        repo = workspace["repo"]
        (repo / ".maestro").write_text("../nonexistent-maestro\n")
        result = find_maestro_root(repo)
        # Should not find via marker, but also not crash
        assert result is None or result != repo.resolve()

    def test_marker_takes_priority_over_walkup(self, workspace):
        """Marker file should be checked before walk-up fallback."""
        repo = workspace["repo"]
        maestro = workspace["maestro"]
        # Put platform.yaml in parent (would match walk-up)
        (workspace["root"] / "platform.yaml").write_text("project: parent\n")
        # Marker points to maestro folder
        (repo / ".maestro").write_text("../my-maestro\n")
        assert find_maestro_root(repo) == maestro.resolve()


class TestEnvVar:
    """Resolution via MAESTRO_ROOT environment variable."""

    def test_env_var(self, workspace, monkeypatch):
        repo = workspace["repo"]
        maestro = workspace["maestro"]
        monkeypatch.setenv("MAESTRO_ROOT", str(maestro))
        assert find_maestro_root(repo) == maestro.resolve()

    def test_env_var_invalid(self, workspace, monkeypatch):
        repo = workspace["repo"]
        monkeypatch.setenv("MAESTRO_ROOT", "/nonexistent/path")
        # Falls through to walk-up
        result = find_maestro_root(repo)
        assert result is None or result != Path("/nonexistent/path")

    def test_marker_beats_env_var(self, workspace, monkeypatch):
        """Marker file has higher priority than env var."""
        repo = workspace["repo"]
        maestro = workspace["maestro"]

        other_maestro = workspace["root"] / "other-maestro"
        other_maestro.mkdir()
        (other_maestro / "platform.yaml").write_text("project: other\n")

        (repo / ".maestro").write_text("../my-maestro\n")
        monkeypatch.setenv("MAESTRO_ROOT", str(other_maestro))

        assert find_maestro_root(repo) == maestro.resolve()


class TestWalkUpFallback:
    """Legacy walk-up resolution for backward compatibility."""

    def test_walkup_platform_yaml(self, tmp_path):
        root = tmp_path / "project"
        root.mkdir()
        (root / "platform.yaml").write_text("project: test\n")
        repo = root / "my-repo"
        repo.mkdir()
        assert find_maestro_root(repo) == root.resolve()

    def test_walkup_agents_dir(self, tmp_path):
        root = tmp_path / "project"
        root.mkdir()
        (root / ".agents").mkdir()
        repo = root / "my-repo"
        repo.mkdir()
        assert find_maestro_root(repo) == root.resolve()

    def test_walkup_from_deep_subdir(self, tmp_path):
        root = tmp_path / "project"
        root.mkdir()
        (root / "platform.yaml").write_text("project: test\n")
        deep = root / "repo" / "src" / "main" / "java"
        deep.mkdir(parents=True)
        assert find_maestro_root(deep) == root.resolve()

    def test_walkup_skips_launcher_folder(self, tmp_path):
        """A dir with platform.yaml AND launch-settings.yaml is a launcher
        folder (scaffold_launcher.py copies platform.yaml next to
        launch-settings.yaml), not an otaman root — the walk-up must skip
        it and keep climbing (fix-macos-onboarding port)."""
        root = tmp_path / "project"
        root.mkdir()
        (root / "platform.yaml").write_text("project: test\n")
        launcher = root / "launchers" / "myproj"
        launcher.mkdir(parents=True)
        (launcher / "platform.yaml").write_text("project: test\n")
        (launcher / "launch-settings.yaml").write_text("connections: {}\n")
        assert find_maestro_root(launcher) == root.resolve()

    def test_launcher_folder_alone_resolves_nothing(self, tmp_path):
        launcher = tmp_path / "myproj-launcher"
        launcher.mkdir()
        (launcher / "platform.yaml").write_text("project: test\n")
        (launcher / "launch-settings.yaml").write_text("connections: {}\n")
        assert find_maestro_root(launcher) is None


class TestNoMatch:
    """When nothing matches."""

    def test_no_maestro_root_found(self, tmp_path):
        orphan = tmp_path / "orphan"
        orphan.mkdir()
        assert find_maestro_root(orphan) is None

    def test_empty_marker_file(self, tmp_path):
        d = tmp_path / "repo"
        d.mkdir()
        (d / ".maestro").write_text("# just a comment\n")
        assert find_maestro_root(d) is None


class TestFromMaestroFolder:
    """Resolution when CWD is the maestro folder itself."""

    def test_cwd_is_maestro(self, workspace):
        """Walk-up should find platform.yaml in CWD."""
        maestro = workspace["maestro"]
        assert find_maestro_root(maestro) == maestro.resolve()


class TestConfigDirExpansion:
    """expand_config_dir — per-shell tilde and env-var handling."""

    def test_empty_input(self):
        assert expand_config_dir("", "bash") == ""

    def test_bash_tilde_expands(self):
        assert (
            expand_config_dir("~/.claude-personal", "bash", home="/home/foo")
            == "/home/foo/.claude-personal"
        )

    def test_bash_bare_tilde(self):
        assert expand_config_dir("~", "bash", home="/home/foo") == "/home/foo"

    def test_zsh_fish_same_as_bash(self):
        for shell in ("zsh", "fish"):
            assert (
                expand_config_dir("~/.claude-personal", shell, home="/home/foo")
                == "/home/foo/.claude-personal"
            )

    def test_powershell_native_backslashes(self):
        assert (
            expand_config_dir("~/.claude-personal", "powershell", home="C:\\Users\\roman")
            == "C:\\Users\\roman\\.claude-personal"
        )

    def test_powershell_normalizes_forward_slash_home(self):
        """If HOME has forward slashes (e.g. from env), output still backslash."""
        assert (
            expand_config_dir("~/.claude-personal", "powershell", home="C:/Users/roman")
            == "C:\\Users\\roman\\.claude-personal"
        )

    def test_wsl_defers_expansion(self):
        """WSL target: pass through unchanged so remote shell expands."""
        assert (
            expand_config_dir("~/.claude-personal", "wsl", home="/does/not/matter")
            == "~/.claude-personal"
        )

    def test_ssh_defers_expansion(self):
        assert (
            expand_config_dir("~/.claude-personal", "ssh", home="/does/not/matter")
            == "~/.claude-personal"
        )

    def test_wsl_normalizes_backslashes_to_forward(self):
        """Input with backslashes still emits POSIX slashes for WSL/ssh."""
        assert expand_config_dir("~\\.claude-personal", "wsl") == "~/.claude-personal"

    def test_env_var_home_expansion(self):
        assert (
            expand_config_dir("$HOME/.claude-foo", "bash", home="/home/foo")
            == "/home/foo/.claude-foo"
        )

    def test_env_var_braced_home_expansion(self):
        assert (
            expand_config_dir("${HOME}/.claude-foo", "bash", home="/home/foo")
            == "/home/foo/.claude-foo"
        )

    def test_userprofile_expansion_for_powershell(self):
        assert (
            expand_config_dir("$USERPROFILE/.claude-foo", "powershell", home="C:\\Users\\roman")
            == "C:\\Users\\roman\\.claude-foo"
        )

    def test_userprofile_braced_expansion_for_powershell(self):
        assert (
            expand_config_dir("${USERPROFILE}/.claude-foo", "powershell", home="C:\\Users\\roman")
            == "C:\\Users\\roman\\.claude-foo"
        )

    def test_absolute_path_passes_through_bash(self):
        assert expand_config_dir("/opt/claude-config", "bash") == "/opt/claude-config"

    def test_absolute_windows_path_normalizes_for_powershell(self):
        assert expand_config_dir("C:/Users/roman/cfg", "powershell") == "C:\\Users\\roman\\cfg"

    def test_unknown_shell_defaults_to_posix(self):
        """Shells we don't recognize get POSIX-style output (safe default)."""
        assert expand_config_dir("~/.claude", "kornshell", home="/home/x") == "/home/x/.claude"


class TestParseMarkerFields:
    """parse_marker_fields — handle legacy + extended marker formats."""

    def test_legacy_single_path(self, tmp_path):
        marker = tmp_path / ".maestro"
        marker.write_text("../my-maestro\n")
        assert parse_marker_fields(marker) == {"maestro_root": "../my-maestro"}

    def test_legacy_with_comments(self, tmp_path):
        marker = tmp_path / ".maestro"
        marker.write_text("# Path to maestro folder\n# Written by maestro init\n../my-maestro\n")
        assert parse_marker_fields(marker) == {"maestro_root": "../my-maestro"}

    def test_extended_format(self, tmp_path):
        marker = tmp_path / ".maestro"
        marker.write_text("../my-maestro\nexpected_account: riseapps\n")
        assert parse_marker_fields(marker) == {
            "maestro_root": "../my-maestro",
            "expected_account": "riseapps",
        }

    def test_explicit_maestro_root_key(self, tmp_path):
        """maestro_root: <path> as an explicit key also works."""
        marker = tmp_path / ".maestro"
        marker.write_text("maestro_root: ../my-maestro\nexpected_account: riseapps\n")
        assert parse_marker_fields(marker) == {
            "maestro_root": "../my-maestro",
            "expected_account": "riseapps",
        }

    def test_windows_absolute_path_bare(self, tmp_path):
        """Windows-style absolute paths (C:/foo) with a colon parse as bare."""
        marker = tmp_path / ".maestro"
        marker.write_text("C:/work/my-maestro\n")
        assert parse_marker_fields(marker) == {"maestro_root": "C:/work/my-maestro"}

    def test_unknown_key_ignored(self, tmp_path):
        """Unknown key: value lines don't pollute the result."""
        marker = tmp_path / ".maestro"
        marker.write_text("../my-maestro\ncustom_field: something\nexpected_account: riseapps\n")
        assert parse_marker_fields(marker) == {
            "maestro_root": "../my-maestro",
            "expected_account": "riseapps",
        }

    def test_empty_file(self, tmp_path):
        marker = tmp_path / ".maestro"
        marker.write_text("")
        assert parse_marker_fields(marker) == {}

    def test_only_comments(self, tmp_path):
        marker = tmp_path / ".maestro"
        marker.write_text("# comment 1\n# comment 2\n")
        assert parse_marker_fields(marker) == {}

    def test_nonexistent_file(self, tmp_path):
        marker = tmp_path / ".maestro"  # does not exist
        assert parse_marker_fields(marker) == {}

    def test_expected_account_alone(self, tmp_path):
        """Marker with only expected_account — no maestro_root."""
        marker = tmp_path / ".maestro"
        marker.write_text("expected_account: personal\n")
        assert parse_marker_fields(marker) == {"expected_account": "personal"}

    def test_first_bare_line_wins(self, tmp_path):
        """If multiple bare lines appear, the first one is maestro_root."""
        marker = tmp_path / ".maestro"
        marker.write_text("../first\n../second\n")
        assert parse_marker_fields(marker)["maestro_root"] == "../first"


class TestFindMarker:
    """find_marker — walk up looking for a .maestro file."""

    def test_in_current_dir(self, tmp_path):
        (tmp_path / ".maestro").write_text("../x\n")
        assert find_marker(tmp_path) == (tmp_path / ".maestro")

    def test_in_ancestor(self, tmp_path):
        (tmp_path / ".maestro").write_text("../x\n")
        deep = tmp_path / "src" / "components"
        deep.mkdir(parents=True)
        assert find_marker(deep) == (tmp_path / ".maestro")

    def test_not_found(self, tmp_path):
        # Use a tmp_path that has no .maestro anywhere above (until filesystem root)
        assert find_marker(tmp_path) is None or find_marker(tmp_path) != tmp_path / ".maestro"


class TestReadExpectedAccount:
    """read_expected_account — convenience over find_marker + parse."""

    def test_returns_account(self, tmp_path):
        (tmp_path / ".maestro").write_text("../my-maestro\nexpected_account: riseapps\n")
        assert read_expected_account(tmp_path) == "riseapps"

    def test_returns_none_for_legacy_marker(self, tmp_path):
        """Legacy marker without the field → None (not empty string)."""
        (tmp_path / ".maestro").write_text("../my-maestro\n")
        assert read_expected_account(tmp_path) is None

    def test_returns_none_for_empty_value(self, tmp_path):
        (tmp_path / ".maestro").write_text("../my-maestro\nexpected_account:\n")
        assert read_expected_account(tmp_path) is None

    def test_returns_none_when_no_marker(self, tmp_path):
        assert read_expected_account(tmp_path) is None


class TestFindMaestroRootWithExtendedMarker:
    """find_maestro_root must still work when marker has the extended format."""

    def test_extended_marker_resolves(self, workspace):
        repo = workspace["repo"]
        maestro = workspace["maestro"]
        (repo / ".maestro").write_text("../my-maestro\nexpected_account: riseapps\n")
        assert find_maestro_root(repo) == maestro.resolve()

    def test_explicit_key_form_resolves(self, workspace):
        repo = workspace["repo"]
        maestro = workspace["maestro"]
        (repo / ".maestro").write_text("maestro_root: ../my-maestro\nexpected_account: riseapps\n")
        assert find_maestro_root(repo) == maestro.resolve()
