#!/usr/bin/env python3
"""Initialize .otaman-presale/ directory structure for a new project.

Usage:
    python init-presale.py <project-code> <project-name> <domain> [--client CLIENT]

Creates .otaman-presale/ in the current directory with:
- project-meta.yaml (project metadata + phase tracking)
- estimation/ directory
- assumptions.yaml (empty register)
- risks.yaml (empty register)
- architecture/ directory
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML required. Install: pip install pyyaml", file=sys.stderr)
    sys.exit(1)


def create_presale_dir(
    root: Path,
    project_code: str,
    project_name: str,
    domain: str,
    client: str | None = None,
) -> list[str]:
    """Create .otaman-presale/ structure. Returns list of created files."""
    presale = root / ".otaman-presale"
    created: list[str] = []

    legacy = root / ".maestro-presale"
    if presale.exists() or legacy.exists():
        if presale.exists():
            print(f"WARNING: .otaman-presale/ already exists at {root}", file=sys.stderr)
        else:
            print(
                f"WARNING: legacy .maestro-presale/ found at {root}; new artifacts "
                f"will write to .otaman-presale/. Migrate manually with: "
                f"mv {root}/.maestro-presale {root}/.otaman-presale",
                file=sys.stderr,
            )
        print("Use --force to reinitialize (project-meta.yaml will NOT be overwritten).", file=sys.stderr)
        # Still create missing subdirectories — idempotent re-run behaviour.
        for d in [presale / "estimation", presale / "architecture", presale / "discovery" / "decisions"]:
            if not d.exists():
                d.mkdir(parents=True, exist_ok=True)
                created.append(str(d.relative_to(root)))
        return created

    # Create directories
    for d in [
        presale,
        presale / "estimation",
        presale / "architecture",
        presale / "discovery" / "decisions",
    ]:
        d.mkdir(parents=True, exist_ok=True)
        created.append(str(d.relative_to(root)))

    # project-meta.yaml
    today = date.today().isoformat()
    meta = {
        "project_code": project_code,
        "project_name": project_name,
        "domain": domain,
        "current_phase": "presale",
        "phase_history": [
            {
                "phase": "presale",
                "started": today,
                "completed": None,
            }
        ],
        "tech_stack": [],
    }
    if client:
        meta["client"] = client

    meta_path = presale / "project-meta.yaml"
    with open(meta_path, "w", encoding="utf-8") as f:
        f.write("# Project metadata — created by /otaman:presale\n")
        f.write("# Update current_phase and phase_history as the project progresses.\n\n")
        yaml.dump(meta, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
    created.append(str(meta_path.relative_to(root)))

    # assumptions.yaml (empty register)
    assumptions_path = presale / "assumptions.yaml"
    with open(assumptions_path, "w", encoding="utf-8") as f:
        f.write("# Assumption Register — populated during Gate 0 intake\n")
        f.write("# Each assumption: id, description, confidence, impact_if_wrong,\n")
        f.write("#   verification_method, status (pending/confirmed/declined/modified)\n\n")
        f.write("assumptions: []\n")
    created.append(str(assumptions_path.relative_to(root)))

    # risks.yaml (empty register)
    risks_path = presale / "risks.yaml"
    with open(risks_path, "w", encoding="utf-8") as f:
        f.write("# Risk Register — populated during Gate 0 intake\n")
        f.write("# Each risk: id, description, probability, impact, score,\n")
        f.write("#   mitigation, status (identified/mitigating/accepted/resolved)\n\n")
        f.write("risks: []\n")
    created.append(str(risks_path.relative_to(root)))

    return created


def main() -> int:
    args = sys.argv[1:]
    if len(args) < 3:
        print(
            "Usage: init-presale.py <project-code> <project-name> <domain> [--client CLIENT]",
            file=sys.stderr,
        )
        print("  domain: healthcare | fintech | marketplace | ml-ai | saas | ecommerce | iot | general", file=sys.stderr)
        return 2

    project_code = args[0]
    project_name = args[1]
    domain = args[2]

    valid_domains = ["healthcare", "fintech", "marketplace", "ml-ai", "saas", "ecommerce", "iot", "general"]
    if domain not in valid_domains:
        print(f"ERROR: Invalid domain '{domain}'. Must be one of: {', '.join(valid_domains)}", file=sys.stderr)
        return 2

    client = None
    if "--client" in args:
        idx = args.index("--client")
        if idx + 1 < len(args):
            client = args[idx + 1]

    root = Path.cwd()
    created = create_presale_dir(root, project_code, project_name, domain, client)

    if created:
        print(f"Initialized .otaman-presale/ for {project_name}")
        for c in created:
            print(f"  Created: {c}")
    else:
        print("No new files created (directory already exists).")

    return 0


if __name__ == "__main__":
    sys.exit(main())
