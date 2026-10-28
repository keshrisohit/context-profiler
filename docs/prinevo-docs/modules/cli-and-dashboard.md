---
doc_type: architecture
scope: context-profiler
last_audited_at: 2026-10-28T22:47:15Z
audited_by: repo-setup
source_commit: 9771c5bd4ba0f4697e2c4af48215d31ca6b55249
staleness_threshold_days: 30
---

# Module: CLI, setup, analysis, and dashboard

| Dimension | Evidence |
|---|---|
| Purpose | Human and agent consumption surfaces plus installation. |
| Entrypoints | `ctx-profiler.sh` (installed as `~/.local/bin/ctx-profile` / `ctx-profiler`; `CTX_PROFILER_DIR` overrides plugin dir); `analyze.sh` (flag CLI; `--enable/--disable/--status/--codex-import/--watch` handled in Bash, everything else in an inline Python heredoc); `visualize.py` (Textual `ContextProfilerApp`); `/context-profiler` slash command template with `__CTX_PROFILER_SOURCE__` placeholder rendered at setup. |
| Setup side effects | `setup`: `ensure_config`; optional `pip install --user textual`; rewrite `~/.claude/settings.json` hooks (dedupes prior `context-profiler/hooks/` commands); write `~/.claude/commands/context-profiler.md`, `~/.codex/commands/context-profiler.md`; copy Codex plugin to `~/.codex/plugins/context-profiler`; write bin shims. Idempotent. `doctor` reports textual, config, enabled flag, Codex transcript count, shims. |
| Analysis (`analysis.py`) | Pure functions over event lists: `compute_stats`, `build_turns` / `classify_turn`, `build_forensics` (compaction/reset), `build_agent_runs` (status rank merge), `build_recommendations` (repeated expensive reads, single large tool result, large agent return, multiple spikes, compaction/reset, approximate-accounting note), ignore-path filtering via `fnmatch` patterns. |
| Dashboard | Tabs: Overview, Timeline, Tools, Spikes, Agents, Skills, Files, Turns, Forensics, Advice, Sessions. Refresh via `set_interval(refresh_interval_seconds)`; each refresh: `run_auto_cleanup`, imports, `refresh_session_index`, render active tab only. Keys documented in README (`s`, `u`, `/`, `c`, `o`, `m`, `i`, `a`, `f`, `g`, `q`, Tab/Shift+Tab). |
| Context-safety invariants | `watch` exits 0 with guidance when stdin/stdout not a TTY (both `ctx-profiler.sh` and `analyze.sh`); agent commands print compact text; ignored paths hidden unless `i` / `--include-ignored` / `--raw`. |
| State | Reads store; writes only via store/config modules and setup functions. |
| Failure / recovery | Unknown command → usage, exit 2; missing textual → setup message. |
| Verification | `tests/test_analysis_turns.py`, `tests/test_visualize_sessions.py` (requires `textual`; errors without it). Gap: no tests for `analyze.sh` output, `ctx-profiler.sh setup`, or slash-command rendering. |
| Change safety | After behavior or installed-command changes rerun `bash ./ctx-profiler.sh setup` (`AGENTS.md` Setup Rules). Session filters must apply to all analytical tabs; Sessions tab sorted by start time newest first. |
| Hotspots | `visualize.py` (1311 lines); `analyze.sh` inline Python (~400 lines) duplicates formatting helpers. |
