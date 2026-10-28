---
doc_type: local-setup
scope: context-profiler
last_audited_at: 2026-10-28T22:47:15Z
audited_by: repo-setup
source_commit: 9771c5bd4ba0f4697e2c4af48215d31ca6b55249
staleness_threshold_days: 30
---

# context-profiler — Runtime Setup

Portable, repo-scoped setup facts. Current-machine resolution and proof belong
in `local-setup/context-profiler.md` (factory-owned; not yet captured — see
Unresolved Inputs).

## Setup Metadata

| Field | Value |
|---|---|
| Plan version | 1 |
| Repo root | `<repo-root>` |
| Setup mode | native (no Docker/Compose); local developer tool |
| Source fingerprint | `source_commit` 9771c5bd4ba0f4697e2c4af48215d31ca6b55249; inputs: `ctx-profiler.sh`, `analyze.sh`, `context_profiler/config.py`, `README.md`, `AGENTS.md`, `tests/` |
| Packaging | none (no `pyproject.toml`, `requirements*.txt`, `setup.py`); run from checkout |

## Runtime Unit Inventory

| Unit | Root | Role | Run command | Ports / endpoints |
|---|---|---|---|---|
| `ctx-profile` CLI | `<repo-root>` | operator/agent CLI | `bash <repo-root>/ctx-profiler.sh <subcommand>` (or `ctx-profile` after setup) | none |
| Dashboard | `<repo-root>/visualize.py` | interactive TUI (requires TTY) | `ctx-profile watch [claude\|codex\|all]` | none |
| Claude hooks | `<repo-root>/hooks/` | invoked by Claude Code per hook event | registered by setup in Claude user settings | none |
| Codex importer | `<repo-root>/codex-profiler.py` | one-shot or polling import | `ctx-profile codex-import --limit N` | none |

Single repo, single deployable unit; no monorepo or cross-repo capability edges.

## Dependencies And Startup

- Python 3 (stdlib only for core; scanner sandbox had 3.14). Minimum version
  not declared — see Unresolved Inputs.
- Bash (scripts use `set -euo pipefail`, `[[ ]]`, `BASH_SOURCE`).
- `textual` Python package — required only for `watch` and
  `tests/test_visualize_sessions.py`; installed by `ctx-profile setup --install-textual`
  (`python3 -m pip install --user textual`). Version not pinned.
- `git` CLI — optional, used for branch labels.
- Startup graph: no services. Data sources must exist to show data: Claude Code
  (hooks + `<home>/.claude/projects`) and/or Codex (`<home>/.codex/sessions`).

## Infrastructure Sources And Local Dependencies

- No Dockerfile, Compose, Kubernetes, Terraform, or CI config in repo.
- No dedicated/shared infra repo referenced; `factory.json` declares no
  `iac_repos`.
- Local capability realization: filesystem only — profile store at
  `<home>/.claude/context-profiles/`, transient stamps at `/tmp/ctx-profiler-start/`.
- Shared libraries: none beyond stdlib + `textual`.

## Machine Preparation

1. Clone the repo to `<repo-root>`.
2. `bash ./ctx-profiler.sh setup [--install-textual]` — idempotent; writes to
   `<home>/.claude/settings.json` (hooks), `<home>/.claude/commands/`,
   `<home>/.codex/commands/`, `<home>/.codex/plugins/context-profiler/`,
   `<home>/.local/bin/ctx-profile` and `ctx-profiler`. Warns if
   `<home>/.local/bin` is not on `PATH`.
3. `ctx-profile doctor` to confirm shims, config, textual, and transcript discovery.

Note: setup mutates user-level Claude/Codex configuration. In sandboxes, run with
an isolated `HOME` to avoid touching real user settings.

## Lifecycle And Data

- Data init: `ensure_config` creates `<home>/.claude/context-profiles/config.json`
  with defaults on first CLI/dashboard run.
- Retention: profiler profiles auto-deleted after `cleanup_retention_days` (5);
  manual `ctx-profile clean [--days N] [--dry-run]`. Raw Codex transcripts only
  with `--include-codex-transcripts`.
- Caches `.session-index.json`, `.import-cursors.json`, `.cleanup-state.json` are
  rebuildable and safe to delete.
- Enable/disable capture: `ctx-profile enable|disable` (config `enabled`).
- Uninstall: no command; evidence absent (manual removal of hook entries and shims).

## Configuration And Credentials

| Source | Kind | Notes |
|---|---|---|
| `<home>/.claude/context-profiles/config.json` | non-secret config | keys listed in `modules/profile-store.md`; paths overridable (`codex_sessions_dir`, `claude_projects_dir`) |
| `CTX_PROFILER_DIR` env var | non-secret | overrides plugin/source directory for scripts |
| `HOME` | non-secret | determines all default paths |
| Credentials | none | no API keys, tokens, or network access |

Secret material: none required (`<host-credentials-root>` not used).

## Operations And Verification

- Tests: `python3 -m unittest discover -s tests -v`. Scanner run (isolated
  `HOME`, no bytecode): 17 tests, 16 pass, 1 error without `textual`
  (`tests/test_visualize_sessions.py`). Install `textual` for a full pass.
- Syntax check: `python3 -m py_compile visualize.py context_profiler_core.py context_profiler/*.py context_profiler/importers/*.py codex-profiler.py hooks/*.py`.
- Smoke: `ctx-profile status`, `ctx-profile doctor`, `ctx-profile codex-import --limit 5`.
- Dashboard verification needs an interactive TTY; it exits 0 with guidance otherwise.
- Repo rule: remove `__pycache__` before committing.

## Runtime Setup Questions

None blocking.

## Unresolved Inputs

| Input | Why | Resolver |
|---|---|---|
| Minimum Python version | not declared; only 3.14 exercised by scanner | bring-up / Verify |
| `textual` version | unpinned | bring-up |
| `local-setup/context-profiler.md` | not yet captured (Runtime Setup Gap) | `/prinevo-bring-up context-profiler` |
| Live Claude/Codex data for smoke | sandbox has no real sessions | operator or Verify with fixtures |
