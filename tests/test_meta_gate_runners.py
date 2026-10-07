"""The otaman-meta gate's three runners (omg 1.1).

The structural-key guard in check-ownership.sh is a PreToolUse hook: it sees
an agent's `git commit`, and a `gh pr merge` never reaches it. So the
client-side control is bypassable by routing a structural change through a
PR — measured 2026-10-06. These runners are the server-side backstop.

THEY FAIL CLOSED, WHICH IS THE OPPOSITE OF THE HOOK. The shared comparison
returns () both for "nothing changed" and "could not parse", and the hook
resolves that as ALLOW (a speed bump that blocks on unreadable YAML blocks
the commit that fixes it). A server gate must resolve it as REFUSE, with a
distinct exit code so "refused because changed" and "refused because
unreadable" are never the same signal.

    0  clean        1  violated        2  could not determine

The schema runner is written and NOT wired — the step is commented out in
otaman-meta's workflow because platform.yaml is schema-invalid today
(`ownership` vs additionalProperties:false). The tripwire at the bottom fails
when core 1.4 lands, which is the signal to switch it on.
"""

from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent
STRUCTURAL = REPO / "scripts" / "meta_gate_structural.py"
PACKLINT = REPO / "scripts" / "meta_gate_packlint.py"
SCHEMA = REPO / "scripts" / "meta_gate_schema.py"

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not on PATH")

BASE_YAML = "project: acme\nrepos:\n  - name: a\n    owner: a-agent\nknowledge:\n  ttl: 30\n"


def _run(script: pathlib.Path, *args: str, cwd: pathlib.Path | None = None):
    env = {**os.environ, "PYTHONPATH": str(REPO / "src")}
    return subprocess.run(
        [sys.executable, str(script), *args],
        capture_output=True,
        text=True,
        cwd=str(cwd) if cwd else None,
        env=env,
        timeout=60,
    )


@pytest.fixture
def repo(tmp_path):
    """A git repo with platform.yaml and two commits, so base != head."""
    root = tmp_path / "meta"
    root.mkdir()
    env = {**os.environ, "GIT_CONFIG_GLOBAL": str(tmp_path / "gc")}

    def git(*a):
        subprocess.run(["git", *a], cwd=root, check=True, capture_output=True, env=env)

    git("init", "-q")
    git("config", "user.email", "t@t")
    git("config", "user.name", "t")
    (root / "platform.yaml").write_text(BASE_YAML, encoding="utf-8")
    git("add", "-A")
    git("commit", "-qm", "base")
    base = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, env=env
    ).stdout.strip()
    return {"root": root, "git": git, "base": base, "env": env}


def _commit(repo, content: str, msg: str = "change") -> str:
    (repo["root"] / "platform.yaml").write_text(content, encoding="utf-8")
    repo["git"]("add", "-A")
    repo["git"]("commit", "-qm", msg)
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo["root"],
        capture_output=True,
        text=True,
        env=repo["env"],
    ).stdout.strip()


