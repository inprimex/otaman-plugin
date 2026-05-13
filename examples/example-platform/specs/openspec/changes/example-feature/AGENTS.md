# Conventions for openspec change folders

When working on the parent change folder (`example-feature/`):

- Cross-reference proposal ↔ design ↔ tasks consistently — every
  acceptance criterion should map to a task.
- Use the **compact table + numbered rationale** pattern for any
  multi-row scoring or comparison (see project-estimator skill).
- Tables with cells > 120 chars get split into a compact summary
  table + numbered rationale section underneath.
- Mark tasks as `[x]` when complete; agents update via
  `otaman complete <change-name> --tasks "1.1, 1.2"`.

Cross-references to other openspec changes use relative paths from
the change folder root.
