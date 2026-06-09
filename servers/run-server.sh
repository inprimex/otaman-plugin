#!/usr/bin/env bash
# Cross-platform wrapper to launch an otaman MCP server with the correct Python.
# Usage: bash run-server.sh <module-name-or-script.py>
#
# Accepts either:
#   - A dotted module path: bash run-server.sh otaman_plugin.servers.bus_server
#     (run via `python -m`; works after `pip install otaman-plugin` OR in dev)
#   - A direct script path: bash run-server.sh bus_server.py
#     (legacy form; resolves relative to servers/ — kept for back-compat)
#
# Resolves Python in this order:
#   1. otaman uv-workspace venv (covers dev mode where otaman-core /
#      otaman-cli / otaman-bridge / otaman-plugin are all installed editable)
#   2. plugin-local servers/.venv (if user set one up explicitly)
#   3. python3 on PATH (Linux/macOS/WSL)
#   4. py on PATH (Windows py launcher)
#   5. python on PATH (fallback)
#
# Per ce-org-agent-bootstrap (task 3.x), the dotted-module form is the
# canonical CE runtime entry point so the per-org runner can invoke
# `python -m otaman_plugin.servers.bus_server` without vendoring source.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TARGET="${1:?Usage: run-server.sh <module-name-or-script.py>}"

# Decide invocation mode by checking whether the target looks like a
# dotted module (no .py extension) or a script filename.
if [[ "$TARGET" == *.py ]]; then
    if [[ "$TARGET" != /* ]]; then
        TARGET="$SCRIPT_DIR/$TARGET"
    fi
    PYTHON_ARGS=("$TARGET")
else
    PYTHON_ARGS=(-m "$TARGET")
fi

# 1. Prefer the otaman uv-workspace venv. Layout:
#    otaman-plugin/servers/run-server.sh → ../../.venv/
WORKSPACE_VENV="$SCRIPT_DIR/../../.venv"
if [[ -x "$WORKSPACE_VENV/bin/python" ]]; then
    exec "$WORKSPACE_VENV/bin/python" "${PYTHON_ARGS[@]}"
elif [[ -x "$WORKSPACE_VENV/Scripts/python.exe" ]]; then
    exec "$WORKSPACE_VENV/Scripts/python.exe" "${PYTHON_ARGS[@]}"
fi

# 2. Try a plugin-local servers/.venv (if the user set one up explicitly)
VENV="$SCRIPT_DIR/.venv"
if [[ -x "$VENV/Scripts/python.exe" ]]; then
    exec "$VENV/Scripts/python.exe" "${PYTHON_ARGS[@]}"
elif [[ -x "$VENV/bin/python3" ]]; then
    exec "$VENV/bin/python3" "${PYTHON_ARGS[@]}"
elif [[ -x "$VENV/bin/python" ]]; then
    exec "$VENV/bin/python" "${PYTHON_ARGS[@]}"
fi

# 3. Fall back to system Python
if command -v python3 &>/dev/null && python3 -c "pass" 2>/dev/null; then
    exec python3 "${PYTHON_ARGS[@]}"
elif command -v py &>/dev/null; then
    exec py "${PYTHON_ARGS[@]}"
elif command -v python &>/dev/null && python -c "pass" 2>/dev/null; then
    exec python "${PYTHON_ARGS[@]}"
fi

echo "Python not found. Install Python 3.10+ or create servers/.venv" >&2
exit 1
