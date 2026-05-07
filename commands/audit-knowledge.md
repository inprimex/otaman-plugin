---
name: audit-knowledge
description: "Audit Claude's knowledge of the project's tech stack — identify gaps before development"
model: sonnet
effort: medium
arguments:
  - name: source
    description: "Source of tech stack: 'auto' (from platform.yaml/presale), or comma-separated list"
    required: false
---

# /otaman:audit-knowledge

Assess Claude's knowledge confidence for each technology in the project's tech stack. Identifies gaps that need documentation before development starts.

## Steps

### Step 0: Gather tech stack

Determine what technologies to audit:

1. If `.otaman-presale/project-meta.yaml` exists → read `tech_stack` field
2. If `platform.yaml` exists → read `repos[].tech` arrays + `standards.repo_standards` for frameworks
3. If `<source>` argument provided as comma-separated list → use that
4. If nothing found → ask the user to list the key technologies

Deduplicate and compile a flat list. Include: frameworks, libraries, major integrations, infrastructure tools, and any technology where Claude will need to write implementation code.

### Step 1: Self-assessment

For each technology in the list, assess your knowledge across these dimensions (score 0-4):

- **Core API**: Can you write a complete, working configuration from memory? (0=never seen, 4=deep knowledge)
- **Version awareness**: Do you know the latest major version and its breaking changes? (0=no idea, 4=specific version knowledge)
- **Integration patterns**: Can you write auth/data/API integration code without docs? (0=would hallucinate, 4=production-quality)
- **Edge cases**: Do you know common pitfalls and their solutions? (0=none, 4=comprehensive)

**Scoring guide**:
- 0 = Never seen this / would hallucinate API calls
- 1 = Heard of it, know the concept, need docs for any real code
- 2 = Can write basic code, uncertain about advanced patterns or recent versions
- 3 = Solid knowledge, may miss latest version changes
- 4 = Deep knowledge, confident in production-quality code

**Overall confidence per technology**:
- Average of 4 dimensions: 0-1 = `none`, 1-2 = `low`, 2-3 = `medium`, 3-4 = `high`

### Step 2: Generate gap report

Write the report to `.otaman-presale/knowledge-audit.yaml` (or `.agents/knowledge-audit.yaml` if in development phase):

```yaml
audit_date: 2026-03-27
overall_readiness: 72%

items:
  - tech: nextjs-14
    confidence: high
    dimensions:
      core_api: 4
      version_awareness: 3
      integration_patterns: 4
      edge_cases: 3
    gaps: []
    action: none

  - tech: payload-cms-3
    confidence: low
    dimensions:
      core_api: 1
      version_awareness: 1
      integration_patterns: 1
      edge_cases: 0
    gaps:
      - "v3 config format (migrated from Express to Next.js)"
      - "Collection hook lifecycle specifics"
      - "Custom endpoint patterns"
    action: needs_docs
    suggested_sources:
      - "https://payloadcms.com/docs"
```

### Step 3: Present results

Show a dashboard:

```
Knowledge Readiness: 72%

  ✅ nextjs-14          high   (ready)
  ✅ typescript          high   (ready)
  ⚠️  refine-core        medium (examples recommended)
  ❌ payload-cms-3      low    (docs needed)
  ❌ eclinicalworks-api none   (BLOCKED — cannot proceed without docs)

Action required for 2 items before development:
1. payload-cms-3: Provide official docs → .agents/knowledge/payload-cms-3/
2. eclinicalworks-api: Provide full API docs → .agents/knowledge/eclinicalworks-api/
```

### Step 4: Attempt revlet.ai (future)

If a revlet.ai MCP server is available, attempt to auto-fetch knowledge packs for items with `needs_docs` or `needs_examples` action:

```
Checking revlet.ai for knowledge packs...
  ✅ payload-cms@3.0 — pack available, installing to .agents/knowledge/
  ❌ eclinicalworks-api — no pack available (manual docs required)
```

If revlet.ai is not available, skip this step silently.

### Step 5: Update platform.yaml knowledge section

If `platform.yaml` exists, suggest adding a `knowledge` section:

```yaml
knowledge:
  - pack: payload-cms@3.0
    status: needs_docs
  - pack: eclinicalworks-api
    path: .agents/knowledge/eclinicalworks-api/
    status: needs_full_docs
```

### Step 6: Soft blocks in generated CLAUDE.md

For technologies with `none` or `low` confidence, the generated CLAUDE.md (via `/otaman:init`) will include:

```markdown
### Knowledge Gaps (CRITICAL)
⚠️ The following technologies have LOW or NO knowledge confidence.
**DO NOT write implementation code for these without reading the docs first.**

- **payload-cms-3**: Read .agents/knowledge/payload-cms-3/ before any CMS code
- **eclinicalworks-api**: Read .agents/knowledge/eclinicalworks-api/ before ANY API call

If docs are not available in .agents/knowledge/, STOP and inform the human.
```

## Notes

- Run this BEFORE `/otaman:init` or `/otaman:handoff` so the knowledge gaps are captured in generated configs
- The audit is a point-in-time assessment — re-run after providing docs to update readiness scores
- Technologies with `high` confidence still benefit from version-specific docs if available
- The knowledge audit feeds into `/otaman:status` readiness dashboard