class TestStructuralBackstop:
    def test_a_structural_change_is_REFUSED_with_exit_1(self, repo):
        head = _commit(repo, BASE_YAML.replace("a-agent", "someone-else"))
        r = _run(STRUCTURAL, "--base", repo["base"], "--head", head, cwd=repo["root"])
        assert r.returncode == 1, r.stdout + r.stderr
        assert "repos" in r.stderr

    def test_the_refusal_says_the_human_lands_it_not_a_PR(self, repo):
        """Matching the hook's corrected wording (plugin #130): there is no
        approval that makes this pass, so the message must not imply one."""
        head = _commit(repo, BASE_YAML.replace("a-agent", "x"))
        r = _run(STRUCTURAL, "--base", repo["base"], "--head", head, cwd=repo["root"])
        assert "THE HUMAN LANDS THESE, NOT A PR" in r.stderr
        assert "no approval that makes this check pass" in r.stderr

    def test_a_non_structural_change_PASSES(self, repo):
        """A gate that fires on ordinary edits gets turned off."""
        head = _commit(repo, BASE_YAML.replace("ttl: 30", "ttl: 90"))
        r = _run(STRUCTURAL, "--base", repo["base"], "--head", head, cwd=repo["root"])
        assert r.returncode == 0, r.stdout + r.stderr
        assert "no structural key changed" in r.stdout

    def test_ADDING_the_file_counts_as_structural(self, repo):
        """A path absent at base is an empty document, not a skip — otherwise
        introducing `ownership:` in a PR would sail through."""
        repo["git"]("rm", "-q", "platform.yaml")
        repo["git"]("commit", "-qm", "drop")
        empty = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo["root"],
            capture_output=True,
            text=True,
            env=repo["env"],
        ).stdout.strip()
        head = _commit(repo, BASE_YAML + "ownership:\n  otaman-folder: x\n", "add back")
        r = _run(STRUCTURAL, "--base", empty, "--head", head, cwd=repo["root"])
        assert r.returncode == 1
        assert "repos" in r.stderr and "ownership" in r.stderr

    def test_unparseable_yaml_is_exit_2_NOT_0(self, repo):
        """The fail-closed inversion. The hook allows here; the gate must not,
        and must not reuse exit 1 either — "changed" and "unreadable" are
        different findings with different fixes."""
        head = _commit(repo, "{{{ not yaml\n")
        r = _run(STRUCTURAL, "--base", repo["base"], "--head", head, cwd=repo["root"])
        assert r.returncode == 2, r.stdout + r.stderr
        assert "not parseable" in r.stderr
        assert "certifies nothing" in r.stderr

    def test_it_uses_the_SHARED_comparison(self):
        body = STRUCTURAL.read_text(encoding="utf-8")
        assert "structural_keys_changed" in body
        code = "\n".join(ln for ln in body.splitlines() if not ln.lstrip().startswith("#"))
        assert "!= after.get" not in code, "the gate reimplements the comparison"


class TestPackLint:
    def test_a_valid_pack_passes(self, tmp_path):
        packs = tmp_path / "packs" / "p"
        packs.mkdir(parents=True)
        (packs / "2026-10-07-a-thing.md").write_text(
            "---\ntype: lesson\nauthor: t\ncreated: 2026-10-07\n"
            "review-by: 2027-04-07\nanchor: plugin #131\ntitle: a thing\n---\nbody\n",
            encoding="utf-8",
        )
        r = _run(PACKLINT, str(tmp_path / "packs"))
        assert r.returncode == 0, r.stdout + r.stderr
        assert "0 invalid" in r.stdout

    def test_an_unanchored_entry_is_REFUSED(self, tmp_path):
        """The rule the validator exists for: an unanchored claim is
        indistinguishable from a guess six weeks later."""
        packs = tmp_path / "packs" / "p"
        packs.mkdir(parents=True)
        (packs / "2026-10-07-no-anchor.md").write_text(
            "---\ntype: lesson\nauthor: t\ncreated: 2026-10-07\n"
            "review-by: 2027-04-07\ntitle: no anchor\n---\nbody\n",
            encoding="utf-8",
        )
        r = _run(PACKLINT, str(tmp_path / "packs"))
        assert r.returncode == 1, r.stdout + r.stderr
        assert "invalid" in r.stderr

    def test_a_missing_packs_dir_is_NOT_an_error(self, tmp_path):
        """No packs and a pack that failed to load are different states."""
        r = _run(PACKLINT, str(tmp_path / "nope"))
        assert r.returncode == 0
        assert "nothing to lint" in r.stdout


