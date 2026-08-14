#!/usr/bin/env python3
"""Otaman Estimation MCP Server — structured access to estimation data.

Provides tools for querying past project benchmarks, component estimation
library, domain expert knowledge, and project metadata. Designed as a
stable MCP interface — currently backed by YAML files on disk, can be
migrated to external DB/service later without changing the protocol.

Transport: stdio (launched by Claude Code via .mcp.json)
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore[assignment]

from fastmcp import FastMCP

mcp = FastMCP(
    name="otaman-estimation",
    instructions=(
        "Otaman estimation tools for pre-sale and project planning. "
        "Use these tools to search past project benchmarks, get component "
        "estimates, load domain expert knowledge, and manage project metadata."
    ),
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _find_plugin_root() -> Path | None:
    """Find the otaman plugin root (where assets/ lives)."""
    # Check env var first (set by Claude Code)
    import os

    env_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if env_root:
        p = Path(env_root)
        if (p / "assets").is_dir():
            return p
    # Walk up from this file to find the repo root that holds `assets/`.
    # After ce-org-agent-bootstrap moved this module under
    # otaman_plugin.servers, the repo root is four parents up
    # (servers → otaman_plugin → src → repo). Both depths are checked so
    # the legacy `servers/estimation_server.py` invocation path keeps
    # working if the file is ever symlinked back.
    here = Path(__file__).resolve()
    for candidate in (here.parents[3], here.parents[1]):
        if (candidate / "assets").is_dir():
            return candidate
    return None


def _find_presale_dir(cwd: str) -> Path | None:
    """Find presale dir by walking up from cwd. Prefers .otaman-presale/, falls back to legacy .maestro-presale/  # legacy: .maestro-presale/ supported."""
    d = Path(cwd).resolve()
    for _ in range(10):
        new = d / ".otaman-presale"
        if new.is_dir():
            return new
        legacy = d / ".maestro-presale"  # legacy: .maestro-presale/ directory
        if legacy.is_dir():
            return legacy
        parent = d.parent
        if parent == d:
            break
        d = parent
    return None


def _load_yaml(path: Path) -> Any:
    """Load a YAML file. Returns None on error."""
    if not path.exists() or yaml is None:
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f)
    except Exception:
        return None


def _save_yaml(path: Path, data: Any) -> bool:
    """Save data to YAML file."""
    if yaml is None:
        return False
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Tools: Benchmarks
# ---------------------------------------------------------------------------


@mcp.tool
def search_benchmarks(
    query: str,
    domain: str = "",
    max_results: int = 5,
) -> dict[str, Any]:
    """Search past project estimation benchmarks for similar projects.

    Args:
        query: Search query — matches against project type, tags, domain, key factors
        domain: Filter by domain (healthcare, fintech, marketplace, ml-ai, saas, etc.)
        max_results: Maximum number of results to return (default: 5)

    Returns:
        Dict with matching benchmarks including actual hours, accuracy, key learnings.
    """
    plugin_root = _find_plugin_root()
    if not plugin_root:
        return {"error": "Plugin root not found"}

    benchmarks_path = plugin_root / "assets" / "estimation-benchmarks.yaml"
    data = _load_yaml(benchmarks_path)
    if not data or "benchmarks" not in data:
        return {
            "benchmarks": [],
            "note": "No benchmarks file found. Create assets/estimation-benchmarks.yaml.",
        }

    query_lower = query.lower()
    query_terms = set(re.split(r"[\s,;]+", query_lower))

    results = []
    for b in data["benchmarks"]:
        # Score by relevance
        score = 0
        searchable = " ".join(
            [
                b.get("type", ""),
                b.get("domain", ""),
                " ".join(b.get("tags", [])),
                " ".join(b.get("key_factors", [])),
                b.get("code", ""),
            ]
        ).lower()

        for term in query_terms:
            if term in searchable:
                score += 1

        # Domain filter
        if domain and b.get("domain", "").lower() != domain.lower():
            continue

        if score > 0:
            results.append({"benchmark": b, "relevance_score": score})

    results.sort(key=lambda x: x["relevance_score"], reverse=True)
    return {"benchmarks": results[:max_results], "total_matches": len(results)}


