# otaman-example: a curated starter project

This is a complete 3-repo otaman project you can clone, init, and run
in about 5 minutes. It demonstrates:

- A real `platform.yaml` with 3 repos, observers, OpenSpec, and a
  `git_host:` block stub
- The dedicated-folder layout (maestro folder named
  `example-platform-otaman/` next to the three managed repos)
- A populated OpenSpec change folder under `specs/openspec/changes/`
- Per-repo tech stack detection (React/TypeScript frontend, Python
  backend, Markdown-only specs)

## Layout

```
example-platform/
├── example-platform-otaman/        ← maestro folder (otaman state lives here)
│   ├── platform.yaml               ← project source of truth
│   ├── launch-settings.yaml.template
│   └── README.md
├── frontend/                        ← React/TS app (frontend-agent owns)
├── backend/                         ← Python service (backend-agent owns)
└── specs/                           ← OpenSpec (spec-agent owns)
```

## Try it

```bash
# 1. Clone or copy the example
cp -r path/to/otaman-plugin/examples/example-platform ~/my-otaman-trial
cd ~/my-otaman-trial

# 2. Init each subfolder as a real git repo (the example ships as one
#    flat tree; in real life each would be its own GitHub repo)
for r in frontend backend specs; do
  cd ~/my-otaman-trial/$r
  git init -q
  git add . && git config user.email t@t && git config user.name t
  git commit -q -m "initial"
done
cd ~/my-otaman-trial

# 3. Initialize otaman state
cd example-platform-otaman
otaman init

# 4. Verify
otaman doctor    # should pass
otaman status    # cross-repo dashboard

# 5. Open a tab in one of the repos and start an agent session
cd ~/my-otaman-trial/frontend
claude --plugin-dir <path-to-otaman-plugin> '/otaman:check'
```

## What this example skips

To keep clone-to-running tight, the example doesn't include:

- **Telegram bridge config** — see `references/telegram-setup.md`
- **Real `git_host:` PAT** — the `git_host:` block in `platform.yaml`
  is a commented stub; uncomment + add your PAT to enable PR features
- **Launcher folder** — see `references/launcher-walkthrough.md`
- **Working application code** — frontend/backend stubs are minimal,
  just enough for tech-stack detection
- **Tier templates / estimation artifacts** — not part of a normal
  active project, see `/otaman:presale` for those

## Promote to a real project

When you're ready to build a real multi-repo project:

1. Create your real frontend / backend / specs as separate top-level
   git repos (not nested folders)
2. Copy or adapt this `example-platform-otaman/platform.yaml` to
   `<your-project>-otaman/platform.yaml`, adjusting `repos:` paths
3. Add `git_host:` token (see `references/git-host-setup.md`)
4. Add launcher folder on your laptop (see `references/launcher-walkthrough.md`)
5. Add Telegram bridge for AFK approvals (see `references/telegram-setup.md`)

## Reference

This example backs the 15-minute getting-started walkthrough at
`references/getting-started.md`.
