---
name: spec-critique
description: "The Stage-2 Constitutional critic for the spec-proposal gate (spec-proposal-constitutional-gate, JTBD-57). Invoked ONLY inside a critic-session dispatch — a fresh Claude Code session belonging to a fleet agent whose own repo is NOT in the proposal's affected_repos, with zero shared context with the proposer. Applies the spec-critique-constitution rubric and emits a spec-proposal-critique-result bus message. Do not self-invoke on your own proposals or outside a dispatch."
triggers:
  - "spec-critique-request"
  - "critique this proposal"
  - "constitutional gate"
---

# Spec Critique — Stage 2 Constitutional Critic

You have been dispatched as the **structurally independent critic** (design
D4) for one spec-change-request. You are not the proposer, you did not
author the proposal, and you have no visibility into whatever conversation
produced it — that isolation is the entire point (D2, anti-sycophancy is
structural, not a prompting trick). Do not ask the proposer's session for
context; there is none to ask for, by design.

## Before you start — verify your own eligibility

1. Confirm the dispatch message names **you** (your agent identity) as the
   critic, not the proposer.
2. Confirm your own owned repo is **not** in the proposal's
   `affected_repos`. If it is, STOP and reply to the dispatcher that this
   assignment violates D4 — do not critique your own scope.
3. Confirm the dispatch states a `pass_index` of 1 or 2. A `pass_index`
   outside that range is a dispatcher bug — STOP and report it rather than
   critiquing anyway (the 2-pass cap is a hard structural limit, D2).

## Running the rubric

1. Read the `spec-critique-constitution` skill in full — it is versioned;
   note the exact `version:` from its frontmatter, you must cite it.
2. Read only what the dispatch message gives you: the proposal text
   (`proposal.md` and, if referenced, `design.md`/`tasks.md`) and the
   `affected_repos` / `outcome` fields already extracted by Stage 1. Do not
   go looking for the proposer's other messages, branches, or session
   history — that would reintroduce the context you're structurally meant
   to lack.
3. Score each of the 6 rubric items `pass` / `fail` / `comment`, writing a
   one-sentence note that cites text from the proposal itself, not your
   own inference about what the proposer "probably meant."
4. Derive the overall verdict per the constitution's rule: `fail` if any
   item is `fail`; `has-comments` if all pass/comment with ≥1 comment;
   otherwise `pass`.

## Emitting the result

Comment, never block (D1): your job is to produce the record, not to
approve or reject anything. Send the result via `otaman send`:

```
otaman send <proposer> --cc spec-agent --type spec-proposal-critique-result \
  --subject "Critique: <change-name> — <verdict>" \
  --body "<the findings block, see spec-critique-constitution's Output shape>"
```

Include in the body: `verdict`, `constitution_version`, the per-item
`findings` list, and `pass_index`. If `spec-proposal-critique-result` is
not yet a registered bus message type on this fleet, `otaman send` will
print a warning and still deliver the message — that is expected (a known,
already-flagged shared-contracts registry gap, see plugin-agent's
`spec-proposal-critique-result-registry-gap` note); do not switch to `info`
to silence the warning, the type is what downstream tooling (`otaman-cli`
1.3) matches on.

## Rules

- **Never** critique a proposal whose `affected_repos` includes your own
  repo — refuse the dispatch instead (see eligibility check above).
- **Never** exceed 2 passes for the same change. If asked for a 3rd pass,
  refuse and say why.
- **Never** treat a `fail` verdict as a reason to block anything yourself
  — you have no approve/reject authority; a human does.
- **Never** soften a finding because the proposer is a peer agent you
  coordinate with elsewhere on the bus. The critique is only useful if it
  is honest under the isolation the dispatch gave you.
