"""Tests for scripts/_log.sh — bash size-based log rotation helper.

Skipped on Windows: the GitHub-Actions Windows runner maps ``bash`` to
``wsl.exe bash``, and the runner image has no WSL distro installed, so
every subprocess call fails with "Windows Subsystem for Linux has no
installed distributions." The helper itself is only ever sourced by
Linux/macOS hooks on the server side — there's no production path that
runs ``_log.sh`` on Windows, so skipping the matrix entry is correct.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform == "win32",
    reason="bash helper not exercised on Windows; see module docstring",
)

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
LOG_SH = PLUGIN_ROOT / "scripts" / "_log.sh"


def _run_rotate(
    log_file: Path, *extra_args: str, env: dict | None = None
) -> subprocess.CompletedProcess:
    """Source _log.sh and call rotate_log; returns the completed process."""
    args = " ".join(f"'{a}'" for a in extra_args)
    log_posix = Path(log_file).as_posix()
    helper_posix = LOG_SH.as_posix()
    script = f'set -e; source "{helper_posix}"; rotate_log "{log_posix}" {args}'
    return subprocess.run(
        ["bash", "-c", script],
        capture_output=True,
        text=True,
        env={**os.environ, **(env or {})},
    )


@pytest.fixture
def log_dir(tmp_path):
    return tmp_path


def test_missing_file_is_noop(log_dir):
    """Calling rotate on a nonexistent file should not raise or create anything."""
    result = _run_rotate(log_dir / "missing.log")
    assert result.returncode == 0
    assert not (log_dir / "missing.log").exists()
    assert not (log_dir / "missing.log.1").exists()


def test_under_threshold_is_noop(log_dir):
    """A small log file should not get rotated."""
    log = log_dir / "small.log"
    log.write_text("tiny\n")
    result = _run_rotate(log)
    assert result.returncode == 0
    assert log.exists()
    assert log.read_text() == "tiny\n"
    assert not (log_dir / "small.log.1").exists()


def test_over_threshold_shifts_to_log_1(log_dir):
    """A log over the threshold should move to <log>.1 and the base file should be gone."""
    log = log_dir / "big.log"
    log.write_bytes(b"X" * 2_000_000)  # 2 MiB > 1 MiB default
    result = _run_rotate(log)
    assert result.returncode == 0, result.stderr
    assert not log.exists()
    assert (log_dir / "big.log.1").exists()
    assert (log_dir / "big.log.1").stat().st_size == 2_000_000


def test_custom_threshold_via_arg(log_dir):
    """Explicit max_bytes argument should override the default."""
    log = log_dir / "med.log"
    log.write_bytes(b"X" * 500)  # 500 bytes
    # Threshold 200 → should rotate
    result = _run_rotate(log, "200")
    assert result.returncode == 0
    assert not log.exists()
    assert (log_dir / "med.log.1").exists()


def test_custom_threshold_via_env(log_dir):
    """OTAMAN_LOG_MAX_BYTES env var should be honored when args omitted."""
    log = log_dir / "env.log"
    log.write_bytes(b"X" * 500)
    result = _run_rotate(log, env={"OTAMAN_LOG_MAX_BYTES": "200"})
    assert result.returncode == 0
    assert not log.exists()
    assert (log_dir / "env.log.1").exists()


def test_shift_chain_promotes_each_backup(log_dir):
    """Multiple rotations: each old backup gets shifted by one, oldest is dropped."""
    log = log_dir / "chain.log"
    # Seed prior backups so we can check the shift cleanly.
    (log_dir / "chain.log.1").write_text("backup-1\n")
    (log_dir / "chain.log.2").write_text("backup-2\n")
    (log_dir / "chain.log.3").write_text("backup-3-OLDEST\n")
    log.write_bytes(b"Z" * 2_000_000)  # current run, over threshold

    result = _run_rotate(log)
    assert result.returncode == 0, result.stderr

    # Base log is gone.
    assert not log.exists()
    # Previously .1 (most recent backup) should now be .2.
    assert (log_dir / "chain.log.2").read_text() == "backup-1\n"
    # Previously .2 should now be .3.
    assert (log_dir / "chain.log.3").read_text() == "backup-2\n"
    # The oldest (.3 "backup-3-OLDEST") should have been dropped.
    assert "backup-3-OLDEST" not in (log_dir / "chain.log.3").read_text()
    # New .1 is the previously-current log.
    assert (log_dir / "chain.log.1").stat().st_size == 2_000_000
    # Total backup count is the configured keep=3, not 4.
    assert not (log_dir / "chain.log.4").exists()


def test_custom_keep_count(log_dir):
    """Explicit keep argument should override the default of 3."""
    log = log_dir / "keep5.log"
    (log_dir / "keep5.log.1").write_text("b1\n")
    (log_dir / "keep5.log.2").write_text("b2\n")
    (log_dir / "keep5.log.3").write_text("b3\n")
    (log_dir / "keep5.log.4").write_text("b4\n")
    (log_dir / "keep5.log.5").write_text("b5-oldest\n")
    log.write_bytes(b"Y" * 2_000_000)

    result = _run_rotate(log, "1048576", "5")
    assert result.returncode == 0, result.stderr

    assert (log_dir / "keep5.log.5").read_text() == "b4\n"
    assert (log_dir / "keep5.log.4").read_text() == "b3\n"
    assert (log_dir / "keep5.log.3").read_text() == "b2\n"
    assert (log_dir / "keep5.log.2").read_text() == "b1\n"
    assert (log_dir / "keep5.log.1").stat().st_size == 2_000_000
    # The oldest "b5-oldest" was dropped during the rotation.
    assert not (log_dir / "keep5.log.6").exists()


def test_empty_path_argument_is_noop(log_dir):
    """Calling with an empty path should not error and not create files."""
    result = _run_rotate(Path(""))
    assert result.returncode == 0


def test_rotation_preserves_directory_siblings(log_dir):
    """Rotation should only touch <log>* files, not unrelated siblings in the same dir."""
    log = log_dir / "iso.log"
    log.write_bytes(b"X" * 2_000_000)
    sibling = log_dir / "unrelated.txt"
    sibling.write_text("keep me\n")

    result = _run_rotate(log)
    assert result.returncode == 0
    assert sibling.exists()
    assert sibling.read_text() == "keep me\n"


def test_repeated_rotation_caps_backup_count(log_dir):
    """Calling rotate_log multiple times shouldn't accumulate extra backups."""
    log = log_dir / "loop.log"
    # Round 1
    log.write_bytes(b"A" * 2_000_000)
    _run_rotate(log)
    # Round 2 — new content over threshold
    log.write_bytes(b"B" * 2_000_000)
    _run_rotate(log)
    # Round 3
    log.write_bytes(b"C" * 2_000_000)
    _run_rotate(log)
    # Round 4 (one more than keep=3)
    log.write_bytes(b"D" * 2_000_000)
    _run_rotate(log)

    assert not log.exists()
    assert (log_dir / "loop.log.1").exists()
    assert (log_dir / "loop.log.2").exists()
    assert (log_dir / "loop.log.3").exists()
    # No .4 — keep=3 should have dropped the oldest each round.
    assert not (log_dir / "loop.log.4").exists()
