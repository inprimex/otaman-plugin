#!/usr/bin/env python3
"""Thin shim -> ``otaman_plugin.specs_drain`` (task-complete-reconciler 2.1).

Path-invocable entry point for the SessionStart hook; holds no logic of its
own, the same shape as ``map-tasks.py``.

Prints ONE line: ``<verdict>: <reason>``. Always exits 0 — a session must not
fail to start because a backlog could not be drained — so the LINE is the
signal, never the exit code. The hook logs it; `not-checked-*` verdicts mean
the drain did not happen and an absence of ticks proves nothing.
"""

from __future__ import annotations

import sys
from pathlib import Path

if __package__ in (None, ""):  # path-invoked, not imported
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from otaman_plugin.specs_drain import drain  # noqa: E402


def main() -> int:
    try:
        import yaml
        from otaman_core._resolve import find_maestro_root
    except ImportError as exc:
        print(f"not-checked-no-deps: {exc}")
        return 0

    root = find_maestro_root()
    if root is None:
        print("not-checked-no-root: no otaman root resolved from here")
        return 0
    root = Path(root)

    agent_file = root / ".agents" / "current-agent"
    agent = agent_file.read_text(encoding="utf-8").strip() if agent_file.is_file() else None

    try:
        config = yaml.safe_load((root / "platform.yaml").read_text(encoding="utf-8")) or {}
    except OSError as exc:
        print(f"not-checked-no-config: platform.yaml unreadable ({exc})")
        return 0

    result = drain(agent, config, root)
    print(f"{result.verdict}: {result.reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
