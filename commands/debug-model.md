---
name: debug-model
description: "Diagnostic — make Claude report which model is actually executing this command (verifies model: frontmatter routing)"
model: haiku
effort: low
---

# /otaman:debug-model

One-shot diagnostic to verify that the `model:` frontmatter on plugin
commands actually routes the command's execution to the declared model.

This command declares `model: haiku` in its own frontmatter. If Claude
Code honors per-command `model:`, the response to this command should
come from Haiku 4.5 — even if the session model is Opus or Sonnet.

## Steps

Respond in exactly this format (no other text, no tool calls, no
reasoning-out-loud):

```
{"declared_model": "haiku", "actual_model": "<your actual model name and version>", "actual_effort": "<your effort level if you know it, else unknown>", "session_header_model": "<best guess of what the session header shows>"}
```

Fill in:

- `actual_model`: the exact model you are right now. You should be able
  to state this precisely — e.g. `Haiku 4.5`, `Sonnet 4.6`, `Opus 4.7`.
  Don't hedge; don't add qualifiers. If the model: haiku frontmatter on
  this command is being respected, you ARE Haiku 4.5. If not, you're
  whatever the session model is.
- `actual_effort`: the effort/thinking level you're running at, if you
  can tell. If you can't, write `unknown`. Don't guess.
- `session_header_model`: your best guess of what the session's active
  model header shows (based on what the user would see if the session
  hasn't been changed via `/model`). Usually matches the greeting the
  user saw at session start.

## How to interpret the output

The user runs this from an **Opus** session. Three outcomes:

| actual_model | Means |
|---|---|
| `Haiku 4.5` | ✓ Command frontmatter routing works. Billing seeing 100% Opus is explained by direct prompts dominating the token volume, not broken frontmatter. |
| `Opus 4.7` (same as session) | ✗ Command frontmatter is silently ignored. `model: haiku` decorative; re-engineer. |
| `Sonnet 4.6` (or anything else) | Confusing — probably session model under a different name. Worth investigating further. |

Say nothing else. Just the JSON line.