@mcp.tool
def add_benchmark(
    code: str,
    domain: str,
    project_type: str,
    complexity_score: int,
    tier_used: str,
    estimated_range: list[int],
    actual_hours: int,
    team: list[str],
    duration_months: int,
    key_factors: list[str],
    tags: list[str],
) -> dict[str, Any]:
    """Add a new benchmark entry from a completed project (used by /otaman:retrospective).

    Args:
        code: Project reference code (e.g., TLH-WF-PB-EST-241023)
        domain: Project domain (healthcare, fintech, etc.)
        project_type: Project type description (e.g., telehealth-platform)
        complexity_score: Complexity score from Gate 1 (0-25)
        tier_used: Estimation tier used (A-E)
        estimated_range: [min_hours, max_hours]
        actual_hours: Actual hours spent
        team: Team composition (e.g., ["2 backend", "1 frontend", "0.5 devops"])
        duration_months: Actual duration in months
        key_factors: Key learnings and factors (list of strings)
        tags: Searchable tags
    """
    plugin_root = _find_plugin_root()
    if not plugin_root:
        return {"error": "Plugin root not found"}

    benchmarks_path = plugin_root / "assets" / "estimation-benchmarks.yaml"
    data = _load_yaml(benchmarks_path) or {
        "benchmarks": [],
        "patterns": [],
        "adjustment_factors": {},
    }

    midpoint = (estimated_range[0] + estimated_range[1]) / 2
    accuracy = round((actual_hours - midpoint) / midpoint * 100, 1) if midpoint > 0 else 0

    entry = {
        "code": code,
        "domain": domain,
        "type": project_type,
        "complexity_score": complexity_score,
        "tier_used": tier_used,
        "estimated_range": estimated_range,
        "actual_hours": actual_hours,
        "accuracy": f"{'+' if accuracy >= 0 else ''}{accuracy}%",
        "team": team,
        "duration_months": duration_months,
        "key_factors": key_factors,
        "tags": tags,
    }

    data["benchmarks"].append(entry)
    if _save_yaml(benchmarks_path, data):
        return {"added": True, "code": code, "accuracy": entry["accuracy"]}
    return {"error": "Failed to save benchmarks file"}


# ---------------------------------------------------------------------------
# Tools: Component Estimation
# ---------------------------------------------------------------------------


@mcp.tool
def get_component_estimate(
    component: str,
    variant: str = "",
) -> dict[str, Any]:
    """Get hour estimates for a specific component type (auth, API, integration, etc.).

    Args:
        component: Component category (e.g., "auth", "api", "integrations", "infrastructure", "compliance")
        variant: Specific variant (e.g., "oauth2_social_login", "stripe_marketplace", "hipaa_infrastructure")

    Returns:
        Dict with hour ranges, notes, and related components.
    """
    plugin_root = _find_plugin_root()
    if not plugin_root:
        return {"error": "Plugin root not found"}

    library_path = plugin_root / "assets" / "component-library.yaml"
    data = _load_yaml(library_path)
    if not data or "components" not in data:
        return {
            "components": {},
            "note": "No component library found. Create assets/component-library.yaml.",
        }

    components = data["components"]
    component_lower = component.lower()

    if component_lower in components:
        cat = components[component_lower]
        if variant:
            variant_lower = variant.lower()
            if variant_lower in cat:
                return {"component": component, "variant": variant, "data": cat[variant_lower]}
            # Fuzzy match
            matches = {k: v for k, v in cat.items() if variant_lower in k}
            if matches:
                return {"component": component, "matches": matches}
            return {
                "error": f"Variant '{variant}' not found in '{component}'",
                "available": list(cat.keys()),
            }
        return {"component": component, "variants": cat}

    # Fuzzy search across all components
    matches = {}
    for cat_name, cat_data in components.items():
        if component_lower in cat_name:
            matches[cat_name] = cat_data
        elif isinstance(cat_data, dict):
            for var_name, var_data in cat_data.items():
                if component_lower in var_name:
                    matches[f"{cat_name}.{var_name}"] = var_data

    if matches:
        return {"fuzzy_matches": matches}
    return {
        "error": f"Component '{component}' not found",
        "available_categories": list(components.keys()),
    }


# ---------------------------------------------------------------------------
# Tools: Domain Expert
# ---------------------------------------------------------------------------


@mcp.tool
def get_domain_expert(
    domain: str,
    section: str = "",
) -> dict[str, Any]:
    """Load domain expert knowledge for a specific domain.

    Args:
        domain: Domain name (healthcare, fintech, marketplace, ml-ai, saas, ecommerce, iot)
        section: Optional specific section (requirements_checklist, compliance_frameworks,
                 integration_patterns, estimation_adjustments, risk_patterns, reference_architectures)

    Returns:
        Dict with domain expert content (markdown text).
    """
    plugin_root = _find_plugin_root()
    if not plugin_root:
        return {"error": "Plugin root not found"}

    expert_path = plugin_root / "references" / "domain-experts" / f"{domain}.md"
    if not expert_path.exists():
        available = (
            [p.stem for p in (plugin_root / "references" / "domain-experts").glob("*.md")]
            if (plugin_root / "references" / "domain-experts").is_dir()
            else []
        )
        return {"error": f"No domain expert for '{domain}'", "available": available}

    content = expert_path.read_text(encoding="utf-8")

    if section:
        # Extract specific section
        pattern = rf"##\s+.*{re.escape(section)}.*?\n(.*?)(?=\n## |\Z)"
        match = re.search(pattern, content, re.DOTALL | re.IGNORECASE)
        if match:
            return {"domain": domain, "section": section, "content": match.group(1).strip()}
        return {"error": f"Section '{section}' not found in {domain} expert", "content": content}

    return {"domain": domain, "content": content}


