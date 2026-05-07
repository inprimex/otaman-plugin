---
name: reverse-doc
description: "Generate architecture documentation from existing code — C4 diagrams, component inventory, dependency map"
model: sonnet
effort: medium
arguments:
  - name: scope
    description: "Scope: 'all' (full project), or a specific repo name"
    required: false
---

# /otaman:reverse-doc

Generate architecture documentation by analyzing existing code. Useful for brownfield adoption — when inheriting a codebase that lacks documentation.

## Steps

### Step 0: Find project context

Read `platform.yaml` to understand repos, owners, and tech stacks. If not found, scan the current directory.

### Step 1: Component Inventory

For each repo (or the specified repo):

1. **Read key config files**: package.json, tsconfig.json, Dockerfile, docker-compose.yml, platform.yaml
2. **Scan source structure**: List top-level directories under src/ or app/. Each is likely a module/component.
3. **Identify entry points**: Main files, route definitions, API endpoints
4. **Detect patterns**: Look for common architecture patterns:
   - Directory named `controllers/`, `routes/`, `handlers/` → REST API layer
   - Directory named `services/`, `usecases/` → Business logic layer
   - Directory named `repositories/`, `models/`, `entities/` → Data access layer
   - Directory named `middleware/`, `guards/`, `interceptors/` → Cross-cutting concerns
   - `events/`, `subscribers/`, `listeners/` → Event-driven patterns
   - `jobs/`, `workers/`, `queues/` → Background processing

Write to `.agents/docs/component-inventory.md`:

```markdown
# Component Inventory

## repo-api (backend-agent)
- **Type**: REST API (NestJS)
- **Entry**: src/main.ts
- **Modules**: auth, users, orders, payments, notifications
- **Patterns**: DDD (entities/repositories), CQRS (commands/queries)
- **External deps**: PostgreSQL, Redis, Stripe, SendGrid
```

### Step 2: C4 Context Diagram

Generate a C4 Context diagram showing:
- The system boundary
- External actors (users, admins, third-party services)
- External systems (databases, APIs, cloud services)

Write as Mermaid in `.agents/docs/c4-context.md`.

### Step 3: C4 Container Diagram

Generate a C4 Container diagram showing:
- Each repo as a container
- Communication between containers (HTTP, events, shared DB)
- External services

Write as Mermaid in `.agents/docs/c4-container.md`.

### Step 4: Dependency Map

For each repo, identify:
- Internal dependencies (which repos call which)
- External dependencies (npm packages, Python packages, cloud services)
- Shared types or contracts

Write to `.agents/docs/dependency-map.md`.

### Step 5: Identified Gaps

List what's missing or unclear:
- Repos without tests
- Missing API documentation
- No error handling strategy visible
- No logging/monitoring setup
- Missing security measures

Write to `.agents/docs/architecture-gaps.md`.

## Output

All files go to `.agents/docs/`. This provides a starting point for the team to refine and maintain.

## Notes

- This is best-effort analysis — it reads code structure, not runtime behavior
- Generated docs should be reviewed and refined by the team
- For brownfield projects, run this before `/otaman:init` to understand the landscape
- The SA agent can use these docs during estimation for existing codebases
