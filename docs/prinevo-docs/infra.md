---
doc_type: infra
scope: context-profiler
last_audited_at: 2026-10-28T22:47:15Z
audited_by: repo-setup
source_commit: 9771c5bd4ba0f4697e2c4af48215d31ca6b55249
staleness_threshold_days: 14
---

# context-profiler — Infra

## Summary

No infrastructure. Context Profiler is a local workstation tool distributed as a
git checkout plus Claude Code / Codex plugin manifests. It runs no services,
opens no ports, and makes no network calls (no socket/HTTP client code found).

## Declared (IaC / Deployment Sources)

| Surface | Status | Evidence |
|---|---|---|
| Terraform / CDK / CloudFormation / Pulumi | not present | repo file list |
| Docker / Compose / Kubernetes / Helm | not present | repo file list |
| CI/CD workflows | not present (no `.github/`, no other CI config) | repo file list |
| Release / distribution | git clone + `ctx-profiler.sh setup`; plugin manifests `.claude-plugin/plugin.json`, `.codex-plugin/plugin.json` (v0.1.0) | manifests, README § Quick Install |
| Package registry | none | no packaging metadata |

Deployment ownership: the operator installs locally. No pipeline to conflict
with IaC, so no Deployment Ownership Gap; absence of CI is recorded as a
verification gap in `architecture.md`.

## Observed (Read-only Runtime)

Not applicable — no cloud, observability, data warehouse, or control-plane
surface is declared in the repo, and `factory.json` declares no `cloud`,
`observability`, `data`, or `infra_hints` integrations. No live provider calls
were made. No `SETUP_REQUIREMENT` lines are emitted because no optional
live-evidence surface was detected.

## Local Footprint

| Location | Purpose |
|---|---|
| `<home>/.claude/context-profiles/` | profile JSONL store, config, caches |
| `<home>/.claude/settings.json` | Claude hook registrations (written by setup) |
| `<home>/.claude/commands/`, `<home>/.codex/commands/` | slash command shims |
| `<home>/.codex/plugins/context-profiler/` | Codex plugin copy |
| `<home>/.local/bin/ctx-profile`, `ctx-profiler` | CLI shims |
| `/tmp/ctx-profiler-start/` | transient tool-duration stamps |
| Reads: `<home>/.claude/projects/`, `<home>/.codex/sessions/` | upstream transcripts |

## Observability

The tool is itself an observability product for agent sessions. Its own
operation has no logging/metrics: hooks swallow all exceptions silently
(recorded as a risk in `architecture.md`). Diagnostics: `ctx-profile doctor`.

## Gaps

- No CI: tests are not run automatically on change.
- No release/versioning automation; manifest versions are hand-maintained.

## Agent Work Log

- Inputs checked: repo tree, plugin manifests, `ctx-profiler.sh`, `config.py`,
  factory `factory.json`.
- Decision: declared-only, no live surfaces → no setup requirements.
- Next action: none for infra.
