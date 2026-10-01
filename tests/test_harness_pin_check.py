"""Installed harness vs the fleet's pin (harness-version-management 1.3).

D1: the platform harness registry is the ONE authority — "two sources WILL
disagree, and that lesson is literally in the knowledge pack". So the pin is
read there and nowhere else.

NOT-CHECKED IS THE PERMANENT ANSWER for a pin-less tenant, not a stopgap
(spec-agent ruling 20261001T112410). A platform.yaml with no pin is a real
state the check must keep speaking about, and reporting `fresh` for a fleet
that was never compared is the failure this check exists to prevent.

Clause 3, as the ruling specified it: deleting the pin field must flip the
verdict from compared to NOT-CHECKED — never to OK.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest
import yaml

from otaman_plugin.runtime_freshness import (
    HARNESS_PIN_FIELD,
    check_harness_vs_pin,
)

#: A binary that exists everywhere the suite runs, so the "installed" side is
#: real rather than mocked — the check shells out, and a mock would not catch
#: a broken invocation.
PROBE_BINARY = "python3"


def _real_version() -> str:
    out = subprocess.run([PROBE_BINARY, "--version"], capture_output=True, text=True)
    return re.search(r"\d+\.\d+\.\d+", out.stdout or out.stderr).group(0)


def _root(tmp_path: Path, *, pin: str | None = None, binary: str = PROBE_BINARY, harnesses=...):
    entry: dict = {"id": "claude-code", "binary": binary}
    if pin is not None:
        entry["pin"] = pin
    cfg: dict = {"project": "t"}
    if harnesses is ...:
        cfg["runner"] = {"harnesses": [entry]}
    elif harnesses is not None:
        cfg["runner"] = {"harnesses": harnesses}
    (tmp_path / "platform.yaml").write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return tmp_path


class TestAbsentPinIsNotCheckedForever:
    def test_no_pin_renders_not_checked(self, tmp_path):
        f = check_harness_vs_pin(_root(tmp_path))[0]
        assert f.verdict == "not-checked"

    def test_no_pin_is_never_fresh(self, tmp_path):
        """Reporting a never-compared fleet as on-pin is the whole failure."""
        f = check_harness_vs_pin(_root(tmp_path))[0]
        assert f.verdict != "fresh"

    def test_no_pin_is_not_an_error_either(self, tmp_path):
        """A pin-less tenant is a legitimate state, not a fault — crying error
        on every such tenant is how the check gets ignored."""
        f = check_harness_vs_pin(_root(tmp_path))[0]
        assert f.verdict not in ("skewed", "stale", "halted")

    def test_it_names_the_field_that_would_hold_the_pin(self, tmp_path):
        """The ruling asks for this by name. It also makes a core-side spelling
        change self-reporting: the message says what was looked for."""
        f = check_harness_vs_pin(_root(tmp_path))[0]
        assert HARNESS_PIN_FIELD in f.reason
        assert HARNESS_PIN_FIELD in (f.remedy or "")

    def test_it_still_reports_what_IS_installed(self, tmp_path):
        """'Not compared' must not mean 'nothing known' — the installed version
        is the useful half an operator can act on."""
        f = check_harness_vs_pin(_root(tmp_path))[0]
        assert f.evidence["installed"] == _real_version()
        assert f.evidence["pin"] is None

    def test_no_harness_registry_at_all_is_not_checked(self, tmp_path):
        f = check_harness_vs_pin(_root(tmp_path, harnesses=None))[0]
        assert f.verdict == "not-checked"
        assert "nothing declares" in f.reason

    def test_unreadable_platform_yaml_is_not_checked(self, tmp_path):
        (tmp_path / "platform.yaml").write_text("{[not yaml", encoding="utf-8")
        f = check_harness_vs_pin(tmp_path)[0]
        assert f.verdict == "not-checked"
        assert "could not be read" in f.reason


class TestComparisonWhenAPinExists:
    def test_matching_version_is_fresh(self, tmp_path):
        f = check_harness_vs_pin(_root(tmp_path, pin=_real_version()))[0]
        assert f.verdict == "fresh"
        assert f.remedy is None

    def test_mismatched_version_is_skewed(self, tmp_path):
        f = check_harness_vs_pin(_root(tmp_path, pin="0.0.1"))[0]
        assert f.verdict == "skewed"
        assert "OFF-PIN" in f.reason
        assert f.evidence == {
            "harness": "claude-code",
            "installed": _real_version(),
            "pin": "0.0.1",
        }

    def test_an_undeterminable_installed_version_is_not_checked(self, tmp_path):
        """Absence of an answer is not a match. A pinned harness that is not
        on PATH must never read as on-pin."""
        f = check_harness_vs_pin(_root(tmp_path, pin="1.2.3", binary="no-such-binary-xyz"))[0]
        assert f.verdict == "not-checked"
        assert f.evidence["installed"] is None

    def test_the_remedy_names_a_provisioning_act(self, tmp_path):
        """D3: off-pin is remediated at a provisioning act, NEVER mid-session —
        changing the harness under a running agent changes what executes it."""
        f = check_harness_vs_pin(_root(tmp_path, pin="0.0.1"))[0]
        assert "provision" in (f.remedy or "").lower()
        assert "mid-session" in (f.remedy or "")


class TestClause3TheRulingNamed:
    def test_deleting_the_pin_flips_compared_to_NOT_CHECKED_not_to_ok(self, tmp_path):
        """The ruling's exact clause-3 requirement."""
        pinned = check_harness_vs_pin(_root(tmp_path, pin="0.0.1"))[0]
        assert pinned.verdict == "skewed"

        cfg = yaml.safe_load((tmp_path / "platform.yaml").read_text())
        del cfg["runner"]["harnesses"][0]["pin"]
        (tmp_path / "platform.yaml").write_text(yaml.safe_dump(cfg), encoding="utf-8")

        unpinned = check_harness_vs_pin(tmp_path)[0]
        assert unpinned.verdict == "not-checked", "a deleted pin reported as OK"
        assert unpinned.verdict != "fresh"


class TestWiring:
    def test_assess_runs_the_check(self, tmp_path):
        from otaman_plugin.runtime_freshness import assess

        root = _root(tmp_path, pin="0.0.1")
        assert any(f.check == "harness-vs-pin" for f in assess(root))

    def test_doctor_surfaces_it(self, tmp_path):
        from otaman_plugin.doctor_checks import check_runtime_freshness

        codes = [w.code for w in check_runtime_freshness(_root(tmp_path, pin="0.0.1"))]
        assert any("HARNESS_VS_PIN" in c for c in codes)

    def test_not_checked_surfaces_as_info_not_silence(self, tmp_path):
        """no-silent-success: a check that could not run renders as its own
        visible state, never as nothing."""
        from otaman_plugin.doctor_checks import check_runtime_freshness

        ws = [w for w in check_runtime_freshness(_root(tmp_path)) if "HARNESS" in w.code]
        assert ws, "an unchecked harness produced no doctor output at all"
        assert ws[0].severity == "info"


@pytest.mark.parametrize("pin", ["2.1.259", " 2.1.259 "])
def test_pin_whitespace_is_tolerated(tmp_path, pin):
    """A trailing space in YAML must not read as off-pin."""
    (tmp_path / "platform.yaml").write_text(
        yaml.safe_dump(
            {
                "project": "t",
                "runner": {"harnesses": [{"id": "h", "binary": PROBE_BINARY, "pin": pin}]},
            }
        ),
        encoding="utf-8",
    )
    f = check_harness_vs_pin(tmp_path)[0]
    assert f.evidence["pin"] == "2.1.259"
