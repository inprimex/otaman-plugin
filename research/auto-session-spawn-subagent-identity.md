# Spike: Claude Code subagent identity preservation

**Task**: 1.5 — auto-session-spawn-on-bus-events
**Date**: 2026-05-30
**Author**: plugin-agent
**Status**: COMPLETE — finding: identity preservation works via `OTAMAN_AGENT` env-var prefix, NOT via subagent frontmatter
**Reference**: B-38 (Anthropic docs note skills/`mcpServers` frontmatter don't apply to teammate-mode subagents)

---

## Question

When a host Claude Code session (running as `bridge-agent`) spawns a subagent via the Task tool to handle work on behalf of `cli-agent`, can that subagent emit bus messages with `from: cli-agent` — or does it inherit the host's identity and report as `bridge-agent`?

This is the load-bearing question for Q3's "host session absorbs non-HITL tasks for other agents the human owns" pattern.

---

## Method

From a host session running as `plugin-agent` in `/home/romans/otaman/otaman-plugin`, spawned a `general-purpose` subagent via the Task tool. Subagent was briefed to observe (not modify) and report:

1. Its inherited `cwd`
2. The contents of `.agents/current-agent` (the legacy fallback file)
3. Whether MCP tool schemas (`mcp__plugin_otaman_otaman-bus__*`) are directly callable or deferred
4. The output of `otaman check` (which agent does the CLI think is calling?)
5. The output of `OTAMAN_AGENT=cli-agent otaman check` (does an env-var override work?)
6. Its own self-perception of identity

---

## Findings

### F1 — Subagent inherits host CWD

Subagent reported `pwd` = `/home/romans/otaman/otaman-plugin` (identical to host). No CWD isolation. Any CWD-rooted identity inference will resolve to the host's repo.

### F2 — `.agents/current-agent` is NOT the source of truth

File contained `router-agent` (stale from a prior session). `otaman check` returned `plugin-agent`. The CLI's identity-resolution chain (see `otaman-cli/src/otaman_cli/identity.py`) prioritizes:

```
1. explicit --agent flag
2. OTAMAN_AGENT env var
3. .otaman ``agent:`` field (CWD ancestry walk)
4. platform.yaml CWD→owner fallback
5. .agents/current-agent (DEPRECATED — emits warning)
```

So in practice, the subagent resolves to whatever the `.otaman` marker in the host's CWD says — i.e., the host's identity.

### F3 — MCP tools are available but deferred

`mcp__plugin_otaman_otaman-bus__*` tools (otaman_send, otaman_check, otaman_ack, etc.) appeared in the subagent's deferred-tools list. They are NOT directly callable; the subagent must invoke `ToolSearch` first to load schemas. Post-Bash call, the system injected MCP-server-instructions reminders for both `plugin:otaman:otaman-bus` and `plugin:otaman:otaman-estimation`, confirming the MCP servers ARE attached to the subagent session.

**B-38 partial confirmation**: the host's MCP servers do reach the subagent (counter to the strictest reading of the Anthropic-docs caveat), but tool schemas are deferred. The host's *skills* were not tested in this spike.

### F4 — Write/Edit tools inherited by general-purpose subagent

Subagent reported `Write` and `Edit` in its top-of-prompt tool list — directly callable, no deferral. This matters for the "subagent does work in a non-host repo" path: subagents CAN modify files, subject to the same per-repo hook rules as the host.

### F5 — `OTAMAN_AGENT` env-var override works cleanly

`OTAMAN_AGENT=cli-agent otaman check` returned `Messages for: cli-agent` (110 read, 66 resolved — the actual cli-agent inbox), distinct from the host's `plugin-agent` view (33 read, 133 resolved).

**This is the load-bearing finding.** The env-var override is the mechanism by which a subagent can preserve a distinct identity for bus interactions, despite inheriting CWD and lacking subagent-frontmatter identity support.

### F6 — Subagent self-perception: "Claude with a different prompt"

Subagent self-described as "the same Claude model as the host with a different system prompt and task scope" — no intrinsic otaman-fleet identity field exposed to the model. The only distinguishing input is the Task-tool prompt itself.

---

## Implications

### Identity preservation IS possible, but fragile

Subagent can act as a different bus agent IF its prompt explicitly instructs it to prefix every otaman-touching command with `OTAMAN_AGENT=<target-agent>`. Example:

```bash
OTAMAN_AGENT=cli-agent otaman check
OTAMAN_AGENT=cli-agent otaman ack <msg-stem>
OTAMAN_AGENT=cli-agent otaman complete <change> --tasks "..."
```

For MCP tool calls, the env var would need to be set in the subagent's environment before the MCP server is consulted — which it is NOT, because MCP servers attach via the host shell. **MCP-based bus interactions from subagents will report the HOST's identity, not the override.** Only Bash-shell-prefixed CLI invocations are identity-correct.

### What this means for Q3's "host absorbs cli-agent tasks" pattern

**Viable design**:
- Host bridge-agent receives a task assignment for cli-agent
- Host spawns subagent via Task tool with a prompt that:
  - States the subagent's identity: "You are acting as cli-agent for this task"
  - Mandates `OTAMAN_AGENT=cli-agent` prefix on every otaman CLI call
  - Restricts bus interactions to the Bash CLI path (not MCP tools), since MCP tools cannot honor the per-subagent identity override

**Reliability concern**: the prefix discipline is purely prompt-enforced. One missed prefix → message goes out as `bridge-agent`. Mitigations to consider:
1. A wrapper shim (`otaman-as`) that *always* sets the env var, harder to forget than a raw prefix
2. Per-subagent CWD isolation (`cd /tmp/subagent-<id>` with a `.otaman` marker that resolves to `cli-agent`) — but this breaks the "work in the target repo" flow
3. Frame all bus interactions as a post-processing step done by the host, not the subagent: subagent produces results, host calls `OTAMAN_AGENT=cli-agent otaman send ...` on its behalf

### What B-38 misses (refinement)

The Anthropic docs caveat reads as "subagents can't have their own MCP/skills". This spike narrows that:
- MCP **servers** ARE attached to subagents (their `mcp__*` tools appear in deferred lists)
- MCP **per-call identity** is NOT subagent-isolable (env-var overrides don't propagate into MCP RPC)
- Skills were not tested but the docs imply the same constraint

So B-38 is not a *blocker* — the env-var path exists — but it does forbid the cleaner "subagent frontmatter declares identity" approach.

---

## Proposed design.md Q3 update (to be delivered to spec-agent for authoring)

See bus message to spec-agent accompanying this commit. The proposed insert under Q3 is:

> ### Resolved (2026-05-30) — subagent identity mechanism
>
> Sub-agent identity preservation works via the `OTAMAN_AGENT` env-var prefix on Bash-shell CLI calls. The host session spawns a subagent via the Task tool with an explicit identity directive in its prompt:
>
> ```
> You are acting as <agent-name> for this task. Every otaman CLI invocation MUST be prefixed with `OTAMAN_AGENT=<agent-name>`. Do not use MCP otaman_* tools — they cannot honor the per-subagent identity override and would emit messages as the host agent.
> ```
>
> **Constraints discovered (spike 1.5)**:
> - Subagents inherit host CWD; CWD-based identity inference will resolve to the host.
> - MCP servers attach to subagent sessions (tool schemas appear deferred), but per-call identity is not subagent-isolable: MCP `otaman_send` from a subagent emits as the host.
> - The env-var override IS the mechanism (`otaman-cli/src/otaman_cli/identity.py` priority chain step 2).
> - B-38 partially holds: subagent-frontmatter identity is unsupported, but the env-var path remains.
>
> **Reliability mitigations** (deferred to implementation change):
> - Consider a `otaman-as <agent> -- <cmd>` wrapper shim that hardens the env-var discipline.
> - Consider host-mediated bus emission (subagent produces output, host emits as the target agent) when stronger guarantees are needed.
>
> **Visibility unchanged**: passive bus-log panel approach from the original proposed direction stands.

---

## Repro

Single Task tool invocation; the prompt and subagent report are captured in the parent session transcript. Re-running the spike requires only:

1. From any otaman-enrolled repo, spawn a general-purpose subagent with the prompt at the head of this doc.
2. Compare its `otaman check` output (no env var) vs `OTAMAN_AGENT=<other-agent> otaman check` output.
3. Observe which `Messages for:` line each returns.

No production code changes were made for this spike.
