"""otaman-plugin MCP servers.

Two stdio MCP servers ship with the plugin:

- :mod:`otaman_plugin.servers.bus_server` — agent message bus tools
- :mod:`otaman_plugin.servers.estimation_server` — pre-sale estimation tools

Both modules are runnable as scripts (``python -m
otaman_plugin.servers.bus_server``) and as direct file invocations
(``python /path/to/bus_server.py``). The ``if __name__ == "__main__"``
entry points in each module preserve the direct-invocation contract used
by the legacy ``servers/run-server.sh`` wrapper and the ``.mcp.json``
configurations referenced by Claude Code.

Per ``ce-org-agent-bootstrap`` (otaman-specs change), the package-import
form is the canonical CE runtime entry point — it lets per-org runner
deployments invoke ``python -m otaman_plugin.servers.bus_server`` after
``pip install otaman-plugin`` without vendoring source files.
"""
