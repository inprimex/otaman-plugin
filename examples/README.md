# Examples

Two kinds of content live here:

| Path | What |
|---|---|
| [`example-platform/`](example-platform/) | **Runnable demo** — a complete 3-repo project (frontend/backend/specs) you can copy, init, and run in ~5 minutes |
| `*.yaml` | **Reference templates** — annotated `platform.yaml` patterns for common project shapes |

---

## Runnable demo — `example-platform/`

A self-contained project with:
- `platform.yaml` pre-configured with 3 repos, observers, launcher profiles, and a `git_host:` stub
- An OpenSpec change folder (`specs/openspec/changes/example-feature/`) showing the full proposal → design → tasks flow
- Stubs for React/TypeScript frontend and Python backend (enough for tech-stack detection)

**Quick start:**
```bash
cp -r example-platform ~/my-otaman-trial
cd ~/my-otaman-trial
for r in frontend backend specs; do
  cd $r && git init -q && git add . && git config user.email t@t && git config user.name t
  git commit -q -m "initial" && cd ..
done
cd example-platform-otaman
otaman init
otaman doctor
```

See [`example-platform/README.md`](example-platform/README.md) for the full walkthrough.

---

## Reference templates

Each `.yaml` file is a standalone annotated `platform.yaml` for a specific project shape.
Copy the one closest to your project and adjust.

| File | Shape |
|---|---|
| `fullstack-monorepo.yaml` | Single git repo with `apps/` and `packages/` (turborepo/nx/pnpm workspace) |
| `microservices.yaml` | 5–8 service repos + shared infra; one agent per service boundary |
| `ml-platform.yaml` | Data pipeline + model training + serving repos; includes notebook ownership |
| `healthcare-full.yaml` | Regulated environment; compliance-observer configured, audit-log refs |

To use one:
```bash
mkdir my-project-otaman
cp otaman-plugin/examples/microservices.yaml my-project-otaman/platform.yaml
# edit paths and owner names for your repos
otaman init
```
