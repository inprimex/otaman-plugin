---
name: retrospective
description: "Post-project retrospective — captures estimation accuracy, lessons learned, updates benchmarks"
model: sonnet
effort: medium
arguments:
  - name: project-code
    description: "Project reference code (reads from .otaman-presale/project-meta.yaml if not provided)"
    required: false
---

# /otaman:retrospective

Run a post-project retrospective that captures estimation accuracy and feeds the learning loop.

## Steps

### Step 0: Find project context

Look for `.otaman-presale/project-meta.yaml` by walking up directories. If found, read it for project code, domain, estimation data.

If not found and no `<project-code>` argument provided, ask the user for the project reference code.

### Step 1: Gather actual data

Use the AskUserQuestion tool to collect:

1. **Actual total hours**: How many hours did the project actually take?
2. **Actual duration**: How many months from kickoff to delivery?
3. **Actual team composition**: Who worked on it? (e.g., "2 backend, 1 frontend, 0.5 devops, 1 QA")
4. **What was underestimated?**: Which components/areas took longer than expected? By how much?
5. **What was overestimated?**: Which components/areas took less time? By how much?
6. **Key factors**: What were the main drivers of variance? (list 3-5 items)
7. **Surprises**: Anything unexpected that significantly affected the project?

### Step 2: Calculate accuracy

If estimation data exists in project-meta.yaml:
- Read `estimation.total_range_hours` → [min, max]
- Midpoint = (min + max) / 2
- Accuracy = (actual - midpoint) / midpoint × 100%
- Report: "Estimated {min}-{max}h (midpoint {mid}h), actual {actual}h → {accuracy}% variance"

If no prior estimation data, skip this step and just record the actuals.

### Step 3: Save benchmark

**First, make this direct tool call** (one call, no subagent, no Grep/Read/Bash — `ToolSearch` is a built-in tool you invoke the same way as `Read`):
- Tool: `ToolSearch`
- `query`: `select:add_benchmark,save_knowledge_item,update_project_phase`
- `max_results`: `3`

Then use `add_benchmark` to save the retrospective data:

```
add_benchmark(
  code=<project-code>,
  domain=<domain>,
  project_type=<type>,
  complexity_score=<from project-meta>,
  tier_used=<from project-meta>,
  estimated_range=<from project-meta>,
  actual_hours=<actual>,
  team=<team list>,
  duration_months=<actual>,
  key_factors=<factors list>,
  tags=<relevant tags>
)
```

### Step 4: Extract reusable patterns

Review the retrospective findings for reusable knowledge:

- **Component estimates that differ significantly from library**: If actual hours for a component type (e.g., "FHIR integration") differ by >30% from component-library.yaml, suggest updating the library.
- **Domain-specific adjustment factors**: If domain-related overhead was consistent (e.g., "HIPAA compliance added 22%"), suggest adding to benchmarks adjustment_factors.
- **Common underestimates/overestimates**: If a pattern emerges (e.g., "data migration always 2.5x"), suggest adding to common_underestimates.

Present each suggestion to the user for approval before saving.

Use `save_knowledge_item` MCP tool for approved items with:
- `item_type`: "learning" or "estimation"
- `confidence`: "high" (these are actual vs estimated data)
- `destination`: "benchmarks"

### Step 5: Update project phase

If project-meta.yaml exists, use `update_project_phase` MCP tool to mark the project as "archived" with notes summarizing the retrospective findings.

### Step 6: Summary

Present:
- Project code and domain
- Estimation accuracy (if available)
- Top 3 lessons learned
- Number of items saved to benchmarks
- Reminder: "These benchmarks will improve future estimations via the `search_benchmarks` MCP tool"

## Notes

- Retrospectives should be run as soon as possible after project completion while memory is fresh.
- The benchmark data is stored in `assets/estimation-benchmarks.yaml` and accessible to all future SA agent sessions.
- Even projects without a formal pre-sale estimation benefit from retrospectives — the actual data alone is valuable for future analogous estimation.
