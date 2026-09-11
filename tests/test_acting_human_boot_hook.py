"""Tests for hooks/acting-human-boot.sh — team-mode-registers-and-sessions
2.1 (B1), plugin's reader half.

Bridge writes <otaman-root>/.otaman/acting-human.json for a multi-human
tenant's runner-spawned session (otaman_bridge.acting_human.write_acting_human);
this hook reads it and (a) injects additionalContext naming the acting
human + roster roles, (b) exports GIT_AUTHOR/COMMITTER env into
CLAUDE_ENV_FILE so commits for the rest of the session are attributed
correctly. Absent file (CE/single-human, or bridge never ran) is a silent
no-op — this suite's autouse isolate_bus fixture already strips
OTAMAN_ROOT/MAESTRO_ROOT/OTAMAN_AGENT so a real ambient identity in this
dev environment can't leak into the hermetic test subprocess.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).parent.parent
HOOK = REPO / "hooks" / "acting-human-boot.sh"

HAVE_BASH = shutil.which("bash") is not None
HAVE_PYTHON3 = shutil.which("python3") is not None

pytestmark = [
    pytest.mark.skipif(not HAVE_BASH, reason="bash not on PATH"),
    pytest.mark.skipif(not HAVE_PYTHON3, reason="python3 not on PATH"),
]


@pytest.fixture(autouse=True)
def _unpin_root(monkeypatch):
    """bus-test-isolation 4.2 footgun: the shared isolate_bus fixture pins
    OTAMAN_ROOT at a sandbox, which the hook's find_maestro_root (called
    with no args -> checks OTAMAN_ROOT before walking up from PWD) would
    pick up instead of this suite's own tmp_path fixtures. Delete it (and
    the legacy MAESTRO_ROOT) on top of isolate_bus for this file only."""
    monkeypatch.delenv("OTAMAN_ROOT", raising=False)
    monkeypatch.delenv("MAESTRO_ROOT", raising=False)


def _make_root(tmp_path: Path, *, acting_human: dict | None) -> Path:
    root = tmp_path / "otaman-root"
    root.mkdir()
    (root / "platform.yaml").write_text("project: test\n", encoding="utf-8")
    if acting_human is not None:
        (root / ".otaman").mkdir()
        (root / ".otaman" / "acting-human.json").write_text(
            json.dumps(acting_human), encoding="utf-8"
        )
    return root


def _run_hook(root: Path, env_file: Path) -> subprocess.CompletedProcess:
    # Inherits os.environ AS ALREADY STRIPPED by the suite's autouse
    # isolate_bus fixture (OTAMAN_ROOT/MAESTRO_ROOT/OTAMAN_AGENT gone) —
    # not the raw ambient dev-session environment.
    env = {**os.environ, "CLAUDE_ENV_FILE": str(env_file)}
    return subprocess.run(
        ["bash", str(HOOK)],
        cwd=str(root),
        capture_output=True,
        text=True,
        timeout=15,
        env=env,
    )


class TestInertOnAbsentFile:
    def test_no_file_no_output_no_env(self, tmp_path):
        root = _make_root(tmp_path, acting_human=None)
        env_file = tmp_path / "env.sh"
        env_file.write_text("", encoding="utf-8")
        r = _run_hook(root, env_file)
        assert r.returncode == 0
        assert r.stdout.strip() == ""
        assert env_file.read_text(encoding="utf-8") == ""


class TestMultiHumanBoot:
    def test_injects_additional_context(self, tmp_path):
        root = _make_root(
            tmp_path,
            acting_human={
                "email": "alice@example.com",
                "name": "Alice",
                "roles": ["cofounder", "cto"],
                "source": "attach-jwt",
            },
        )
        env_file = tmp_path / "env.sh"
        env_file.write_text("", encoding="utf-8")
        r = _run_hook(root, env_file)
        assert r.returncode == 0, r.stderr
        payload = json.loads(r.stdout)
        ctx = payload["hookSpecificOutput"]["additionalContext"]
        assert payload["hookSpecificOutput"]["hookEventName"] == "SessionStart"
        assert "Alice" in ctx
        assert "alice@example.com" in ctx
        assert "cofounder" in ctx and "cto" in ctx
        assert "acting-human: alice@example.com" in ctx

    def test_exports_git_author_and_committer(self, tmp_path):
        root = _make_root(
            tmp_path,
            acting_human={"email": "bob@example.com", "name": "Bob", "roles": []},
        )
        env_file = tmp_path / "env.sh"
        env_file.write_text("", encoding="utf-8")
        r = _run_hook(root, env_file)
        assert r.returncode == 0, r.stderr
        exports = env_file.read_text(encoding="utf-8")
        assert "GIT_AUTHOR_NAME=Bob" in exports
        assert "GIT_AUTHOR_EMAIL=bob@example.com" in exports
        assert "GIT_COMMITTER_NAME=Bob" in exports
        assert "GIT_COMMITTER_EMAIL=bob@example.com" in exports

    def test_missing_name_falls_back_to_email(self, tmp_path):
        """Human authenticated but not on the roster — bridge attributes by
        email with an empty name (its own docstring: 'still attributed by
        email, roles empty, never silently dropped')."""
        root = _make_root(tmp_path, acting_human={"email": "carol@example.com", "roles": []})
        env_file = tmp_path / "env.sh"
        env_file.write_text("", encoding="utf-8")
        r = _run_hook(root, env_file)
        assert r.returncode == 0, r.stderr
        payload = json.loads(r.stdout)
        ctx = payload["hookSpecificOutput"]["additionalContext"]
        assert "carol@example.com" in ctx
        exports = env_file.read_text(encoding="utf-8")
        assert "GIT_AUTHOR_NAME=carol@example.com" in exports

    def test_no_roles_omits_roster_roles_sentence(self, tmp_path):
        root = _make_root(
            tmp_path, acting_human={"email": "dave@example.com", "name": "Dave", "roles": []}
        )
        env_file = tmp_path / "env.sh"
        env_file.write_text("", encoding="utf-8")
        r = _run_hook(root, env_file)
        payload = json.loads(r.stdout)
        ctx = payload["hookSpecificOutput"]["additionalContext"]
        assert "Roster roles" not in ctx


class TestMalformedFileDegradesSilently:
    def test_invalid_json_no_crash(self, tmp_path):
        root = _make_root(tmp_path, acting_human=None)
        (root / ".otaman").mkdir()
        (root / ".otaman" / "acting-human.json").write_text("{not json", encoding="utf-8")
        env_file = tmp_path / "env.sh"
        env_file.write_text("", encoding="utf-8")
        r = _run_hook(root, env_file)
        assert r.returncode == 0
        assert r.stdout.strip() == ""

    def test_empty_email_no_crash(self, tmp_path):
        root = _make_root(tmp_path, acting_human={"email": "", "name": "Nobody"})
        env_file = tmp_path / "env.sh"
        env_file.write_text("", encoding="utf-8")
        r = _run_hook(root, env_file)
        assert r.returncode == 0
        assert r.stdout.strip() == ""
