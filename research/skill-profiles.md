# Skill Profiles

> **Task**: 1.8 from `per-project-skill-management`  
> **Date**: 2026-05-27  
> **Author**: plugin-agent  
> **Depends on**: task 1.2 (`research/skill-token-baseline.md`) for token cost data

---

## 1. Profile mechanism overview

A **skill profile** is a named, versioned YAML file that declares a curated set of skills and agent definitions for a class of project. Profiles are the platform-curated layer — they encode "this skill set has been validated for this domain" so project teams get sensible defaults without authoring from scratch.

### Resolution rule

The **active set** for a session is resolved as:

```
active_set = (profile.skills ∪ platform.enable) − platform.disable
```

Where:
- `profile.skills` = the skills declared by the named profile (after inheritance is resolved)
- `platform.enable` = project-specific additions in `platform.yaml` (custom or marketplace skills)
- `platform.disable` = project-specific exclusions in `platform.yaml`

Resolution happens once at **session-spawn** by the spawn-decision component (per `design.md` Q3). The resolved set is logged for audit; humans can inspect exactly what is active.

### Platform.yaml declaration

```yaml
# platform.yaml — per-project skill configuration
skills:
  profile: software-development-default   # references profiles/software-development-default.yaml
  enable:
    - mycompany:internal-compliance-skill  # project-local skill
  disable:
    - project-estimator                    # this project doesn't need presale estimation
```

If `skills:` is absent, the platform defaults to the `software-development-default` profile.

---

## 2. Profile YAML shape

```yaml
# profiles/<name>.yaml
name: <slug>                     # unique id; kebab-case; no namespace prefix for platform-shipped
version: "1.0.0"                 # semver; platform-shipped profiles version with plugin release
description: >
  <One-to-two sentence summary of what project type this profile serves.>

extends: <parent-profile-name>   # OPTIONAL — inherit parent's skill list + apply this file's overrides
                                 # Maximum inheritance depth: 2 (parent → child; no grandchild)

skills:
  - <skill-or-agent-name>        # items from otaman-plugin/skills/ or agents/
  # ...

# OPTIONAL — only used in child profiles (extends: present)
disable:
  - <skill-or-agent-name>        # remove items inherited from the parent
```

### Field reference

| Field | Required | Notes |
|-------|----------|-------|
| `name` | ✅ | Must match filename stem. Validated at load. |
| `version` | ✅ | Semver. Platform-shipped increments with plugin release. Project-local: git history is authoritative. |
| `description` | ✅ | Shown in `otaman skill list --profiles`. |
| `extends` | optional | Parent profile name. Resolved before `skills` + `disable` are applied. |
| `skills` | ✅ | Explicit skill list. In child profiles, adds to the parent's set. May be empty `[]` if child only disables. |
| `disable` | optional | Only valid when `extends` is present. Removes named items from the inherited set. |

### What profile files do NOT contain

- `enable:` — that lives in `platform.yaml` (project-specific additions, not platform-curated)
- Skill bodies or configuration — profiles reference skills by name; they don't embed content
- Per-agent tool grants — tool permissions are declared in agent definitions, not profiles

---

## 3. Where profiles live

### Platform-shipped profiles

```
otaman-plugin/
└── profiles/
    ├── software-development-default.yaml
    ├── healthcare-default.yaml
    ├── fintech-default.yaml          # (v0.1 — drafted here as stub; not yet in catalog)
    └── minimal-meta-only.yaml
```

Distributed with the plugin. Versioned with the plugin release. Customers reference these by name in `platform.yaml`. They are read-only from a project's perspective — customers customise via `platform.yaml enable/disable`, not by editing platform files.

### Project-local profiles

```
<project-root>/
└── .otaman/
    └── profiles/
        └── mycompany-saas-default.yaml   # project-local; extends a platform profile
```

- Versioned via the project's git history.
- Take precedence over platform-shipped profiles on name collision (project-local wins).
- Typically authored by extending a platform profile with `extends:` + adding company-specific skills.
- Committed to the project repo alongside `platform.yaml`.

### Resolution order (name lookup)

1. `<project-root>/.otaman/profiles/<name>.yaml` — project-local (highest priority)
2. `otaman-plugin/profiles/<name>.yaml` — platform-shipped

If the name is not found in either location, session-spawn fails with a clear error naming the missing profile.

---

## 4. Versioning

### Platform-shipped profile versioning

Platform profiles version with the plugin release (same semver). When a new skill is added to the catalog, the relevant platform profiles bump their minor version to include it. Projects that pin `otaman-plugin` to a release get a stable profile automatically.

