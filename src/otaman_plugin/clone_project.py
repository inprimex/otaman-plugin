#!/usr/bin/env python3
"""Otaman Clone — set up a project from platform.yaml (clone all repos + init).

Sources for platform.yaml:
  1. Local file path
  2. Git repo URL (clones the otaman repo first; legacy: pre-rebrand `*-maestro`
     naming convention is still recognized)
  3. SSH remote path (fetches via scp/ssh)

Usage:
    python clone-project.py <source> [--target <dir>]

    # From local file:
    python clone-project.py /path/to/platform.yaml --target ~/projects/my-project

    # From git repo (otaman folder is a git repo):
    python clone-project.py git@github.com:org/project-otaman.git --target ~/projects

    # From SSH remote:
    python clone-project.py user@host:/path/to/otaman/ --target ~/projects

Exit codes:
    0 — success
    1 — partial (some repos failed to clone)
    2 — error (config not found, etc.)
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
    print("ERROR: PyYAML required. Install with: pip install pyyaml", file=sys.stderr)
    sys.exit(2)


def _run(cmd: list[str], cwd: str | None = None, timeout: int = 120, env: dict | None = None) -> tuple[int, str, str]:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=cwd, env=env)
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        return -1, "", str(e)


def _progress(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def fetch_config(source: str, target_dir: Path) -> Path | None:
    """Fetch platform.yaml from source. Returns path to local config file."""

    # Case 1: Local file
    source_path = Path(source)
    if source_path.exists():
        if source_path.is_file():
            return source_path.resolve()
        # Directory — look for platform.yaml inside
        config = source_path / "platform.yaml"
        if config.exists():
            return config.resolve()
        _progress(f"ERROR: No platform.yaml found in {source}")
        return None

    # Case 2: Git URL (ends with .git or contains github/gitlab)
    if source.endswith(".git") or "github.com" in source or "gitlab.com" in source or "bitbucket.org" in source:
        _progress(f"Cloning maestro repo: {source}")  # legacy: pre-rebrand reference
        # Extract repo name for local dir
        repo_name = source.rstrip("/").split("/")[-1].replace(".git", "")
        maestro_dir = target_dir / repo_name
        rc, out, err = _run(["git", "clone", source, str(maestro_dir)], timeout=300)
        if rc != 0:
            _progress(f"ERROR: git clone failed: {err}")
            return None
        config = maestro_dir / "platform.yaml"
        if config.exists():
            return config.resolve()
        _progress(f"ERROR: No platform.yaml in cloned repo {maestro_dir}")
        return None

    # Case 3: SSH remote (user@host:path)
    if ":" in source and "@" in source:
        _progress(f"Fetching config from SSH: {source}")
        # Parse user@host:path
        host_part, remote_path = source.split(":", 1)
        remote_config = f"{remote_path.rstrip('/')}/platform.yaml"

        # Fetch via ssh cat
        rc, content, err = _run(["ssh", host_part, f"cat {remote_config}"], timeout=30)
        if rc != 0:
            _progress(f"ERROR: SSH fetch failed: {err}")
            return None

        # Determine maestro folder name from config  # legacy: pre-rebrand reference
        try:
            cfg = yaml.safe_load(content)
            project_name = cfg.get("project", "project")
        except yaml.YAMLError:
            project_name = "project"

        maestro_dir = target_dir / f"{project_name}-maestro"  # legacy: pre-rebrand reference
        maestro_dir.mkdir(parents=True, exist_ok=True)
        config_path = maestro_dir / "platform.yaml"
        config_path.write_text(content, encoding="utf-8")

        # Also fetch .gitignore if exists
        rc2, gi_content, _ = _run(["ssh", host_part, f"cat {remote_path.rstrip('/')}/.gitignore"], timeout=10)
        if rc2 == 0:
            (maestro_dir / ".gitignore").write_text(gi_content, encoding="utf-8")

        # Git init
        _run(["git", "init", str(maestro_dir)])

        return config_path.resolve()

    _progress(f"ERROR: Cannot resolve source: {source}")
    return None


def clone_repos(config: dict[str, Any], maestro_dir: Path) -> dict[str, Any]:
    """Clone all repos defined in platform.yaml."""
    report: dict[str, Any] = {"cloned": [], "skipped": [], "failed": []}

    repos = config.get("repos", [])
    total = len(repos)

    for i, repo in enumerate(repos, 1):
        name = repo["name"]
        remote = repo.get("remote", "")
        rel_path = repo.get("path", f"../{name}")
        target = (maestro_dir / rel_path).resolve()

        _progress(f"  [{i}/{total}] {name}")

        # Skip if already exists
        if target.is_dir() and (target / ".git").is_dir():
            _progress(f"    Already exists, skipping")
            report["skipped"].append(name)
            continue

        if not remote:
            # Try to derive from git_platform
            platform = config.get("git_platform", {})
            provider = platform.get("provider", "")
            org = platform.get("org", "")
            if provider == "github" and org:
                remote = f"git@github.com:{org}/{repo.get('dir_name', name)}.git"
            elif provider == "gitlab" and org:
                remote = f"git@gitlab.com:{org}/{repo.get('dir_name', name)}.git"

        if not remote:
            _progress(f"    No remote URL, skipping")
            report["failed"].append({"name": name, "error": "No remote URL"})
            continue

        # Clone (with SSH key if available)
        target.parent.mkdir(parents=True, exist_ok=True)
        clone_env = dict(os.environ)
        if remote.startswith("git@") and not os.environ.get("GIT_SSH_COMMAND"):
            # Try to find an SSH key
            home = Path.home()
            for key_candidate in [
                home / ".ssh" / "github_maestro",
                home / ".ssh" / "github_key",
                home / ".ssh" / "id_ed25519",
                home / ".ssh" / "id_rsa",
                home / "github_key",
            ]:
                if key_candidate.exists():
                    # Use forward slashes for SSH (Windows backslashes break it)
                    key_posix = str(key_candidate).replace("\\", "/")
                    clone_env["GIT_SSH_COMMAND"] = f'ssh -i "{key_posix}" -o StrictHostKeyChecking=no'
                    break
        rc, out, err = _run(["git", "clone", remote, str(target)], timeout=300, env=clone_env)
        if rc != 0:
            _progress(f"    FAILED: {err[:100]}")
            report["failed"].append({"name": name, "error": err[:200]})
        else:
            _progress(f"    Cloned from {remote}")
            report["cloned"].append(name)

    return report


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    target_dir = Path.cwd()
    has_target = False

    # Parse --target
    for i, a in enumerate(sys.argv[1:], 1):
        if a == "--target" and i < len(sys.argv) - 1:
            target_dir = Path(sys.argv[i + 1]).resolve()
            target_dir.mkdir(parents=True, exist_ok=True)
            has_target = True

    if not args:
        print("Usage: clone-project.py <source> [--target <dir>]", file=sys.stderr)
        print("  source: local path | git URL | user@host:path", file=sys.stderr)
        return 2

    source = args[0]

    # Step 1: Fetch config
    _progress("=== Fetching platform.yaml ===")
    config_path = fetch_config(source, target_dir)
    if not config_path:
        return 2

    with open(config_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    project = config.get("project", "unknown")
    repos = config.get("repos", [])
    _progress(f"Project: {project} ({len(repos)} repos)")

    # Determine maestro dir: if --target given, create maestro folder inside target  # legacy: pre-rebrand reference
    if has_target:
        maestro_dir = target_dir / f"{project}-maestro"  # legacy: pre-rebrand reference
        maestro_dir.mkdir(parents=True, exist_ok=True)
        # Copy config to maestro folder  # legacy: pre-rebrand reference
        import shutil
        dest_config = maestro_dir / "platform.yaml"
        if config_path.resolve() != dest_config.resolve():
            shutil.copy2(str(config_path), str(dest_config))
        config_path = dest_config
        # Git init
        if not (maestro_dir / ".git").is_dir():
            _run(["git", "init", str(maestro_dir)])
        # Generate .gitignore
        gi = maestro_dir / ".gitignore"
        if not gi.exists():
            gi.write_text(
                "# Runtime artifacts\n.agents/bus/\n.agents/blocked/\n"
                ".agents/queue/\n.agents/sessions/\n.agents/current-agent\n"
                "\n# Maestro runtime state (secrets, bridge sockets, AFK flag)\n"  # legacy: pre-rebrand reference
                ".otaman/secrets.env\n.otaman/bridge-*.endpoint\n.otaman/afk\n",
                encoding="utf-8",
            )
    else:
        maestro_dir = config_path.parent

    _progress(f"Maestro folder: {maestro_dir}")  # legacy: pre-rebrand reference

    # Step 2: Clone repos
    _progress("\n=== Cloning repositories ===")
    clone_report = clone_repos(config, maestro_dir)

    # Step 3: Run init
    _progress("\n=== Running maestro init ===")  # legacy: pre-rebrand reference
    scripts_dir = Path(__file__).resolve().parent
    init_script = scripts_dir / "generate-agent-config.py"
    if init_script.exists():
        rc, out, err = _run([sys.executable, str(init_script), str(config_path)], timeout=60)
        if rc != 0:
            _progress(f"Init warnings: {err[:200]}")
    else:
        _progress("WARNING: generate-agent-config.py not found, skipping init")

    # Step 3.5: Install OpenSpec if needed
    specs = config.get("specs", {})
    if specs.get("format") == "openspec":
        import shutil as _shutil
        if not _shutil.which("openspec"):
            _progress("\n=== Installing OpenSpec CLI ===")
            npm_path = _shutil.which("npm")
            if npm_path:
                rc, out, err = _run([npm_path, "install", "-g", "@fission-ai/openspec@latest"], timeout=120)
                if rc == 0:
                    _progress("  OpenSpec CLI installed globally")
                    clone_report["openspec_installed"] = True
                else:
                    _progress(f"  WARNING: Failed to install openspec: {err[:100]}")
                    _progress("  Fix manually: npm install -g @fission-ai/openspec@latest")
                    clone_report["openspec_installed"] = False
            else:
                _progress("  WARNING: npm not found — cannot install openspec")
                _progress("  Install Node.js first, then: npm install -g @fission-ai/openspec@latest")
                clone_report["openspec_installed"] = False
        else:
            _progress("\n=== OpenSpec CLI already installed ===")

    # Step 4: Run doctor
    _progress("\n=== Running environment check ===")
    doctor_script = scripts_dir / "doctor.py"
    if doctor_script.exists():
        rc, out, err = _run([sys.executable, str(doctor_script), str(maestro_dir)], timeout=30)
        if rc == 0 and out:
            try:
                doctor_report = json.loads(out)
                clone_report["doctor"] = doctor_report.get("summary", {})
            except json.JSONDecodeError:
                pass

    # Output
    clone_report["project"] = project
    clone_report["maestro_dir"] = str(maestro_dir)
    clone_report["config_path"] = str(config_path)
    print(json.dumps(clone_report, indent=2))

    if clone_report["failed"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
