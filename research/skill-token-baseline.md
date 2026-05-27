# Skill Token Baseline

> **Task**: 1.2 from `per-project-skill-management`  
> **Date**: 2026-05-27  
> **Author**: plugin-agent  
> **Method**: Character-based BPE estimate (~4 chars/token, calibrated to cl100k_base). Measures two token surfaces: (a) **prompt-repr** — the name + description line loaded into the system prompt at session-spawn for skill selection; (b) **full load** — frontmatter + body, loaded on activation. Token counts are estimates (±10%); exact figures require a runtime tokenizer call against the live model.

---

## 1. Current catalog snapshot (2026-05-27)

14 items: 8 skills + 6 agent definitions. All measured from `otaman-plugin/` main at commit `1cc1a33`.

### 1a. Per-item token costs

| Name | Kind | Lines | Chars | Prompt repr (tok) | Frontmatter (tok) | Body (tok) | Full load (tok) |
|------|------|------:|------:|------------------:|------------------:|-----------:|----------------:|
| `multi-repo-orchestration` | skill | 362 | 16,779 | 35 | 76 | 4,117 | 4,193 |
| `ba-skill` | skill | 477 | 20,804 | 124 | 201 | 4,999 | 5,200 |
| `risk-reviewer` | skill | 425 | 20,195 | 138 | 213 | 4,834 | 5,047 |
| `cto-advisor` | skill | 145 | 10,803 | 247 | 253 | 2,446 | 2,699 |
| `project-estimator` | skill | 225 | 13,837 | 249 | 255 | 3,203 | 3,458 |
| `cpo-skill` | skill | 245 | 10,823 | 94 | 148 | 2,557 | 2,705 |
| `spec-management` | skill | 163 | 6,760 | 35 | 74 | 1,615 | 1,689 |
| `knowledge-capture` | skill | 125 | 5,083 | 32 | 79 | 1,190 | 1,269 |
| `otaman-cto-reviewer-extended` | agent | 363 | 14,661 | 122 | 168 | 3,496 | 3,664 |
| `otaman-cto-reviewer` | agent | 118 | 4,479 | 30 | 74 | 1,044 | 1,118 |
| `otaman-security-observer` | agent | 133 | 5,546 | 37 | 75 | 1,310 | 1,385 |
| `otaman-solution-architect` | agent | 90 | 6,427 | 53 | 114 | 1,491 | 1,605 |
| `otaman-spec-validator` | agent | 116 | 4,460 | 27 | 71 | 1,042 | 1,113 |
| `otaman-debug-model-agent` | agent | 38 | 1,406 | 50 | 68 | 282 | 350 |
| **CATALOG TOTAL** | | **3,025** | **142,063** | **1,273** | **1,869** | **33,626** | **35,495** |

### 1b. Cost breakdown — two distinct token surfaces

```
Session-spawn cost (prompt-repr, name+description only):
  All 14 items  →  1,273 tokens

Full-load cost (if ALL items loaded body-on-activation, worst case):
  All 14 items  →  35,495 tokens

Average per item:
  Prompt-repr:  ~91 tokens
  Full load:    ~2,535 tokens
  Ratio:        ~28× — body dominates; description-set scoping is the high-leverage lever
```

### 1c. Per-skill prompt-repr histogram

```
                                  Prompt tokens (name+description at spawn)
                                  0        50       100      150      200      250
                                  |        |        |        |        |        |
cto-advisor                       ████████████████████████████████████████████████ 247
project-estimator                 ████████████████████████████████████████████████ 249
cpo-skill                         ████████████████████ 94
ba-skill                          ████████████████████████ 124
risk-reviewer                     ████████████████████████████ 138
otaman-cto-reviewer-extended      ████████████████████████ 122
otaman-solution-architect         ██████████ 53
otaman-debug-model-agent          ██████████ 50
otaman-security-observer          ███████ 37
multi-repo-orchestration          ███████ 35
spec-management                   ███████ 35
otaman-cto-reviewer               ██████ 30
otaman-spec-validator             █████ 27
knowledge-capture                 ██████ 32
```

`cto-advisor` and `project-estimator` have the longest descriptions (~249 tokens each) because they must precisely distinguish their trigger surface from one another. This is expected and desirable — ambiguous descriptions cause misfires.

---

## 2. Per-project active-set sizes — 3 representative archetypes

Active set = `(profile_base ∪ enable) − disable`. The three archetypes below use the platform-shipped profile defaults (see `research/skill-profiles.md` for full profile definitions).

### Archetype A: `software-development-default`

