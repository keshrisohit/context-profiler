# Claude Code Rules

Rules are hard constraints loaded into every turn via glob scoping. They are permanent context — so keep them rare and narrow.

## When to add a rule

Add a rule **reactively, only after something breaks**. Do not pre-create rules for hypothetical problems — they bloat permanent context and dilute attention.

Examples of incidents that justify a rule:

- Agent committed `.env` → `no-secrets.md` with `globs: **/.env*`
- Agent skipped a migration → `migrations-required.md` with `globs: **/migrations/**`
- Agent wrote Dockerfile without pinning → `dockerfile-pinning.md` with `globs: **/Dockerfile*`

## Shape of a rule

```markdown
---
globs: **/Dockerfile*
---

Pin all base images to a specific digest (`image@sha256:...`).
Reason: floating tags broke the 2026-03 prod deploy.
```

## Guidelines

- Prefer narrow globs. `globs: **` loads the rule everywhere and should be used sparingly.
- Keep each rule under ~30 lines.
- Every rule should trace back to a real incident.
- If a rule hasn't fired / been needed in a long time, consider removing it.

See the factory-level `docs/harness/guidelines/repo-setup/README.md` for the full tiering framework.