# ---------------------------------------------------------------------------
# Tools: Project Metadata
# ---------------------------------------------------------------------------


@mcp.tool
def get_project_meta(cwd: str) -> dict[str, Any]:
    """Read project metadata from .otaman-presale/project-meta.yaml (or legacy .maestro-presale/).  # legacy: .maestro-presale/ directory

    Args:
        cwd: Current working directory (used to find .otaman-presale/)

    Returns:
        Dict with project metadata including phase, domain, estimation info.
    """
    presale = _find_presale_dir(cwd)
    if not presale:
        return {
            "error": "No .otaman-presale/ (or legacy .maestro-presale/).  # legacy: .maestro-presale/ directorydirectory found"
        }

    meta = _load_yaml(presale / "project-meta.yaml")
    if not meta:
        return {"error": "project-meta.yaml not found or invalid"}

    return {"meta": meta, "presale_dir": str(presale)}


@mcp.tool
def update_project_phase(
    cwd: str,
    new_phase: str,
    notes: str = "",
) -> dict[str, Any]:
    """Update the current project phase in project-meta.yaml.

    Args:
        cwd: Current working directory
        new_phase: New phase (presale, discovery, development, support, archived)
        notes: Optional notes about the phase transition
    """
    from datetime import date

    presale = _find_presale_dir(cwd)
    if not presale:
        return {
            "error": "No .otaman-presale/ (or legacy .maestro-presale/).  # legacy: .maestro-presale/ directorydirectory found"
        }

    meta_path = presale / "project-meta.yaml"
    meta = _load_yaml(meta_path)
    if not meta:
        return {"error": "project-meta.yaml not found or invalid"}

    today = date.today().isoformat()

    # Complete current phase
    if meta.get("phase_history"):
        for entry in meta["phase_history"]:
            if entry.get("completed") is None:
                entry["completed"] = today

    # Start new phase
    new_entry: dict[str, Any] = {"phase": new_phase, "started": today, "completed": None}
    if notes:
        new_entry["notes"] = notes

    meta.setdefault("phase_history", []).append(new_entry)
    meta["current_phase"] = new_phase

    if _save_yaml(meta_path, meta):
        return {"updated": True, "current_phase": new_phase, "started": today}
    return {"error": "Failed to save project-meta.yaml"}


@mcp.tool
def save_knowledge_item(
    cwd: str,
    item_type: str,
    content: str,
    confidence: str,
    source: str,
    destination: str = "project",
) -> dict[str, Any]:
    """Save a knowledge item extracted from artifacts (used by knowledge capture skill).

    Args:
        cwd: Current working directory
        item_type: Type: fact, metric, decision, estimation, learning, vendor-quirk
        content: The knowledge item text
        confidence: Confidence level: high, medium, low
        source: Where this was extracted from (e.g., "meeting notes 2026-03-25", "client email")
        destination: Where to store: project (in .otaman-presale/), benchmarks, component-library, domain-knowledge
    """
    from datetime import datetime, timezone

    if destination == "project":
        presale = _find_presale_dir(cwd)
        if not presale:
            return {
                "error": "No .otaman-presale/ (or legacy .maestro-presale/).  # legacy: .maestro-presale/ directorydirectory found"
            }

        knowledge_file = presale / "captured-knowledge.yaml"
        data = _load_yaml(knowledge_file) or {"items": []}

        data["items"].append(
            {
                "type": item_type,
                "content": content,
                "confidence": confidence,
                "source": source,
                "captured": datetime.now(timezone.utc).isoformat(),
            }
        )

        if _save_yaml(knowledge_file, data):
            return {"saved": True, "destination": "project", "items_count": len(data["items"])}
        return {"error": "Failed to save knowledge file"}

    elif destination == "benchmarks":
        # Append to adjustment_factors or patterns in benchmarks file
        plugin_root = _find_plugin_root()
        if not plugin_root:
            return {"error": "Plugin root not found"}

        benchmarks_path = plugin_root / "assets" / "estimation-benchmarks.yaml"
        data = _load_yaml(benchmarks_path) or {
            "benchmarks": [],
            "patterns": [],
            "adjustment_factors": {},
        }

        data.setdefault("patterns", []).append(
            {
                "pattern": content,
                "source": source,
                "confidence": confidence,
            }
        )

        if _save_yaml(benchmarks_path, data):
            return {"saved": True, "destination": "benchmarks"}
        return {"error": "Failed to save benchmarks file"}

    return {"error": f"Unsupported destination: {destination}"}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run()
