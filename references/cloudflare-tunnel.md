# Cloudflare Tunnel deployment

Deploy the otaman-bridge + Zitadel behind a single Cloudflare Tunnel so
teammates can reach the bridge from anywhere over public HTTPS — no
Netbird, no VPN, no LAN access required.

**Audience:** team admins deploying the otaman-bridge stack to a host
behind Cloudflare. Roman/devs joining an *existing* team should read
[team-mode setup](team-mode-setup.md) instead.

**Prerequisites:**
- A Cloudflare account with a domain you control (zone management API access).
- `cloudflared` installed on the host. Verified with v2026.x; the older 2024.x line works for the basic tunnel, but the bridge needs at least the post-2025-04 release for the originRequest options used below.
- Otaman stack already deployed locally on the host: `otaman-bridge` daemon listening on `127.0.0.1:8090`, `otaman-runner` on `127.0.0.1:8091`, Zitadel + Postgres in `docker compose` on `127.0.0.1:18080`.
- Zitadel bootstrap already run (`zitadel-bootstrap.py` from `otaman-deploy/scripts/`).

---

## The gotcha that drives the design

**Cloudflare Tunnel cannot forward HTTP/2 cleartext (h2c) to the
origin.** Zitadel documents this limitation at
[zitadel.com/docs/self-hosting/manage/reverseproxy/cloudflare_tunnel](https://zitadel.com/docs/self-hosting/manage/reverseproxy/cloudflare_tunnel):

> "The Cloudflare tunnel client currently has an issue which disallows
> it to force HTTP/2 usage towards the origin."

Zitadel's `/management/v1/*` mgmt API is gRPC-Gateway-wrapped — it
needs h2c for proper `:authority`/Host header propagation during JWT
audience validation. Without h2c, **client_credentials JWTs are
rejected with `Errors.Token.Invalid (AUTH-7fs1e)`** on every mgmt
call, while OIDC endpoints (REST-over-HTTP/1.1) work fine.

The fix is **PAT auth** instead of client_credentials for the bridge's
mgmt API calls. PATs are opaque DB-introspected tokens that bypass the
JWT validation interceptor entirely. They're a documented Zitadel auth
mechanism, not a security bypass:

- Bound to one machine user (same as a client secret)
- Scoped by that user's roles (`otaman-dcr-shim` has `PROJECT_OWNER` only)
- Revocable independently
- Optional explicit expiry

The bridge already supports both modes and prefers PAT when set. The
bootstrap script (ships with otaman-deploy) creates the PAT automatically.

---

## Step 1: Configure cloudflared ingress

Edit `/etc/cloudflared/config.yml` to route two hostnames at this
host's local services. **Adjust the hostnames** to ones in your
Cloudflare-managed zone:

```yaml
tunnel: <your-tunnel-uuid>
credentials-file: /etc/cloudflared/<your-tunnel-uuid>.json
ingress:
  # Whatever else you were already routing first.
  - hostname: otaman.<your-team-domain>
    service: http://localhost:8090
  - hostname: otaman-auth.<your-team-domain>
    service: http://localhost:18080
  - service: http_status:404
```

Then create the DNS CNAMEs (cloudflared adds them via the Cloudflare
API; no manual dashboard work):

```bash
cloudflared tunnel route dns <tunnel-name> otaman.<your-team-domain>
cloudflared tunnel route dns <tunnel-name> otaman-auth.<your-team-domain>
```

Apply by restarting cloudflared (the systemd unit ships without an
`ExecReload=` so plain `reload` invokes the binary without args):

```bash
sudo systemctl restart cloudflared
```

Verify both hostnames respond:

```bash
curl -fsS https://otaman.<your-team-domain>/status
curl -fsS https://otaman-auth.<your-team-domain>/debug/healthz
```

The first returns the bridge's status JSON; the second returns `ok` from Zitadel.

---

## Step 2: Reconfigure Zitadel for HTTPS / new ExternalDomain

Zitadel persists its `ExternalDomain` to the database at first-init.
If your sandbox was bootstrapped with a different domain (a netbird IP,
LAN IP, etc.), you must either:

- **Drop the Postgres volume and re-init** (predictable, loses users
  and registered apps — fine for fresh setups), or
- Re-issue domain via the Zitadel admin API (less destructive, more
  steps, beyond this walkthrough — see [Zitadel custom domain
  docs](https://zitadel.com/docs/self-hosting/manage/custom-domain)).

For a fresh deployment, just set the env vars correctly before first
boot:

```bash
# In /etc/otaman/secrets.env (or compose env-file)
ZITADEL_EXTERNAL_DOMAIN=otaman-auth.your-team.example
ZITADEL_EXTERNAL_PORT=443
ZITADEL_EXTERNAL_SECURE=true
```

And in your compose file's Zitadel service env block:

```yaml
ZITADEL_EXTERNALSECURE: "${ZITADEL_EXTERNAL_SECURE:-false}"
ZITADEL_EXTERNALDOMAIN: ${ZITADEL_EXTERNAL_DOMAIN}
ZITADEL_EXTERNALPORT: ${ZITADEL_EXTERNAL_PORT:-443}
```

After Zitadel starts, `curl https://otaman-auth.your-team.example/.well-known/openid-configuration | jq .issuer` should print `"https://otaman-auth.your-team.example"`.

---

## Step 3: Bootstrap (creates PAT)

Run `zitadel-bootstrap.py` with the public HTTPS URL. The bootstrap
creates the otaman-dcr-shim machine user, grants it PROJECT_OWNER, and
issues a PAT — all emitted in the env fragment:

```bash
python3 /path/to/otaman-deploy/scripts/zitadel-bootstrap.py \
    --base-url https://otaman-auth.your-team.example \
    --external-host otaman-auth.your-team.example \
    --pat-file /path/to/zitadel-init/pat.txt \
    --output /etc/otaman/secrets.env.fragment
```

The output env fragment includes:

```
OIDC_ISSUER=https://otaman-auth.your-team.example
OIDC_ORG_ID=<numeric>
OIDC_PROJECT_ID=<numeric>
OIDC_AUDIENCE_BRIDGE=<numeric>
OTAMAN_DCR_SHIM_PAT=<opaque token>           # <= used by bridge to call mgmt API
OTAMAN_DCR_SHIM_CLIENT_ID=otaman-dcr-shim    # <= legacy fallback (won't work behind Cloudflare)
OTAMAN_DCR_SHIM_SECRET=<secret>              # <= legacy fallback
```

Append this fragment to `/etc/otaman/secrets.env`.

---

## Step 4: Configure the bridge

The bridge reads the same env vars at startup. Critical pieces:

```bash
# Tell the bridge its public URL so it advertises HTTPS in the .well-known
# discovery doc (without this, the bridge advertises http://<Host header>,
# which is the cloudflared-internal URL).
OTAMAN_BRIDGE_PUBLIC_URL=https://otaman.your-team.example

# Enable the DCR shim.
OTAMAN_DCR_SHIM=1

# PAT (preferred behind any TLS terminator that can't forward h2c).
OTAMAN_DCR_SHIM_PAT=<from bootstrap>
```

Restart the bridge daemon. The startup log should report:

```
DCR shim enabled (type=zitadel mgmt=https://otaman-auth.your-team.example ...)
OIDC validator enabled (issuer=https://otaman-auth.your-team.example ...)
```

---

## Step 5: Smoke-test the full flow

From a machine that **does not** have any VPN/mesh access to the
host (your laptop on a coffee shop wifi is the ideal test):

```bash
# 1. Public endpoints reachable
curl -fsS https://otaman.your-team.example/.well-known/oauth-protected-resource | jq .authorization_servers
curl -fsS https://otaman-auth.your-team.example/.well-known/openid-configuration | jq .issuer

# 2. Bridge protected route returns 401 with the standard challenge
curl -i -X POST https://otaman.your-team.example/mcp \
    -H "Content-Type: application/json" \
    -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' \
  | head -10
# Expect: HTTP/2 401 + www-authenticate: Bearer resource_metadata="..."
```

Then in a Claude Code session pointing at the bridge URL (see
[team-mode setup](team-mode-setup.md) for the `.mcp.json`), run
`/mcp` => Authenticate => log in via Zitadel in the browser => tool
calls succeed.

---

## Known gotchas

### Cloudflare's Bot Fight Mode blocks urllib

Any Python `urllib` request through Cloudflare gets HTTP 403 by default
because urllib's default User-Agent (`Python-urllib/3.x`) trips the bot
rules. The otaman codebase sets an explicit `User-Agent` header in four
places that go through Cloudflare:

- `otaman-bridge/src/otaman_bridge/dcr_shim.py`: `fetch_upstream_metadata`, `_fetch_client_credentials_token`, `_mgmt_request`
- `otaman-core/src/otaman_core/auth_oidc.py`: `_default_jwks_fetcher`
- `otaman-deploy/scripts/zitadel-bootstrap.py`: `_request`, `discover_issuer`

If you add a new path that calls Zitadel from Python, set
`User-Agent: <your-component>/<version>` on the Request explicitly. Don't
rely on urllib defaults.

### `client_credentials` JWT path fails on `/management/v1/*`

This is the whole reason for the PAT path. If you see
`Errors.Token.Invalid (AUTH-7fs1e)` in bridge logs after the OAuth flow
completes, ensure `OTAMAN_DCR_SHIM_PAT` is set in the bridge's env.
The bridge prefers PAT over client_credentials when both are set; only
client_credentials is broken behind Cloudflare Tunnel.

### Zitadel rejects `ExternalDomain` mismatch as 404

If you ever curl Zitadel via a hostname different from what
`ZITADEL_EXTERNALDOMAIN` was set to, Zitadel returns:

```
unable to set instance using origin ... (ExternalDomain is X)
ID=QUERY-1kIjX Message=Instance not found
```

This is Zitadel's origin check, not a real 404. Fix: align
`ZITADEL_EXTERNAL_DOMAIN` (in env) with the hostname clients use
publicly.

### `systemctl reload cloudflared` errors

The systemd unit installed by cloudflared `service install` doesn't
declare `ExecReload=`, so `systemctl reload` invokes the binary without
args and you see "Too few arguments. Use `cloudflared tunnel run`...".
Use `restart` instead. Brief tunnel downtime (~5s) covers any
co-located services on the same tunnel.

---

## What's next

- [Team-mode setup](team-mode-setup.md) — share with each developer joining the team.
- [MCP tools reference](../reference/mcp-tools.md#otaman-bridge-7-tools) — the seven team-mode tools.
- [Auth architecture](../architecture/team-mode-auth.md) — DCR shim, PAT-vs-JWT, role gates.
