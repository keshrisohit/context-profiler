---
doc_type: architecture
scope: context-profiler
last_audited_at: 2026-10-28T21:52:36Z
audited_by: repo-setup
source_commit: 9771c5bd4ba0f4697e2c4af48215d31ca6b55249
staleness_threshold_days: 30
---

# Module: CLI, Setup & Plugin Packaging

**Scope:** `ctx-profiler.sh`, `analyze.sh`, `codex-profiler.py`, `commands/context-profiler.md`, `.claude-plugin/plugin.json`, `.codex-plugin/plugin.json`, `context_profiler_core.py`.
**Role:** User- and agent-facing command surface plus the installer that wires hooks and shims into the host. Distinct because setup mutates host configuration outside the repo.

## Entry / Contract

- `ctx-profile` (`ctx-profiler` alias) → `ctx-profiler.sh` subcommands: `setup [--install-textual]`, `watch`, `status`, `enable`, `disable`, `latest`, `summary`, `session <id>`, `top [N]`, `files [N]`, `turns`, `explain`, `clean [--days N] [--dry-run] [--include-codex-transcripts]`, `codex-import [--limit N]`, `doctor`, `help`. Most delegate to `analyze.sh --<cmd>`.
- `analyze.sh`: enable/disable/status via `python3 -c`; `--watch` → `visualize.py`; `--codex-import` → `codex-profiler.py --latest`; everything else → inline Python heredoc that first runs `run_auto_cleanup` and imports (skippable with `--no-claude-import` / `--no-codex-import`).
- `/context-profiler` slash command: template with `__CTX_PROFILER_SOURCE__` placeholder rendered at setup; instructs agents never to stream `watch`.
- Output contract for agents: compact human-readable text; no JSON mode (API contract gap).
- `context_profiler_core.py`: stable facade (`__all__`) imported by hooks and scripts; removing names breaks installed hooks.

## Host Side Effects Of `setup`

`ensure_config`; optional `pip install --user textual`; rewrite `$HOME/.claude/settings.json` `hooks` (adds five async command hooks, removes older `context-profiler/hooks/` entries with different paths; falls back to `{}` if settings JSON is unreadable); write slash-command files under `$HOME/.claude/commands/` and `$HOME/.codex/commands/`; copy Codex plugin to `$HOME/.codex/plugins/context-profiler/`; write shims in `$HOME/.local/bin/`. Idempotent. No uninstall.

## Safety Rules

- `watch` refuses without an interactive TTY (both `ctx-profiler.sh` and `analyze.sh`).
- Read commands are not side-effect free (import + throttled deletion).

## Risks

- CLI logic inside a heredoc is untested and duplicates formatting helpers.
- Version string duplicated in `context_profiler/__init__.py` and both manifests.
- Unreadable settings file would be replaced by hooks-only content.

## Verification

No automated tests for shell scripts (LLD capture gap). Manual: `HOME=<tmp> bash ./ctx-profiler.sh setup && ctx-profile doctor`.
