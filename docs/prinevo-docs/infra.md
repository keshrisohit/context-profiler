---
doc_type: infra
scope: context-profiler
last_audited_at: 2026-10-28T21:52:36Z
audited_by: repo-setup
source_commit: 9771c5bd4ba0f4697e2c4af48215d31ca6b55249
staleness_threshold_days: 14
---

# context-profiler — Infra

## Access Decision

No cloud, observability, data-warehouse, or runtime control-plane surfaces were
detected in repo evidence, and factory hints (`cloud`, `observability`, `data`,
`infra_hints`, `iac_repos`) are empty. No live read-only access is needed; no
setup requirements are emitted.

## Runtime / Deployment Location

- Runs entirely on the operator's workstation as local processes: `ctx-profile` CLI, `visualize.py` Textual dashboard, and Claude Code hook subprocesses.
- Distribution: git clone + `bash ./ctx-profiler.sh setup`; also packaged as a Claude plugin (`.claude-plugin/plugin.json`) and a Codex plugin (`.codex-plugin/plugin.json`), both version `0.1.0`.
- No containers, servers, functions, clusters, queues, or databases. No network listener or outbound network call.

## Runtime Config / Observability

- Config source: `$HOME/.claude/context-profiles/config.json`, defaults in `context_profiler/config.py`. Details in [`runtime-setup.md`](runtime-setup.md).
- Secrets: none.
- Logs/metrics/traces: none emitted by the tool itself; it *is* an observability tool for agent sessions, storing its output as local JSONL profiles. Hook errors are swallowed silently.
- Data sensitivity: profiles hold command text, prompt/output previews, and file paths from observed sessions; retention default 5 days.

## Infra Ownership Map

| Concern | Owner |
|---|---|
| Code | this repo |
| Service-local IaC | none |
| Shared/platform IaC | none |
| Environment / network | operator workstation |
| Security / secrets | not applicable |
| Data | local user home directory |
| Observability | not applicable |
| Release | manual git clone / plugin install; no CI/CD |

## Deployment Ownership Gap

No CI/CD, release pipeline, or tagging evidence exists. Version is duplicated
in `context_profiler/__init__.py` and both plugin manifests with no automated
sync. Rollback = checkout previous commit and rerun `setup`.

## Live Access Gap

Not applicable — no live surface detected.

## Observability Config Gap

Not applicable for deployed observability; hook failures have no diagnostic
log (recorded as an operational risk in `architecture.md`).

## Agent Work Log

- Inputs checked: repo tree for Docker/Compose/IaC/CI files (none), plugin manifests, setup script, factory hints.
- Decision: declared-only; no provider preflight needed.
- Next action: none for infra.
