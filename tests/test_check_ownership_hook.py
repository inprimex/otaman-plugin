"""Tests for scripts/check-ownership.sh.

Focus of this suite: the deny path must surface its reason. The hook used
to print JSON *and* exit 2, but exit 2 makes Claude Code ignore stdout JSON
and read (empty) stderr — so denials showed only a generic "denied" (the
same opacity bug fixed in check-blocked.sh, issue #73). Every deny site now
emits permissionDecision:deny + permissionDecisionReason + systemMessage and
exits 0. These tests also lock in the underlying ownership / spec / contract
protection behaviour, which previously had no regression coverage.

Runs the real shell hook via subprocess against a fixture otaman project.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).parent.parent
HOOK = REPO / "scripts" / "check-ownership.sh"
AGENT = "test-agent"


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "proj"
    (root / ".agents" / "blocked").mkdir(parents=True)
    (root / "platform.yaml").write_text(
        "project: test\nversion: \"1.0\"\nspecs:\n  path: ../specsrepo\n  format: openspec\n",
        encoding="utf-8",
    )
    (root / ".otaman").write_text(".\n", encoding="utf-8")
    # Pretty-printed (one field per line) — matches `otaman init` output,
    # which the sed field extraction relies on.
    (root / ".agents" / "ownership.json").write_text(
        json.dumps(
            {
                "project": "test",
                "repos": [
                    {"name": "myrepo", "path": "../myrepo", "owner": AGENT},
                    {"name": "otherrepo", "path": "../otherrepo", "owner": "other-agent"},
                    {"name": "specsrepo", "path": "../specsrepo", "owner": "spec-agent"},
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    for r in ("myrepo", "otherrepo", "specsrepo"):
        (tmp_path / r / "src").mkdir(parents=True)
    return {"root": root, "base": tmp_path}


def run_write(project, target: Path) -> tuple[int, dict | None]:
    payload = json.dumps(
        {"tool_name": "Edit", "tool_input": {"file_path": str(target)}, "file_path": str(target)}
    )
    return _run(project, payload)


def run_bash(project, command: str) -> tuple[int, dict | None]:
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}, "command": command})
    return _run(project, payload)


def _run(project, payload: str) -> tuple[int, dict | None]:
    root = project["root"]
    proc = subprocess.run(
        ["bash", str(HOOK)],
        input=payload,
        capture_output=True,
        text=True,
        timeout=15,
        cwd=str(root),
        env={"PATH": "/usr/bin:/bin", "OTAMAN_AGENT": AGENT, "HOME": str(root)},
    )
    out = proc.stdout.strip()
    return proc.returncode, (json.loads(out) if out else None)


def assert_allowed(rc: int, parsed: dict | None):
    assert rc == 0
    assert parsed is None, f"expected allow (no output), got {parsed}"


def assert_denied(rc: int, parsed: dict | None) -> str:
    # The core fix: deny MUST exit 0 (not 2) so the JSON is honoured.
    assert rc == 0, f"deny must exit 0 (not {rc}); exit 2 discards stdout JSON"
    assert parsed is not None, "deny must emit JSON on stdout"
    hso = parsed["hookSpecificOutput"]
    assert hso["hookEventName"] == "PreToolUse"
    assert hso["permissionDecision"] == "deny"
    assert hso.get("permissionDecisionReason"), "reason must reach the model"
    assert parsed.get("systemMessage"), "reason must reach the operator"
    return hso["permissionDecisionReason"]


class TestAllow:
    def test_own_repo_write_allowed(self, project):
        assert_allowed(*run_write(project, project["base"] / "myrepo" / "src" / "foo.py"))

    def test_coordination_file_allowed(self, project):
        assert_allowed(
            *run_write(project, project["root"] / ".agents" / "blocked" / f"{AGENT}.md")
        )

    def test_own_repo_contract_allowed(self, project):
        # Repo owner may modify contracts in their own repo.
        assert_allowed(*run_write(project, project["base"] / "myrepo" / "api.openapi.yaml"))

    def test_own_repo_bash_redirect_allowed(self, project):
        tgt = project["base"] / "myrepo" / "src" / "x.txt"
        assert_allowed(*run_bash(project, f"echo hi > {tgt}"))


class TestDenySurfacesReason:
    def test_other_agent_repo_denied(self, project):
        reason = assert_denied(*run_write(project, project["base"] / "otherrepo" / "src" / "bar.py"))
        assert "otherrepo" in reason and "other-agent" in reason

    def test_specs_repo_denied_for_non_owner(self, project):
        reason = assert_denied(
            *run_write(project, project["base"] / "specsrepo" / "openspec" / "spec.md")
        )
        assert "/otaman:propose" in reason

    def test_contract_in_other_repo_denied(self, project):
        reason = assert_denied(
            *run_write(project, project["base"] / "otherrepo" / "api.openapi.yaml")
        )
        assert "contract" in reason.lower()
        assert "/otaman:propose" in reason

    def test_schemas_dir_in_other_repo_denied(self, project):
        reason = assert_denied(
            *run_write(project, project["base"] / "otherrepo" / "schemas" / "x.json")
        )
        assert "/otaman:propose" in reason

    def test_bash_redirect_to_other_repo_denied(self, project):
        tgt = project["base"] / "otherrepo" / "src" / "x.txt"
        reason = assert_denied(*run_bash(project, f"echo hi > {tgt}"))
        assert "Bash redirect" in reason

    def test_deny_json_is_valid_with_quoted_agent_name(self, project):
        # The reason quotes the agent name (Agent "test-agent" ...); the
        # helper must JSON-escape those quotes. json.loads in _run already
        # proves validity — assert the quoting made it through intact.
        reason = assert_denied(*run_write(project, project["base"] / "otherrepo" / "src" / "bar.py"))
        assert '"test-agent"' in reason
