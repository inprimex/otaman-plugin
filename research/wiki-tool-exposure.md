# Wiki Tool Exposure — Agent-Facing Query Interface Design

> **Task**: 2.3 from `architecture-dependency-graph` tasks.md  
> **Date**: 2026-05-27  
> **Author**: plugin-agent  
> **Scope**: `@otaman-plugin` — the design of the MCP tool surface + CLI facade for the project-knowledge wiki query layer. Feeds `design.md` Q5 in `otaman-specs/openspec/changes/architecture-dependency-graph/`.  
> **Reference**: `research/codegraph-comparison-2026-05-23.md` (codegraph prior art, Q5 callout in §4 item 6 + §7)

---

## 1. Decision: MCP server (primary) + CLI facade (secondary)

**MCP server is the primary exposure surface.** CLI (`otaman wiki query ...`) is the secondary surface for humans and shell scripts; both delegate to the same query engine.

### Rationale for MCP-first

1. **Native Claude Code integration.** Claude Code agents invoke tools via MCP; the auto-session-spawn mechanism declares `mcpServers:` in agent definitions. MCP is the zero-friction path.
2. **codegraph benchmark evidence.** codegraph's MCP surface delivers **~35% cheaper, ~70% fewer tool calls, ~59% fewer tokens** vs agents using grep/read directly — on 7 real OSS codebases. These are the strongest published numbers for the "tool-for-context, not reasoning" thesis. An MCP interface is how we capture the same gains.
3. **Token-cost discipline is expressible in tool descriptions.** MCP tool descriptions are injected into the model's system prompt. Well-written descriptions steer the model to the right access pattern and away from token-burning anti-patterns (e.g., spawning grep loops in the main session). A CLI tool can't do this.
4. **Session scope.** MCP tools are available per-session, not globally. An agent session without the wiki MCP server declared simply doesn't see the wiki tools — no overhead in sessions that don't need the wiki.

### Rationale for CLI facade

- Humans want `otaman wiki query "what calls PaymentProcessor?"` in their terminal.
- Shell scripts, CI pipelines, and the `otaman doctor` / `otaman check` commands need programmatic query access.
- CLI is a thin wrapper: `otaman wiki query <pattern>` → validates args → calls the same query engine → prints the structured result.

### What this is NOT

- A unified HTTP API exposed externally. The wiki server is **100% local** (Mode 1); it binds to a local socket, not a network port. Same privacy story as codegraph.
- A replacement for filesystem access. Agents can still read entity markdown files directly via the `Read` tool. The MCP tools provide higher-level, pre-indexed queries — they complement, not replace, direct file reads.

---

## 2. Tool count and shape — 8 tools in three layers

Following codegraph's discipline: **separate tools per concern, tight descriptions that guide the agent to the right tool.** codegraph ships 9 tools; we ship 8 at v0.

### Layer A — Markdown-direct (3 tools)

These tools hit the markdown files directly. No derived index needed. Instant when the wiki directory is present; degrade gracefully if the index hasn't been built.

| Tool | Purpose | When to use |
|------|---------|-------------|
| `otaman_wiki_entity` | Read one entity file by id or name; returns frontmatter + body | You know which entity you want. Cheapest single-entity read. |
| `otaman_wiki_list` | List entities matching a filter (lens, kind, status, tag) | Browse a slice of the wiki: "list all Container-kind entities in the c4 lens" |
| `otaman_wiki_search_text` | Full-text search across entity files (FTS5 or grep-backed) | You know a keyword but not the entity id; returns ranked matches with snippet context |

**Description discipline example for `otaman_wiki_entity`:**
```
Read one wiki entity by id or name. Returns frontmatter + full body.
Use this FIRST when you already know which entity you want. Do NOT use
otaman_wiki_list or otaman_wiki_search_text to discover the entity first
if you already have its id — those are more expensive. Do NOT read
.otaman/wiki/ files directly unless the MCP server is unavailable.
```

### Layer B — Structured graph queries (3 tools)

