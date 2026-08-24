"""agent-credential-access 2.1: the generated CLAUDE.local.md must carry a
compaction-durable connection/credential inventory — LOCATORS ONLY, never
values — rendered from otaman-core's frozen connection resolver contract
(core-agent 20260824T164952).

Pins the load-bearing behavior so a future generator edit can't silently drop
the block or start leaking values — same convention as
test_spec_authoring_guard_template.py.
"""

from __future__ import annotations

import importlib
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
gen = importlib.import_module("otaman_plugin.generate_agent_config")

REPO_ROOT = Path(__file__).resolve().parent.parent
GENERATOR = REPO_ROOT / "src" / "otaman_plugin" / "generate_agent_config.py"


@dataclass
class _StubConn:
    """Duck-typed stand-in for otaman_core.connections.Connection.

    Carries an extra ``token`` attribute the renderer must NEVER read — a
    tripwire proving the block only emits declared locator fields.
    """

    name: str
    type: str
    endpoint: str
    scope: str
    secret_ref: str | None = None
    ssh_ref: str | None = None
    token: str = "SUPER-SECRET-VALUE-should-never-render"


def test_empty_inventory_renders_nothing():
    assert gen._render_connection_inventory([]) == ""


def test_renders_table_with_locator_columns():
    block = gen._render_connection_inventory(
        [_StubConn("gh", "git-https", "github.com", "program", secret_ref="gh-pat")]
    )
    assert "### Connections & credentials" in block
    # Column header + the row's locator fields.
    for cell in ("name", "type", "endpoint", "scope", "secret_ref", "ssh_ref", "last-check"):
        assert cell in block
    assert "gh" in block and "git-https" in block and "github.com" in block
    assert "gh-pat" in block  # secret_ref locator IS shown


def test_never_renders_values():
    """The tripwire: a value-bearing attribute must never reach output."""
    block = gen._render_connection_inventory(
        [_StubConn("api", "api", "api.example.com", "tenant", secret_ref="api-key")]
    )
    assert "SUPER-SECRET-VALUE-should-never-render" not in block


def test_missing_refs_render_as_dash_and_last_check_is_placeholder():
    block = gen._render_connection_inventory(
        [_StubConn("ssh-host", "ssh", "sunflowers.host", "program", ssh_ref="sunflowers")]
    )
    # secret_ref absent -> em dash; ssh_ref shown; last-check always em dash (1.3 pending)
    assert "sunflowers" in block
    row = [ln for ln in block.splitlines() if ln.startswith("| ssh-host ")][0]
    assert row.count("—") >= 2  # missing secret_ref + last-check placeholder


def test_rows_sorted_by_scope_then_name():
    block = gen._render_connection_inventory(
        [
            _StubConn("zeta", "api", "z", "program"),
            _StubConn("alpha", "api", "a", "tenant"),
            _StubConn("beta", "api", "b", "program"),
        ]
    )
    order = [ln.split("|")[1].strip() for ln in block.splitlines() if ln.startswith("| ")][1:]
    # scope order program/tenant is alphabetical on the tuple; within scope by name
    assert order == ["beta", "zeta", "alpha"]


def test_aligns_with_core_connection_dataclass():
    """Render the REAL core Connection to prove the contract fields match."""
    from otaman_core.connections import Connection

    c = Connection(
        name="core-real",
        type="ssh",
        endpoint="git@github.com",
        scope="program",
        secret_ref="deploy-key",
        ssh_ref="gh-alias",
    )
    block = gen._render_connection_inventory([c])
    assert "core-real" in block and "deploy-key" in block and "gh-alias" in block


def test_block_is_wired_into_maestro_template():
    """The section must be interpolated into the CLAUDE.local.md template and
    fed by the core resolver — guard against a silent drop on future edits."""
    source = GENERATOR.read_text(encoding="utf-8")
    assert "{connection_section}" in source
    assert "connections.resolve_for(project_root)" in source


def test_build_maestro_block_embeds_program_connections(tmp_path):
    """End-to-end: a program-scoped connections.yaml surfaces in the block."""
    (tmp_path / "connections.yaml").write_text(
        "connections:\n"
        "  - name: prog-git\n"
        "    type: git-https\n"
        "    endpoint: github.com\n"
        "    secret_ref: prog-pat\n",
        encoding="utf-8",
    )
    repo = {"name": "backend", "path": "./backend", "owner": "dev-agent"}
    block = gen._build_maestro_block(repo, [repo], ".agents/bus", {}, tmp_path)
    assert "### Connections & credentials" in block
    assert "prog-git" in block and "prog-pat" in block
