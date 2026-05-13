# specs (example-platform)

OpenSpec-driven specifications. Owned by `spec-agent`.

This repo holds the source-of-truth for what we're building and why.
Changes flow:

1. Agent or human proposes via `/otaman:propose`
2. Human approves via `/otaman:approve`
3. Spec change folder lands in `openspec/changes/<change-name>/`
4. Agents read updated specs + adapt their implementation

The single example change folder at `openspec/changes/example-feature/`
demonstrates the structure.
