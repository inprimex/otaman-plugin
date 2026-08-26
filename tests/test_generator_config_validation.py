"""Regression: the generator must FAIL FAST on a malformed/wrong platform.yaml,
not crash deep in generation with a cryptic ``KeyError: 'project'`` that reads
as a partial success (bug 20260826T211138, fleet-impact).

Root cause: `otaman init --update` resolved a stale org-level platform.yaml
(only `models`/`bus`, no schema-required `project`/`version`/`repos`) and passed
it to the generator; `generate_ownership_json`'s `config["project"]` raised.
The crash blocked CLAUDE.local.md regeneration fleet-wide while the wrapping
output still claimed patches applied.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
gen = importlib.import_module("otaman_plugin.generate_agent_config")


def _run_main_on(path: Path, monkeypatch) -> int:
    monkeypatch.setattr(sys, "argv", ["generate-agent-config.py", str(path)])
    return gen.main()


def test_missing_project_fails_fast_not_keyerror(tmp_path, monkeypatch, capsys):
    """A partial platform.yaml (the org-level models+bus stray) → rc 2 + clear
    message, NEVER a raw KeyError."""
    bad = tmp_path / "platform.yaml"
    bad.write_text("models:\n  default: sonnet\nbus:\n  routing_rules: []\n", encoding="utf-8")
    rc = _run_main_on(bad, monkeypatch)  # must not raise
    assert rc == 2
    err = capsys.readouterr().err
    assert "missing required key(s)" in err
    assert "project" in err
    # names the offending file so the wrong-file cause is debuggable
    assert str(bad) in err


def test_non_dict_config_fails_fast(tmp_path, monkeypatch, capsys):
    """An empty / non-mapping YAML must also fail cleanly, not TypeError."""
    empty = tmp_path / "platform.yaml"
    empty.write_text("", encoding="utf-8")  # safe_load -> None
    rc = _run_main_on(empty, monkeypatch)
    assert rc == 2
    assert "did not parse as a platform config" in capsys.readouterr().err


def test_all_three_required_keys_are_checked(tmp_path, monkeypatch, capsys):
    """project present but version/repos missing still fails fast."""
    partial = tmp_path / "platform.yaml"
    partial.write_text("project: demo\n", encoding="utf-8")
    rc = _run_main_on(partial, monkeypatch)
    assert rc == 2
    err = capsys.readouterr().err
    assert "version" in err and "repos" in err
