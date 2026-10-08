"""The post-commit hook notifies declared observers, or nobody.

MEASURED FAILURE THIS FIXES (2026-10-03). The hook's header has always said it
"checks observer triggers from platform.yaml". It never did. It hardcoded
`to: human` and told the human that "observers matching these triggers should
review this commit" — while no observer concept was declared anywhere in the
platform schema. Result: 953 review-requests into one queue over four months,
69% of a 1,385-message backlog, from a notifier with no recipients notifying a
bystander.

A second defect rode along: attribution read `$PROJECT_ROOT/.agents/current-agent`,
a single TENANT-WIDE file. On one sampled day, 43 messages about four different
repos all claimed `from: fswatch-agent`, an agent that had committed nothing —
it was simply the name last written to that file. It is also step 5 of cli's
6-step identity chain and deprecated; cwd-ownership was made authoritative by
team-mode B1 precisely so a stale shared value cannot claim another repo.

THE DEFAULT IS SILENCE. An unresolved recipient is not a reason to pick one.
With no observers declared the hook writes no message and says so on stderr,
which git shows to whoever ran the commit — not to a queue nobody asked for.
That branch is the one that fired 953 times, so it is the one most of these
tests are about.
"""

from __future__ import annotations

import os
import pathlib
import shutil
import subprocess

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent
HOOK = REPO / "scripts" / "post-commit-hook.sh"

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not on PATH")


