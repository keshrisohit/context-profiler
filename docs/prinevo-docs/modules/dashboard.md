---
doc_type: architecture
scope: context-profiler
last_audited_at: 2026-10-28T21:52:36Z
audited_by: repo-setup
source_commit: 9771c5bd4ba0f4697e2c4af48215d31ca6b55249
staleness_threshold_days: 30
---

# Module: Dashboard

**Scope:** `visualize.py` (1311 lines, `ContextProfilerApp(textual.App)`).
**Role:** Human-facing live Textual TUI. Only module requiring `textual`; only runs in an interactive TTY.

## Entry

`ctx-profile watch [<source>] [--session <id>] [--all-sessions]` → `analyze.sh --watch` → `python3 visualize.py [--source] [--session] [--all-sessions]`.

## Behavior (from README, AGENTS.md, imports, tests)

- Tabs: Overview, Timeline, Tools, Spikes, Agents, Skills, Files, Turns, Compaction forensics, Advice, Sessions. Keys: `s` source cycle, `u` sessions, `/` search, `c` clear pin, `o` sort, `m` file grouping, `i` ignored paths, `a` all sessions, `f`/`g` timeline, `q` quit.
- Refresh loop (`set_interval(refresh_interval_seconds)`) runs `run_auto_cleanup`, Claude/Codex imports, `refresh_session_index`, then `compute_stats`; only the active tab is rendered.
- Session pin filters all analytical tabs; Sessions tab sorted by start time newest-first; Role column `parent:N` / `child-><id>` / `-`.
- Agents tab falls back to recent agents of the source (`collect_source_agent_rows`) when the session has none.

## State

Reads profiles and session index; writes through storage via the refresh-triggered import/cleanup and `save_config` (imported). No own persistent state.

## Rules

Session filters must apply consistently across tabs; keep Textual code here only; navigation must not trap the user (AGENTS.md).

## Risks / Gaps

- Large single file mixing data loading, aggregation, and rendering.
- Architecture Depth Gap: internals inspected by symbols, imports, and tests rather than line-by-line; recovery: rescan `visualize.py` when it changes.

## Verification

`tests/test_visualize_sessions.py` (timestamp format, session sort, relationship labels, source agent rows) — requires `textual` to import.
