# Changelog fragments

Every PR touching shipped code carries one fragment here, named
`<pr>.<category>.md` (e.g. `142.feature.md`), category one of:
`feature`, `fix`, `doc`, `removal`, `misc`.

Write it human, customer-facing — this is release-notes source
material, not a commit-message dump. At release-cut, the
accumulated fragments (and only the fragments) are assembled into
the published notes; nothing from commit history, PR bodies, or
source strings leaks in.

Docs/CI-only PRs are exempt: put `"changelog: exempt"` in the PR body
instead of adding a fragment.