These tools hit the derived SQLite index. They return bounded, deterministic results.

| Tool | Purpose | When to use |
|------|---------|-------------|
| `otaman_wiki_depends_on` | Direct + transitive dependencies of an entity; optional depth limit | "What does X import, call, or contain?" Impact-scope before a change. |
| `otaman_wiki_depended_by` | Reverse: what depends on entity X (callers, importers, containing parents) | "What would be affected if X changes?" — the `impact-of-change` query. |
| `otaman_wiki_coverage_of` | Given an outcome / flow / spec id, list the code-unit entities that implement it | Gap analysis: "Is outcome OUT-7 covered? Which components implement FLOW-3?" |

**Description discipline example for `otaman_wiki_depends_on`:**
```
Get dependencies of a wiki entity: which entities this entity imports, calls,
or contains. Returns up to `depth` hops (default 1, max 3). Use for:
understanding scope of a dependency chain; pre-change impact analysis.
Do NOT use for reverse lookups (callers/importers) — use otaman_wiki_depended_by.
Do NOT use for semantic / NL queries — use otaman_wiki_search_semantic.
IMPORTANT: Do NOT call this with depth > 2 in the main session; spawn an
Explore subagent for wide transitive-closure queries on large graphs.
```

### Layer C — Semantic search (1 tool)

| Tool | Purpose | When to use |
|------|---------|-------------|
| `otaman_wiki_search_semantic` | NL query against the vector index; returns top-K entity ids with relevance scores | Exploratory queries when entity name is unknown: "find code related to authentication", "what handles payment retries?" |

**Description discipline example:**
```
Semantic (NL) search across all wiki entities using vector similarity.
Use when you do NOT know the entity id and a keyword search would miss
related but differently-named entities. Returns top-K ids + snippets.
Caution: requires the vector index to be built (check otaman_wiki_status
first). If the vector index is absent, fall back to otaman_wiki_search_text.
Do NOT use for deterministic graph traversal — use otaman_wiki_depends_on.
```

### Meta (1 tool)

| Tool | Purpose | When to use |
|------|---------|-------------|
| `otaman_wiki_status` | Index freshness: entity count, last ingest timestamp, index staleness, vector index presence | Use at session-start to verify wiki is populated before issuing queries. If index_age_minutes > 60, note that results may be stale. |

---

## 3. Why 8 tools and not N alternatives

### Why not one unified mega-tool?

A single `otaman_wiki_query(mode: "entity|list|text|depends_on|depended_by|coverage_of|semantic|status", ...)` tool:
- Has a description 4× longer → higher prompt-repr token cost (loaded at every session with the wiki MCP server active)
- Cannot guide the model to the right mode without an elaborate decision tree in the description
- Prevents prompt-caching optimization (the one-tool description changes when modes are added)

Separate tools: each description is ~50–80 tokens, tightly scoped. The model picks the right one. Total prompt cost for all 8: ~400–640 tokens — similar to codegraph's 9-tool surface.

### Why not just Read + Grep?

Agents can already use `Read` + `Grep` against `.otaman/wiki/`. These are correct for ad-hoc exploration. But:
- Multi-hop graph traversal via grep is O(edges²) tool calls — exactly the anti-pattern codegraph's benchmarks document
- FTS5 and vector search are not expressible via grep
- `otaman_wiki_depended_by` traverses a pre-built index in one round-trip; an equivalent grep would require following every wikilink in every file

### Why not a CLI-only tool exposed via Bash?

Bash tool calls (e.g., `otaman wiki depends-on auth-service`) are allowed by Claude Code. But:
- Every call forks a subprocess with Python startup overhead (~200–400ms per call)
- The result is unstructured text that the model must re-parse
- MCP tools return structured JSON, directly consumable by the model's context
- MCP tools appear in the model's function-call surface with typed schemas — lower error rate than string-parsed CLI

The CLI facade exists for humans; agents use MCP.

---

## 4. MCP server architecture

### Server identity