```yaml
# After adding 'fintech-compliance-skill' to catalog in plugin v0.3.0
name: fintech-default
version: "0.3.0"   # bumped when skill was added
```

### Project-local profile versioning

Project-local profiles do not carry an explicit version field for their own history — git history of `.otaman/profiles/<name>.yaml` is the authoritative record. The `version:` field in a project-local file indicates which platform profile version it was authored against (useful for drift detection).

```yaml
# .otaman/profiles/mycompany-saas.yaml
name: mycompany-saas
version: "0.2.1"     # authored against otaman-plugin v0.2.1
extends: software-development-default
```

### Drift detection (future)

`otaman doctor` SHOULD warn when:
- A project-local profile's `version:` is older than the current plugin release AND the parent profile has changed since that version.
- A named skill in a profile no longer exists in the catalog (renamed, removed).

Implementation is deferred to the follow-on `per-project-skill-scoping-v0` change.

---

## 5. Inheritance

### Single-level inheritance (recommended pattern)

```
software-development-default  ←  healthcare-default
       (parent)                       (child)
```

Child declares `extends: software-development-default`. The resolved set is:

```
resolved = parent.skills ∪ child.skills − child.disable
```

### Why max depth = 2

Deeper inheritance chains (grandparent → parent → child) create fragile skill sets where a change to the grandparent cascades through multiple levels unexpectedly. Two levels (platform base → domain specialisation) covers all practical cases:

- Level 1 (`software-development-default`): the universal base
- Level 2 (`healthcare-default`, `fintech-default`): domain specialisations

A project-local profile that `extends` a domain profile would be level 3 — permitted but NOT recommended. Document clearly if you do it.

### Inheritance example

```yaml
# profiles/software-development-default.yaml
name: software-development-default
version: "1.0.0"
skills:
  - multi-repo-orchestration
  - spec-management
  - knowledge-capture
  - cto-advisor
  - project-estimator
  - otaman-cto-reviewer
  - otaman-security-observer
  - otaman-spec-validator
  - otaman-solution-architect
  - otaman-debug-model-agent

---

# profiles/healthcare-default.yaml
name: healthcare-default
version: "1.0.0"
extends: software-development-default
skills:
  - cpo-skill
  - ba-skill
  - risk-reviewer
  - otaman-cto-reviewer-extended
# disable: []   # nothing to remove from the parent
```

Resolved healthcare active set = 10 (from parent) + 4 (from child) − 0 = **14 items**.

---

## 6. The three v0 profiles

### 6a. `software-development-default` — 10 items

For general software delivery projects. Covers architecture review, security, spec management, presale estimation, and strategic advisory. BA-layer artifacts (outcomes, flows, risk register) handled informally or not at all.

**Resolves open question from task 1.2 §6:**
- `cpo-skill` → ❌ excluded. Requires `cpo-agent` + `outcomes.yaml` to be useful; most software projects don't have this configured.
- `ba-skill` → ❌ excluded. Requires formal BA artifacts (`flows/`, `processes/`) which software projects typically don't author.
- `risk-reviewer` → ❌ excluded. Risk register not enabled by default for software projects.
- `otaman-cto-reviewer-extended` → ❌ excluded. Depends on `cpo-skill` being present; including it without `cpo-skill` wastes tokens and causes misfires.
- `otaman-debug-model-agent` → ✅ included. 50 prompt tokens; universally useful; no downside.

**Prompt-repr cost: 795 tokens** (see task 1.2 §2 Archetype A)

```yaml
name: software-development-default
version: "1.0.0"
description: >
  General software delivery projects. Covers multi-repo orchestration, architecture
  and security review, spec management, presale estimation, and strategic advisory.
  BA-layer artifacts (outcome registry, flow registry, risk register) are not
  enabled by default — add them via platform.yaml enable: if needed.
skills:
  - multi-repo-orchestration
  - spec-management
  - knowledge-capture
  - cto-advisor
  - project-estimator
  - otaman-cto-reviewer
  - otaman-security-observer
  - otaman-spec-validator
  - otaman-solution-architect
  - otaman-debug-model-agent
```

### 6b. `healthcare-default` — 14 items

For regulated healthcare platforms (patient apps, clinical tools, EHR integrations, telehealth). Adds the full BA layer on top of `software-development-default` — formal outcome management (JTBD), user flow and business process authoring, and risk register review are required for HIPAA audit readiness.

