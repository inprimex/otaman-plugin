#!/usr/bin/env python3
"""platform.yaml schema validation for the otaman-meta gate (omg 1.1).

WRITTEN BUT NOT YET WIRED. The step that calls this is commented out in
otaman-meta's meta-gate workflow, deliberately, and the reason is measured
rather than cautious: `platform-schema.yaml` is `additionalProperties: false`
at top level and does not declare `ownership`, so the omo-mandated ownership
block Roman committed on 2026-10-06 (otaman-meta 4321498) is schema-INVALID
against the installed v0.5.22 schema.

Enabling the step today would be correct and useless: it would fail on main
and block every merge to the fleet's coordination repo, including the commits
that fix it. otaman-core 1.4 adds the schema entry; this turns on then.

A tripwire test fails the moment `ownership` appears in the installed schema,
which is the signal to uncomment the step rather than a note someone has to
remember.

IT USES CORE'S SCHEMA, NOT A COPY. The whole point of validating here is that
the gate and the runtime agree on what a valid platform.yaml is; a schema
vendored into CI would drift and then certify files the runtime rejects.

Exit codes:
  0  valid
  1  invalid — each violation named
  2  could not validate — refused, naming why
"""

from __future__ import annotations

import argparse
import pathlib
import sys


def _installed_schema() -> tuple[dict | None, str | None]:
    """core's platform schema as shipped, or (None, why not)."""
    try:
        import yaml
    except ImportError:
        return None, "PyYAML is not installed in the gate environment"
    try:
        import otaman_core
    except ImportError as exc:
        return None, f"otaman_core is not importable ({exc})"

    base = pathlib.Path(otaman_core.__file__).parent / "schemas" / "platform-schema.yaml"
    if not base.is_file():
        return None, f"core ships no schema at {base}"
    try:
        return yaml.safe_load(base.read_text(encoding="utf-8")), None
    except Exception as exc:  # noqa: BLE001
        return None, f"core's schema is not parseable: {type(exc).__name__}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("platform_yaml")
    args = ap.parse_args(argv)

    schema, err = _installed_schema()
    if err:
        print(
            f"REFUSED: {err}. Validating against a vendored copy instead would let "
            "the gate certify files the runtime rejects.",
            file=sys.stderr,
        )
        return 2

    try:
        import jsonschema
        import yaml
    except ImportError as exc:
        print(
            f"REFUSED: {exc}. A schema check that cannot run must not report a pass.",
            file=sys.stderr,
        )
        return 2

    path = pathlib.Path(args.platform_yaml)
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        print(f"REFUSED: {path} is not parseable YAML: {type(exc).__name__}", file=sys.stderr)
        return 2

    validator = jsonschema.Draft7Validator(schema)
    violations = sorted(validator.iter_errors(doc), key=lambda e: list(e.path))
    if not violations:
        print(f"ok: {path} validates against core's installed platform schema")
        return 0

    print(f"REFUSED: {path} violates core's platform schema:", file=sys.stderr)
    for v in violations:
        where = "/".join(str(p) for p in v.path) or "<top level>"
        print(f"  {where}: {v.message}", file=sys.stderr)
    return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
