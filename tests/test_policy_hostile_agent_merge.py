"""policy-engine 4.1: hostile-agent enforcement test (rails acceptance triple, D7).

Exercises the REAL merge guard — ``otaman policy check-merge`` — by
importing it directly from the sibling ``otaman-cli`` checkout's source
(not a possibly-stale pipx-installed ``otaman`` binary), matching this
repo's own ``otaman_stub_bin`` convention in conftest.py: test against the
actual sibling-checkout code, not whatever release happens to be
installed on the machine running the suite.

Scope: the policy-pack-git spec (``specs/policy-pack-git/spec.md``,
scenario "hostile agent merge is refused twice") requires the merge be
refused BY GENERATED BRANCH PROTECTION *and* BY THE CLI GUARD. Generated
protection is live GitHub state applied by deploy's task 3.1 — not
testable here without a live repo. This test covers the cli-guard half,
which is pure ``otaman-core``/``otaman-cli`` resolution logic this repo
can exercise directly, end to end, against real fixtures.

Per otaman-cli's own module docs: owner intent is resolved from
``resolve_branch_owner`` (``<type>/<owner>/<topic>`` convention, or
``policy/git/branch-owners.yaml``) — NEVER from live branch protection
(design D4a). Exit 3 = refused; exit 0 = allowed.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

_CLI_SRC = str(Path(__file__).resolve().parent.parent.parent / "otaman-cli" / "src")
if _CLI_SRC not in sys.path:
    sys.path.insert(0, _CLI_SRC)

from otaman_cli.commands.policy import _cmd_check_merge  # noqa: E402

_GUARD_REFUSED = 3


def _setup(tmp_path, monkeypatch, *, repo_owner: str) -> Path:
    """A (meta root, repo dir) fixture pair, resolved via ``OTAMAN_ROOT``
    (the env-var resolution step conftest.py's autouse fixture strips for
    every test specifically so tests can set their own) rather than a
    ``.otaman`` marker file: otaman-core's marker resolution rejects any
    relative marker path resolving outside ``$HOME`` as a security
    measure, which a ``tmp_path``-based fixture (under the OS tmp tree)
    always trips. root/platform.yaml declares one repo owned by
    ``repo_owner`` and one human-roster entry (roman)."""
    root = tmp_path / "otaman-meta"
    root.mkdir()
    repo_dir = tmp_path / "agent-repo"
    repo_dir.mkdir()
    monkeypatch.setenv("OTAMAN_ROOT", str(root))

    config = {
        "project": "test",
        "human-roster": [
            {"name": "roman", "email": "roman@example.com", "roles": ["founder"]},
        ],
        "repos": [{"name": "agent-repo", "path": "../agent-repo", "owner": repo_owner}],
    }
    (root / "platform.yaml").write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    return repo_dir


class TestHostileAgentMergeGuard:
    def test_hostile_agent_merge_into_human_owned_branch_is_refused(
        self, tmp_path, monkeypatch, capsys
    ):
        """The named motivating scenario: an agent session (caller resolved
        via cwd -> platform.yaml -> owner, no OTAMAN_HUMAN set) attempts to
        merge into a branch owned by a human (naming convention
        `feat/roman/billing`) -> refused, naming the owner."""
        repo_dir = _setup(tmp_path, monkeypatch, repo_owner="some-agent")
        monkeypatch.setenv("OTAMAN_TEST_MODE", "1")
        monkeypatch.chdir(repo_dir)

        code = _cmd_check_merge("feat/roman/billing", None)

        assert code == _GUARD_REFUSED
        out = capsys.readouterr().out
        assert "roman" in out
        assert "agent" in out.lower()

    def test_agent_self_merge_on_agent_owned_branch_succeeds(self, tmp_path, monkeypatch, capsys):
        """Positive control: the same agent caller merging into a branch it
        owns itself succeeds — proves the guard discriminates real
        ownership, not just refusing everything."""
        repo_dir = _setup(tmp_path, monkeypatch, repo_owner="some-agent")
        monkeypatch.setenv("OTAMAN_TEST_MODE", "1")
        monkeypatch.chdir(repo_dir)

        code = _cmd_check_merge("feat/some-agent/topic", None)

        assert code == 0
        assert "OK to merge" in capsys.readouterr().out

    def test_owner_less_branch_is_refused(self, tmp_path, monkeypatch, capsys):
        """A branch matching no convention and no registry entry is
        owner-less — refused, per the pack's 'branch without a resolvable
        owner is flagged' requirement."""
        repo_dir = _setup(tmp_path, monkeypatch, repo_owner="some-agent")
        monkeypatch.setenv("OTAMAN_TEST_MODE", "1")
        monkeypatch.chdir(repo_dir)

        code = _cmd_check_merge("random-branch-name", None)

        assert code == _GUARD_REFUSED
        assert "owner-less" in capsys.readouterr().out

    def test_human_caller_merging_into_own_branch_succeeds(self, tmp_path, monkeypatch, capsys):
        """The owner themself (identified via OTAMAN_HUMAN matching the
        roster) merging into their own branch is not an agent-hostile
        case — succeeds."""
        repo_dir = _setup(tmp_path, monkeypatch, repo_owner="some-agent")
        monkeypatch.setenv("OTAMAN_TEST_MODE", "1")
        monkeypatch.setenv("OTAMAN_HUMAN", "roman")
        monkeypatch.chdir(repo_dir)

        code = _cmd_check_merge("feat/roman/billing", None)

        assert code == 0
        assert "OK to merge" in capsys.readouterr().out
