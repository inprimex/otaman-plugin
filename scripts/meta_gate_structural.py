#!/usr/bin/env python3
"""Server-side structural-key re-check for otaman-meta PRs (omg 1.1).

The PreToolUse guard in `check-ownership.sh` sees an agent's `git commit`. A
`gh pr merge` never reaches it, so the client-side control is bypassable by
routing a structural change through a PR — measured 2026-10-06. This runs in
CI, where no hook can be skipped.

IT SHARES THE HOOK'S COMPARISON, it does not reimplement it:
`structural_keys_changed` is imported from the same module the hook imports.
A backstop that classified changes differently from the thing it backs up
would pass what the hook refuses or refuse what it allows, and both answers
would be defensible from their own code.

IT FAILS CLOSED, WHICH IS THE OPPOSITE OF THE HOOK. The shared comparison
returns () both for "nothing structural changed" and for "I could not parse a
side" — ambiguous by construction. The hook resolves that ambiguity as ALLOW:
it is a speed bump on a developer's machine, and one that blocked on
unreadable YAML would block the commit that fixes it. A server gate must
resolve it as REFUSE: a check that passes what it could not read certifies
nothing. Same function, opposite default, and the difference is deliberate.

Exit codes:
  0  no structural key changed (and both sides parsed)
  1  a structural key changed — the PR is refused, keys named
  2  could not determine — refused, naming why
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from typing import Any


def _show(ref: str, path: str) -> tuple[Any | None, str | None]:
    """`git show ref:path` parsed as YAML.

    Returns (doc, error). A path ABSENT at a ref is not an error — it is an
    empty document, which is how "the file was added in this PR" must read:
    adding `ownership:` is a structural change and has to be caught, not
    skipped because the base had no file.
    """
    try:
        import yaml
    except ImportError:  # pragma: no cover - CI installs it
        return None, "PyYAML is not installed in the gate environment"

    r = subprocess.run(["git", "show", f"{ref}:{path}"], capture_output=True, text=True)
    if r.returncode != 0:
        stderr = (r.stderr or "").lower()
        if "does not exist" in stderr or "exists on disk" in stderr:
            return {}, None
        return None, f"could not read {path} at {ref}: {(r.stderr or '').strip()[:120]}"
    try:
        return yaml.safe_load(r.stdout) or {}, None
    except Exception as exc:  # noqa: BLE001 - any parse failure is the same verdict
        return None, f"{path} at {ref} is not parseable YAML: {type(exc).__name__}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base", required=True, help="base commit sha")
    ap.add_argument("--head", required=True, help="head commit sha")
    ap.add_argument("--path", default="platform.yaml")
    args = ap.parse_args(argv)

    try:
        from otaman_plugin.generate_agent_config import (
            STRUCTURAL_PLATFORM_KEYS,
            structural_keys_changed,
        )
    except ImportError as exc:
        print(
            f"REFUSED: the gate could not import the shared structural check ({exc}). "
            "This check exists to be the backstop for a bypassable hook; running it "
            "without the real comparison would certify nothing.",
            file=sys.stderr,
        )
        return 2

    before, err_b = _show(args.base, args.path)
    after, err_h = _show(args.head, args.path)
    for err in (err_b, err_h):
        if err:
            print(
                f"REFUSED: {err}. A server check that passes what it could not read "
                "certifies nothing — fix the file, or say in the PR why this is "
                "unreadable.",
                file=sys.stderr,
            )
            return 2

    changed = structural_keys_changed(before, after)
    if not changed:
        print(
            f"ok: no structural key changed in {args.path} "
            f"(checked {', '.join(STRUCTURAL_PLATFORM_KEYS)})"
        )
        return 0

    print(
        f"REFUSED: this PR changes structural key(s) in {args.path}: "
        f"{', '.join(changed)}.\n"
        "Structural keys re-point who owns what, who hears what, and which repos "
        "exist. THE HUMAN LANDS THESE, NOT A PR: there is no approval that makes "
        "this check pass, by design — the client-side guard refuses the same change "
        "locally and this is its backstop for the PR path it cannot see.\n"
        "Emit a decision-required naming the key and what it changes, and hand the "
        "edit over. Everything else in this PR can merge once the structural change "
        "is dropped from it.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
