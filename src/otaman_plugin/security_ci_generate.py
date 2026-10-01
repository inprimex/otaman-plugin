"""Generate a repo's Hook C security-gate CI (security-gates-hook-c 1.4).

deploy 1.3 owns the MECHANISM (reusable workflow, per-language caller variants,
the layer runner); core 1.1 owns the POLICY resolution
(``resolve_repo_gates`` -> ``RepoSecurityGates``). This module is the join: it
turns a repo's metadata into a resolved gate set and renders deploy's variant
with the resolved values substituted.

It decides nothing about which tools run. Policy lives in ``security-gates:``
config and nowhere else — a second home for that rule would disagree with the
first, and the second one is the broken one (the fleet-lessons entry is
literally about this).

THREE OUTCOMES, kept apart, because they look identical in a repo with no
workflow file:

  - ``generated``   — gates resolved, a workflow written;
  - ``opt-out``     — the repo declined Hook C, and the skip is STATED
                      (the spec requires the skip be visible, not silent);
  - ``no-gates``    — nothing configured for this repo's languages at all.

The third is the one that bites. A repo with no ``security-gates:`` config
produces no layers, and emitting a workflow anyway would give it a green check
that gates nothing — a security surface reporting success for work it never
did. So no workflow is written and the reason is named.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

#: Repo `tech:` values mapped to the languages the gate templates know.
#: The fleet's vocabulary is broader than the security one — `tech` describes
#: what a repo is built with, not what scanners apply to it.
TECH_TO_LANGUAGE: dict[str, str] = {
    "python": "python",
    "bash": "shell",
    "shell": "shell",
    "sh": "shell",
    "go": "go",
    "golang": "go",
    "node": "node",
    "javascript": "node",
    "typescript": "node",
    "react": "node",
    "astro": "node",
    "vue": "node",
}

#: `tech:` values that carry no executable attack surface of their own. Mapped
#: EXPLICITLY rather than falling through to "unknown", so a docs repo reads as
#: a deliberate no-language rather than a vocabulary gap someone should fix.
NON_CODE_TECH: frozenset[str] = frozenset(
    {"docs", "markdown", "mkdocs", "yaml", "json", "toml", "text"}
)

#: Caller variants deploy ships. `shell` has defaults but NO variant, so a
#: shell-only repo cannot be rendered — see `unsupported_languages`.
VARIANTS: tuple[str, ...] = ("python", "node", "go")

GENERATED = "generated"
OPT_OUT = "opt-out"
NO_GATES = "no-gates"
NO_VARIANT = "no-variant"


@dataclass(frozen=True)
class GenerationResult:
    """What happened for one repo, and why — never just a file or its absence."""

    repo: str
    outcome: str
    reason: str
    workflow: str | None = None
    languages: tuple[str, ...] = ()
    unknown_tech: tuple[str, ...] = field(default_factory=tuple)
    unsupported_languages: tuple[str, ...] = field(default_factory=tuple)

    @property
    def wrote_workflow(self) -> bool:
        return self.workflow is not None


def languages_for(
    tech: list[str] | tuple[str, ...] | None,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Map a repo's ``tech:`` to gate languages. Returns ``(languages, unknown)``.

    Unknown values are RETURNED, not dropped. A `tech: [rust]` repo that
    silently generated no Rust gates would look identical to one correctly
    configured, and the vocabulary gap would never surface. Non-code tech
    (docs, yaml) is known-and-empty, which is a different thing from unknown.
    """
    langs: list[str] = []
    unknown: list[str] = []
    for raw in tech or ():
        key = str(raw).strip().lower()
        if key in TECH_TO_LANGUAGE:
            lang = TECH_TO_LANGUAGE[key]
            if lang not in langs:
                langs.append(lang)
        elif key not in NON_CODE_TECH:
            unknown.append(key)
    return tuple(langs), tuple(unknown)


