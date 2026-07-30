# Security Policy

## Reporting a vulnerability

If you believe you have found a security vulnerability in `otaman-plugin` or any
other repository in the Otaman organization, **please do not open a public
GitHub issue**. Public disclosure before a fix is in place puts users at risk.

**Preferred channel — GitHub Security Advisory (private):**

1. Navigate to this repository's **Security** tab on GitHub
2. Click **Report a vulnerability**
3. Fill in the form — the report is visible only to repository maintainers

This routes through GitHub's coordinated disclosure tooling, which lets
maintainers triage privately, draft a fix, request a CVE if appropriate,
and publish the advisory simultaneously with the patch release.

**Fallback channel — email:**

Email security@otaman.ai with subject line beginning `[otaman-security]`.
We aim to acknowledge within 5 business days.

## Scope

**In scope:**

- Authentication or authorization bypass in `otaman-bridge` daemon
- Secret leakage through logs, error messages, telemetry, or bus messages
- Path traversal or arbitrary file read/write in CLI, plugin hooks, or bridge
- Code execution via untrusted input (bus messages, slash command args, MCP
  tool parameters, hook payloads)
- Privilege escalation in PreToolUse / SessionStart hooks
- Telegram transport: spoofing, replay, or token exfiltration
- Git host adapter (`otaman-cli`): credential leakage to wrong host

**Out of scope:**

- Vulnerabilities in dependencies (report upstream first; we'll bump pins
  promptly once an upstream fix lands)
- Issues requiring local-machine access (Otaman runs locally; root-on-host
  is already game-over for any local tool)
- Theoretical attacks without a working PoC
- Rate limiting or DoS against the local bridge daemon (single-user runtime;
  not a multi-tenant service)
- Configuration mistakes by the user (e.g., committing `.maestro/secrets.env`
  to a public repo)

## Response timeline

This is experimental software maintained by a small team. We aim for:

- **Acknowledgement**: within 5 business days
- **Initial assessment**: within 2 weeks
- **Fix or workaround**: best-effort; typically 30–90 days depending on
  severity and complexity
- **Public disclosure**: coordinated with reporter; default 90 days after
  initial report or upon patch release, whichever comes first

If a vulnerability is being actively exploited, we accelerate.

## What you can expect from us

- We will acknowledge your report and credit you in the advisory unless you
  request anonymity
- We will keep you informed of remediation progress
- We will not pursue legal action against good-faith security research that
  follows this policy (no DMCA, no CFAA threats — see
  <https://disclose.io/safe-harbor/>)

## What we ask from you

- Give us reasonable time to respond before disclosing publicly
- Do not access, modify, or destroy data beyond what is necessary to
  demonstrate the vulnerability
- Do not perform attacks against other users
- Do not violate any laws

## No bug bounty (yet)

Otaman does not currently operate a paid bug bounty program. This may change
at a future commercial-offering milestone. Good-faith researchers will be
publicly credited regardless.

---

*This policy is part of the Otaman project's open-source commitments. See
[CONTRIBUTING.md](./CONTRIBUTING.md) for general contribution guidelines.*
