# Example feature proposal

## Problem statement

Users currently have to authenticate twice — once with the frontend
and again to access the API directly. This is a known papercut that
generates support tickets weekly.

## Proposed solution

Implement OAuth2 + JWT shared between frontend and backend so a single
login covers both surfaces.

## Out of scope

- Multi-tenant org switching (separate change)
- Social login providers (separate change)

## Acceptance criteria

- [ ] Logging in via frontend creates a JWT valid for backend API calls
- [ ] Token refresh works without re-prompt for active sessions < 24h
- [ ] Logout invalidates token on both surfaces
