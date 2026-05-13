# Example feature — implementation tasks

## Backend tasks

- [ ] 1.1 Add `auth-svc` module to backend repo
- [ ] 1.2 Implement JWT signing + verification
- [ ] 1.3 Add `/auth/login`, `/auth/refresh`, `/auth/logout` endpoints
- [ ] 1.4 Add Redis-backed refresh-token storage
- [ ] 1.5 Add integration tests covering 6 acceptance criteria

## Frontend tasks

- [ ] 2.1 Add login form component
- [ ] 2.2 Add JWT storage in httpOnly cookies (set by auth-svc)
- [ ] 2.3 Add automatic token refresh logic
- [ ] 2.4 Add logout button + flow

## Cross-cutting

- [ ] 3.1 Update API contracts in specs/contracts/ (auth endpoints)
- [ ] 3.2 Add CSP headers in frontend deployment config
- [ ] 3.3 Document HSM key rotation procedure
