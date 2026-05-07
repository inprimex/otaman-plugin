# Tier D — Detailed Estimation Template (15-25 pages)

## {Project Name} — Detailed Estimation

**Project Code**: {CODE}
**Date**: {DATE}
**Prepared by**: {SA name / organization}
**Client**: {Client name}
**Confidence**: ±20-25%
**Method**: Three-Point PERT

---

### 1. Executive Summary (1-2 pages)

{Project understanding. Total investment range. Timeline. Key risks. Team composition. Recommendation.}

**Quick Numbers**:
- Investment: ${MIN} - ${MAX} ({CURRENCY})
- Timeline: {X}-{Y} months
- Team: {composition}
- Confidence: ±{X}%
- Top risk: {one sentence}

### 2. Initial Analysis & Clarification (2-3 pages)

#### Information Verification Summary

| Category | Score | Key Findings |
|----------|-------|-------------|
| Business Context | X/5 | {findings} |
| Technical Environment | X/5 | {findings} |
| Compliance | X/5 | {findings} |
| Team & Resources | X/5 | {findings} |
| Budget & Timeline | X/5 | {findings} |
| Domain-Specific | X/5 | {findings} |

**Overall Confidence**: {X}%

#### Assumption Register

| ID | Assumption | Confidence | Impact if Wrong | Verification |
|----|-----------|------------|----------------|-------------|
| A1 | {assumption} | {High/Med/Low} {%} | {hours/cost} | {method} |

### 3. Requirements Documentation (4-6 pages)

#### Functional Requirements

| Epic | Feature | Complexity | Initial Estimate |
|------|---------|-----------|-----------------|
| {epic} | {feature} | {Low/Med/High} | {hours range} |

#### Non-Functional Requirements

| Requirement | Metric | Target | Notes |
|------------|--------|--------|-------|
| Response time | p95 latency | < {X}ms | {notes} |
| Availability | Uptime | {X}% | {notes} |
| Scale | Concurrent users | {X} | {notes} |

#### Architecturally Significant Requirements (5-10)

1. **ASR-1**: {requirement} — drives {architectural decision}

### 4. Architecture Recommendation (4-5 pages)

#### Architecture Style

{Justification for chosen architecture style (microservices, modular monolith, serverless, etc.)}

#### System Diagram (C4 Container Level)

```mermaid
flowchart TD
    {C4 container diagram}
```

#### Component Traceability

| Component | Requirements | Tech Stack | Rationale |
|-----------|-------------|-----------|-----------|
| {component} | ASR-1, FR-3 | {tech} | {why} |

#### Tech Stack

| Layer | Choice | Alternative Considered | Rationale |
|-------|--------|----------------------|-----------|
| Frontend | {tech} | {alt} | {why} |
| Backend | {tech} | {alt} | {why} |
| Database | {tech} | {alt} | {why} |
| Infrastructure | {tech} | {alt} | {why} |

### 5. Effort Estimation — Three-Point PERT (5-7 pages)

#### Method

For each component: Optimistic (O), Most Likely (M), Pessimistic (P).
- Expected = (O + 4M + P) / 6
- StdDev = (P - O) / 6
- 68% CI: Expected ± 1σ
- 95% CI: Expected ± 2σ

#### Component Estimates

| Component | O (hours) | M (hours) | P (hours) | Expected | StdDev | 68% CI |
|-----------|-----------|-----------|-----------|----------|--------|--------|
| {component} | {O} | {M} | {P} | {E} | {σ} | {range} |
| **TOTAL** | | | | **{E}** | **{σ}** | **{range}** |

#### Phase Breakdown

| Phase | Duration | Team | Effort | Cost |
|-------|----------|------|--------|------|
| Discovery | {X} weeks | {team} | {hours}h | ${cost} |
| MVP / Phase 1 | {X} weeks | {team} | {hours}h | ${cost} |
| Phase 2 | {X} weeks | {team} | {hours}h | ${cost} |
| Testing & QA | {X} weeks | {team} | {hours}h | ${cost} |
| Launch | {X} weeks | {team} | {hours}h | ${cost} |
| **TOTAL** | **{X} months** | | **{hours}h** | **${total}** |

#### Team Composition

| Role | Count | Phase(s) | Rate | Monthly Cost |
|------|-------|----------|------|-------------|
| {role} | {N} | {phases} | ${rate}/h | ${monthly} |

### 6. Risk Assessment (3-4 pages)

#### Risk Register

| ID | Risk | Category | Prob | Impact | Score | Mitigation | Contingency (hours) |
|----|------|----------|------|--------|-------|-----------|-------------------|
| R1 | {risk} | Technical | H/M/L | H/M/L | {1-9} | {mitigation} | {hours} |

**Risk categories**: Technical, Scope, Organisational, Compliance, External

#### Contingency Summary

- Technical risks contingency: {X} hours ({Y}%)
- Scope risks contingency: {X} hours ({Y}%)
- Total contingency: {X} hours ({Y}% of base estimate)

### 7. Options Comparison (2-3 pages, if applicable)

| Criterion | Option A: {name} | Option B: {name} | Option C: {name} |
|-----------|-----------------|-----------------|-----------------|
| Scope | {scope} | {scope} | {scope} |
| Timeline | {months} | {months} | {months} |
| Investment | ${range} | ${range} | ${range} |
| Risk level | {H/M/L} | {H/M/L} | {H/M/L} |
| Trade-off | {trade-off} | {trade-off} | {trade-off} |

**Recommendation**: Option {X} because {rationale}.

### 8. Implementation Roadmap (2 pages)

```mermaid
gantt
    title Implementation Roadmap
    dateFormat YYYY-MM-DD
    section Discovery
        Discovery Phase: d1, {start}, {duration}
    section MVP
        Core Features: m1, after d1, {duration}
        Integrations: m2, after m1, {duration}
    section Phase 2
        Advanced Features: p2, after m2, {duration}
    section Launch
        QA & Testing: qa, after p2, {duration}
        Launch: launch, after qa, {duration}
```

#### Decision Gates

| Gate | Criteria | Artifacts Required |
|------|----------|-------------------|
| Discovery → MVP | Assumptions validated, specs approved | Updated estimation, platform.yaml |
| MVP → Phase 2 | Core features complete, tested | QA report, user acceptance |
| Phase 2 → Launch | All features complete, compliance ready | Compliance report, pen test |

### 9. Next Steps (1-2 pages)

1. Review this estimation with {stakeholders}
2. {Clarification items that would improve accuracy}
3. If proceeding: run `/otaman:discovery` to start discovery phase
4. Expected discovery duration: {X} weeks
5. Contract structure recommendation: {T&M / Fixed / Hybrid}

---

**Project Reference Code**: {CODE}