Server name: `otaman-wiki`  
Registered in: `otaman-plugin/servers/wiki_server.py` (new file, not implemented in v0)  
Declared by: agent definitions that need wiki access — in their `tools:` + `mcpServers:` frontmatter  

Example agent definition frontmatter:
```yaml
name: otaman-cto-reviewer
model: sonnet
tools:
  - Read
  - Glob
  - Grep
  - Bash
mcpServers:
  - otaman-bus        # existing
  - otaman-wiki       # new — only present when knowledge_wiki: enabled in platform.yaml
```

### Conditional availability

The wiki MCP server is present in a session **only when**:

1. `platform.yaml` declares `knowledge_wiki: enabled` (or the wiki has been initialized via `otaman wiki init`)
2. The agent definition includes `otaman-wiki` in `mcpServers:`

When either condition is absent, the tools are not visible to the model. **Zero prompt-repr cost for sessions that don't use the wiki.**

This is the correct integration with the skill-profile system: the wiki MCP tools are **infrastructure**, not skills. They are declared per-agent (in agent definitions), not per-project-profile (in YAML profiles). The distinction:

| Layer | Managed by | Token surface |
|-------|-----------|---------------|
| Skill (description at spawn) | `profiles/` + `platform.yaml skills:` | Prompt-repr, loaded once at session-spawn |
| MCP tool (schema at spawn) | Agent definition `mcpServers:` | Tool-schema tokens, per agent definition |

Agents that don't need the wiki (e.g., `otaman-debug-model-agent`) don't declare the server and incur no cost.

### Server process lifecycle

Mode 1 (local, per-project):
- The wiki server is a lightweight Python process binding to a Unix domain socket (e.g., `.otaman/wiki-server.sock`)
- Started lazily by `otaman-bridge` when the first agent that needs it is spawned
- Shut down when the last agent session using it exits (or on bridge shutdown)
- **No network exposure.** Socket is in the project's `.otaman/` directory, gitignored

Mode 2+ (remote, multi-project):
- Follows ADR-005 storage tier split — the wiki server becomes a sidecar to the bridge daemon
- Socket or loopback HTTP; implementation detail for Mode 2 change

---

## 5. Coordination with auto-session-spawn

### Tool-availability at spawn time

The auto-session-spawn mechanism (bridge-agent owns the spawn decision per design.md Q1) needs to know which MCP servers to start before spawning an agent. Current state: the bridge reads agent definitions to find `mcpServers:` declarations.

**Required extension for wiki support** (small, backward-compatible):

The bridge's spawn path currently starts `otaman-bus` + `otaman-estimation` servers. With wiki support added:

```python
# bridge spawn logic (pseudocode)
agent_def = load_agent_definition(agent_name)
required_servers = agent_def.mcp_servers  # ["otaman-bus", "otaman-wiki", ...]

for server_name in required_servers:
    if server_name == "otaman-wiki":
        # wiki server is conditional — only start if wiki is enabled
        if platform_config.knowledge_wiki_enabled and not wiki_server_running():
            start_wiki_server(project_root)
    else:
        ensure_server_running(server_name)
```

**No changes to the auto-session-spawn spec are needed** — the conditional-server pattern is already implied by the bridge's role as spawn-decision owner. This is documentation of the expected behavior, not a new mechanism.

### Headless vs interactive modes

Wiki query tools work in **both** `[headless]` and `[interactive]` modes:
- `[headless]` tasks (e.g., nightly lint, coverage gap reporting) use `otaman_wiki_coverage_of` + `otaman_wiki_list` to produce structured reports without human interaction
- `[interactive]` tasks use any tool as part of a back-and-forth session

The tool surface doesn't need to distinguish mode — the agent invocation context handles it.

### HITL and write-scope

Wiki MCP tools are **read-only for query operations.** No wiki-query tool writes to the wiki or triggers ingest. Write access to the wiki is owned by the LLM ingest pipeline (a separate scheduled operation, not an MCP tool). This separation:
- Prevents query tools from accidentally modifying the wiki during a session
- Makes HITL policies simpler: all wiki writes go through the ingest pipeline + dirty-tracking + commit batching (per Q7)

