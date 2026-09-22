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

## After a release cut

The cut broadcasts a `fragments-consumed` signal naming this repo's
consumed files. Clear exactly those filenames with
`otaman release clear-fragments <manifest>` and commit — **never by
glob**, and never by emptying the directory. This `README.md` is
documentation, not a fragment; it always survives. The consumed-
fragments manifest recorded with the release — not the empty
directory — is the dedup authority, so a lagging clear can never
duplicate a note.
