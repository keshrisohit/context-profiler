---
doc_type: runtime-setup
scope: context-profiler
last_audited_at: 2026-10-28T21:52:36Z
audited_by: scanner
source_commit: 9771c5bd4ba0f4697e2c4af48215d31ca6b55249
staleness_threshold_days: 30
---

# context-profiler — Runtime Setup

Portable candidate inputs. Nothing here is verified by Bring-up yet.

## Setup Metadata

| Field | Value |
|---|---|
| plan_version | 1 |
| Repo root token | `<repo-root>` |
| Setup mode | native (Python 3 + bash), no containers |
| Build weight | light — no build step, no package manifest (`pyproject.toml` / `requirements.txt` absent) |
| Source commit | `9771c5bd4ba0f4697e2c4af48215d31ca6b55249` |
| Evidence status | candidate (scanner) |
| Local baseline | `<factory-root>/local-setup/context-profiler.md` — absent (Runtime Setup Gap until Bring-up runs) |
| Known gaps | No declared Python version or dependency manifest; `textual` version unpinned |

## Runtime Unit Inventory

| unit_id | Root | Role | Setup mode | Service kind | Ports / endpoints | Evidence |
|---|---|---|---|---|---|---|
| `context-profiler` | `<repo-root>` | Local CLI + hook scripts + TUI | native | CLI / plugin | none (no network listener) | candidate |

Sub-surfaces sharing the same unit (not separate units): `ctx-profiler.sh` /
`analyze.sh` CLI, `visualize.py` dashboard (needs TTY), `hooks/*.py` (spawned by
Claude Code), `codex-profiler.py` importer. Cross-repo capability edges: none.

## Dependencies And Startup

- Shared libraries: none from other repos.
- External tools: `python3`, `bash`, optional `git` (branch labels), optional `textual` (dashboard and `tests/test_visualize_sessions.py`).
- Upstream data inputs (read-only): Claude transcripts `$HOME/.claude/projects/**/*.jsonl`, Codex rollouts `$HOME/.codex/sessions/**/*.jsonl` (both configurable via `claude_projects_dir`, `codex_sessions_dir`). Absence yields empty imports, not errors.
- Startup order: `setup` (writes config + hooks + shims) → any CLI command or `watch`. No services, databases, queues, or emulators.
- Provider-disabled mode: tests run fully offline with `PROFILE_DIR` patched to temp dirs.

## Infrastructure Sources And Local Dependencies

- Service-local infrastructure: none (no Dockerfile, Compose, devcontainer, IaC, CI, or deploy workflows).
- Dedicated/shared infra repos: none referenced (`factory.json::iac_repos` empty).
- Local dependency realization: host filesystem directories under `$HOME` and `/tmp/ctx-profiler-start/`.

## Machine Preparation

| Prerequisite | Source | Notes |
|---|---|---|
| Python 3 (uses `str.removeprefix`, PEP 604 types via `__future__`) → ≥ 3.9 | inferred from source | Scan host had 3.14 |
| bash | `ctx-profiler.sh`, `analyze.sh` shebangs | |
| `textual` | `visualize.py`, `ctx-profiler.sh setup --install-textual` (`pip install --user textual`) | optional except for dashboard/its test |
| git | `formatting.git_branch_for` | optional |
| `$HOME/.local/bin` on `PATH` | `install_bin_shim` | setup prints a note if missing |
| Interactive TTY | `watch` guard | dashboard only |

## Lifecycle And Data

| Step | Command (cwd `<repo-root>`) | Status |
|---|---|---|
| Install / setup | `bash ./ctx-profiler.sh setup [--install-textual]` | candidate; mutates host config (see Configuration) |
| Syntax check | `python3 -m py_compile context_profiler_core.py context_profiler/*.py context_profiler/importers/*.py codex-profiler.py visualize.py hooks/*.py` | candidate |
| Test | `python3 -m unittest discover -s tests -v` | scanner run: 16 pass, 1 import error without `textual` |
| Run CLI | `ctx-profile status` / `latest` / `explain --session <id>` | candidate |
| Run dashboard | `ctx-profile watch [claude|codex|all]` in a real terminal | candidate |
| Health | `ctx-profile doctor` | candidate |
| Import once | `bash ./ctx-profiler.sh codex-import --limit 5` | candidate |
| Teardown | `ctx-profile disable`; remove hook entries from `$HOME/.claude/settings.json`, shims, and `$HOME/.codex/plugins/context-profiler` manually | no uninstall command (Runtime Setup Gap) |
| Data init | none required; profiles created on first event. Cleanup: `ctx-profile clean [--days N] [--dry-run]` | |

Safe testing note: running the CLI or setup on a host touches the real
`$HOME`; for isolated verification set `HOME` to a temporary directory.

## Configuration And Credentials

Config file: `$HOME/.claude/context-profiles/config.json` (created by
`ensure_config`; missing keys back-filled from `DEFAULT_CONFIG` in
`context_profiler/config.py`). Keys: `enabled`, `spike_threshold_tokens`
(5000), `refresh_interval_seconds` (2), `follow_latest_session`, `sources`
(`["claude","codex"]`), `codex_sessions_dir`, `codex_import_on_refresh`,
`codex_import_limit` (25), `claude_projects_dir`, `claude_import_on_refresh`,
`claude_import_limit` (25), `hide_ignored_paths_by_default`,
`profile_rotation_enabled`, `profile_max_part_bytes` (10,000,000),
`auto_cleanup_enabled`, `auto_cleanup_interval_hours` (24),
`cleanup_retention_days` (5), `advice_ignore_path_patterns`. Malformed config
is treated as `{}`.

Environment variables: `CTX_PROFILER_DIR` (overrides plugin/source dir in
`ctx-profiler.sh` / `analyze.sh`), `HOME`.

Host files written by setup: `$HOME/.claude/settings.json` (`hooks` key),
`$HOME/.claude/commands/context-profiler.md`,
`$HOME/.codex/commands/context-profiler.md`,
`$HOME/.codex/plugins/context-profiler/`, `$HOME/.local/bin/ctx-profile`,
`$HOME/.local/bin/ctx-profiler`.

Credentials: none required.

## Operations And Verification

- No containers or process managers. Hooks are spawned per event by Claude Code (`async: true`).
- Smallest smoke: `HOME=<tmp> bash ./ctx-profiler.sh status` (creates config, prints JSON) then `python3 -m unittest discover -s tests -v`.
- Health: `ctx-profile doctor` reports textual, config, enabled flag, transcript count, command shims, bin shims.
- Logs: none; hook failures are silent by design.

## Unresolved Inputs

| Unit | Input | Evidence checked | Needed for | Options | Materiality |
|---|---|---|---|---|---|
| context-profiler | `textual` availability/version | `visualize.py`, `ctx-profiler.sh`, scan host lacked it | dashboard run, `test_visualize_sessions` | `pip install --user textual`; isolated venv; skip dashboard test | medium |
| context-profiler | Python minimum version | no manifest | Bring-up | use host python3 ≥ 3.9 | low |
| context-profiler | Real Claude/Codex transcripts for end-to-end import | none in repo | optional live smoke | fixtures in tests; empty dirs | low |

## Runtime Setup Questions

None blocking. Candidates above are resolved by Bring-up or Verify.
