# Example feature — design

## Architecture

```
[ frontend ] --login-> [ auth-svc ] --JWT-> [ backend API ]
```

`auth-svc` is a new component owned by `backend-agent`. JWT signing key
lives in HSM (see compliance-guide.md). Refresh tokens stored in Redis
with TTL = 7 days.

## Technology choices

- JWT library: `python-jose` (backend), `jose-jwt` npm pkg (frontend)
- Storage: Redis 7 (already in stack for sessions)
- Algorithm: RS256

## Threat model

- Token theft via XSS — mitigated by httpOnly cookies + CSP headers
- Refresh-token replay — mitigated by single-use refresh tokens
- Key rotation — quarterly cadence with overlap window