**Design rationale:**
- `cpo-skill` → ✅ added. Healthcare projects require formal outcome management (patient journey outcomes, clinical workflow outcomes). A CPO-agent is standard in these programs.
- `ba-skill` → ✅ added. Clinical flows (patient onboarding, appointment booking) and business processes (lab-order lifecycle, prescription state machine) require formal BA artifacts.
- `risk-reviewer` → ✅ added. Regulatory risk (HIPAA breach, PHI exposure, audit failure) is always in scope and requires a structured risk register.
- `otaman-cto-reviewer-extended` → ✅ added. CPO-agent is present; solution proposals and cost-rejection responses are needed for clinical feature estimation cycles.

**Prompt-repr cost: 1,273 tokens** (full catalog at v1.0; will reduce as catalog grows — see task 1.2 §3b)

```yaml
name: healthcare-default
version: "1.0.0"
description: >
  Regulated healthcare platforms (patient apps, clinical tools, EHR integrations,
  telehealth). Extends software-development-default with full BA-layer support:
  outcome registry (JTBD), user flow and business process authoring, risk register
  review. Required for HIPAA audit readiness and clinical workflow governance.
extends: software-development-default
skills:
  - cpo-skill
  - ba-skill
  - risk-reviewer
  - otaman-cto-reviewer-extended
```

### 6c. `minimal-meta-only` — 3 items

A stripped-down profile for projects that need only the core otaman orchestration layer — no advisory, no review observers, no presale tooling. Use cases: early-stage projects before any formal process is adopted; lightweight agent sessions where token budget is tight; CI-only sessions running `otaman doctor` / `otaman check`.

**Prompt-repr cost: 102 tokens** — an 92% reduction vs the full catalog.

```yaml
name: minimal-meta-only
version: "1.0.0"
description: >
  Bare minimum otaman orchestration: multi-repo coordination, spec workflow, and
  knowledge capture only. No advisory, review observers, estimation, or BA-layer
  skills. Use for early-stage projects, CI sessions, or tight token budgets.
  Add specific skills via platform.yaml enable: as the project matures.
skills:
  - multi-repo-orchestration
  - spec-management
  - knowledge-capture
```

---

## 7. Planned profiles (not in v0 catalog yet)

The following profiles are anticipated as the catalog grows. Not shipped in v0 — documented here so the implementation phase can plan the catalog expansion.

| Profile name | Extends | Adds | When |
|---|---|---|---|
| `fintech-default` | `healthcare-default` | fintech-compliance-skill (TBD), regulatory-reviewer (TBD) | When fintech-domain skills are authored |
| `startup-default` | `software-development-default` | cpo-skill (outcomes for lean discovery) | When startup teams want lightweight outcome management |
| `presale-only` | `minimal-meta-only` | project-estimator, cto-advisor, otaman-solution-architect | For presale sessions only; no delivery tooling |
| `gaming-default` | `software-development-default` | game-live-ops-skill (TBD), monetization-reviewer (TBD) | When gaming-domain skills are authored |
| `iot-embedded-default` | `software-development-default` | firmware-review-skill (TBD), safety-observer (TBD) | When IoT/embedded skills are authored |

Each new domain profile that adds domain-specific exclusions for other archetypes is the mechanism that drives the 70–90% token reduction target (see task 1.2 §3b).

---

## 8. Pairing rule: cpo-skill ↔ otaman-cto-reviewer-extended

`otaman-cto-reviewer-extended` is only useful when `cpo-skill` is also active. The extended reviewer responds to `outcome-estimate-requested` and `outcome-cost-rejected` bus events — both of which only fire if the CPO workflow is enabled. Including the extended reviewer without `cpo-skill` wastes 122 prompt tokens and risks misfires on unrelated solution queries.

**Invariant (to be enforced at session-spawn):**

> If `otaman-cto-reviewer-extended` is in the active set AND `cpo-skill` is NOT in the active set, emit a warning at spawn: "otaman-cto-reviewer-extended is active but cpo-skill is not — solution-proposal capabilities will not trigger correctly."

This invariant applies to platform profiles (enforced by design above) and to project-level `enable:` overrides (enforced at runtime by the spawn-decision component).

---

## 9. Profile file locations — final layout

```
otaman-plugin/
└── profiles/
    ├── software-development-default.yaml   # v0 — 10 items
    ├── healthcare-default.yaml             # v0 — 14 items (extends sw-default)
    └── minimal-meta-only.yaml             # v0 — 3 items

<project-root>/
└── .otaman/
    └── profiles/
        └── <custom-name>.yaml             # project-local; typically extends a platform profile
```

The three v0 profile files are shipped as part of `otaman-plugin` in the `profiles/` directory alongside `skills/` and `agents/`.
