---
name: spec-critique-constitution
version: 1.0.0
description: "Versioned rubric for the Stage-2 spec-proposal critic (spec-proposal-constitutional-gate, JTBD-57, design D3). NOT a user-facing skill — it is read by the spec-critique skill inside a fresh critic session and is never invoked directly. The critique SHALL cite this version."
triggers: []
---

# Spec-Critique Constitution v1.0.0

This is the rubric the `spec-critique` skill applies. It is editable canon,
not code — amend it exactly like any other skill (a PR to this file), and
every critique produced after the amendment cites the new `version:`.

Do not amend this file to reference a specific program, proposal, or
outcome. Like the `tech-startup` pack, this rubric is generic methodology;
program-specific judgment belongs in the critique output, not the
constitution.

## Scope

This constitution governs Stage 2 of the spec-proposal gate only. Stage 1
(deterministic lint: front-matter schema, resolvable ids, secret scan,
placeholder scan, `affected_repos` resolution) already ran and passed —
`otaman_core.spec_gate.lint_proposal`. Stage 2 is qualitative judgment on
what Stage 1 cannot check mechanically.

## Rubric

Score each item `pass` / `fail` / `comment` (a `comment` is neither a pass
nor a fail — it is a note the critic wants on record without withholding
approval eligibility). The overall verdict is:

- **pass** — every item is `pass` or `comment`
- **has-comments** — every item is `pass` or `comment`, and at least one
  `comment` was recorded
- **fail** — any item is `fail`

| # | Item | What "pass" means |
|---|------|--------------------|
| 1 | Cites an OpenSpec change id | The proposal names the `openspec/changes/<name>/` it belongs to (or, for a brand-new change, the id it proposes to create) — not a vague reference to "the spec" |
| 2 | Why is linked to an outcome | The proposal's rationale traces to a real, resolvable outcome (JTBD id) — not an isolated technical preference with no business tie |
| 3 | `affected_repos` is explicit | Every repo the change touches is named; "and possibly others" or an empty list on a clearly cross-repo change is a `fail` |
| 4 | References a declared outcome | The cited outcome id actually resolves (this overlaps Stage 1's `unresolved-outcome` check, but Stage 2 additionally judges whether the outcome is the *right* one, not just a resolvable one) |
| 5 | No Done over-claims | Any claim that prior work is "done", "shipped", or "complete" is cross-checked against what has actually been delivered (`otaman complete` history / merged PRs) — an aspirational claim stated as fact is a `fail` |
| 6 | Names the artifacts to be authored | The proposal says what `proposal.md` / `design.md` / `tasks.md` / `spec.md` deltas will exist when done, in enough detail that a reader could tell if the work stalled at "proposed" forever |

## Output shape the critic emits

The `spec-critique` skill packages the rubric evaluation as:

```yaml
verdict: pass | fail | has-comments
constitution_version: "1.0.0"
findings:
  - item: 1
    result: pass | fail | comment
    note: "<one sentence — cite text from the proposal, don't paraphrase judgment as fact>"
```

## Non-negotiables for the critic session

- **Comment, never block (D1).** This rubric produces metadata, not a
  veto. A `fail` verdict still reaches the human queue for approval —
  never refuse to emit a result because the proposal looks weak.
- **No proposer context (D2).** The critic session sees only the
  proposal text and this constitution. It does not see the proposer's
  conversation, reasoning, or any argument for why concerns don't apply.
  If the critique feels like it's "missing context" the proposer would
  supply — that is the point, not a bug (SycEval arXiv 2502.08177).
- **Cite the version.** Every critique result states
  `constitution_version` from this file's frontmatter, so a later rubric
  amendment doesn't silently reinterpret old verdicts.
