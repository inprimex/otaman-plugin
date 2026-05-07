---
name: doctor
description: "Validate environment readiness — git platform, runtimes, CLI tools, MCP dependencies"
model: haiku
effort: low
arguments: []
---

# /otaman:doctor

Check if the development environment is ready for agent work.

## What it checks

1. **Git identity** — user.name and user.email configured
2. **Git platform** — GitHub/GitLab/Bitbucket CLI installed and authenticated (for PR creation)
3. **Runtimes** — Node.js, Python, .NET, etc. based on repo tech stacks
4. **Claude CLI** — installed and accessible
5. **SSH keys** — available for git push (if repos use SSH remotes)
6. **MCP dependencies** — FastMCP, PyYAML installed for bus server
7. **Otaman setup** — .agents/, ownership.json, .mcp.json in repos

## Steps

1. **Run the doctor script**:
   ```bash
   py "${CLAUDE_PLUGIN_ROOT}/scripts/doctor.py" "<project-root>"
   ```

2. **Present results** using the UI system:
   - Group by check (git, runtimes, CLI tools)
   - Show pass/warn/fail status for each
   - For failures: show the issue and the fix command
   - Sort issues by severity (critical first)

3. **Offer to auto-fix** what's possible:
   - Git config: can set directly
   - Missing .mcp.json: re-run otaman init
   - Other fixes: show commands for user to run

## When to run

- After `otaman init` (runs automatically)
- After installing new tools
- When onboarding a new developer
- When moving to a new machine/server
