# Compliance Guide for Otaman-Managed Projects

This guide explains how otaman's features map to compliance requirements for HIPAA, ISO 27001, and GDPR.

## Ownership & Access Control

| Requirement | Otaman Feature | Evidence |
|------------|----------------|----------|
| Principle of least privilege | Ownership model — each agent can only write to owned repos | `.agents/ownership.json`, PreToolUse hook logs |
| Access control documentation | Per-repo CLAUDE.md with explicit ownership rules | CLAUDE.md files in each repo |
| Segregation of duties | Separate agents for development, review, and security | `agents.yaml` registry |

## Audit Trail

| Requirement | Otaman Feature | Evidence |
|------------|----------------|----------|
| Change tracking | All changes go through git commits | Git history per repo |
| Communication logging | All inter-agent messages stored as files | `.agents/bus/` directory |
| Decision documentation | Architecture Decision Records | `.agents/decisions/` directory |
| Review records | Observer reviews preserved | `.agents/reviews/done/` directory |

## Review & Approval

| Requirement | Otaman Feature | Evidence |
|------------|----------------|----------|
| Code review | CTO reviewer and spec validator agents | Review files in `.agents/reviews/` |
| Security review | Security observer agent | Security review files |
| Change approval workflow | Proposals require review before implementation | `.agents/proposals/` or OpenSpec proposals |
| Separation of review and implementation | Observer agents are read-only, never modify code | Agent definitions enforce READ-ONLY |

## Generating Compliance Reports

Run the compliance report script:

```bash
py scripts/compliance-report.py <project-root> --format markdown
```

This generates a report covering:
1. **Ownership enforcement** — Are all repos configured with owners and CLAUDE.md rules?
2. **Communication audit** — Message counts, pending items, response times
3. **Decision records** — ADR inventory and status
4. **Review coverage** — How many reviews done, by which observers
5. **Git integrity** — Commit counts, repo status

## Recommended Practices

### For HIPAA
- Enable security observer on all repos handling PHI
- Require CTO review for any auth-related changes
- Run compliance report weekly and archive results
- Ensure all ADRs mentioning data handling are reviewed

### For ISO 27001
- Document all observer triggers in platform.yaml
- Archive completed reviews (`.agents/reviews/done/`) with retention policy
- Use bus messages to demonstrate change communication
- Maintain ADRs for all significant technical decisions

### For GDPR
- Flag data model changes for security review
- Track which repos handle personal data in platform.yaml descriptions
- Ensure API contract reviews cover data minimization
- Document data flow across repos in ADRs

## Retention

Configure `communication.max_age_days` in platform.yaml. For compliance, consider:
- Messages: 90 days minimum (HIPAA), 1 year recommended
- Reviews: Retain indefinitely or per your retention policy
- ADRs: Retain indefinitely — they document architectural history
- Git history: Never rewrite (no force-push to main branches)
