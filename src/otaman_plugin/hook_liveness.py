"""Does an installed git hook actually RUN? (no-silent-success 1.1)

Existence is not liveness. The haulops incident (deploy-agent
20260921T184535) had three hooks installed, readable, executable — and
completely inert, because the wheel shipped the entry points without
`_resolve.sh`, which every one of them sources. `find_maestro_root` was
never defined, `PROJECT_ROOT="$(find_maestro_root)" || exit 0` took the
exit, and every surface reported the install as fine.

So this probes the property that matters: source the hook's dependencies
and confirm the function it dies without is defined. Used by BOTH
`otaman init` (install-time error) and `otaman doctor` (visible failure),
because a check that only runs at install cannot catch a bundle that
degrades afterwards.

Pure enough to test: `probe_hook_liveness` takes the paths, runs one
short bash, and returns a verdict. No I/O beyond the probe itself.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

#: The function every shipped hook obtains from `_resolve.sh` and cannot
#: proceed without. If sourcing does not define it, the hook is inert.
REQUIRED_FUNCTION = "find_maestro_root"

#: Hooks that source `_resolve.sh` and are therefore subject to this check.
LIVENESS_CHECKED_HOOKS = (
    "post-commit-hook.sh",
    "spec-change-hook.sh",
    "check-branch.sh",
)


@dataclass(frozen=True)
class Liveness:
    """Verdict for one hook.

    ``performed`` is the distinction no-silent-success exists for: a check
    that could not run (no bash, unreadable script) is NOT a pass and NOT a
    failure — it is its own state, and callers must render it as such rather
    than as OK or as silence.
    """

    ok: bool
    performed: bool
    reason: str

    @property
    def state(self) -> str:
        if not self.performed:
            return "not-checked"
        return "live" if self.ok else "inert"


def probe_hook_liveness(hook_path: Path) -> Liveness:
    """Can *hook_path* load its dependencies and define REQUIRED_FUNCTION?

    Sources the hook's own resolver the way the hook does, rather than
    executing the hook — running a post-commit hook to test it would write
    bus messages as a side effect.
    """
    if not hook_path.is_file():
        return Liveness(False, True, f"{hook_path.name} is not installed at {hook_path}")

    resolve = hook_path.parent / "_resolve.sh"
    if not resolve.is_file():
        # The haulops shape exactly: entry point present, dependency absent.
        return Liveness(
            False,
            True,
            f"{hook_path.name} sources _resolve.sh, which is missing from {resolve.parent} — "
            "the hook is installed but inert",
        )

    bash = shutil.which("bash")
    if not bash:
        return Liveness(False, False, "no bash on PATH — hook liveness could not be checked")

    try:
        probe = subprocess.run(
            [bash, "-c", f'source "{resolve}" >/dev/null 2>&1; declare -F {REQUIRED_FUNCTION}'],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return Liveness(False, False, f"hook liveness could not be checked: {exc}")

    if probe.returncode != 0:
        return Liveness(
            False,
            True,
            f"sourcing _resolve.sh did not define {REQUIRED_FUNCTION}() — "
            f"{hook_path.name} would exit 0 without doing anything",
        )
    return Liveness(True, True, f"{hook_path.name} loads its dependencies and can resolve a root")