A standard software delivery project. BA-layer artifacts (outcomes, flows, risks) handled informally or by the human PM directly. Full security + architecture review enabled.

**Active set (10 of 14):**

| Item | Included | Reason |
|------|----------|--------|
| `multi-repo-orchestration` | ✅ | Core orchestration — always on |
| `spec-management` | ✅ | Spec workflow — always on |
| `knowledge-capture` | ✅ | Knowledge retention — always on |
| `cto-advisor` | ✅ | Strategic advisory |
| `project-estimator` | ✅ | Presale / estimation |
| `otaman-cto-reviewer` | ✅ | Architecture review |
| `otaman-security-observer` | ✅ | Security review |
| `otaman-spec-validator` | ✅ | Spec validation |
| `otaman-solution-architect` | ✅ | Solution architecture |
| `otaman-debug-model-agent` | ✅ | Diagnostic utility |
| `cpo-skill` | ❌ | No dedicated cpo-agent; outcome work is ad-hoc |
| `ba-skill` | ❌ | No formal BA artifacts; flows authored informally |
| `risk-reviewer` | ❌ | Risk register not enabled (no `risks.yaml`) |
| `otaman-cto-reviewer-extended` | ❌ | No cpo-workflow dependency (requires `cpo-skill`) |

**Token cost at spawn**: **795 tokens** vs 1,273 full catalog (−38%)  
**Full-load worst case**: **18,879 tokens** vs 35,495 (−47%)

---

### Archetype B: `healthcare-default`

A regulated healthcare platform (patient apps, clinical tools, EHR integrations). Formal outcome + flow + risk management mandated for HIPAA audit readiness. All 14 items active.

**Active set (14 of 14):**

All items active — the current catalog is entirely relevant to healthcare. No exclusions.

**Token cost at spawn**: **1,273 tokens** (full catalog; no reduction at current catalog size)  
**Full-load worst case**: **35,495 tokens**

**Note**: at current catalog size (14 items), a healthcare project uses everything and sees no reduction. The value of per-project scoping for healthcare emerges as the catalog grows to include domain-specific skills irrelevant to healthcare (e.g., gaming-specific, IoT-specific, drone-UAV-specific skills). See §3 for projected impact.

---

### Archetype C: `fintech-default`

A fintech platform (payments, lending, KYC/AML). Similar to healthcare in regulatory intensity — formal outcome, flow, and risk management required. All 14 items active.

**Active set (14 of 14):**

All items active — same reasoning as healthcare. Fintech-specific additions (compliance skill, regulatory-reviewer subagent) are not yet in the catalog; when added they will be fintech-only exclusions for other archetypes.

**Token cost at spawn**: **1,273 tokens** (full catalog; no reduction at current catalog size)  
**Full-load worst case**: **35,495 tokens**

---

## 3. Expected token reduction from per-project scoping

### 3a. Current catalog (14 items)

The current catalog is small and generalist — most items apply to most projects. The reduction is modest:

| Archetype | Active items | Prompt tokens | vs. full catalog | Reduction |
|-----------|-------------|--------------|-----------------|-----------|
| software-dev | 10 / 14 | 795 | 1,273 | **−38%** |
| healthcare | 14 / 14 | 1,273 | 1,273 | −0% |
| fintech | 14 / 14 | 1,273 | 1,273 | −0% |

### 3b. Projected reduction as catalog grows

The design target from `design.md` is **70–90% reduction** for a typical project. That target only materializes as the catalog expands with domain-specific content (gaming, IoT, drones, ML-infra, etc.) that is irrelevant to the majority of projects. Modelled below using current average token costs per item:

| Catalog size | Full-catalog prompt (tok) | software-dev active (10) | healthcare active (12) | fintech active (12) |
|-------------|--------------------------|-------------------------|----------------------|---------------------|
| **14** (today) | 1,273 | 795 (−38%) | 1,273 (−0%) | 1,273 (−0%) |
| **30** | 2,727 | 909 (−67%) | 1,091 (−60%) | 1,091 (−60%) |
| **60** | 5,455 | 909 (−83%) | 1,091 (−80%) | 1,091 (−80%) |
| **100** | 9,092 | 909 (−90%) | 1,091 (−88%) | 1,091 (−88%) |

Assumptions for the projection:
- New skills added to the catalog maintain the current average prompt-repr of ~91 tokens/item.
- A software-dev project's active set stays at ~10 items as domain-specific skills are added (they don't apply).
- A healthcare / fintech project's active set grows modestly to ~12 as healthcare/fintech-domain skills are added.
- Active-set ceiling: healthcare/fintech projects eventually stabilize at ~12–15 items even in a large catalog.

