---
doc_type: runtime-setup
scope: context-profiler
last_audited_at: 2026-10-28T18:57:09Z
audited_by: scanner
source_commit: 9771c5bd4ba0f4697e2c4af48215d31ca6b55249
staleness_threshold_days: 30
---

# context-profiler Runtime Setup

Portable candidate inputs only. Architecture boundaries live in [architecture.md](architecture.md); deployment posture in [infra.md](infra.md). Nothing here is verified on a host until Bring-up writes `local-setup/context-profiler.md`.

## Setup Metadata

| Field | Value |
|---|---|
| plan_version | 1 |
| Repo root token | `<repo-root>` |
| Setup mode | native (Python 3 + Bash); no containers |
| Build weight | light (no build step; interpreted) |
| Source commit | `9771c5bd4ba0f4697e2c4af48215d31ca6b55249` |
| Evidence status | candidate (scanner) |
| Local-setup baseline | `local-setup/context-profiler.md` — absent at scan time (`Runtime Setup Gap`: not yet verified by Bring-up) |
| Known gaps | `textual` not declared in any manifest; no CI |

## Runtime Unit Inventory

| unit_id | Root | Role | Setup mode | Service kind | Ports / endpoints | Evidence |
|---|---|---|---|---|---|---|
| `context-profiler` (root) | `<repo-root>` | Local CLI + TUI + Claude hook scripts + harness plugin | native | CLI / TUI / hooks | none (no network listener) | `ctx-profiler.sh`, `visualize.py`, `hooks/*.py` |

No independently deployable sub-units: hooks, importers, CLI, and TUI share one source tree, config, and lifecycle. No cross-repo capability edges.

## Dependencies And Startup

- Shared libraries: none (stdlib only); optional `textual` for `watch`.
- External services, databases, queues, caches: none.
- Host inputs (read-only): Claude transcripts at `$HOME/.claude/projects/` (config `claude_projects_dir`), Codex rollouts at `$HOME/.codex/sessions/` (config `codex_sessions_dir`). Both are optional; absent directories yield empty imports.
- Startup order: `setup` (once) → Claude Code sessions emit hooks → `watch`/CLI read profiles. No daemon.
- Provider-disabled/fake mode: tests use temp directories by patching `context_profiler.storage.PROFILE_DIR`; fixture transcripts are built inline in tests.

## Infrastructure Sources And Local Dependencies

- Service-local infrastructure: none (no Dockerfile, Compose, devcontainer, IaC, CI, or deploy scripts). Checked: repo file list.
- Dedicated/shared infra repos: none referenced (`factory.json::iac_repos` is unset; no deployment references in repo).
- Local dependency realization: host filesystem only.

## Machine Preparation

| Requirement | Source | Notes |
|---|---|---|
| Python 3 (`python3`) with `from __future__ import annotations`, `X | Y` types | source syntax | Version pin absent; scanner host used 3.14 |
| Bash | `ctx-profiler.sh`, `analyze.sh` (`#!/usr/bin/env bash`, `[[ ]]`) | |
| `textual` | `visualize.py`; `setup --install-textual` runs `python3 -m pip install --user textual` | Optional; required for `watch` and `tests/test_visualize_sessions.py` |
| `git` | `formatting.git_branch_for` | Optional; branch metadata only |
| Interactive TTY | `watch` refuses non-TTY | Human-only surface |
| OS | POSIX paths (`/tmp/ctx-profiler-start`) | Windows: unknown |

## Lifecycle And Data

Working directory: `<repo-root>`.

