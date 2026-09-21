#!/usr/bin/env python3
"""Thin shim → ``otaman_plugin.map_tasks``. Kept as a path-invocable entry
point; it holds no logic of its own.

It used to carry a SECOND implementation of "find the project root": an
8-level ancestor walk for ``platform.yaml``. In the dedicated-otaman-folder
layout that can never succeed — ``platform.yaml`` lives in the sibling
``<program>-otaman/`` folder, so it is never an ancestor of the specs repo.
Hook-driven dispatch was therefore a silent, total failure, while
``otaman notify-change`` worked because the MODULE already consumes the
shared resolver (``otaman_core._resolve.find_maestro_root``, which follows
the repo's ``.otaman`` marker).

Confirmed on otaman-dev by deploy-agent (20260921T152252) after Roman
relayed it from mildef/haulops, and reproduced here before fixing.

This is the shared-logic-single-home shape exactly: two implementations of
one thing, one correct, and the caller happened to use the wrong one. The
fix is to delete the duplicate rather than deepen ``_MAX_WALK_UP``, which
would only mask it in shallower trees.

Exit codes are the module's, NOT swallowed: the old version returned 0 on
every failure path ("caller ignores exit codes anyway"), which is why the
failure was invisible even without the hook's ``|| true``.
"""

from __future__ import annotations

import sys


def _fail(message: str) -> int:
    print(f"[map-tasks] {message}", file=sys.stderr)
    return 2


def main() -> int:
    try:
        from otaman_plugin.map_tasks import main as _main
    except ImportError as exc:
        # Loud on purpose. A dispatcher that cannot dispatch must say so —
        # silence here is the defect being fixed. Callers that must not fail
        # (the post-commit hook) suppress this themselves, visibly.
        return _fail(
            f"cannot import otaman_plugin.map_tasks ({exc}). "
            "Run this with a Python that has otaman-plugin installed — "
            "the hook uses scripts/_resolve.sh's resolve_otaman_python for this."
        )
    return _main()


if __name__ == "__main__":
    sys.exit(main())
