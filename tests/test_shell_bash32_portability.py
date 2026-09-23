"""Shipped shell must run under bash 3.2 — the version stock macOS ships.

Found 2026-09-23 while clearing the macOS matrix. Four launcher tests failed
there with `AssertionError: otaman launcher`, which reads like a fixture
problem. The real message was three lines down in the captured stderr:

    launch-agents.sh: line 714: mapfile: command not found
    assert 127 == 0

`mapfile` (and its alias `readarray`) is bash 4.0+. macOS has shipped bash
3.2.57 since 2007 and will not ship a newer one — GPLv3. So `launch-agents.sh`
died with exit 127 in tmux fleet mode on any Mac without a hand-installed
bash, *after* printing its banner, which is what made it look like it had
started working.

WHY THIS IS A TEST AND NOT JUST A FIX. The defect is invisible on every
machine this fleet runs on, and the CI leg that would catch it is
`continue-on-error`. A grep-based guard fails on Linux, in the blocking job,
the moment a bash-4-only construct reappears — the same reason
`audit-maestro-refs.sh` is a CI step rather than a convention.

Scope note: these are the constructs that fail HARD (command not found, or a
syntax error at parse time). Softer 4.x niceties are not policed here — the
goal is "does not die on stock macOS", not "lowest common denominator style".
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).parent.parent

#: Shell that ships to users — hooks, the launchers, and the server shim.
#: `tests/` and one-off dev scripts are deliberately out of scope.
SHIPPED_DIRS = ("scripts", "hooks", "servers")

#: (pattern, what it is, what to use instead) — each fails outright on 3.2.
BASH4_CONSTRUCTS: tuple[tuple[str, str, str], ...] = (
    (
        r"\bmapfile\b|\breadarray\b",
        "mapfile/readarray (bash 4.0+)",
        'arr=(); while IFS= read -r l; do arr+=("$l"); done < <(cmd)',
    ),
    (
        r"\bdeclare\s+-A\b|\blocal\s+-A\b",
        "associative arrays (bash 4.0+)",
        "parallel indexed arrays, or a `case` lookup",
    ),
    (
        r"\$\{[A-Za-z_][A-Za-z0-9_]*\^\^|\$\{[A-Za-z_][A-Za-z0-9_]*,,",
        "${var^^} / ${var,,} case conversion (bash 4.0+)",
        "tr '[:lower:]' '[:upper:]'",
    ),
    (
        r"\blocal\s+-n\b|\bdeclare\s+-n\b",
        "namerefs (bash 4.3+)",
        "echo the value and capture it, or pass the array by name with eval",
    ),
    (
        r"\bcoproc\b",
        "coproc (bash 4.0+)",
        "a plain pipeline or a temp file",
    ),
)

#: A line already carrying this is a deliberate, explained exception.
_ALLOW = re.compile(r"#\s*bash3-ok", re.IGNORECASE)


def _shipped_shell() -> list[Path]:
    out: list[Path] = []
    for d in SHIPPED_DIRS:
        out.extend(sorted((REPO / d).rglob("*.sh")))
    return out


def test_there_is_shell_to_check():
    """Guards the guard: a bad glob would make every test below vacuous."""
    files = _shipped_shell()
    assert len(files) > 5, f"expected shipped shell scripts, found {files}"
    assert any(f.name == "launch-agents.sh" for f in files), "the launcher must be in scope"


@pytest.mark.parametrize("pattern,name,alternative", BASH4_CONSTRUCTS, ids=lambda v: str(v)[:28])
def test_no_bash4_only_construct(pattern: str, name: str, alternative: str):
    rx = re.compile(pattern)
    offenders: list[str] = []
    for path in _shipped_shell():
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.lstrip()
            if stripped.startswith("#") or _ALLOW.search(line):
                continue
            if rx.search(line):
                offenders.append(f"{path.relative_to(REPO)}:{n}: {stripped[:80]}")
    assert not offenders, (
        f"{name} does not exist in bash 3.2, which is what stock macOS ships — "
        f"the script dies with 'command not found' (exit 127) or a parse error, "
        f"NOT a graceful degrade.\nUse: {alternative}\n  " + "\n  ".join(offenders)
    )