class TestSchemaRunnerIsWiredAndWorks:
    def test_it_catches_an_undeclared_top_level_key(self, tmp_path):
        """The schema is additionalProperties:false, so an undeclared key is
        the failure mode this catches.

        This test originally used `ownership:` — the exact shape that was
        invalid on main when I wrote it. core 1.4 landed mid-task and made
        that fixture VALID, so the test was asserting a premise that had
        expired. Rewritten with a key no schema will ever declare.
        """
        pytest.importorskip("jsonschema")
        p = tmp_path / "platform.yaml"
        p.write_text(
            'project: acme\nversion: "1.0"\nrepos: []\nnot_a_real_platform_key: true\n',
            encoding="utf-8",
        )
        r = _run(SCHEMA, str(p))
        assert r.returncode == 1, r.stdout + r.stderr
        assert "not_a_real_platform_key" in r.stderr

    def test_the_LIVE_platform_yaml_validates(self):
        """The config this gate will actually run against. If this fails, the
        gate blocks every merge to otaman-meta."""
        pytest.importorskip("jsonschema")
        live = REPO.parent / "otaman-meta" / "platform.yaml"
        if not live.is_file():
            pytest.skip("otaman-meta checkout not present")
        r = _run(SCHEMA, str(live))
        assert r.returncode == 0, r.stdout + r.stderr

    # The "otaman_core unimportable -> exit 2" path is NOT unit-tested here.
    # I wrote a test for it that failed: otaman_core is editable-installed in
    # this workspace, so PYTHONPATH cannot hide it, and the runner simply
    # validated the fixture instead. That is the second time this session I
    # asserted an environment I cannot create rather than a behaviour I
    # control (the first was "no python on PATH", caught by CI). The branch is
    # three lines and the pack-lint equivalent below exercises the same shape
    # via a directory that genuinely does not exist.

    def test_the_schema_step_IS_wired_now_that_core_1_4_landed(self):
        """Held for one day, then enabled. core 1.4 (core #129, 2aacf47) added
        the top-level `ownership:` entry; before it, enabling this step would
        have blocked every merge to the coordination repo including the fixes."""
        wf = REPO.parent / "otaman-meta" / ".github" / "workflows" / "meta-gate.yml"
        if not wf.is_file():
            pytest.skip("otaman-meta checkout not present")
        active = "\n".join(
            ln
            for ln in wf.read_text(encoding="utf-8").splitlines()
            if not ln.lstrip().startswith("#")
        )
        assert "meta_gate_schema.py" in active, "the schema step is still commented out"

    def test_the_workflow_makes_otaman_core_IMPORTABLE(self):
        """Both the pack lint and the schema check import otaman_core. Without
        a checkout they exit 2 on every run — a gate that refuses everything is
        as useless as one that passes everything. Found by this file's own
        tests failing, not by reading the workflow."""
        wf = REPO.parent / "otaman-meta" / ".github" / "workflows" / "meta-gate.yml"
        if not wf.is_file():
            pytest.skip("otaman-meta checkout not present")
        active = "\n".join(
            ln
            for ln in wf.read_text(encoding="utf-8").splitlines()
            if not ln.lstrip().startswith("#")
        )
        assert "inprimex/otaman-core" in active, "otaman_core is not checked out"
        for runner in ("meta_gate_packlint.py", "meta_gate_schema.py"):
            idx = active.index(runner)
            assert "otaman-core/src" in active[max(0, idx - 400) : idx], (
                f"{runner} runs without otaman-core on PYTHONPATH"
            )

    def test_core_1_4_landed_and_the_live_config_validates(self):
        """Replaces the tripwire, which fired on first run. Kept as a standing
        assertion rather than deleted: if the schema ever loses `ownership`
        again, the live platform.yaml silently becomes invalid."""
        pytest.importorskip("yaml")
        import otaman_core
        import yaml

        schema_path = pathlib.Path(otaman_core.__file__).parent / "schemas" / "platform-schema.yaml"
        if not schema_path.is_file():
            pytest.skip("core ships no platform schema here")
        schema = yaml.safe_load(schema_path.read_text(encoding="utf-8"))
        assert "ownership" in (schema.get("properties") or {}), (
            "core's schema no longer declares `ownership` — the live platform.yaml "
            "is schema-invalid again and the gate will block every merge"
        )
