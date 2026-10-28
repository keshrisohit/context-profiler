---
doc_type: architecture
scope: context-profiler/dashboard-and-cli
last_audited_at: 2026-10-28T18:57:09Z
audited_by: scanner
source_commit: 9771c5bd4ba0f4697e2c4af48215d31ca6b55249
staleness_threshold_days: 30
---

# Module: dashboard-and-cli

**Scope:** `context_profiler/analysis.py`, `context_profiler/formatting.py`, `visualize.py`, `analyze.sh`, `ctx-profiler.sh`, `commands/context-profiler.md`. **Role:** derived read models plus the human (TUI) and agent (CLI/slash) consumption surfaces, and host setup. Separate doc because it has distinct entrypoints, the TTY/context-safety rule, and a host-mutating setup path.

## Entry / Triggers

- `ctx-profile` / `ctx-profiler` shims → `ctx-profiler.sh` dispatch → `analyze.sh --<cmd>` → inline Python (CLI) or `visualize.py` (TUI).
- `/context-profiler $ARGUMENTS` → same shell surface (`commands/context-profiler.md`, `__CTX_PROFILER_SOURCE__` substituted at setup).
- `visualize.py [--source S] [--session ID] [--all-sessions]` → `ContextProfilerApp`.

## Contracts

- CLI subcommands and flags: `setup [--install-textual]`, `watch [source] [--session] [--all-sessions]`, `status|enable|disable`, `latest|summary|top [N]|files [N] [--include-ignored]|turns|explain [--source S|--claude|--codex|--all] [--session ID]`, `session <id>`, `clean [--days N] [--dry-run] [--include-codex-transcripts]`, `codex-import [--limit N]`, `doctor`. Text output; no JSON yet (planned in `README.md`).
- TUI tabs: Overview, Timeline, Tools, Spikes, Agents, Skills, Files, Turns, Forensics, Advice, Sessions; keybindings in `README.md § Dashboard Basics`.

## Read Model Owner

`analysis.py`: `compute_stats` (aggregates, spikes ≥ `spike_threshold_tokens`, exactness `exact|snapshot-based|estimated-byte-derived`), `build_turns` (explicit `turn_start` or 120s-gap estimation; `classify_turn`), `build_forensics` (compaction/reset contributors), `build_agent_runs`, `build_recommendations` (≤10 heuristic items; ignore-pattern filtered). Ignored-path filtering (`advice_ignore_path_patterns`, `fnmatch`) hides profiler/transcript noise by default; `--include-ignored` / `i` key shows raw.

Staleness: every TUI refresh and CLI invocation first runs auto-cleanup and incremental imports, so views reflect transcripts as of that refresh. Session filter must apply to every analytical tab (`AGENTS.md § Session And Filtering Rules`).

## Invariants

- `watch` refuses to run without TTY on stdin and stdout (checked in both `ctx-profiler.sh` and `analyze.sh`) — keeps UI out of agent context.
- Agent-facing commands return compact summaries.
- Textual imports confined to `visualize.py`.
- `setup` is idempotent: rewrites hook entries, removing stale `context-profiler/hooks/` commands, inserting each once.

## Side Effects

Read commands still write host-local state (auto-cleanup deletions, cursor/index/config writes). `setup` mutates `$HOME/.claude/settings.json`, command dirs, `$HOME/.codex/plugins/`, `$HOME/.local/bin/`, and may `pip install --user textual`.

## Verification

`tests/test_analysis_turns.py`, `tests/test_visualize_sessions.py` (requires `textual`). The `analyze.sh` inline CLI and `ctx-profiler.sh` have no tests (evidence absent).

## Risks / Gaps

- `visualize.py` (1311 lines) mixes state, aggregation, and view.
- `analyze.sh` inline Python duplicates `formatting.py` helpers and is untested.
- `$PLUGIN_DIR` interpolated into `python3 -c` strings.

## Agent Work Log

Read shell dispatch fully, `analyze.sh` header/watch/dispatch, `visualize.py` refresh/args, `analysis.py` turns/recommendations.
