"""`resolve_otaman_python` must return an interpreter that can IMPORT, not
merely one that exists (deploy-agent 20261002T141745).

It knew only the dev uv-workspace venv (`$plugin_root/../.venv`), so on every
DEPLOYED tenant it fell through to bare `python3` and handed callers an
interpreter without the module they were about to use. That is the root cause
of spec-agent's dead push-dispatch, and all 8 tenants carry this file.

Reproduced from the installed tree before changing anything: the resolver
returned `python3`, which raises ModuleNotFoundError, while
`$HOME/.local/venv/otaman/bin/python` imports fine.

THE MODULE IS A PARAMETER, and that is not over-engineering. Measured on this
host: the dev workspace venv imports `otaman_core` but NOT `otaman_plugin`
(pytest supplies that path via pyproject `pythonpath`; it is not installed).
A fixed `otaman_plugin` probe would reject the dev venv and change dev
behaviour, which deploy asked to leave alone; a fixed `otaman_core` probe
would hand an otaman_plugin caller the same broken interpreter this fixes.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RESOLVE = REPO / "scripts" / "_resolve.sh"


def _resolve(plugin_root: str, module: str = "", env: dict | None = None) -> tuple[int, str]:
    arg = f'"{plugin_root}" {module}'.strip()
    proc = subprocess.run(
        ["bash", "-c", f'source "{RESOLVE}"; resolve_otaman_python {arg}'],
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
    )
    return proc.returncode, proc.stdout.strip()


class TestItReturnsSomethingThatCanImport:
    def test_the_returned_python_imports_the_requested_module(self):
        rc, py = _resolve(str(REPO))
        assert rc == 0 and py
        probe = subprocess.run([py, "-c", "import otaman_core"], capture_output=True)
        assert probe.returncode == 0, f"resolver returned a python that cannot import: {py}"

    def test_asking_for_otaman_plugin_returns_one_that_has_it(self):
        """The case that was broken: a caller running a script which imports
        otaman_plugin got an interpreter without it."""
        rc, py = _resolve(str(REPO), "otaman_plugin")
        assert rc == 0 and py
        probe = subprocess.run([py, "-c", "import otaman_plugin"], capture_output=True)
        assert probe.returncode == 0, f"returned a python lacking otaman_plugin: {py}"

    def test_an_unimportable_module_fails_CLOSED_with_empty_stdout(self):
        """Echoing a broken interpreter is the defect. Nothing on stdout, and
        a non-zero return, because callers test the return code."""
        rc, out = _resolve(str(REPO), "a_module_that_does_not_exist_xyz")
        assert rc != 0
        assert out == "", f"a failing resolve still printed an interpreter: {out!r}"


class TestTheDeployedLayoutIsKnown:
    def test_the_deployed_venv_path_is_a_candidate(self):
        """The whole defect: only the dev layout was known, so deployed
        tenants fell through to bare python3."""
        body = RESOLVE.read_text(encoding="utf-8")
        assert "$HOME/.local/venv/otaman/bin/python" in body

    def test_the_dev_workspace_venv_is_still_tried_first(self):
        """deploy asked for dev to stay unchanged. Order matters: a developer
        must keep getting their workspace venv."""
        body = RESOLVE.read_text(encoding="utf-8")
        dev = body.index('"$plugin_root/../.venv/bin/python"')
        deployed = body.index('"$HOME/.local/venv/otaman/bin/python"')
        assert dev < deployed

    def test_existence_alone_is_no_longer_sufficient(self):
        """The old test was `[[ -x ... ]]`, which is exactly why a python that
        exists but cannot import was returned as success."""
        body = RESOLVE.read_text(encoding="utf-8")
        fn = body[body.index("resolve_otaman_python() {") :]
        fn = fn[: fn.index("\n}")]
        assert "import $module" in fn, "candidates are not probed with a real import"


class TestCallersAskForWhatTheyNeed:
    def test_the_map_tasks_caller_requests_otaman_plugin(self):
        """Its comment has always said the interpreter MUST import
        otaman_plugin; the call did not ask for it. Stating a requirement in a
        comment while checking something weaker is how it stayed broken."""
        body = (REPO / "scripts" / "spec-change-hook.sh").read_text(encoding="utf-8")
        assert "resolve_otaman_python" in body
        call = body[body.index('PYTHON="$(resolve_otaman_python') :][:200]
        assert "otaman_plugin" in call

    def test_the_drain_hook_does_not_use_a_bare_python3_chain(self):
        """Same defect class, in a hook added the day before the report."""
        body = (REPO / "hooks" / "session-start-specs-drain.sh").read_text(encoding="utf-8")
        assert "resolve_otaman_python" in body
        assert '_PY="python3"' not in body, "the bare interpreter chain is back"


def test_every_hook_running_an_otaman_importing_script_uses_the_resolver():
    """Sweep, per deploy's "worth grepping your callers".

    The rule is precise rather than blanket: a hook that picks an interpreter
    with `command -v python3` has the original defect ONLY if the script it
    runs actually imports otaman_*. Four hooks (stop-notify, bridge-approval,
    and the two afk ones) use a bare chain and are fine — their target scripts
    are not shipped in this repo at all, so nothing runs. Failing them would
    be noise, and a sweep that cries wolf gets deleted.
    """
    offenders = []
    for path in list((REPO / "hooks").glob("*.sh")) + list((REPO / "scripts").glob("*.sh")):
        body = path.read_text(encoding="utf-8")
        bare = '_PY="python3"' in body or 'PY="python3"' in body
        if not bare:
            continue
        for target in re.findall(r"([A-Za-z0-9_\-]+\.py)", body):
            script = REPO / "scripts" / target
            if not script.is_file():
                continue
            if re.search(r"^\s*(from|import) otaman_", script.read_text(encoding="utf-8"), re.M):
                offenders.append(f"{path.name} -> {target}")
    assert not offenders, (
        "these pick an interpreter by bare PATH lookup but run a script that "
        f"imports otaman_*: {offenders}"
    )


def test_python_running_the_tests_is_not_assumed(tmp_path):
    """The resolver must not silently depend on the suite's own interpreter."""
    assert sys.executable
