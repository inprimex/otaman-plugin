#!/usr/bin/env python3
"""Scan a directory for git repos and generate a draft platform.yaml.

Usage:
    python discover-repos.py [root-directory]

Outputs:
    - platform.yaml.draft in the scanned directory
    - JSON discovery report to stdout

Exit codes:
    0 — success
    1 — no repos found
    2 — error
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML is required. Install with: pip install pyyaml", file=sys.stderr)
    sys.exit(2)


# ---------------------------------------------------------------------------
# Tech stack detection
# ---------------------------------------------------------------------------

TECH_SIGNALS: list[tuple[str, list[str], str]] = [
    # (filename or glob, tech tags, owner suggestion)
    # Order matters: first match wins for owner suggestion, but all tech tags accumulate
]

# Map of indicator file -> (tech_tags, suggested_owner)
INDICATOR_FILES: dict[str, tuple[list[str], str]] = {
    "package.json": (["nodejs"], ""),  # owner determined by package.json contents
    "requirements.txt": (["python"], "backend-agent"),
    "pyproject.toml": (["python"], "backend-agent"),
    "setup.py": (["python"], "backend-agent"),
    "Pipfile": (["python"], "backend-agent"),
    "go.mod": (["go"], "backend-agent"),
    "Cargo.toml": (["rust"], "backend-agent"),
    "pom.xml": (["java"], "backend-agent"),
    "build.gradle": (["java"], "backend-agent"),
    "build.gradle.kts": (["kotlin"], "backend-agent"),
    "*.csproj": (["csharp", "dotnet"], "backend-agent"),
    "*.sln": (["csharp", "dotnet"], "backend-agent"),
    "Gemfile": (["ruby"], "backend-agent"),
    "composer.json": (["php"], "backend-agent"),
    "pubspec.yaml": (["flutter", "dart"], "mobile-agent"),
    "Dockerfile": (["docker"], ""),
    "docker-compose.yml": (["docker"], ""),
    "docker-compose.yaml": (["docker"], ""),
    "terraform.tf": (["terraform"], "devops-agent"),
    "main.tf": (["terraform"], "devops-agent"),
    "Pulumi.yaml": (["pulumi"], "devops-agent"),
    "Chart.yaml": (["helm", "kubernetes"], "devops-agent"),
    "skaffold.yaml": (["kubernetes"], "devops-agent"),
}

# Keywords in package.json dependencies that refine detection
PACKAGE_JSON_HINTS: dict[str, tuple[list[str], str]] = {
    "react": (["react"], "frontend-agent"),
    "react-native": (["react-native"], "mobile-agent"),
    "next": (["nextjs"], "frontend-agent"),
    "vue": (["vue"], "frontend-agent"),
    "nuxt": (["nuxt"], "frontend-agent"),
    "angular": (["angular"], "frontend-agent"),
    "@angular/core": (["angular"], "frontend-agent"),
    "svelte": (["svelte"], "frontend-agent"),
    "express": (["express"], "backend-agent"),
    "fastify": (["fastify"], "backend-agent"),
    "@nestjs/core": (["nestjs"], "backend-agent"),
    "hono": (["hono"], "backend-agent"),
}

# Keywords in Python deps that suggest ML/data
PYTHON_ML_HINTS = {"torch", "tensorflow", "keras", "sklearn", "scikit-learn",
                    "pandas", "numpy", "xgboost", "lightgbm", "transformers",
                    "mlflow", "dvc"}

PYTHON_WEB_HINTS = {"django", "flask", "fastapi", "starlette", "sanic", "tornado"}

# API contract directory names (technical layer)
CONTRACTS_DIR_NAMES = {"openapi", "swagger", "api-specs", "api-spec", "contracts"}

# OpenSpec detection signals
OPENSPEC_DIR_NAME = "openspec"
OPENSPEC_CONFIG_PATTERNS = ["openspec.config.*", ".openspec.*"]


def detect_tech_stack(repo_path: Path) -> tuple[list[str], str]:
    """Detect tech stack and suggest an owner for a repo.

    Returns (tech_tags, suggested_owner).
    """
    tech: list[str] = []
    owner = ""

    # Check indicator files
    for indicator, (tags, suggested) in INDICATOR_FILES.items():
        if "*" in indicator:
            # Glob pattern
            if list(repo_path.glob(indicator)):
                tech.extend(t for t in tags if t not in tech)
                if not owner and suggested:
                    owner = suggested
        elif (repo_path / indicator).exists():
            tech.extend(t for t in tags if t not in tech)
            if not owner and suggested:
                owner = suggested

    # Deep-inspect package.json
    pkg_json = repo_path / "package.json"
    if pkg_json.exists():
        try:
            pkg = json.loads(pkg_json.read_text(encoding="utf-8"))
            all_deps = set()
            for key in ("dependencies", "devDependencies", "peerDependencies"):
                all_deps.update(pkg.get(key, {}).keys())

            if "typescript" in all_deps or (repo_path / "tsconfig.json").exists():
                if "typescript" not in tech:
                    tech.append("typescript")

            for hint_key, (tags, suggested) in PACKAGE_JSON_HINTS.items():
                if hint_key in all_deps:
                    tech.extend(t for t in tags if t not in tech)
                    if not owner and suggested:
                        owner = suggested
        except (json.JSONDecodeError, OSError):
            pass

        if not owner:
            owner = "backend-agent"  # default for node projects

    # Deep-inspect Python deps
    for pyfile in ("requirements.txt", "pyproject.toml", "Pipfile"):
        pypath = repo_path / pyfile
        if pypath.exists():
            try:
                content = pypath.read_text(encoding="utf-8").lower()
                if any(hint in content for hint in PYTHON_ML_HINTS):
                    if "python-ml" not in tech:
                        tech.append("python-ml")
                    owner = "data-agent"
                elif any(hint in content for hint in PYTHON_WEB_HINTS):
                    for fw in PYTHON_WEB_HINTS:
                        if fw in content and fw not in tech:
                            tech.append(fw)
            except OSError:
                pass

    # Check for iOS/Android native
    if (repo_path / "Package.swift").exists() or list(repo_path.glob("*.xcodeproj")):
        tech.extend(t for t in ["swift", "ios"] if t not in tech)
        if not owner:
            owner = "mobile-agent"
    if (repo_path / "settings.gradle").exists() or (repo_path / "settings.gradle.kts").exists():
        if "android" not in tech:
            # Check for android-specific markers
            if (repo_path / "app" / "src" / "main" / "AndroidManifest.xml").exists():
                tech.append("android")
                if not owner:
                    owner = "mobile-agent"

    # Docs-only heuristic: no code indicators but has markdown/rst
    if not tech:
        md_files = list(repo_path.glob("**/*.md"))
        rst_files = list(repo_path.glob("**/*.rst"))
        if len(md_files) + len(rst_files) > 3:
            tech.append("docs")
            owner = "docs-agent"

    return tech, owner


def detect_standards(repo_path: Path) -> dict[str, Any]:
    """Detect coding standards, frameworks, and tooling for a repo.

    Returns a dict suitable for platform.yaml repo_standards section.
    """
    standards: dict[str, Any] = {}

    # Language / runtime
    if (repo_path / "tsconfig.json").exists():
        standards["language"] = "typescript"
    elif (repo_path / "package.json").exists():
        standards["language"] = "javascript"
    elif any((repo_path / f).exists() for f in ("requirements.txt", "pyproject.toml", "Pipfile")):
        standards["language"] = "python"
    elif (repo_path / "go.mod").exists():
        standards["language"] = "go"

    # Framework detection
    framework_signals = {
        "next.config.js": "nextjs", "next.config.mjs": "nextjs", "next.config.ts": "nextjs",
        "nuxt.config.ts": "nuxt", "nuxt.config.js": "nuxt",
        "svelte.config.js": "sveltekit",
        "astro.config.mjs": "astro",
        "remix.config.js": "remix",
        "angular.json": "angular",
    }
    for signal_file, framework in framework_signals.items():
        if (repo_path / signal_file).exists():
            standards["framework"] = framework
            break

    # Check package.json for more framework signals
    pkg_json = repo_path / "package.json"
    if pkg_json.exists() and "framework" not in standards:
        try:
            pkg = json.loads(pkg_json.read_text(encoding="utf-8"))
            all_deps = set()
            for key in ("dependencies", "devDependencies"):
                all_deps.update(pkg.get(key, {}).keys())
            if "nestjs" in " ".join(all_deps).lower() or "@nestjs/core" in all_deps:
                standards["framework"] = "nestjs"
            elif "express" in all_deps:
                standards["framework"] = "express"
            elif "fastify" in all_deps:
                standards["framework"] = "fastify"
            elif "@refinedev/core" in all_deps or "refine" in " ".join(all_deps).lower():
                standards["framework"] = "refine"
        except (json.JSONDecodeError, OSError):
            pass

    # Python framework detection
    for pyfile in ("requirements.txt", "pyproject.toml"):
        pypath = repo_path / pyfile
        if pypath.exists():
            try:
                content = pypath.read_text(encoding="utf-8").lower()
                if "fastapi" in content:
                    standards["framework"] = "fastapi"
                elif "django" in content:
                    standards["framework"] = "django"
                elif "flask" in content:
                    standards["framework"] = "flask"
            except OSError:
                pass

    # Package manager
    pm_signals = {
        "pnpm-lock.yaml": "pnpm",
        "yarn.lock": "yarn",
        "bun.lockb": "bun",
        "package-lock.json": "npm",
        "uv.lock": "uv",
        "poetry.lock": "poetry",
        "Pipfile.lock": "pipenv",
    }
    for signal_file, pm in pm_signals.items():
        if (repo_path / signal_file).exists():
            standards["package_manager"] = pm
            break

    # Styling
    if (repo_path / "tailwind.config.js").exists() or (repo_path / "tailwind.config.ts").exists():
        standards["styling"] = "tailwind"

    # Testing
    testing: dict[str, Any] = {}
    test_signals = {
        "jest.config.js": "jest", "jest.config.ts": "jest", "jest.config.mjs": "jest",
        "vitest.config.js": "vitest", "vitest.config.ts": "vitest", "vitest.config.mjs": "vitest",
        "playwright.config.ts": "playwright", "playwright.config.js": "playwright",
        "cypress.config.js": "cypress", "cypress.config.ts": "cypress",
        "pytest.ini": "pytest", "conftest.py": "pytest", "setup.cfg": "pytest",
    }
    for signal_file, test_fw in test_signals.items():
        if (repo_path / signal_file).exists():
            if test_fw in ("playwright", "cypress"):
                testing["e2e"] = test_fw
            else:
                testing["unit"] = test_fw
    # Check pyproject.toml for pytest
    pyproject = repo_path / "pyproject.toml"
    if pyproject.exists() and "unit" not in testing:
        try:
            if "pytest" in pyproject.read_text(encoding="utf-8").lower():
                testing["unit"] = "pytest"
        except OSError:
            pass
    if testing:
        standards["testing"] = testing

    # Linting
    linting = []
    lint_signals = {
        ".eslintrc": "eslint", ".eslintrc.js": "eslint", ".eslintrc.json": "eslint",
        "eslint.config.js": "eslint", "eslint.config.mjs": "eslint",
        ".prettierrc": "prettier", ".prettierrc.js": "prettier", "prettier.config.js": "prettier",
        "biome.json": "biome",
        ".pylintrc": "pylint",
        "ruff.toml": "ruff", ".ruff.toml": "ruff",
    }
    for signal_file, linter in lint_signals.items():
        if (repo_path / signal_file).exists() and linter not in linting:
            linting.append(linter)
    # Check pyproject.toml for ruff/black
    if pyproject.exists():
        try:
            content = pyproject.read_text(encoding="utf-8").lower()
            if "[tool.ruff]" in content and "ruff" not in linting:
                linting.append("ruff")
            if "[tool.black]" in content:
                linting.append("black")
        except OSError:
            pass
    if linting:
        standards["linting"] = linting

    # IaC
    if (repo_path / "Pulumi.yaml").exists():
        standards["iac"] = "pulumi"
    elif list(repo_path.glob("*.tf")):
        standards["iac"] = "terraform"

    # Containerized
    if (repo_path / "Dockerfile").exists() or (repo_path / "docker-compose.yml").exists():
        standards["containerized"] = True

    return standards


def _looks_like_spec_repo(repo_path: Path) -> bool:
    """Check if a repo is itself an OpenSpec-style specs repository.

    Detects repos named *-specs, *-spec, specs, or openspec that contain
    multiple subdirectories with markdown spec files (spec.md, change.md,
    contracts.md, etc.).
    """
    name = repo_path.name.lower()
    name_match = any(name.endswith(s) for s in ("-specs", "-spec")) or name in ("specs", "openspec")
    if not name_match:
        return False

    # Must have multiple subdirectories with spec-like markdown files
    spec_subdirs = 0
    spec_file_names = {"spec.md", "change.md", "contracts.md", "design.md",
                       "proposal.md", "requirements.md", "api.md"}
    for entry in repo_path.iterdir():
        if entry.is_dir() and not entry.name.startswith("."):
            md_files = {f.name.lower() for f in entry.iterdir() if f.is_file() and f.suffix == ".md"}
            if md_files & spec_file_names:
                spec_subdirs += 1
    return spec_subdirs >= 2


def detect_openspec(root: Path, repo_paths: list[Path]) -> dict[str, Any] | None:
    """Detect OpenSpec installation in any repo or at root level.

    Returns dict with 'path' and 'repo' keys if found, None otherwise.
    """
    # Check each repo for openspec/ directory or openspec.config.* files
    for repo_path in repo_paths:
        openspec_dir = repo_path / OPENSPEC_DIR_NAME
        if openspec_dir.is_dir():
            rel = f"./{repo_path.relative_to(root).as_posix()}"
            return {"path": rel, "repo": repo_path.name}
        for pattern in OPENSPEC_CONFIG_PATTERNS:
            if list(repo_path.glob(pattern)):
                rel = f"./{repo_path.relative_to(root).as_posix()}"
                return {"path": rel, "repo": repo_path.name}

    # Check if any repo IS a spec repo (e.g. watchtower-specs with subdirs)
    for repo_path in repo_paths:
        if _looks_like_spec_repo(repo_path):
            rel = f"./{repo_path.relative_to(root).as_posix()}"
            return {"path": rel, "repo": repo_path.name}

    # Check root level (less common but possible)
    if (root / OPENSPEC_DIR_NAME).is_dir():
        return {"path": ".", "repo": None}
    for pattern in OPENSPEC_CONFIG_PATTERNS:
        if list(root.glob(pattern)):
            return {"path": ".", "repo": None}

    return None


def find_contracts_dir(root: Path, repo_paths: list[Path]) -> str | None:
    """Look for API contract directories (OpenAPI, swagger, etc.)."""
    # Check root level
    for name in CONTRACTS_DIR_NAMES:
        candidate = root / name
        if candidate.is_dir():
            return f"./{name}"

    # Check for openapi yaml files at root
    for pattern in ("*.openapi.yaml", "*.openapi.yml", "*.swagger.yaml", "*.swagger.yml"):
        if list(root.glob(pattern)):
            return "./"

    # Check inside repos
    for repo_path in repo_paths:
        for name in CONTRACTS_DIR_NAMES:
            candidate = repo_path / name
            if candidate.is_dir():
                rel = candidate.relative_to(root).as_posix()
                return f"./{rel}"
        # Also check for specs/ inside repos (common for contracts)
        specs_candidate = repo_path / "specs"
        if specs_candidate.is_dir():
            rel = specs_candidate.relative_to(root).as_posix()
            return f"./{rel}"

    return None


def detect_monorepo_indicators(repo_path: Path) -> bool:
    """Check if a repo looks like a monorepo (multiple package.json at different depths)."""
    pkg_files = list(repo_path.glob("**/package.json"))
    # Filter out node_modules
    pkg_files = [p for p in pkg_files if "node_modules" not in str(p)]
    if len(pkg_files) > 2:
        depths = {len(p.relative_to(repo_path).parts) for p in pkg_files}
        if len(depths) > 1:
            return True
    return False


def _looks_like_project(path: Path) -> bool:
    """Check if a directory looks like a project even without .git/.

    Detects directories with source code, config files, or Claude Code configs.
    """
    # Strong signals: project manifests or source directories
    project_indicators = [
        "package.json", "pyproject.toml", "requirements.txt", "setup.py",
        "Pipfile", "go.mod", "Cargo.toml", "pom.xml", "build.gradle",
        "composer.json", "Gemfile", "pubspec.yaml",
        "Makefile", "CMakeLists.txt", "Dockerfile", "docker-compose.yml",
        "docker-compose.yaml", ".gitignore", ".env.example",
    ]
    for indicator in project_indicators:
        if (path / indicator).exists():
            return True

    # Claude Code config is a strong signal
    if (path / ".claude").is_dir():
        return True

    # Has a CLAUDE.md or README.md with subdirectories (likely a project)
    if (path / "CLAUDE.md").exists() or (path / "README.md").exists():
        subdirs = [d for d in path.iterdir() if d.is_dir() and not d.name.startswith(".")]
        if len(subdirs) >= 2:
            return True

    # Has src/ or lib/ directory
    for src_dir in ("src", "lib", "app", "core"):
        if (path / src_dir).is_dir():
            return True

    return False


def _progress(msg: str) -> None:
    """Print progress to stderr (stdout is reserved for JSON output)."""
    print(msg, file=sys.stderr, flush=True)


def scan_directory(root: Path) -> dict[str, Any]:
    """Scan root directory for git repos and build discovery report."""
    report: dict[str, Any] = {
        "root": str(root),
        "repos": [],
        "openspec": None,
        "contracts_path": None,
        "warnings": [],
    }

    repo_paths: list[Path] = []

    # Find project directories (git repos + directories that look like projects)
    non_git_projects: list[Path] = []

    _progress("Scanning directories...")
    entries = sorted(e for e in root.iterdir() if e.is_dir() and not e.name.startswith("."))
    for i, entry in enumerate(entries, 1):
        _progress(f"  [{i}/{len(entries)}] {entry.name}")

        # Skip maestro/otaman folders. Three signals:
        #   1. Has platform.yaml + .agents/ (fully-init project — original heuristic)
        #   2. Name ends with -maestro or -otaman (just-created shell, no platform.yaml yet)
        is_maestro_folder = (entry / "platform.yaml").exists() and (entry / ".agents").is_dir()
        is_otaman_named = entry.name.endswith("-maestro") or entry.name.endswith("-otaman")
        if is_maestro_folder or is_otaman_named:
            _progress(f"    (skipped — maestro/otaman folder)")
            continue

        git_dir = entry / ".git"
        if git_dir.exists():
            repo_paths.append(entry)
        elif _looks_like_project(entry):
            non_git_projects.append(entry)

    # Include non-git project directories alongside git repos
    for proj in non_git_projects:
        repo_paths.append(proj)
        report["warnings"].append(
            f"'{proj.name}' has no .git/ directory but looks like a project. "
            f"Consider running 'git init' in it."
        )

    _progress(f"Found {len(repo_paths)} git repos, {len(non_git_projects)} non-git projects")

    if not repo_paths:
        report["warnings"].append(
            "No repos or project directories found as direct subdirectories. "
            "Make sure you're pointing at the parent directory that contains your repos."
        )
        return report

    _progress("Detecting tech stacks...")
    for idx, repo_path in enumerate(repo_paths, 1):
        _progress(f"  [{idx}/{len(repo_paths)}] {repo_path.name}")
        rel_path = f"./{repo_path.relative_to(root).as_posix()}"
        name = repo_path.name
        # Normalize name: strip common prefixes like "repo-"
        display_name = name
        for prefix in ("repo-", "service-", "svc-", "app-"):
            if display_name.startswith(prefix):
                display_name = display_name[len(prefix):]
                break

        tech, suggested_owner = detect_tech_stack(repo_path)
        if not suggested_owner:
            suggested_owner = f"agent-{display_name}"

        has_claude_md = (repo_path / "CLAUDE.md").exists()
        has_claude_config = (
            (repo_path / ".claude").is_dir()
            or (repo_path / ".claude" / "settings.json").exists()
            or (repo_path / ".claude" / "settings.local.json").exists()
        )
        existing_hooks = False
        for settings_file in ("settings.json", "settings.local.json"):
            sf = repo_path / ".claude" / settings_file
            if sf.exists():
                try:
                    data = json.loads(sf.read_text(encoding="utf-8"))
                    if data.get("hooks"):
                        existing_hooks = True
                except (json.JSONDecodeError, OSError):
                    pass

        is_monorepo = detect_monorepo_indicators(repo_path)
        if is_monorepo:
            report["warnings"].append(
                f"'{name}' looks like a monorepo (multiple package.json at different depths). "
                f"Consider splitting into separate entries or managing as a single repo."
            )

        has_git = (repo_path / ".git").exists()

        # Detect git remote URL
        remote_url = ""
        if has_git:
            try:
                r = subprocess.run(
                    ["git", "-C", str(repo_path), "remote", "get-url", "origin"],
                    capture_output=True, text=True, timeout=5,
                )
                if r.returncode == 0:
                    remote_url = r.stdout.strip()
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass

        # Also check for CLAUDE-*.md variants (e.g. CLAUDE-edge.md)
        if not has_claude_md:
            has_claude_md = bool(list(repo_path.glob("CLAUDE*.md")))

        # Detect coding standards and tooling
        standards = detect_standards(repo_path)

        repo_info: dict[str, Any] = {
            "name": display_name,
            "dir_name": name,
            "path": rel_path,
            "tech": tech,
            "suggested_owner": suggested_owner,
            "has_git": has_git,
            "has_claude_md": has_claude_md,
            "has_claude_config": has_claude_config,
            "has_existing_hooks": existing_hooks,
            "is_monorepo": is_monorepo,
            "standards": standards,
        }
        if remote_url:
            repo_info["remote"] = remote_url

        # Try to get description from package.json or README
        desc = _get_repo_description(repo_path)
        if desc:
            repo_info["description"] = desc

        report["repos"].append(repo_info)

    # Detect OpenSpec installation
    _progress("Checking for OpenSpec...")
    openspec = detect_openspec(root, repo_paths)
    if openspec:
        report["openspec"] = openspec
        _progress(f"  OpenSpec found: {openspec.get('repo', openspec.get('path'))}")

    # Find API contracts directory
    _progress("Checking for API contracts...")
    contracts = find_contracts_dir(root, repo_paths)
    if contracts:
        report["contracts_path"] = contracts
        _progress(f"  Contracts found: {contracts}")

    _progress("Discovery complete.")
    return report


def _get_repo_description(repo_path: Path) -> str:
    """Try to extract a description from package.json or first line of README."""
    pkg = repo_path / "package.json"
    if pkg.exists():
        try:
            data = json.loads(pkg.read_text(encoding="utf-8"))
            desc = data.get("description", "")
            if desc and len(desc) <= 256:
                return desc
        except (json.JSONDecodeError, OSError):
            pass

    for readme_name in ("README.md", "README.rst", "README.txt", "README"):
        readme = repo_path / readme_name
        if readme.exists():
            try:
                lines = readme.read_text(encoding="utf-8").strip().splitlines()
                for line in lines:
                    stripped = line.strip().lstrip("#").strip()
                    if stripped and len(stripped) <= 256:
                        return stripped
                        break
            except OSError:
                pass

    return ""


def _relative_path(from_dir: Path, to_dir: Path) -> str:
    """Compute a relative path from from_dir to to_dir using posix separators."""
    try:
        rel = os.path.relpath(to_dir.resolve(), from_dir.resolve())
        return Path(rel).as_posix()
    except ValueError:
        # Different drives on Windows — fall back to absolute
        return to_dir.resolve().as_posix()


def generate_draft_yaml(root: Path, report: dict[str, Any], maestro_dir: Path | None = None) -> Path:
    """Generate platform.yaml.draft from discovery report.

    Args:
        root: The scanned directory (where repos were found).
        report: Discovery report from scan_directory().
        maestro_dir: If set, output goes here and repo paths are relative to it.
                     If None, falls back to legacy behavior (output in root).
    """
    output_dir = maestro_dir or root

    project_name = root.name.lower().replace(" ", "-").replace("_", "-")
    # Sanitize to match pattern ^[a-z][a-z0-9-]{1,63}$
    project_name = "".join(c for c in project_name if c.isalnum() or c == "-")
    if not project_name or not project_name[0].isalpha():
        project_name = "my-platform"

    config: dict[str, Any] = {
        "project": project_name,
        "version": "1.0",
        "repos": [],
    }

    for repo in report["repos"]:
        # Compute path relative to maestro dir (not scan root)
        if maestro_dir:
            repo_abs = (root / repo["path"]).resolve()
            rel_path = _relative_path(output_dir, repo_abs)
        else:
            rel_path = repo["path"]

        entry: dict[str, Any] = {
            "name": repo["name"],
            "path": rel_path,
            "owner": repo["suggested_owner"],
        }
        if repo.get("tech"):
            entry["tech"] = repo["tech"]
        if repo.get("description"):
            entry["description"] = repo["description"]
        if repo.get("remote"):
            entry["remote"] = repo["remote"]
        config["repos"].append(entry)

    # Specs section: openspec if detected, fallback otherwise
    if report.get("openspec"):
        spec_path = report["openspec"]["path"]
        if maestro_dir:
            spec_abs = (root / spec_path).resolve()
            spec_path = _relative_path(output_dir, spec_abs)
        config["specs"] = {
            "path": spec_path,
            "format": "openspec",
        }
    else:
        # When maestro hosts openspec, path is local
        if maestro_dir:
            config["specs"] = {
                "path": "./openspec",
                "format": "fallback",
            }
        else:
            config["specs"] = {
                "format": "fallback",
            }

    # Contracts section: API contracts (OpenAPI, etc.)
    if report.get("contracts_path"):
        contracts_path = report["contracts_path"]
        if maestro_dir:
            contracts_abs = (root / contracts_path).resolve()
            contracts_path = _relative_path(output_dir, contracts_abs)
        config["contracts"] = {
            "path": contracts_path,
            "format": "openapi",
            "auto_detect": True,
        }

    config["observers"] = [
        {"role": "cto-reviewer", "triggers": ["pr", "spec-change", "architecture-change"]},
        {"role": "security", "triggers": ["pr", "dependency-update", "auth-change"]},
    ]

    config["communication"] = {
        "bus_path": ".agents/bus",
        "format": "markdown",
        "max_age_days": 30,
    }

    # Standards section: auto-detected from repo tooling
    repo_standards: dict[str, Any] = {}
    for repo in report["repos"]:
        if repo.get("standards"):
            repo_standards[repo["name"]] = repo["standards"]
    if repo_standards:
        config["standards"] = {"repo_standards": repo_standards}

    draft_path = output_dir / "platform.yaml.draft"
    with open(draft_path, "w", encoding="utf-8") as f:
        f.write("# Maestro Platform Configuration (DRAFT)\n")
        f.write("# Generated by /otaman:scan — review and adjust before running /otaman:init\n")
        f.write("# Repo paths are relative to this maestro folder.\n")
        f.write("# Pay special attention to 'owner' fields — these are suggestions based on tech stack detection.\n\n")
        yaml.dump(config, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

    return draft_path


def update_existing_config(root: Path, report: dict[str, Any], *, dry_run: bool = False) -> tuple[Path, dict[str, Any]]:
    """Merge discovery results into an existing platform.yaml.

    Preserves:
    - Existing repo ownership assignments
    - Existing repo descriptions (if manually edited)
    - Observers, communication, and other user-configured sections

    Updates:
    - Tech stack tags (re-detected)
    - Adds newly discovered repos (with suggested owners)
    - Updates specs/contracts paths if OpenSpec newly detected
    """
    config_path = root / "platform.yaml"
    try:
        with open(config_path, encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
    except yaml.YAMLError as _e:
        # Malformed YAML — preserve users file as .bak, surface a clear error
        import shutil
        bak = config_path.with_suffix(config_path.suffix + ".bak")
        shutil.copy2(config_path, bak)
        print(
            f"ERROR: Failed to parse {config_path}: {_e}",
            file=sys.stderr,
        )
        print(
            f"Your file was backed up to {bak}.",
            file=sys.stderr,
        )
        print(
            "Hint: Restore from .bak, fix the syntax, then re-run otaman scan --update.",
            file=sys.stderr,
        )
        raise

    changes: dict[str, Any] = {"added": [], "updated": [], "removed": [], "unchanged": []}

    # Build lookups of existing repos
    existing_by_path: dict[str, dict[str, Any]] = {}
    existing_by_name: dict[str, dict[str, Any]] = {}
    for repo in config.get("repos", []):
        existing_by_path[repo["path"]] = repo
        existing_by_name[repo["name"]] = repo

    new_repos: list[dict[str, Any]] = []
    seen_existing: set[str] = set()

    # Match discovered repos to existing ones
    for drepo in report["repos"]:
        path = drepo["path"]
        if path in existing_by_path:
            existing = existing_by_path[path]
            seen_existing.add(path)
            updated_fields = []
            if drepo.get("tech") and existing.get("tech") != drepo["tech"]:
                existing["tech"] = drepo["tech"]
                updated_fields.append("tech")
            if updated_fields:
                changes["updated"].append({"name": existing["name"], "fields": updated_fields})
            else:
                changes["unchanged"].append(existing["name"])
            new_repos.append(existing)
        elif drepo["name"] in existing_by_name:
            existing = existing_by_name[drepo["name"]]
            seen_existing.add(existing["path"])
            existing["path"] = path
            if drepo.get("tech"):
                existing["tech"] = drepo["tech"]
            changes["updated"].append({"name": existing["name"], "fields": ["path"]})
            new_repos.append(existing)
        else:
            entry: dict[str, Any] = {
                "name": drepo["name"],
                "path": drepo["path"],
                "owner": drepo["suggested_owner"],
            }
            if drepo.get("tech"):
                entry["tech"] = drepo["tech"]
            if drepo.get("description"):
                entry["description"] = drepo["description"]
            new_repos.append(entry)
            changes["added"].append(drepo["name"])

    # Keep repos that are in config but not discovered (flag them)
    for repo in config.get("repos", []):
        if repo["path"] not in seen_existing:
            new_repos.append(repo)
            changes["removed"].append(repo["name"])

    config["repos"] = new_repos

    # Update specs if OpenSpec newly detected
    if report.get("openspec") and config.get("specs", {}).get("format") != "openspec":
        config["specs"] = {
            "path": report["openspec"]["path"],
            "format": "openspec",
        }
        changes["updated"].append({"name": "(specs)", "fields": ["format=openspec"]})

    # Update contracts if newly detected and not set
    if report.get("contracts_path") and "contracts" not in config:
        config["contracts"] = {
            "path": report["contracts_path"],
            "format": "openapi",
            "auto_detect": True,
        }
        changes["updated"].append({"name": "(contracts)", "fields": ["added"]})

    out_path = root / "platform.yaml.updated"
    if dry_run:
        return out_path, changes
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("# Maestro Platform Configuration (UPDATED)\n")
        f.write("# Re-scanned by /otaman:scan --update\n")
        f.write("# Review changes, then rename to platform.yaml\n\n")
        yaml.dump(config, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

    return out_path, changes


def main() -> int:
    update_mode = "--update" in sys.argv
    dry_run = "--dry-run" in sys.argv

    # Parse --maestro-dir option
    maestro_dir: Path | None = None
    argv_filtered = []
    skip_next = False
    for i, arg in enumerate(sys.argv[1:], 1):
        if skip_next:
            skip_next = False
            continue
        if arg == "--maestro-dir" and i < len(sys.argv) - 1:
            maestro_dir = Path(sys.argv[i + 1]).resolve()
            skip_next = True
        elif arg.startswith("--"):
            pass  # skip other flags
        else:
            argv_filtered.append(arg)

    root = Path(argv_filtered[0]).resolve() if argv_filtered else Path.cwd().resolve()

    if not root.is_dir():
        print(f"ERROR: Not a directory: {root}", file=sys.stderr)
        return 2

    report = scan_directory(root)

    if not report["repos"]:
        print(json.dumps(report, indent=2))
        return 1

    if update_mode:
        config_path = root / "platform.yaml"
        if not config_path.exists():
            print(f"ERROR: --update requires existing platform.yaml at {config_path}", file=sys.stderr)
            return 2
        if dry_run:
            # Don't mutate; report what would change
            from copy import deepcopy
            _, changes = update_existing_config(root, deepcopy(report), dry_run=True)
            report["update_path"] = str(root / "platform.yaml.updated")
            report["changes"] = changes
            report["dry_run"] = True
        else:
            out_path, changes = update_existing_config(root, report)
            report["update_path"] = str(out_path)
            report["changes"] = changes
        print(json.dumps(report, indent=2))
        return 0

    # Create maestro dir if specified and doesn't exist
    if maestro_dir:
        if not dry_run:
            maestro_dir.mkdir(parents=True, exist_ok=True)
        report["maestro_dir"] = str(maestro_dir)

    if dry_run:
        # Skip writing draft; report the path it WOULD land at
        target_dir = maestro_dir if maestro_dir else root
        report["draft_path"] = str(target_dir / "platform.yaml.draft")
        report["dry_run"] = True
    else:
        draft_path = generate_draft_yaml(root, report, maestro_dir=maestro_dir)
        report["draft_path"] = str(draft_path)

    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