def _tenant(tmp_path: pathlib.Path, platform_yaml: str) -> tuple[pathlib.Path, pathlib.Path]:
    """A sandbox otaman root + one repo inside it, with a real commit."""
    root = tmp_path / "otaman-meta"
    (root / ".agents" / "bus" / "active").mkdir(parents=True)
    (root / "platform.yaml").write_text(platform_yaml, encoding="utf-8")

    repo = tmp_path / "acme-widget"
    repo.mkdir()
    env = {**os.environ, "GIT_CONFIG_GLOBAL": str(tmp_path / "gitconfig")}
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True, env=env)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=repo, check=True, env=env)
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True, env=env)
    # Two commits: `git diff-tree -r HEAD` is empty on a root commit (no
    # parent), so a single-commit fixture would exercise nothing and pass.
    (repo / "README.md").write_text("acme\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, env=env)
    subprocess.run(["git", "commit", "-qm", "chore: init"], cwd=repo, check=True, env=env)
    (repo / "thing.py").write_text("x = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, env=env)
    subprocess.run(["git", "commit", "-qm", "feat: a thing"], cwd=repo, check=True, env=env)
    return root, repo


def _run(root: pathlib.Path, repo: pathlib.Path, *, path_extra: str | None = None):
    env = {
        **os.environ,
        "OTAMAN_ROOT": str(root),
        "OTAMAN_PROJECT_ROOT": str(root),
        "GIT_CONFIG_GLOBAL": str(root.parent / "gitconfig"),
    }
    if path_extra is not None:
        env["PATH"] = path_extra
    return subprocess.run(["bash", str(HOOK)], cwd=repo, capture_output=True, text=True, env=env)


def _messages(root: pathlib.Path) -> list[pathlib.Path]:
    return sorted((root / ".agents" / "bus" / "active").glob("*.md"))


NO_OBSERVERS = """\
project: acme
repos:
  - name: acme-widget
    path: ../acme-widget
    owner: widget-agent
"""

WITH_OBSERVERS = """\
project: acme
observers:
  - security-agent
  - arch-agent
repos:
  - name: acme-widget
    path: ../acme-widget
    owner: widget-agent
"""


class TestTheDefaultIsSilence:
    """The branch that fired 953 times."""

    def test_no_observers_declared_writes_NO_message(self, tmp_path):
        root, repo = _tenant(tmp_path, NO_OBSERVERS)
        result = _run(root, repo)
        assert result.returncode == 0, result.stderr
        assert _messages(root) == [], (
            "a commit with no declared observers still produced a bus message — "
            "this is the 953-message defect"
        )

    def test_it_SAYS_why_on_stderr_rather_than_silently(self, tmp_path):
        """Silence toward the bus, not toward the person who ran the commit.
        git shows hook stderr, so the one human in a position to act sees it."""
        root, repo = _tenant(tmp_path, NO_OBSERVERS)
        result = _run(root, repo)
        assert "no observers are declared" in result.stderr
        assert "no review-request sent" in result.stderr

    def test_the_human_is_never_the_fallback_recipient(self, tmp_path):
        root, repo = _tenant(tmp_path, NO_OBSERVERS)
        _run(root, repo)
        assert not list((root / ".agents" / "bus" / "active").glob("*to-human*"))

    def test_no_recipient_is_hard_coded_in_the_script(self):
        """A reinstated `to: human` is the whole defect returning."""
        body = HOOK.read_text(encoding="utf-8")
        code = "\n".join(ln for ln in body.splitlines() if not ln.lstrip().startswith("#"))
        assert "to: human" not in code
        assert "to-human" not in code


class TestDeclaredObserversAreNotified:
    def test_the_first_observer_is_the_recipient(self, tmp_path):
        root, repo = _tenant(tmp_path, WITH_OBSERVERS)
        result = _run(root, repo)
        assert result.returncode == 0, result.stderr
        msgs = _messages(root)
        assert len(msgs) == 1, f"expected one message, got {[m.name for m in msgs]}"
        assert "to-security-agent" in msgs[0].name
        assert "to: security-agent" in msgs[0].read_text(encoding="utf-8")

    def test_the_rest_are_CC_not_dropped(self, tmp_path):
        """Two declared observers and one notified is a silent half-delivery."""
        root, repo = _tenant(tmp_path, WITH_OBSERVERS)
        _run(root, repo)
        text = _messages(root)[0].read_text(encoding="utf-8")
        assert "cc: [arch-agent]" in text

    def test_a_single_observer_emits_no_empty_cc(self, tmp_path):
        root, repo = _tenant(tmp_path, "observers:\n  - solo-agent\n")
        _run(root, repo)
        text = _messages(root)[0].read_text(encoding="utf-8")
        assert "to: solo-agent" in text
        assert "cc:" not in text, "an empty cc list is malformed frontmatter"


class TestAttributionIsThisRepoNotTheTenantFile:
    def test_the_deprecated_shared_file_is_not_read(self):
        """`.agents/current-agent` is step 5 of cli's chain and deprecated; it
        is one file for the whole tenant, so reading it attributes every repo's
        commits to whoever wrote it last."""
        body = HOOK.read_text(encoding="utf-8")
        code = "\n".join(ln for ln in body.splitlines() if not ln.lstrip().startswith("#"))
        assert "current-agent" not in code

    def test_a_stale_tenant_file_cannot_claim_this_repo(self, tmp_path):
        """The measured failure, reproduced: a tenant file naming a completely
        different agent must not end up on this repo's commit."""
        root, repo = _tenant(tmp_path, WITH_OBSERVERS)
        (root / ".agents" / "current-agent").write_text("someone-else\n", encoding="utf-8")
        _run(root, repo, path_extra="/usr/bin:/bin")  # no `otaman` on PATH
        text = _messages(root)[0].read_text(encoding="utf-8")
        assert "someone-else" not in text
        assert "from: acme-widget" in text, "the fallback should be the repo itself"

    def test_it_asks_otaman_when_otaman_is_available(self):
        """Resolution belongs to cli's identity chain, not to a second copy
        of ownership logic in a shell script."""
        body = HOOK.read_text(encoding="utf-8")
        assert "whoami --resolve-only" in body
        assert "platform.yaml" in body
        # ...but it must NOT hand-roll ownership parsing to get there.
        assert "owner:" not in body.replace("# ", ""), "ownership is resolved, not parsed"


MAP_SHAPED = """\
project: acme
observers:
  - role: cto-reviewer
    triggers:
      - code-change
      - ci-change
  - role: security-observer
    triggers:
      - security-change
repos:
  - name: acme-widget
    path: ../acme-widget
    owner: widget-agent
"""


class TestAMapShapedObserversBlockIsRefusedNotGuessedAt:
    """Relayed from the pmeets tenant (20261008T090540), reproduced here
    against this hook's own awk before fixing.

    THREE defects, only one of which was the reported symptom:

      1. the end-of-list test only fired at column 0, so a nested `triggers:`
         block never ended the list and its items became recipients — two
         observers produced FIVE names, three of them trigger values;
      2. `to: role: cto-reviewer` is INVALID YAML (ScannerError: mapping
         values are not allowed here) — an unparseable message in every
         reader's triage, and the half a filename fix does not touch;
      3. `cc: [code-change,...,role: security-observer,...]` PARSES, into four
         bogus recipients one of which is a dict. Valid YAML, garbage
         semantics — the quieter and worse half, since CC fan-out would have
         written per-recipient copies addressed to `code-change`.

    The fix REFUSES rather than adding map support: this hook's own comment
    says the `observers:` shape is deliberately minimal and unratified, and
    honouring a key is not the same as inventing a contract. A malformed
    message in the bus is strictly worse than no message.
    """

    def test_it_sends_NOTHING(self, tmp_path):
        root, repo = _tenant(tmp_path, MAP_SHAPED)
        result = _run(root, repo)
        assert result.returncode == 0, result.stderr
        assert _messages(root) == [], "a map-shaped observers block still produced a bus message"

    def test_it_says_why_and_what_to_do(self, tmp_path):
        root, repo = _tenant(tmp_path, MAP_SHAPED)
        result = _run(root, repo)
        assert "non-flat entry" in result.stderr
        assert "flat list of agent names" in result.stderr
        assert "ratify" in result.stderr, "it should name the alternative, not just refuse"

    def test_no_unparseable_frontmatter_can_be_written(self, tmp_path):
        """Defect 2 directly: nothing in the bus may carry `to: role: x`."""
        root, repo = _tenant(tmp_path, MAP_SHAPED)
        _run(root, repo)
        for m in _messages(root):
            assert "to: role:" not in m.read_text(encoding="utf-8")

    def test_trigger_names_never_become_recipients(self, tmp_path):
        """Defect 1 and 3: `code-change` is a trigger, not an agent."""
        root, repo = _tenant(tmp_path, MAP_SHAPED)
        _run(root, repo)
        names = " ".join(m.name for m in _messages(root))
        for trigger in ("code-change", "ci-change", "security-change"):
            assert trigger not in names

    def test_a_FLAT_block_still_works(self, tmp_path):
        """The regression that matters: fixing the map case must not break the
        shape the hook actually supports."""
        root, repo = _tenant(tmp_path, WITH_OBSERVERS)
        _run(root, repo)
        msgs = _messages(root)
        assert len(msgs) == 1
        text = msgs[0].read_text(encoding="utf-8")
        assert "to: security-agent" in text
        assert "cc: [arch-agent]" in text

    def test_the_awk_reads_only_TOP_LEVEL_items(self, tmp_path):
        """Narrower than the refusal: even before the `:` check, the parser
        must stop pulling nested list items. Asserted by count, since a
        future map-support change would keep the parser and drop the refusal.
        """
        import re
        import subprocess as sp

        hook = (REPO / "scripts" / "post-commit-hook.sh").read_text(encoding="utf-8")
        awk = re.search(r"OBSERVERS=\"\$\(awk '(.*?)' \"\$PLATFORM_YAML\"", hook, re.S)
        assert awk, "could not locate the observers parser"
        pf = tmp_path / "platform.yaml"
        pf.write_text(MAP_SHAPED, encoding="utf-8")
        out = (
            sp.run(["awk", awk.group(1), str(pf)], capture_output=True, text=True)
            .stdout.strip()
            .splitlines()
        )
        assert len(out) == 2, f"parser emitted {len(out)} items from 2 observers: {out}"


class TestTheDefenceInDepthIsActuallyREACHABLE:
    """Sabotage caught these as untested: with a map-shaped block the refusal
    fires first, so nothing downstream of it could be exercised that way.

    But both guards are reachable by a flat entry that is still not a usable
    agent name — which is the realistic case anyway, since the refusal only
    screens for `:`."""

    def test_a_name_with_a_SPACE_is_refused_before_frontmatter(self, tmp_path):
        """Passes the `:` screen, would still break the `to:` line's meaning
        and the filename. The guard, not the refusal, catches this."""
        root, repo = _tenant(tmp_path, "observers:\n  - two words\n")
        result = _run(root, repo)
        assert _messages(root) == []
        assert "not a usable agent name" in result.stderr

    def test_a_name_needing_SLUGIFY_keeps_the_real_value_in_to(self, tmp_path):
        """The reporter's design intent: sanitise the FILENAME, never the
        recipient. `agent/foo` is a legal YAML scalar and a bad path
        component."""
        root, repo = _tenant(tmp_path, "observers:\n  - agent/foo\n")
        result = _run(root, repo)
        msgs = _messages(root)
        assert len(msgs) == 1, result.stderr
        assert "/" not in msgs[0].name, "an unslugified name reached the path"
        assert "agent-foo" in msgs[0].name
        assert "to: agent/foo" in msgs[0].read_text(encoding="utf-8"), (
            "the recipient was mangled; only the filename should be slugified"
        )
