# example-platform-otaman (maestro folder)

This is the **maestro folder** for the example project. It holds:

- `platform.yaml` — source of truth for which repos exist, who owns them,
  what observers run, what specs system is in use
- `launch-settings.yaml.template` — per-user, per-machine launcher config
  (copy to `launch-settings.yaml` and customise)
- `.agents/` — runtime state (created by `otaman init`):
  bus messages, ownership map, agent registry, blocked tasks, queues

Sibling directories (`../frontend`, `../backend`, `../specs`) are the
managed repos. Each gets per-repo configs written by `otaman init`:
`CLAUDE.md`, `.mcp.json`, `.claude/settings.local.json`, `.otaman` marker.

To set this up locally:

```bash
cp launch-settings.yaml.template launch-settings.yaml
# edit launch-settings.yaml to point at your local clone path
otaman init     # generates .agents/ + per-repo configs
otaman doctor   # verify the setup
```
