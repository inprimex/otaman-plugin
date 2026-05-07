# Workflow: Database Migration

## When to use
Any schema change (new table, column change, index, constraint) that may affect multiple services.

## Steps

1. **Check impact**: Read the contracts/specs to understand which services query this table. If multiple services are affected, this is a cross-repo change.

2. **Design migration**: Write the migration (up + down). Ensure it's reversible. For data migrations, plan for zero-downtime (expand-contract pattern):
   - Phase 1: Add new column/table (expand)
   - Phase 2: Dual-write to old and new
   - Phase 3: Migrate existing data
   - Phase 4: Switch reads to new
   - Phase 5: Remove old column/table (contract)

3. **Notify affected agents**: Send `contract-change` to all agents whose repos query the affected tables. Include: what changed, backward-compatible or breaking, migration timeline.

4. **Run migration**: Apply in development/staging first. Verify with integration tests.

5. **Update API contracts**: If the migration changes API response shapes, update OpenAPI specs.

6. **Coordinate rollout**: For breaking changes, coordinate deployment order via bus messages.

## Risks
- Data loss if migration is not reversible
- Downtime if migration locks tables
- Breaking consumers if types change without notification
