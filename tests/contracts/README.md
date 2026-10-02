# Pinned cross-repo contracts

otaman-deploy is **private**; otaman-plugin is public, and its CI has no token
for a private sibling. So the Hook C template tests cannot run against the real
templates in the gate — they skipped, and CI reported green on a contract it
had never checked (deploy's `{{ CI_*_TIMEOUT }}` addition proved it).

What is pinned here is the **interface**, not deploy's file: the placeholder
names my generator must substitute. Those are already public by necessity — my
generator names them in `src/otaman_plugin/security_ci_generate.py`, which is
public. Deploy's template body is theirs and is deliberately NOT vendored.

Two tests use this:

- one runs in CI against the pinned list, so the gate verifies the generator
  substitutes every placeholder it is contracted to;
- one runs only where the sibling exists and compares the pinned list against
  the placeholders actually present in deploy's templates — drift detection.

The second cannot run in CI, and that is an honest limit rather than a hidden
one: CI can verify *my side* of the contract, and only a machine with both
repos can verify they still agree.