| Step | Command (candidate) | Notes |
|---|---|---|
| install / setup | `bash ./ctx-profiler.sh setup [--install-textual]` | **Host-mutating**: writes `$HOME/.claude/settings.json` hooks, `$HOME/.claude/commands/` and `$HOME/.codex/commands/` shims, `$HOME/.codex/plugins/context-profiler/`, `$HOME/.local/bin/ctx-profile{,r}`, config. Run only with operator approval on the target host. |
| build | none | interpreted |
| syntax check | `python3 -m py_compile visualize.py context_profiler_core.py context_profiler/*.py context_profiler/importers/*.py hooks/*.py codex-profiler.py` | `AGENTS.md`, `README.md` |
| test | `python3 -m unittest discover -s tests -v` | Use an isolated `HOME` for safety; tests patch `PROFILE_DIR` to temp dirs |
| start (TUI) | `ctx-profile watch [claude|codex|all|<source>]` or `bash ./ctx-profiler.sh watch` | TTY only |
| one-shot import | `bash ./ctx-profiler.sh codex-import --limit 5` | |
| health | `ctx-profile doctor`, `ctx-profile status` | |
| teardown / cleanup | `ctx-profile clean [--days N] [--dry-run]`; `ctx-profile disable` | Raw Codex transcripts deleted only with `--include-codex-transcripts` |

Data initialization: not applicable (profiles accrue from usage). Caches `.session-index.json`, `.import-cursors.json` are rebuildable. Remove `__pycache__` before commit (`AGENTS.md`).

## Configuration And Credentials

Non-secret config: `<profile-dir>/config.json` where `<profile-dir>` = `$HOME/.claude/context-profiles` (hardcoded via `Path.home()`). Precedence: file values override `DEFAULT_CONFIG`; default `advice_ignore_path_patterns` are always re-merged. Invalid/missing JSON → defaults. Keys: `enabled`, `spike_threshold_tokens` (5000), `refresh_interval_seconds` (2), `follow_latest_session`, `sources` (`["claude","codex"]`), `codex_sessions_dir`, `codex_import_on_refresh`, `codex_import_limit` (25), `claude_projects_dir`, `claude_import_on_refresh`, `claude_import_limit` (25), `hide_ignored_paths_by_default`, `profile_rotation_enabled`, `profile_max_part_bytes` (10,000,000), `auto_cleanup_enabled`, `auto_cleanup_interval_hours` (24), `cleanup_retention_days` (5), `advice_ignore_path_patterns`. Source: `context_profiler/config.py`.

Environment variables: `CTX_PROFILER_DIR` (overrides plugin dir in `ctx-profiler.sh`/`analyze.sh`), `HOME`.

Credentials: none required. No secrets, tokens, or provider logins. Captured profiles may contain command text, file paths, and output previews from observed sessions — treat `<profile-dir>` as sensitive host-local data.

## Operations And Verification

- Process: foreground Textual app (`visualize.py`) or one-shot CLI; hooks run as short async processes spawned by Claude Code.
- Logs: none emitted; state inspected via `ctx-profile status|doctor|summary`.
- Smallest smoke: `python3 -m unittest discover -s tests` (expect all pass with `textual` installed; scan-time result 16/17 pass, 1 error for missing `textual`). CLI smoke: `bash ./ctx-profiler.sh status` (creates/merges config — host-local write).
- Evidence owner: Bring-up / Verify.

## Unresolved Inputs

| Unit | Input kind | Evidence checked | Needed for | Safe options | Materiality | Recovery |
|---|---|---|---|---|---|---|
| context-profiler | `textual` package | no manifest; `setup --install-textual` | `watch`, TUI test | install into an isolated venv; or skip TUI test declared-only | low | Bring-up installs or records skip |
| context-profiler | Python version floor | source syntax only | all | use host `python3` ≥ 3.9 (inferred: `str.removeprefix`; union annotations are deferred by `from __future__ import annotations`) | low | Bring-up records version used |
| context-profiler | Approval for host-mutating `setup` | `ctx-profiler.sh setup` writes under `$HOME` | end-to-end hook capture | run with isolated `HOME`; or skip | medium | Bring-up/Verify asks via shared gate before running against a real home dir |

## Runtime Setup Questions

No blocking questions. Candidates are listed in Unresolved Inputs; Bring-up or Verify owns any resulting gate.

## Agent Work Log

- Inputs: shell entrypoints, config module, tests, README/AGENTS. Decisions: single native unit, no ports/credentials. Gaps: `textual` undeclared, local-setup baseline absent. Next: Bring-up verification.
