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

import shutil
import subprocess
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
