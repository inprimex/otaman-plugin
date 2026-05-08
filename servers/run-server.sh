#!/usr/bin/env bash
# Cross-platform wrapper to launch a maestro MCP server with the correct Python.
# Usage: bash run-server.sh <server-script.py>
#
# Resolves Python in this order:
#   1. Virtual env in servers/.venv (Scripts/ on Windows, bin/ on Unix)
#   2. python3 on PATH (Linux/macOS/WSL)
#   3. py on PATH (Windows py launcher)
#   4. python on PATH (fallback)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SERVER_SCRIPT="${1:?Usage: run-server.sh <server.py>}"

# Resolve server path (absolute or relative to servers/)
if [[ "$SERVER_SCRIPT" != /* ]]; then
    SERVER_SCRIPT="$SCRIPT_DIR/$SERVER_SCRIPT"
fi

# 1a. Prefer the otaman uv-workspace venv (covers dev mode where
#     otaman-core / otaman-cli / otaman-bridge / otaman-plugin are all
#     installed editable, so `from otaman_core._resolve import ...` works).
#     Layout: otaman-plugin/servers/run-server.sh → ../../.venv/
WORKSPACE_VENV="$SCRIPT_DIR/../../.venv"
if [[ -x "$WORKSPACE_VENV/bin/python" ]]; then
    exec "$WORKSPACE_VENV/bin/python" "$SERVER_SCRIPT"
elif [[ -x "$WORKSPACE_VENV/Scripts/python.exe" ]]; then
    exec "$WORKSPACE_VENV/Scripts/python.exe" "$SERVER_SCRIPT"
fi

# 1b. Try a plugin-local servers/.venv (if user set one up explicitly)
VENV="$SCRIPT_DIR/.venv"
if [[ -x "$VENV/Scripts/python.exe" ]]; then
    exec "$VENV/Scripts/python.exe" "$SERVER_SCRIPT"
elif [[ -x "$VENV/bin/python3" ]]; then
    exec "$VENV/bin/python3" "$SERVER_SCRIPT"
elif [[ -x "$VENV/bin/python" ]]; then
    exec "$VENV/bin/python" "$SERVER_SCRIPT"
fi

# 2. Fall back to system Python
if command -v python3 &>/dev/null && python3 -c "pass" 2>/dev/null; then
    exec python3 "$SERVER_SCRIPT"
elif command -v py &>/dev/null; then
    exec py "$SERVER_SCRIPT"
elif command -v python &>/dev/null && python -c "pass" 2>/dev/null; then
    exec python "$SERVER_SCRIPT"
fi

echo "Python not found. Install Python 3.10+ or create servers/.venv" >&2
exit 1