**Conclusion**: the 70–90% design target is achievable, but requires catalog growth to ~60–100 items. At today's 14-item catalog, the mechanism is correct but the payoff is front-loaded toward software-dev projects (−38%) and will compound as domain-specific skills are added.

### 3c. What drives the most token cost today

The two heaviest description-tokens items are `cto-advisor` (247) and `project-estimator` (249). Their descriptions are long by design — precise disambiguation is more valuable than brevity for these two skills, which handle overlapping trigger surfaces ("how should we…" vs. "estimate this"). Do not shorten them.

The three heaviest full-load items are:
1. `ba-skill` — 5,200 tokens (large: covers flows + processes + 5 capabilities + 2 worked examples)
2. `risk-reviewer` — 5,047 tokens (large: 5 capabilities + full worked health-check sample)
3. `multi-repo-orchestration` — 4,193 tokens (large: core orchestration rules, intentionally comprehensive)

These are loaded on-demand (bodies only when triggered), so their size is acceptable. No body-size optimization warranted for v0.

---

## 4. Measurement methodology

### Token counting

All counts use a character-based BPE estimate: `tokens ≈ chars / 4`. This is accurate to ±10% for English prose. The actual Anthropic tokenizer (not publicly available) produces slightly different counts; for planning purposes this estimate is sufficient.

**Two token surfaces measured per item:**

1. **Prompt-repr** (`name + description` only): what appears in the Claude Code system prompt at session-spawn so the model can decide which skill to activate. This is the primary lever for per-project scoping — loading only the active set's descriptions minimizes the session-spawn token cost.

2. **Full load** (`frontmatter + body`): what is injected when the skill is activated by a trigger match. This cost is incurred at most once per skill per session; it is lazy by design (per `design.md` Q3 resolution: descriptions at spawn, bodies on-demand).

### What is NOT measured here

- **References / domain files**: `cto-advisor` and `project-estimator` ship reference files (`references/domains/*.md`, `references/worked-examples.md`) that are loaded on-demand within those skills. These add 500–3,000 additional tokens per domain reference loaded. Not included here; baseline is skill-definition cost only.
- **Agent subagent invocation**: when an agent spawns a subagent (e.g., `otaman-cto-reviewer`), the subagent's full body is loaded in the child session, not the parent's. Costs are per-session, not cumulative.
- **Command files** (`commands/*.md`): slash command definitions are a separate cost surface. Not in scope for skill-management baseline.

---

## 5. Implications for the implementation

### Active-set resolution

The per-project scoping mechanism (profile + enable/disable, per `design.md` Q2) reduces the **prompt-repr cost** at session-spawn. This is the right optimization target: 1,273 tokens today → 795 for software-dev → projects at catalog scale 60+ seeing 80%+ reduction.

### Body loading is already lazy

Claude Code loads skill bodies on-demand when a trigger fires. No architectural change needed for body-side optimization. The implementation's main job is computing and narrowing the description set.

### Prompt-caching opportunity

The active description set for a given project is stable across sessions (profile rarely changes). It is an excellent candidate for Anthropic's prompt caching (5-minute TTL, or until the profile changes). At 795–1,273 tokens, the cost is small today; at catalog scale (9,000+ tokens for a full catalog), caching the description set could save 80–90% of the per-session description cost.

### Priority: grow the catalog with domain-specific skills

The largest token-reduction wins come not from trimming existing skills but from adding domain-specific skills that are naturally excluded from most projects. Each new IoT / gaming / drone-UAV / clinical-trial skill adds to the full-catalog cost but leaves the software-dev active set unchanged, compounding the reduction ratio.

---

## 6. Open questions for task 1.8 (skill-profiles)

The profile mechanism determines which skills are "active by default" for each archetype. This baseline surfaces three open questions for `research/skill-profiles.md`:

1. **Should `cpo-skill` be in `software-development-default`?** Today excluded. If even small software projects want JTBD outcome management, it should be included. Decision: human confirms.
2. **Should `otaman-debug-model-agent` be in all profiles?** It's tiny (50 prompt tokens, 350 full-load tokens) and useful in any context. Recommend: include in all profiles.
3. **Is `otaman-cto-reviewer-extended` a natural extension of `healthcare` + `fintech` profiles only?** It requires `cpo-skill` to be useful (solution proposals respond to CPO estimate requests). Including it in a profile without `cpo-skill` wastes tokens. Rule: include only when `cpo-skill` is in the same profile.
