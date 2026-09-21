"""ce-org-agent-bootstrap 3.3: prove the servers import cleanly from an
actual built-and-installed wheel, not just this repo's editable dev
install.

Tasks 3.1 (package restructure) and 3.2 (packaging config) are covered by
test_servers_package_import.py against the dev install; that gives no
signal on whether a future `[tool.hatch.build.targets.wheel]` edit
silently drops the `servers/` subpackage from the actual distributable
artifact (editable installs don't go through wheel-building at all). This
file builds a real wheel, installs it into a throwaway venv alongside a
local otaman-core checkout, and proves `python -m
otaman_plugin.servers.<name>` starts without ImportError there.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
CORE_ROOT = REPO_ROOT.parent / "otaman-core"

pytestmark = [
    pytest.mark.skipif(shutil.which("uv") is None, reason="uv not on PATH"),
    pytest.mark.skipif(not CORE_ROOT.is_dir(), reason="otaman-core sibling checkout not present"),
]


@pytest.fixture(scope="module")
def wheel_path(tmp_path_factory):
    out_dir = tmp_path_factory.mktemp("wheel-build")
    subprocess.run(
        ["uv", "build", "--out-dir", str(out_dir)],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=120,
    )
    wheels = list(out_dir.glob("otaman_plugin-*.whl"))
    assert len(wheels) == 1, f"expected exactly one built wheel, got {wheels}"
    return wheels[0]


@pytest.fixture(scope="module")
def fresh_venv_python(tmp_path_factory, wheel_path):
    venv_dir = tmp_path_factory.mktemp("fresh-venv") / "venv"
    subprocess.run(
        ["uv", "venv", str(venv_dir)], check=True, capture_output=True, text=True, timeout=60
    )
    python = venv_dir / "bin" / "python"
    subprocess.run(
        ["uv", "pip", "install", "--python", str(python), str(wheel_path), str(CORE_ROOT)],
        check=True,
        capture_output=True,
        text=True,
        timeout=180,
    )
    return python


@pytest.mark.parametrize(
    "module",
    ["otaman_plugin.servers.bus_server", "otaman_plugin.servers.estimation_server"],
)
def test_module_starts_without_import_error_from_built_wheel(fresh_venv_python, module):
    """`python -m <module>` must not raise ImportError from a plain
    `pip install otaman-plugin` — proves the servers subpackage actually
    shipped in the built wheel, per task 3.3.

    Neither server recognizes `--help` as a real flag (they're stdio MCP
    servers, not argparse CLIs) — passing it is harmless and the process
    just starts serving and blocks on stdin, which IS the "no ImportError"
    outcome under test. Kill it once that's evident from the timeout.
    """
    proc = subprocess.Popen(
        [str(fresh_venv_python), "-m", module, "--help"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        _, stderr = proc.communicate(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        _, stderr = proc.communicate()
    assert "ImportError" not in stderr, stderr
    assert "ModuleNotFoundError" not in stderr, stderr


# ---------------------------------------------------------------------------
# Shipped-hook dependency closure
#
# The wheel shipped three .sh entry points but NOT `_resolve.sh`, which all
# three source at line ~20. `find_maestro_root` was therefore never defined,
# and `PROJECT_ROOT="$(find_maestro_root)" || exit 0` took the exit —
# silently, with status 0. Every git hook was inert in a wheel install while
# looking perfectly healthy. Verified on haulops by deploy-agent
# (20260921T184535); the vendored tree had 20 files, the wheel had 3.
#
# These assert the CLOSURE, not a hardcoded list, so adding a new `source`
# line to a shipped hook fails here instead of in a tenant's silent hook.
# ---------------------------------------------------------------------------

_SHIPPED_HOOKS = ("spec-change-hook.sh", "post-commit-hook.sh", "check-branch.sh")

_DEP_RE = re.compile(r"\$SCRIPT_DIR/([A-Za-z0-9_.-]+)|/scripts/([A-Za-z0-9_.-]+)")


def _wheel_script_names(wheel_path) -> set[str]:
    with zipfile.ZipFile(wheel_path) as z:
        return {n.rsplit("/", 1)[-1] for n in z.namelist() if "/otaman_plugin/scripts/" in f"/{n}"}


def _sourced_deps(script: Path) -> set[str]:
    """Filenames a shipped hook sources or execs out of scripts/."""
    text = script.read_text(encoding="utf-8")
    found: set[str] = set()
    for a, b in _DEP_RE.findall(text):
        name = a or b
        # Only real files in scripts/, not glob-ish or templated fragments.
        if name and (REPO_ROOT / "scripts" / name).is_file():
            found.add(name)
    return found


def test_every_shipped_hook_has_its_dependencies_in_the_wheel(wheel_path):
    shipped = _wheel_script_names(wheel_path)
    missing: dict[str, set[str]] = {}
    for hook in _SHIPPED_HOOKS:
        assert hook in shipped, f"{hook} itself is not in the wheel"
        gap = _sourced_deps(REPO_ROOT / "scripts" / hook) - shipped
        if gap:
            missing[hook] = gap
    assert not missing, (
        "shipped hooks reference scripts that the wheel does not carry — "
        f"they will be inert in an installed tenant: {missing}"
    )


def test_resolve_sh_is_shipped(wheel_path):
    """Named explicitly because it is the fatal one: every shipped hook
    sources it, so its absence disables all of them at once."""
    assert "_resolve.sh" in _wheel_script_names(wheel_path)


def test_find_maestro_root_is_defined_for_a_wheel_installed_hook(fresh_venv_python):
    """The behavioural end of it, mirroring deploy-agent's reproduction: the
    function the hook dies without must actually be defined when the hook is
    sourced from an INSTALLED tree, not just present in the zip."""
    pkg_dir = subprocess.run(
        [
            str(fresh_venv_python),
            "-c",
            "import otaman_plugin,os;print(os.path.dirname(otaman_plugin.__file__))",
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    resolve_sh = Path(pkg_dir) / "scripts" / "_resolve.sh"
    assert resolve_sh.is_file(), f"_resolve.sh missing from installed tree: {resolve_sh}"

    probe = subprocess.run(
        [
            "bash",
            "-c",
            f'source "{resolve_sh}" && declare -F find_maestro_root >/dev/null && echo DEFINED',
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert "DEFINED" in probe.stdout, probe.stderr
