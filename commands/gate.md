---
name: gate
description: "Validate readiness to transition between project lifecycle phases"
model: opus
effort: xhigh
arguments:
  - name: transition
    description: "Gate transition (e.g., 'discovery-to-development', 'development-to-launch'). Omit for auto-detect."
    required: false
---

# /otaman:gate

Check whether the project is ready to move from one lifecycle phase to the next.

## Steps

### Step 0: Determine current phase and transition

1. Read `platform.yaml` → check `lifecycle.phases` (or use defaults: presale, discovery, development, support)
2. Determine current phase from `.agents/project-meta.yaml` or `.otaman-presale/project-meta.yaml`
3. If `<transition>` argument provided, use it. Otherwise, infer the next natural transition.
4. Look up gate requirements in `platform.yaml` → `lifecycle.gates.{transition}`

### Step 1: Check required artifacts

For the target gate, verify that all required artifacts exist:

```yaml
# Example gate definition in platform.yaml
lifecycle:
  gates:
    discovery-to-development:
      required:
        - .otaman-presale/estimation/estimate-v1.md
        - .otaman-presale/knowledge-audit.yaml
        - platform.yaml
      checks:
        - "otaman validate"
```

For each required artifact:
- If file path: check existence with Read tool
- Report: PASS (exists) / FAIL (missing)

### Step 2: Run validation checks

For each check command:
- Run via Bash tool
- Report: PASS (exit 0) / FAIL (non-zero exit)

### Step 3: Domain-specific checks

If `platform.yaml` has a `domain` field, apply additional domain-specific checks:

**Healthcare**:
- HIPAA compliance checklist started (`.agents/compliance/hipaa-checklist.md`)
- BAA template exists
- PHI data flow documented

**Fintech**:
- PCI scope documented
- KYC/AML requirements captured
- Financial calculation tests exist

**General** (all domains):
- All repos have CLAUDE.md with otaman block
- Ownership map exists (`.agents/ownership.json`)
- At least one observer configured
- No `none` confidence items in knowledge audit without docs provided

### Step 4: Present gate report

```
Gate Check: discovery-to-development
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Required Artifacts:
  ✅ estimation/estimate-v1.md
  ✅ knowledge-audit.yaml
  ✅ platform.yaml
  ❌ discovery/validated-assumptions.yaml

Validation Checks:
  ✅ otaman validate

Domain Checks (healthcare):
  ⚠️  HIPAA checklist not started
  ❌ PHI data flow not documented

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Result: CONCERNS (2 failures, 1 warning)

Blocking:
  - Validate assumptions before proceeding
  - Document PHI data flows

Recommended:
  - Start HIPAA compliance checklist
```

Results: **PASS** (all green) / **CONCERNS** (warnings but no failures) / **FAIL** (blocking failures).

### Default gates (when lifecycle.gates is not defined)

| Transition | Required | Checks |
|-----------|----------|--------|
| presale-to-discovery | estimation exists, project-meta.yaml | — |
| discovery-to-development | platform.yaml, assumptions validated, knowledge audit | `otaman validate` |
| development-to-launch | all tests pass, compliance report, no pending urgent messages | `otaman validate`, `otaman compliance` |

## Notes

- Gates are recommendations, not hard blocks. The human can override with "proceed anyway."
- Custom gates in `lifecycle.gates` override defaults for that transition.
- Gate checks are idempotent — run them multiple times to track progress.
