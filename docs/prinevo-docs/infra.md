---
doc_type: infra
scope: context-profiler
last_audited_at: 2026-10-28T18:57:09Z
audited_by: scanner
source_commit: 9771c5bd4ba0f4697e2c4af48215d31ca6b55249
staleness_threshold_days: 14
---

# context-profiler Infra

## Access Decision

No cloud, observability, data-warehouse, or runtime control-plane surfaces were detected in repo evidence, and `factory.json` declares no `cloud`, `observability`, `data`, `infra_hints`, or `iac_repos`. No live provider calls were made; none are needed. No `SETUP_REQUIREMENT` lines are emitted because no optional live-evidence surface exists.

## Runtime / Deployment Location

- Runs as local processes on a developer host: Bash wrappers, a foreground Textual TUI, and short-lived Claude Code hook processes (`async: true` in `$HOME/.claude/settings.json`).
- Distribution: git clone + `bash ./ctx-profiler.sh setup`; also packaged as Claude and Codex plugins (`.claude-plugin/plugin.json`, `.codex-plugin/plugin.json`, version `0.1.0`). Setup copies the Codex plugin to `$HOME/.codex/plugins/context-profiler`.
- No containers, Kubernetes, serverless, VMs, ports, health URLs, databases, or queues.

## Deployment Source Summary

| Kind | Present | Evidence |
|---|---|---|
| IaC (Terraform/CDK/Pulumi/Helm/K8s/Compose) | no | repo file list |
| Dockerfile / devcontainer | no | repo file list |
| CI/CD workflows | no (`.github/` absent) | repo file list |
| Release process | manual; plugin manifests carry version; `AGENTS.md § Git Rules` describes squash/amend history | `AGENTS.md` |

Deployment ownership: the repo owner via manual install. No `Deployment Ownership Gap` (no conflicting deploy sources). Terraform: not applicable.

## Runtime Config / Observability

- Config source: `$HOME/.claude/context-profiles/config.json` merged over `DEFAULT_CONFIG` (see [runtime-setup.md](runtime-setup.md#configuration-and-credentials)).
- Secrets: none.
- Feature flags: `enabled` (global on/off checked by every hook and importer), import-on-refresh toggles, rotation and auto-cleanup toggles.
- Logs/metrics/traces: the tool emits none of its own; it *is* a local observability tool for agent sessions. Hooks swallow errors silently, so failures are invisible except via missing events (`ctx-profile doctor` is the only diagnostic).
- Data retention: profiles auto-cleaned after `cleanup_retention_days` (default 5), throttled per `auto_cleanup_interval_hours`; large profiles rotate at `profile_max_part_bytes`.
- Sensitive data: profiles store command text (`cmd_full`), output previews, prompts (`prompt_preview`, `description_full`), and file paths from observed sessions. Host-local only; no export.

## Live Access Gap

Not applicable — no live surfaces.

## Observability Config Gap

Not applicable for external observability. Internal note: hook failures are silent (`except Exception: pass` in `hooks/*.py`); there is no error log for diagnosing dropped capture.

## Infra Ownership Map

| Area | Owner |
|---|---|
| Code | this repo |
| Service-local IaC | none |
| Shared/platform IaC | none |
| Environment / network | developer host (no network use) |
| Security / secrets | not applicable; host user owns `$HOME` data |
| Data / warehouse | not applicable |
| Observability | not applicable |
| Host integration points | `$HOME/.claude/settings.json` (hooks), `$HOME/.claude/commands/`, `$HOME/.codex/commands/`, `$HOME/.codex/plugins/`, `$HOME/.local/bin/` — written by `ctx-profiler.sh setup` |

## Agent Work Log

- Inputs: repo file list, plugin manifests, `ctx-profiler.sh`, `config.py`, `factory.json` hints. Decisions: declared-only local tool, no provider surfaces. Gaps: none material. Next: none for infra.
