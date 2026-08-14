#!/usr/bin/env python3
"""Scaffold a launcher folder for an otaman project.

Creates a dedicated folder the user can place anywhere (e.g., C:/work/launchers/myproj)
containing:
  - launch.ps1                 Thin wrapper calling scripts/launch-agents.ps1
  - launch-settings.yaml       Named connections (local + lan + mesh placeholders)
  - platform.yaml              Copied from the otaman folder (if provided)

The launcher folder is decoupled from the otaman folder so it can live on the
developer's laptop even when the otaman folder lives on a remote server.

Usage:
    scaffold-launcher.py <target> [options]

Arguments:
    <target>                   Where to create the launcher folder

Options:
    --name NAME                Project name (defaults to target folder name)
    --otaman-root PATH         Local otaman folder (for local connection + platform.yaml copy)
                               (legacy: alias --maestro-root accepted)
    --plugin-path PATH         Path to otaman-plugin (defaults to this script's parent)
    --remote-host USER@HOST    SSH host for `lan` connection (optional)
    --remote-root PATH         Remote otaman folder path (optional)
    --remote-plugin PATH       Remote otaman-plugin path (optional, default /home/USER/otaman-plugin)
    --ssh-key PATH             SSH private key path (optional)
    --mesh-host USER@HOST      SSH host for `mesh` connection (optional, extends lan)
    --force                    Overwrite existing files
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path


def parse_args(argv: list[str]) -> dict:
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        sys.exit(0 if argv else 2)

    opts = {
        "target": None,
        "name": None,
        "maestro_root": None,
        "plugin_path": str(Path(__file__).resolve().parent.parent),
        "remote_host": None,
        "remote_root": None,
        "remote_plugin": None,
        "ssh_key": None,
        "mesh_host": None,
        "force": False,
    }
    positional: list[str] = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--force":
            opts["force"] = True
            i += 1
        elif a.startswith("--") and i + 1 < len(argv):
            key = a[2:].replace("-", "_")
            if key in opts:
                opts[key] = argv[i + 1]
                i += 2
            else:
                print(f"Unknown option: {a}", file=sys.stderr)
                sys.exit(2)
        else:
            positional.append(a)
            i += 1

    if not positional:
        print("Error: target folder required", file=sys.stderr)
        print(__doc__)
        sys.exit(2)
    opts["target"] = positional[0]
    if not opts["name"]:
        opts["name"] = Path(opts["target"]).name
    return opts


def render_launch_ps1(plugin_path: str, project_name: str) -> str:
    # Forward slashes work on Windows; keep single source of truth
    plugin_posix = plugin_path.replace("\\", "/")
    script = f"{plugin_posix}/scripts/launch-agents.ps1"
    return (
        f"# {project_name} agent launcher — calls maestro plugin script with project-specific settings\n"  # legacy: pre-rebrand reference
        f"# Settings live in this folder (launch-settings.yaml, platform.yaml).\n"
        f"$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path\n"
        f'$MaestroScript = "{script}"\n'
        f"& $MaestroScript -WorkDir $ScriptDir @args\n"
    )


def render_launch_settings(opts: dict) -> str:
    name = opts["name"]
    maestro_root = opts["maestro_root"]
    remote_host = opts["remote_host"]
    remote_root = opts["remote_root"]
    remote_plugin = opts["remote_plugin"] or "/home/USER/otaman-plugin"
    ssh_key = opts["ssh_key"]
    mesh_host = opts["mesh_host"]

    # local_root: either provided maestro_root, or a sensible placeholder
    local_root = (
        maestro_root.replace("\\", "/") if maestro_root else f"C:/work/{name}/{name}-maestro"
    )  # legacy: pre-rebrand reference
    rroot = remote_root or f"/home/USER/{name}/{name}-maestro"  # legacy: pre-rebrand reference

    lines = [
        f"# Maestro launch settings for {name}",  # legacy: pre-rebrand reference
        "# Re-run setup: .\\launch.ps1 -Setup",
        "#",
        "# `active_connection` picks which connection block to use by default.",
        "# Override per-invocation with: .\\launch.ps1 -Connection <name>",
        "",
        'active_connection: "local"',
        "",
        "connections:",
        "  local:",
        '    type: "local"',
        f'    local_root: "{local_root}"',
        '    local_shell: "wsl"',
        '    wsl_distro: "Ubuntu"',
        "",
        "  lan:",
        '    type: "ssh"',
        '    ssh_client: "ssh"',
    ]
    if remote_host:
        lines.append(f'    ssh_default_host: "{remote_host}"')
    else:
        lines.append('    ssh_default_host: "USER@HOST"')
    if ssh_key:
        lines.append(f'    ssh_key: "{ssh_key}"')
    lines += [
        f'    ssh_remote_root: "{rroot}"',
        f'    ssh_plugin_path: "{remote_plugin}"',
        "",
        "  mesh:",
        '    type: "ssh"',
        '    extends: "lan"',
    ]
    if mesh_host:
        lines.append(f'    ssh_default_host: "{mesh_host}"')
    else:
        lines.append('    ssh_default_host: "USER@MESH-HOST"')
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    opts = parse_args(argv)
    target = Path(opts["target"]).resolve()

    if target.exists() and any(target.iterdir()) and not opts["force"]:
        print(f"[!] Target folder is not empty: {target}", file=sys.stderr)
        print("    Pass --force to overwrite, or choose a different path.", file=sys.stderr)
        return 1

    target.mkdir(parents=True, exist_ok=True)

    launch_ps1 = target / "launch.ps1"
    settings = target / "launch-settings.yaml"
    platform_yaml = target / "platform.yaml"

    launch_ps1.write_text(render_launch_ps1(opts["plugin_path"], opts["name"]), encoding="utf-8")
    settings.write_text(render_launch_settings(opts), encoding="utf-8")

    # Copy platform.yaml from the maestro folder if provided  # legacy: pre-rebrand reference
    if opts["maestro_root"]:
        src = Path(opts["maestro_root"]) / "platform.yaml"
        if src.exists():
            shutil.copy2(src, platform_yaml)
            print(f"  [OK] Copied platform.yaml from {src}")
        else:
            print(f"  [!] {src} not found — skipping platform.yaml copy.")
            print("      Copy it manually or .\\launch.ps1 will fetch from remote on first run.")

    print(f"  [OK] Wrote {launch_ps1}")
    print(f"  [OK] Wrote {settings}")
    print()
    print("Next steps:")
    print(f"  1. cd {target}")
    print(
        "  2. Review launch-settings.yaml — fill in USER@HOST / USER@MESH-HOST / ssh_key as needed"
    )
    print("  3. .\\launch.ps1 -Setup       # interactive wizard to add/edit connections")
    print("  4. .\\launch.ps1               # launch agents")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
