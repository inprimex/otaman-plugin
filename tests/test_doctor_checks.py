"""Tests for otaman_plugin.doctor_checks (tasks 2.4 / 2.5 from
finish-maestro-to-otaman-migration)."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

from otaman_plugin.doctor_checks import (
    DoctorWarning,
    check_launch_commands_have_continue_flag,
    check_plugin_dir_consistency,
    run_all_checks,
)


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dedent(body).lstrip())


def _platform_yaml(commands: list[str], repo_name: str = "repo-a") -> str:
    # Build the YAML directly without dedent gymnastics so each `- "..."`
    # entry lands at the right indent level under `commands:`.
    cmd_lines = "\n".join(f"          - {c!r}" for c in commands)
    return (
        "project: test\n"
        "repos:\n"
        f"  - name: {repo_name}\n"
        f"    path: ../{repo_name}\n"
        "    owner: test-agent\n"
        "    launch:\n"
        "      title: T\n"
        "      shell: ssh\n"
        "      commands:\n"
        f"{cmd_lines}\n"
    )


def _launch_settings(
    active_connection: str = "lan",
    conn_type: str = "ssh",
    ssh_plugin_path: str = "/home/u/otaman/otaman-plugin",
) -> str:
    body = (
        f"active_connection: {active_connection}\n"
        "connections:\n"
        f"  {active_connection}:\n"
        f"    type: {conn_type}\n"
    )
    if ssh_plugin_path:
        body += f"    ssh_plugin_path: {ssh_plugin_path}\n"
    return body


# ---------------------------------------------------------------------------
# M-4 — plugin-dir consistency


class TestPluginDirConsistency:
    def test_matching_plugin_dir_no_warning(self, tmp_path: Path) -> None:
        _write(
            tmp_path / "platform.yaml",
            _platform_yaml(
                [
                    "claude --plugin-dir /home/u/otaman/otaman-plugin '/otaman:check'",
                ]
            ),
        )
        _write(tmp_path / "launch-settings.yaml", _launch_settings())
        warnings = check_plugin_dir_consistency(tmp_path)
        assert [w for w in warnings if w.code == "M4_PLUGIN_DIR_DRIFT"] == []

    def test_drift_warns(self, tmp_path: Path) -> None:
        _write(
            tmp_path / "platform.yaml",
            _platform_yaml(
                [
                    "claude --plugin-dir /home/u/legacy-maestro-plugin '/otaman:check'",
                ]
            ),
        )
        _write(tmp_path / "launch-settings.yaml", _launch_settings())
        warnings = check_plugin_dir_consistency(tmp_path)
        drift = [w for w in warnings if w.code == "M4_PLUGIN_DIR_DRIFT"]
        assert len(drift) == 1
        assert "legacy-maestro-plugin" in drift[0].message
        assert "/home/u/otaman/otaman-plugin" in drift[0].message
        assert drift[0].repo == "repo-a"
        assert drift[0].hint is not None

    def test_no_settings_no_warnings(self, tmp_path: Path) -> None:
        _write(
            tmp_path / "platform.yaml",
            _platform_yaml(["claude --plugin-dir /some/path '/otaman:check'"]),
        )
        # No launch-settings.yaml → check is a no-op (nothing to compare against)
        warnings = check_plugin_dir_consistency(tmp_path)
        assert warnings == []

    def test_local_connection_skips_plugin_dir_check(self, tmp_path: Path) -> None:
        """Plugin-dir drift only matters for SSH connections; for `local`
        the path stays on the laptop and ssh_plugin_path is irrelevant."""
        _write(
            tmp_path / "platform.yaml",
            _platform_yaml(["claude --plugin-dir /home/u/whatever '/otaman:check'"]),
        )
        _write(
            tmp_path / "launch-settings.yaml",
            _launch_settings(conn_type="local", ssh_plugin_path=""),
        )
        warnings = check_plugin_dir_consistency(tmp_path)
        assert [w for w in warnings if w.code == "M4_PLUGIN_DIR_DRIFT"] == []

    def test_wsl_path_under_ssh_warns(self, tmp_path: Path) -> None:
        _write(
            tmp_path / "platform.yaml",
            _platform_yaml(
                [
                    "claude --plugin-dir /mnt/c/work/otaman/otaman-plugin '/otaman:check'",
                ]
            ),
        )
        _write(tmp_path / "launch-settings.yaml", _launch_settings())
        warnings = check_plugin_dir_consistency(tmp_path)
        codes = [w.code for w in warnings]
        assert "M4_WSL_PATH_UNDER_SSH" in codes

    def test_wsl_path_under_local_no_warning(self, tmp_path: Path) -> None:
        """WSL paths are fine when the connection IS local-wsl."""
        _write(
            tmp_path / "platform.yaml",
            _platform_yaml(["claude --plugin-dir /mnt/c/work/p '/otaman:check'"]),
        )
        _write(
            tmp_path / "launch-settings.yaml",
            _launch_settings(conn_type="local", ssh_plugin_path=""),
        )
        warnings = check_plugin_dir_consistency(tmp_path)
        assert [w for w in warnings if w.code == "M4_WSL_PATH_UNDER_SSH"] == []

    def test_disabled_repo_skipped(self, tmp_path: Path) -> None:
        _write(
            tmp_path / "platform.yaml",
            "project: t\n"
            "repos:\n"
            "  - name: dead\n"
            "    path: ../dead\n"
            "    owner: t\n"
            "    disabled: true\n"
            "    launch:\n"
            "      commands:\n"
            "        - \"claude --plugin-dir /wrong/path '/otaman:check'\"\n",
        )
        _write(tmp_path / "launch-settings.yaml", _launch_settings())
        warnings = check_plugin_dir_consistency(tmp_path)
        assert warnings == []


# ---------------------------------------------------------------------------
# M-13b — -c flag presence


class TestContinueFlagCheck:
    def test_command_with_c_short_flag_passes(self, tmp_path: Path) -> None:
        _write(
            tmp_path / "platform.yaml",
            _platform_yaml(["claude -c '/otaman:check'"]),
        )
        warnings = check_launch_commands_have_continue_flag(tmp_path)
        assert warnings == []

    def test_command_with_continue_long_flag_passes(self, tmp_path: Path) -> None:
        _write(
            tmp_path / "platform.yaml",
            _platform_yaml(["claude --continue '/otaman:check'"]),
        )
        warnings = check_launch_commands_have_continue_flag(tmp_path)
        assert warnings == []

    def test_command_with_resume_passes(self, tmp_path: Path) -> None:
        _write(
            tmp_path / "platform.yaml",
            _platform_yaml(["claude --resume abc123 '/otaman:check'"]),
        )
        warnings = check_launch_commands_have_continue_flag(tmp_path)
        assert warnings == []

    def test_missing_c_warns(self, tmp_path: Path) -> None:
        _write(
            tmp_path / "platform.yaml",
            _platform_yaml(
                [
                    "source ~/.nvm/nvm.sh && claude --plugin-dir /p '/otaman:check'",
                ]
            ),
        )
        warnings = check_launch_commands_have_continue_flag(tmp_path)
        missing = [w for w in warnings if w.code == "M13B_MISSING_CONTINUE_FLAG"]
        assert len(missing) == 1
        assert missing[0].repo == "repo-a"
        assert "without -c" in missing[0].message

    def test_version_probe_alone_does_not_warn(self, tmp_path: Path) -> None:
        """A command that ONLY does --version probing isn't an interactive
        slash-command call; shouldn't flag for missing -c."""
        _write(
            tmp_path / "platform.yaml",
            _platform_yaml(["claude --version >/dev/null 2>&1"]),
        )
        warnings = check_launch_commands_have_continue_flag(tmp_path)
        assert warnings == []

    def test_version_probe_plus_slash_command_in_one_line(self, tmp_path: Path) -> None:
        """A line with BOTH a --version probe AND a real claude call should
        evaluate the real call only; the probe is stripped before the check."""
        # Without -c on the real call → warn
        _write(
            tmp_path / "platform.yaml",
            _platform_yaml(
                [
                    "claude --version >/dev/null 2>&1 || true; claude '/otaman:check'",
                ]
            ),
        )
        warnings = check_launch_commands_have_continue_flag(tmp_path)
        assert any(w.code == "M13B_MISSING_CONTINUE_FLAG" for w in warnings)

        # With -c on the real call → no warn
        _write(
            tmp_path / "platform.yaml",
            _platform_yaml(
                [
                    "claude --version >/dev/null 2>&1 || true; claude -c '/otaman:check'",
                ]
            ),
        )
        warnings = check_launch_commands_have_continue_flag(tmp_path)
        assert [w for w in warnings if w.code == "M13B_MISSING_CONTINUE_FLAG"] == []

    def test_non_claude_command_ignored(self, tmp_path: Path) -> None:
        """Commands that don't invoke `claude` aren't subject to this check."""
        _write(
            tmp_path / "platform.yaml",
            _platform_yaml(["echo hi && bash -c 'echo done'"]),
        )
        warnings = check_launch_commands_have_continue_flag(tmp_path)
        assert warnings == []

    def test_word_boundary_avoids_false_positives(self, tmp_path: Path) -> None:
        """A token like `claude-something` shouldn't match the claude word
        boundary."""
        _write(
            tmp_path / "platform.yaml",
            _platform_yaml(["claudette --foo /bar"]),
        )
        warnings = check_launch_commands_have_continue_flag(tmp_path)
        assert warnings == []


# ---------------------------------------------------------------------------
# entry point


class TestRunAllChecks:
    def test_empty_root_returns_empty(self, tmp_path: Path) -> None:
        warnings = run_all_checks(tmp_path)
        assert warnings == []

    def test_returns_list_of_doctor_warnings(self, tmp_path: Path) -> None:
        _write(
            tmp_path / "platform.yaml",
            _platform_yaml(
                [
                    "claude --plugin-dir /legacy/path '/otaman:check'",
                ]
            ),
        )
        _write(tmp_path / "launch-settings.yaml", _launch_settings())
        warnings = run_all_checks(tmp_path)
        assert len(warnings) >= 2  # plugin-dir drift + missing -c
        assert all(isinstance(w, DoctorWarning) for w in warnings)
        codes = {w.code for w in warnings}
        assert "M4_PLUGIN_DIR_DRIFT" in codes
        assert "M13B_MISSING_CONTINUE_FLAG" in codes
