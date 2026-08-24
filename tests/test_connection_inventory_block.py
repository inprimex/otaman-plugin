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
import json
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


def test_missing_refs_and_no_report_render_as_dash():
    block = gen._render_connection_inventory(
        [_StubConn("ssh-host", "ssh", "sunflowers.host", "program", ssh_ref="sunflowers")]
    )
    # secret_ref absent -> em dash; ssh_ref shown; last-check em dash (no report)
    assert "sunflowers" in block
    row = [ln for ln in block.splitlines() if ln.startswith("| ssh-host ")][0]
    assert row.count("—") >= 2  # missing secret_ref + no-report last-check


def test_last_check_joins_persisted_report_on_name():
    """When a persisted check report is supplied, last-check shows status · time."""
    checks = {"gh": "ok · 2026-08-24T17:00Z"}
    block = gen._render_connection_inventory(
        [
            _StubConn("gh", "git-https", "github.com", "program", secret_ref="gh-pat"),
            _StubConn("api", "api", "api.example.com", "program"),  # no report
        ],
        checks,
    )
    gh_row = [ln for ln in block.splitlines() if ln.startswith("| gh ")][0]
    api_row = [ln for ln in block.splitlines() if ln.startswith("| api ")][0]
    assert "ok · 2026-08-24T17:00Z" in gh_row
    assert api_row.rstrip().endswith("— |")  # unmatched name falls back to —


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


def _write_checks(home: Path, program: str, reports: list[dict]) -> None:
    (home / ".otaman").mkdir(parents=True, exist_ok=True)
    (home / ".otaman" / "connection-checks.json").write_text(
        json.dumps({"version": 1, "programs": {program: reports}}),
        encoding="utf-8",
    )


def test_load_checks_reads_persisted_report(tmp_path):
    """cli-agent §3.1 contract: ~/.otaman/connection-checks.json keyed by program."""
    _write_checks(
        tmp_path,
        "otaman-dev",
        [{"name": "gh", "status": "ok", "checked_at": "2026-08-24T17:00Z"}],
    )
    checks = gen._load_connection_checks("otaman-dev", home=tmp_path)
    assert checks == {"gh": "ok · 2026-08-24T17:00Z"}


def test_load_checks_absent_or_wrong_program_returns_empty(tmp_path):
    # No file at all
    assert gen._load_connection_checks("otaman-dev", home=tmp_path) == {}
    # File exists but program key absent
    _write_checks(tmp_path, "other-prog", [{"name": "x", "checked_at": "t"}])
    assert gen._load_connection_checks("otaman-dev", home=tmp_path) == {}
    # No program name -> empty
    assert gen._load_connection_checks(None, home=tmp_path) == {}


def test_load_checks_malformed_json_degrades_to_empty(tmp_path):
    (tmp_path / ".otaman").mkdir(parents=True)
    (tmp_path / ".otaman" / "connection-checks.json").write_text("{not json", encoding="utf-8")
    assert gen._load_connection_checks("otaman-dev", home=tmp_path) == {}


def test_load_checks_skips_entries_without_name_or_timestamp(tmp_path):
    _write_checks(
        tmp_path,
        "p",
        [
            {"name": "good", "status": "ok", "checked_at": "2026-08-24T17:00Z"},
            {"name": "no-time", "status": "ok"},  # missing checked_at -> skipped
            {"status": "ok", "checked_at": "t"},  # missing name -> skipped
        ],
    )
    assert gen._load_connection_checks("p", home=tmp_path) == {"good": "ok · 2026-08-24T17:00Z"}


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
