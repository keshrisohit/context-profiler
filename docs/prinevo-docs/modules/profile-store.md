---
doc_type: architecture
scope: context-profiler
last_audited_at: 2026-10-28T22:47:15Z
audited_by: repo-setup
source_commit: 9771c5bd4ba0f4697e2c4af48215d31ca6b55249
staleness_threshold_days: 30
---

# Module: Profile store and config (`storage.py`, `session_index.py`, `config.py`)

| Dimension | Evidence |
|---|---|
| Purpose | Sole owner of durable profiler state under `PROFILE_DIR = ~/.claude/context-profiles` (computed from `Path.home()` at import). |
| Source of truth | Logical profile = `<sid>.jsonl` (Claude/custom) or `codex-<sid>.jsonl` (Codex) plus ordered `*.part-NNNN.jsonl` overflow parts. `safe_session_id` replaces non `[A-Za-z0-9_-]` chars. |
| Writers | `append_event` (append to last part; roll to next part when over `profile_max_part_bytes`, default 10,000,000); `write_profile` (chunk, write `.tmp`, atomic `replace`, delete surplus stale parts; no-op if identical); `config.save_config` / `ensure_config`; `session_index._write_index`; `run_auto_cleanup` (`.cleanup-state.json`). |
| Readers | `load_events` (all parts in order), `get_all_profiles(sources)`, `get_latest_session(pin, sources)`, `filter_profiles_by_session`, `profile_mtime` (newest part). |
| Projections / caches | `.session-index.json` (per-session summary, invalidated per profile by part signature), `.import-cursors.json` (transcript signatures, `IMPORT_CURSOR_VERSION = 2` invalidates older records). Both rebuildable; safe to delete. |
| Cleanup | `cleanup_old_profiles(days, dry_run, sources)` deletes a logical profile (all parts) only when newest part is older than cutoff; `run_auto_cleanup` throttled by `auto_cleanup_interval_hours` (min 1) and `cleanup_retention_days` (min 1, default 5); `cleanup_old_codex_transcripts` only on explicit CLI flag. |
| Config contract | `DEFAULT_CONFIG` keys: `enabled`, `spike_threshold_tokens`, `refresh_interval_seconds`, `follow_latest_session`, `sources`, `codex_sessions_dir`, `codex_import_on_refresh`, `codex_import_limit`, `claude_projects_dir`, `claude_import_on_refresh`, `claude_import_limit`, `hide_ignored_paths_by_default`, `profile_rotation_enabled`, `profile_max_part_bytes`, `auto_cleanup_enabled`, `auto_cleanup_interval_hours`, `cleanup_retention_days`, `advice_ignore_path_patterns`. User values override; default ignore patterns are always re-appended. Unreadable config → defaults. |
| Concurrency | No file locking; hooks append while importers may rewrite Claude profiles. Atomic `replace` avoids torn files but a concurrent append between read and replace can be lost (inferred from code; not tested). |
| Verification | `tests/test_storage.py` (session id sanitization, plain vs codex-prefixed match, auto-cleanup + throttle, rotation write/load, append rotation, cursor current/skip/version, cleanup keeps recent logical profile), `tests/test_session_index.py` (cache reuse). |
| Change safety | Keep base+parts as one logical unit in every reader/cleanup; keep raw transcript deletion behind explicit flag (`AGENTS.md` Context Safety Rules). |
