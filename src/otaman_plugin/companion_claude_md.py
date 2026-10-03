"""CLAUDE.md templates for the two program-companion repo kinds (pcrs 2.1/2.2).

`<program>-business` is owned by a CPO-role agent, `<program>-strategy` by a
cofounder-role agent. This module renders the COMMITTED, public-safe
`CLAUDE.md` for either — the per-repo orientation an owner reads on arrival.

DERIVED, NOT INVENTED. otaman-business and otaman-strategy already exist and
carry hand-written CLAUDE.md files; this template is their shape
parameterised, not a third variant. Writing a fresh one and leaving the two
live files as a second and third form is the mistake the version-authority
sweep already paid for once (plugin #73: a README note that had drifted into
three wordings across the fleet because each pass re-authored it).

IT WRITES NO ORCHESTRATION RULES, EVER. The generator deliberately never puts
the orchestration block in a committed file — it goes to the gitignored
`CLAUDE.local.md` (see `generate_agent_config.generate_repo_claude_md`, and
the external-audit remediation behind it). This renders the other half: the
public guide. Bus internals, fleet layout and queue mechanics are not its
business, and a test asserts none of them appear in the output.

SCOPE. 2.1/2.2 ask for the TEMPLATES. The opt-in schema is spec-agent's (pcrs
3.2, unticked), the scaffold orchestration is bridge's (1.2) and the CLI verb
is cli's (1.1). So this renders from an already-parsed platform config and
writes nothing to disk; it does not invent the `program.processes.<kind>`
shape it would read, because that shape is not declared yet and a guess here
becomes the de-facto schema the moment someone scaffolds with it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

BUSINESS = "business"
STRATEGY = "strategy"
KINDS: tuple[str, ...] = (BUSINESS, STRATEGY)

#: What each kind is FOR, in the one line that opens the file. The owner reads
#: this before anything else, so it says the job, not the taxonomy.
_PURPOSE: dict[str, str] = {
    BUSINESS: "the business-artifacts repo",
    STRATEGY: "the program-strategy repo",
}

#: The second clause: what actually lives there. Split from _PURPOSE so the
#: opening sentence reads as a sentence rather than two appositions colliding.
_HOLDS: dict[str, str] = {
    BUSINESS: "pitch deck, investor materials and GTM, assembled from the strategy repo's inputs",
    STRATEGY: (
        "value proposition, market and competitive analysis, financial projections, narrative"
    ),
}

#: The default audience label for a path nobody classified. NOT "public" and
#: NOT "internal": an unclassified path is unclassified, and saying otherwise
#: is the silent-OK this fleet keeps paying for.
UNCLASSIFIED = "unclassified"

#: Rendered where a repo declares no sensitivity at all. An ABSENT section
#: reads as "nothing here is sensitive"; what it actually means is "nobody
#: said". These two are different and only one of them is safe.
NO_SENSITIVITY_DECLARED = (
    "No sensitivity classes are declared for this repo. That is not the same "
    "as nothing here being sensitive — it means nobody has classified it yet. "
    "Treat everything as internal until the owner declares otherwise, and "
    "declare the classes in `platform.yaml` so this section stops saying this."
)

#: A skill-pack path under `openspec/changes/` dies when that change archives.
#: Both live dogfood repos point at one today, so this is an observed hazard
#: rather than a hypothetical.
_VOLATILE_SKILL_PACK = "openspec/changes/"
VOLATILE_SKILL_PACK_NOTE = (
    "> **This path lives inside an OpenSpec *change* directory and will break "
    "when that change archives.** It is correct today and will not stay "
    "correct. When the skill pack moves to a permanent home, update "
    "`platform.yaml` and re-render — do not hand-edit this file."
)


@dataclass(frozen=True)
class SensitivePath:
    """One classified path: what it is, who may see it, and why it matters."""

    path: str
    audience: str = UNCLASSIFIED
    note: str = ""

    def render(self) -> str:
        line = f"- `{self.path}` — **{self.audience}**."
        return f"{line} {self.note}".rstrip()


@dataclass(frozen=True)
class CompanionRepoSpec:
    """Everything the template needs, already resolved by the caller."""

    kind: str
    repo: str
    owner: str
    program: str
    description: str = ""
    siblings: dict[str, str] = field(default_factory=dict)
    sensitivity: tuple[SensitivePath, ...] = ()
    skill_pack: str = ""
    otaman_dir: str = "../otaman-meta/"


class CompanionTemplateError(ValueError):
    """An unrenderable spec — unknown kind, or a repo that is not a companion."""


def spec_from_platform(
    config: dict[str, Any],
    repo_name: str,
    *,
    kind: str | None = None,
) -> CompanionRepoSpec:
    """Build a :class:`CompanionRepoSpec` from a parsed `platform.yaml`.

    *kind* is inferred from the repo's name suffix when not given — the naming
    convention IS the declaration today, because the `program.processes.<kind>`
    opt-in block the proposal describes is not in the schema yet (pcrs 3.2).
    Pass *kind* explicitly once it is, rather than letting a repo named
    `acme-strategy-archive` infer its way into the wrong template.

    Raises :class:`CompanionTemplateError` rather than guessing: a scaffold
    that renders the wrong kind's guide is worse than one that refuses, because
    the guide is what the owner trusts on arrival.
    """
    repos = config.get("repos") or []
    entry = next((r for r in repos if isinstance(r, dict) and r.get("name") == repo_name), None)
    if entry is None:
        raise CompanionTemplateError(f"{repo_name!r} is not declared in platform.yaml repos")

    if kind is None:
        kind = next((k for k in KINDS if repo_name.endswith(f"-{k}")), None)
    if kind not in KINDS:
        raise CompanionTemplateError(
            f"cannot tell which companion kind {repo_name!r} is "
            f"(expected a name ending in {' or '.join('-' + k for k in KINDS)}, "
            f"or an explicit kind in {list(KINDS)})"
        )

    owner = str(entry.get("owner") or "").strip()
    if not owner:
        raise CompanionTemplateError(
            f"{repo_name!r} declares no owner — the guide's whole first section is "
            "'who you are', and a companion repo with no owner agent has nobody to address"
        )

    program = repo_name[: -(len(kind) + 1)]
    others = {
        str(r.get("name")): str(r.get("path") or f"../{r.get('name')}")
        for r in repos
        if isinstance(r, dict) and r.get("name") and r.get("name") != repo_name
    }
    siblings = {
        name: path
        for name, path in others.items()
        if name.startswith(f"{program}-") and _is_companion_or_specs(name, program)
    }

    program_cfg = config.get("program") or {}
    registries = program_cfg.get("registries") or {}

    return CompanionRepoSpec(
        kind=kind,
        repo=repo_name,
        owner=owner,
        program=program,
        description=str(entry.get("description") or "").strip(),
        siblings=siblings,
        sensitivity=_sensitivity_from(entry),
        skill_pack=str(registries.get("skill_pack") or "").strip(),
    )


def _is_companion_or_specs(name: str, program: str) -> bool:
    suffix = name[len(program) + 1 :]
    return suffix in KINDS or suffix == "specs"


def _sensitivity_from(entry: dict[str, Any]) -> tuple[SensitivePath, ...]:
    """Read a repo's declared sensitivity, tolerating the two obvious shapes.

    Tolerant on SHAPE, never on CONTENT: a path with no audience renders as
    `unclassified`, which is a visible state the owner can act on, rather than
    silently defaulting to something reassuring.
    """
    raw = entry.get("sensitivity")
    out: list[SensitivePath] = []
    if isinstance(raw, dict):
        for path, value in raw.items():
            if isinstance(value, dict):
                out.append(
                    SensitivePath(
                        path=str(path),
                        audience=str(value.get("audience") or UNCLASSIFIED),
                        note=str(value.get("note") or ""),
                    )
                )
            else:
                out.append(SensitivePath(path=str(path), audience=str(value or UNCLASSIFIED)))
    elif isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict) and item.get("path"):
                out.append(
                    SensitivePath(
                        path=str(item["path"]),
                        audience=str(item.get("audience") or UNCLASSIFIED),
                        note=str(item.get("note") or ""),
                    )
                )
            elif isinstance(item, str):
                out.append(SensitivePath(path=item))
    return tuple(out)


def render(spec: CompanionRepoSpec) -> str:
    """Render the committed `CLAUDE.md` for one companion repo."""
    if spec.kind not in KINDS:
        raise CompanionTemplateError(f"unknown companion kind {spec.kind!r}")

    lines: list[str] = [
        f"# {spec.repo} — CLAUDE.md",
        "",
        f"You are working in **`{spec.repo}`**, {_PURPOSE[spec.kind]} for the "
        f"**{spec.program}** program: {_HOLDS[spec.kind]}.",
    ]
    if spec.description:
        lines += ["", spec.description]

    lines += [
        "",
        "## Owner",
        "",
        f"**`{spec.owner}`** owns this repo and is the only agent that writes here.",
        "",
        "## What you do here",
        "",
        *_workflow(spec),
        "",
        "## Sensitivity",
        "",
        *_sensitivity_section(spec),
        "",
        "## Where things are",
        "",
        f"- Otaman folder: `{spec.otaman_dir}`",
    ]
    for name, path in sorted(spec.siblings.items()):
        lines.append(f"- `{name}`: `{path}`")
    if spec.skill_pack:
        lines.append(f"- Skill pack: `{spec.skill_pack}`")
        if _VOLATILE_SKILL_PACK in spec.skill_pack:
            lines += ["", VOLATILE_SKILL_PACK_NOTE]

    lines += [
        "",
        "---",
        "",
        "> Your private orchestration rules — fleet layout, bus internals, task "
        "queue — are **not** in this file. They are generated into a gitignored "
        "`CLAUDE.local.md`, which Claude Code loads after this one. Re-run "
        "`otaman init` to refresh them. This file is the public-safe guide and "
        "is committed.",
        "",
    ]
    return "\n".join(lines)


def _workflow(spec: CompanionRepoSpec) -> list[str]:
    """The kind's working loop.

    Deliberately short and directional rather than a numbered recipe. The two
    live repos each carry a 6-7 step pipeline naming specific skill files, and
    those steps are THEIR content: a template that bakes them ships Otaman's
    pipeline into every customer program. What generalises is the direction
    work flows between the two repos, which is what this says.
    """
    if spec.kind == STRATEGY:
        return [
            "Produce the program's strategy artifacts — value proposition, "
            "customer development, market sizing, competitive positioning, "
            "financial projections, narrative. Each lands in its own directory "
            "in this repo.",
            "",
            "Strategy flows OUTWARD: your artifacts are the inputs the business "
            "repo assembles into investor-facing material. Write them to be read "
            "by that repo's owner, not only by you.",
            "",
            "One artifact, one home. When a document could plausibly live in "
            "either repo, it belongs where the work that consumes it happens — "
            "and the other repo links to it rather than forking a second copy.",
        ]
    return [
        "Assemble the program's business artifacts — pitch deck, investor "
        "materials, GTM — from the strategy repo's outputs.",
        "",
        "Business flows INWARD: you are a consumer of the strategy repo, not a "
        "second author of it. When an input is missing or stale, ask its owner "
        "rather than deriving your own version here — a divergent second copy "
        "is harder to find than an absent one.",
        "",
        "One artifact, one home. A model or analysis that already exists in the "
        "strategy repo gets linked, not re-derived.",
    ]


def _sensitivity_section(spec: CompanionRepoSpec) -> list[str]:
    """Who may see what — the section that must never be silently empty."""
    if not spec.sensitivity:
        return [NO_SENSITIVITY_DECLARED]
    body = [p.render() for p in spec.sensitivity]
    unclassified = [p.path for p in spec.sensitivity if p.audience == UNCLASSIFIED]
    if unclassified:
        body += [
            "",
            f"Paths listed with no audience ({', '.join(f'`{p}`' for p in unclassified)}) "
            "are **unclassified, not cleared** — they were declared sensitive and then "
            "never given a reader. Resolve them with the owner before sharing anything "
            "from them.",
        ]
    return body


__all__ = [
    "BUSINESS",
    "KINDS",
    "NO_SENSITIVITY_DECLARED",
    "STRATEGY",
    "UNCLASSIFIED",
    "VOLATILE_SKILL_PACK_NOTE",
    "CompanionRepoSpec",
    "CompanionTemplateError",
    "SensitivePath",
    "render",
    "spec_from_platform",
]
