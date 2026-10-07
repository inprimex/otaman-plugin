#!/usr/bin/env python3
"""Knowledge-pack lint for the otaman-meta gate (omg 1.1).

Validates every entry in the knowledge packs with `otaman_core.knowledge` —
core's validator, imported, not a second set of rules here. The anchor rule is
the one it exists for: an entry with no evidence anchor is refused, because an
unanchored claim is indistinguishable from a guess six weeks later.

WHY A GATE AND NOT JUST THE WRITER'S DISCIPLINE. Pack entries arrive as
prepared handoffs from agents who cannot merge them (that is the whole shape
omo introduced). The author validates before handing over, the owner validates
before merging — and both are the same person's habit, which is to say not a
guarantee. This is the check that does not depend on anyone remembering.

FAILS CLOSED on an unusable validator: if core's knowledge module cannot be
imported, the gate refuses rather than reporting a clean pack it never read.
A pack directory that does not exist is NOT an error — a repo with no packs
has nothing to lint, which is different from a pack that failed to load.

Exit codes:
  0  every entry valid (or there are no packs)
  1  at least one entry invalid — each named with its errors
  2  could not validate — refused, naming why
"""

from __future__ import annotations

import argparse
import pathlib
import sys


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("packs_dir", help="directory holding knowledge packs")
    args = ap.parse_args(argv)

    root = pathlib.Path(args.packs_dir)
    if not root.is_dir():
        print(f"ok: no knowledge packs at {root} — nothing to lint")
        return 0

    try:
        from otaman_core import knowledge
    except ImportError as exc:
        print(
            f"REFUSED: could not import otaman_core.knowledge ({exc}). Reporting a "
            "pack as clean without validating it is the failure this gate exists to "
            "prevent.",
            file=sys.stderr,
        )
        return 2

    packs = sorted(p for p in root.iterdir() if p.is_dir())
    if not packs:
        print(f"ok: {root} contains no packs — nothing to lint")
        return 0

    total = 0
    bad: list[str] = []
    for pack in packs:
        try:
            entries = knowledge.load_entries(pack)
        except Exception as exc:  # noqa: BLE001 - unreadable pack is a refusal
            print(
                f"REFUSED: pack {pack.name} could not be loaded: {type(exc).__name__}: {exc}",
                file=sys.stderr,
            )
            return 2
        for entry in entries:
            total += 1
            errors = knowledge.validate_entry(entry)
            if errors:
                bad.append(f"  {pack.name}/{entry.title[:60]}: {'; '.join(errors)}")

    if bad:
        print(
            f"REFUSED: {len(bad)} of {total} knowledge entries are invalid:",
            file=sys.stderr,
        )
        for line in bad:
            print(line, file=sys.stderr)
        return 1

    print(f"ok: {total} knowledge entries across {len(packs)} pack(s), 0 invalid")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