def render_variant(variant_text: str, gates: Any) -> str:
    """Substitute the resolved gate values into deploy's caller template.

    ``ci-slow`` is REMOVED entirely when the repo did not opt in, rather than
    emitted with a false `if:`. deploy's contract is explicit about why: an
    advisory job nobody asked for burns minutes on every PR and gets ignored,
    which trains people to ignore the ones that block.
    """
    by_layer = {la.layer: la for la in gates.layers}
    slow = by_layer.get("ci-slow")
    opted_in = bool(slow and not slow.opt_in)

    text = variant_text
    if not opted_in:
        text = _drop_job(text, "ci-slow")

    pair = by_layer.get("ci-medium")
    replacements = {
        "{{ CI_FAST_TOOLS }}": ",".join(by_layer["ci-fast"].tools) if "ci-fast" in by_layer else "",
        "{{ CI_MEDIUM_TOOLS }}": ",".join(by_layer["ci-medium"].tools)
        if "ci-medium" in by_layer
        else "",
        "{{ CI_SLOW_TOOLS }}": ",".join(slow.tools) if slow else "",
        "{{ SCANNER_PAIR }}": ",".join(pair.scanner_pair) if pair else "",
        "{{ CI_SLOW_OPT_IN }}": "true" if opted_in else "false",
    }
    for token, value in replacements.items():
        text = text.replace(token, value)
    return text


def _drop_job(text: str, job: str) -> str:
    """Remove a top-level job block from a caller template.

    Line-based on the two-space job indent deploy's variants use. Deliberately
    narrow: a YAML round-trip would reorder and reformat the whole file, and a
    generated workflow that no longer diffs against deploy's template is one
    nobody can review against its source.
    """
    lines = text.splitlines()
    out: list[str] = []
    skipping = False
    for line in lines:
        if line.startswith(f"  {job}:"):
            skipping = True
            continue
        if skipping:
            if line.strip() and not line.startswith("    ") and not line.startswith("  #"):
                skipping = False
            else:
                continue
        out.append(line)
    return "\n".join(out).rstrip() + "\n"


def generate_for_repo(
    repo: dict[str, Any],
    config_block: Any,
    templates_dir: Path,
) -> GenerationResult:
    """Resolve *repo*'s gates and render its workflow, or say why not."""
    from otaman_core.security_gates import parse_security_gates, resolve_repo_gates

    name = str(repo.get("name", "<unnamed>"))
    languages, unknown = languages_for(repo.get("tech"))

    gates = resolve_repo_gates(
        parse_security_gates(config_block), name, languages=languages or None
    )

    if gates.opt_out:
        # STATED, never silent — the spec requires a visible skip, and doctor
        # must be able to tell "opted out" from "never configured".
        return GenerationResult(
            repo=name,
            outcome=OPT_OUT,
            reason="repo opted out of Hook C in security-gates config",
            languages=languages,
            unknown_tech=unknown,
        )

    if not gates.layers:
        return GenerationResult(
            repo=name,
            outcome=NO_GATES,
            reason=(
                "no security-gates config resolved for languages "
                f"{list(languages) or '(none detected)'} — NO workflow written, because "
                "a workflow with no layers is a green check that gates nothing"
            ),
            languages=languages,
            unknown_tech=unknown,
        )

    renderable = [lang for lang in languages if lang in VARIANTS]
    if not renderable:
        return GenerationResult(
            repo=name,
            outcome=NO_VARIANT,
            reason=(
                f"gates resolved for {list(languages)} but deploy ships caller variants "
                f"only for {list(VARIANTS)} — not rendering a variant I would have to invent"
            ),
            languages=languages,
            unknown_tech=unknown,
            unsupported_languages=tuple(lang for lang in languages if lang not in VARIANTS),
        )

    variant_path = templates_dir / "variants" / f"{renderable[0]}.yml"
    workflow = render_variant(variant_path.read_text(encoding="utf-8"), gates)
    return GenerationResult(
        repo=name,
        outcome=GENERATED,
        reason=f"rendered the {renderable[0]} variant with resolved gates",
        workflow=workflow,
        languages=languages,
        unknown_tech=unknown,
        unsupported_languages=tuple(lang for lang in languages[1:] if lang not in VARIANTS),
    )