---

## 6. Description discipline — implementation rules

Codegraph's key finding (per research §4 item 6): tool descriptions should explicitly steer agent behavior. Rules for all `otaman_wiki_*` tool descriptions:

**Rule W-1: Primary use-case first.**  
The first sentence states exactly what the tool does and the primary situation to use it. Model description scanners weight first sentences most.

**Rule W-2: Explicit "Use for" list.**  
2–3 bullet points or inline list of `Use for: X, Y, Z` — makes routing deterministic.

**Rule W-3: Explicit "Do NOT use" guards.**  
For the two most common misrouting mistakes per tool, add: `Do NOT use for <mistake> — use <correct-tool> instead.`

**Rule W-4: Main-session subagent guard for expensive operations.**  
Any tool whose result set could be large (deep transitive closure, full semantic index scan) includes: `IMPORTANT: Do NOT call with depth > N in the main session; spawn an Explore subagent.` (Mirrors codegraph's `explore` tool description verbatim.)

**Rule W-5: Fallback instructions.**  
If the tool requires a derived index and the index may be absent, the description tells the model what to do: `If wiki_index_present is false in otaman_wiki_status, use otaman_wiki_search_text as fallback.`

**Rule W-6: Keep descriptions ≤ 80 tokens.**  
The 8 tools' prompt-repr cost target: ≤ 80 tokens/tool = ≤ 640 tokens total for the full wiki MCP surface. This is the same order of magnitude as the full skill profile prompt-repr (795 tokens for software-development-default). Total session-spawn overhead with wiki active: ~1,435 tokens — still well within the 4K-token practical budget for context setup.

---

## 7. Token cost summary

| Surface | Tokens (est.) | Condition |
|---------|-------------|-----------|
| 8 wiki MCP tool schemas (all descriptions + param schemas) | ~640 tokens | When agent definition includes `otaman-wiki` |
| wiki-enabled platform overhead (none) | 0 | wiki availability is per-agent-def, not global |
| wiki MCP tool schemas for agents that don't use wiki | 0 | Server not declared → not loaded |
| **Total per wiki-enabled agent session** | ~640 tokens | On top of existing session overhead |

This is acceptable: a `otaman-cto-reviewer` session with wiki access pays ~640 tokens for 8 tool schemas — comparable to 7 skill prompt-repr entries (~637 tokens for the software-development-default's non-cto-advisor items). The payoff is potentially thousands of tokens saved per query (vs grep-loop alternatives).

---

## 8. Open questions for the implementation change

1. **`otaman_wiki_coverage_of` scope**: should it accept an outcome-id, flow-id, or spec-section-id as the input entity? All three are natural inputs. v0 recommendation: accept any wiki entity-id — the entity-file type determines the traversal direction (outcome → solution → code-unit, flow → component, spec-section → code-unit). The tool description states accepted input kinds explicitly.

2. **`otaman_wiki_search_text` vs FTS5 vs grep**: in v0 (before the derived index is built), the search falls back to grep against the wiki directory. This is acceptable for v0 performance targets (< 1000 entities). FTS5 index should be built alongside the structured graph index in `project-knowledge-wiki-query-v0`.

3. **Streaming vs batch returns**: `otaman_wiki_depends_on` at depth > 1 can return large result sets. Prefer: return a list of entity-ids with edge labels; let the agent call `otaman_wiki_entity` for the ones it needs. This caps per-call token cost. The description should state: "Returns ids + edge labels only; call `otaman_wiki_entity` for full content."

4. **Schema versioning**: when a new lens adds new edge types or entity kinds, `otaman_wiki_depends_on` / `otaman_wiki_depended_by` should accept optional `edge_type` filter. Add as an optional parameter in v0 even if only C4 edges exist — prevents a breaking schema change when the clinical-pathway or value-stream lens is added.

5. **Cross-repo queries in a polyrepo**: entity ids are globally unique (namespaced by repo-slug per the entity spec). In a polyrepo, `otaman_wiki_depends_on` traverses across repo boundaries naturally if the derived index is built from a union of all repos' wiki directories. This is a Mode 1 behavior that doesn't require a spec change — document in the implementation hints.

---

## 9. Output: design.md Q5 update

The following text is the expanded Q5 for `architecture-dependency-graph/design.md`. It replaces the current Q5 section in full (the current text stays as the direction statement; this adds the implementation detail resolved by task 2.3).

> **See section 10 below for the exact Q5 replacement text**, ready to apply to `otaman-specs`.

---

## 10. Q5 replacement text — for `design.md`

```markdown
## Q5 — Query interface: markdown-direct, structured, semantic, or all three?

**Question**: How do agents and humans query the wiki?

- (a) **Markdown-direct**: read entity files via filesystem + grep
- (b) **Structured**: derived graph index, deterministic queries (`depends-on`, `coverage-of`, ...)
- (c) **Semantic**: vector store, NL queries
- (d) **All three**

**Proposed direction**: **(d) all three, each at a different layer**. Rationale:
- (a) is the cheapest access pattern — no index needed, just filesystem ops. Suited for "read me entity X" queries.
- (b) is needed for impact-analysis and coverage queries that traverse multiple hops. Bounded result size; deterministic; auditable.
- (c) is needed for fuzzy / exploratory queries when the agent doesn't know which entity to ask about by name.

All three access patterns are equally first-class. Agents pick the right tool for the query. No single interface is "the canonical" — they're complementary.

**Alternatives considered**:
- *(a) only*: misses bounded-traversal + semantic search.
- *(b) only*: misses cheap access + semantic search.
- *(c) only*: misses determinism for impact queries.

**NL-to-structured-query wrapper**: optional, can be added in a future change. For v0, the three layers are exposed separately; agents that need NL-over-structured can compose them themselves (vector search → entity ids → structured query).

---

### Q5.1 — Tool exposure mechanism: MCP server (primary) + CLI facade (secondary)

**Resolved (2026-05-27) — plugin-agent task 2.3**. Reference: `otaman-plugin/research/wiki-tool-exposure.md`.

The wiki query surface is exposed as an **MCP server** named `otaman-wiki`, backed by a CLI facade (`otaman wiki query ...`) that shares the same query engine.

**MCP is primary** for agent-facing queries:
- Native to Claude Code's tool-calling model; agent definitions declare `mcpServers: [otaman-wiki]`
- codegraph benchmark evidence: MCP-backed graph tools deliver ~35% cheaper, ~70% fewer tool-calls vs. grep/read loops on the same query tasks
- Tool descriptions inject steering text into the session prompt — they can guide the model to the correct access pattern and away from expensive anti-patterns (grep loops, wide transitive-closure in main session)

**CLI is secondary** for humans and shell scripts: `otaman wiki query "what calls PaymentProcessor?"` → delegates to the same engine, returns structured output.

**Conditional activation**: the wiki MCP server is present in a session **only when**:
1. `platform.yaml` declares `knowledge_wiki: enabled` (or `otaman wiki init` has been run)
2. The agent definition includes `otaman-wiki` in `mcpServers:`

Agents that don't need wiki access incur zero prompt-repr overhead. Tool schemas are per-agent, not global.

**Server lifecycle**: Mode 1 — a lightweight local process bound to a Unix domain socket in `.otaman/`. Started lazily by `otaman-bridge` when the first wiki-enabled agent session is spawned; shut down when the last such session exits.

---

### Q5.2 — Tool set: 8 tools in three layers

**All tools are read-only for query operations.** Wiki writes go through the ingest pipeline (Q4/Q7), not through query tools.

#### Layer A — Markdown-direct (3 tools)

No derived index required. Degrades gracefully when index is absent.

| Tool | One-line purpose |
|------|-----------------|
| `otaman_wiki_entity` | Read one entity file by id or name (frontmatter + body) |
| `otaman_wiki_list` | List entities matching a filter (lens, kind, status, tag) |
| `otaman_wiki_search_text` | Full-text search across entity files (FTS5 or grep-backed) |

#### Layer B — Structured graph queries (3 tools)

Requires derived SQLite index. Deterministic, bounded results.

| Tool | One-line purpose |
|------|-----------------|
| `otaman_wiki_depends_on` | Direct + transitive dependencies of an entity (depth-limited) |
| `otaman_wiki_depended_by` | Reverse: what depends on entity X (callers, importers, parents) |
| `otaman_wiki_coverage_of` | Given an outcome/flow/spec id, list implementing code-unit entities |

#### Layer C — Semantic search (1 tool)

Requires vector index. Falls back to `otaman_wiki_search_text` if vector index absent.

| Tool | One-line purpose |
|------|-----------------|
| `otaman_wiki_search_semantic` | NL query against vector index; returns top-K entity ids + scores |

#### Meta (1 tool)

| Tool | One-line purpose |
|------|-----------------|
| `otaman_wiki_status` | Index freshness: entity count, last ingest timestamp, index age, vector-index presence |

**Token cost of 8-tool surface**: ~640 tokens for all tool schemas (descriptions + parameter schemas), per session that has the wiki server active. This is the same order of magnitude as a 7-item skill profile prompt-repr.

---

### Q5.3 — Tool description discipline (anti-token-burn rules)

Derived from codegraph's tool-design patterns (codegraph ships 9 tools; their descriptions explicitly steer agents away from expensive call patterns). All `otaman_wiki_*` tool descriptions MUST follow these rules:

**W-1: Primary use-case first.** First sentence states exactly what the tool does and the primary situation to use it.

**W-2: Explicit "Use for" list.** 2–3 inline items: `Use for: X, Y, Z.`

**W-3: Explicit "Do NOT use" guards.** For the two most common misrouting mistakes: `Do NOT use for <mistake> — use <correct-tool> instead.`

**W-4: Main-session subagent guard.** For operations whose result set can be large: `IMPORTANT: Do NOT call with depth > 2 in the main session; spawn an Explore subagent for wide transitive-closure queries.`

**W-5: Fallback instructions.** If the tool requires a derived index that may be absent: `If wiki index is absent (check otaman_wiki_status), fall back to otaman_wiki_search_text.`

**W-6: ≤ 80 tokens per description.** Hard cap. The combined 8-tool prompt-repr budget is 640 tokens.

---

### Q5.4 — Auto-session-spawn coordination

`otaman-bridge` (spawn-decision owner per Q1) extends its server-start logic as follows:

```
for each server_name in agent_definition.mcp_servers:
  if server_name == "otaman-wiki":
    if platform_config.knowledge_wiki_enabled:
      ensure_wiki_server_running(project_root)
    # else: skip — wiki disabled, agent spawns without wiki tools
  else:
    ensure_server_running(server_name)
```

No changes to the auto-session-spawn spec are needed. This is an additive extension to the bridge's existing server-management logic.

The `[headless]` / `[interactive]` task classification (Q2) does not affect tool availability — wiki tools work in both modes.

---

### Q5.5 — Open questions for implementation change `project-knowledge-wiki-query-v0`

1. `otaman_wiki_coverage_of` input kinds: accept any wiki entity-id; entity type determines traversal direction. State accepted input kinds in the description.
2. `otaman_wiki_depends_on` depth > 1: return entity-ids + edge labels only; caller invokes `otaman_wiki_entity` for full content. Cap per-call token cost.
3. `otaman_wiki_search_text` v0 fallback: FTS5 not yet built → grep against wiki directory. Acceptable for < 1,000 entities.
4. Optional `edge_type` filter on graph tools: add as optional parameter in v0 even if only C4 edges exist — prevents breaking schema change when non-C4 lenses arrive.
5. Cross-repo polyrepo queries: entity ids are globally namespaced (repo-slug prefix). The derived index built from union of all repos' wiki directories supports cross-repo traversal naturally. Document in implementation hints; no spec change needed.
```
