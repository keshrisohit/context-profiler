---
doc_type: architecture
scope: context-profiler/profile-store
last_audited_at: 2026-10-28T18:57:09Z
audited_by: scanner
source_commit: 9771c5bd4ba0f4697e2c4af48215d31ca6b55249
staleness_threshold_days: 30
---

# Module: profile-store

**Scope:** `context_profiler/storage.py`, `context_profiler/session_index.py`, `context_profiler/config.py`. **Role:** sole writer for all profiler state (profiles, cursors, session index, config, cleanup state). Separate doc because it owns the source-of-truth files, rotation/atomicity rules, and destructive cleanup safety rules.

## Entry / Contracts

Library API only (re-exported through `context_profiler_core.py`): `profile_path`, `append_event`, `write_profile`, `load_events`, `profile_part_paths`, `get_all_profiles`, `get_latest_session`, `profile_matches_session`, `transcript_import_current`, `mark_transcript_imported`, `cleanup_old_profiles`, `cleanup_old_codex_transcripts`, `run_auto_cleanup`, `refresh_session_index`, `load_config`, `save_config`, `ensure_config`, `is_enabled`, `configured_sources`.

## State

| File (under `<profile-dir>` = `$HOME/.claude/context-profiles`) | Role |
|---|---|
| `<sid>.jsonl`, `codex-<sid>.jsonl` | Logical profile base part (source of truth for events) |
| `<stem>.part-NNNN.jsonl` | Rotation overflow parts (index ≥ 2), loaded in order |
| `config.json` | User config merged over defaults |
| `.import-cursors.json` | Import signatures per source/transcript (rebuildable) |
| `.session-index.json` | Per-profile summary cache for Sessions tab (rebuildable) |
| `.cleanup-state.json` | Auto-cleanup throttle timestamp |

## Writer Rules / Invariants

- Session ids sanitized to `[A-Za-z0-9_-]` (`safe_session_id`); Codex stems get a `codex-` prefix; source is inferred from stem prefix, else first event `source`.
- `append_event` appends to the last part, opening a new part when the next line would exceed `profile_max_part_bytes` (0 disables rotation).
- `write_profile` chunks lines to the limit, skips write when content is unchanged, writes `*.tmp` then `replace`, and unlinks surplus stale parts.
- Cursor and index files written atomically (tmp + replace).
- Cleanup treats a logical profile as one unit: deletes base + all parts only when the newest part is older than retention. Raw Codex transcripts are deleted only via `cleanup_old_codex_transcripts`, reachable only with `--include-codex-transcripts`.
- `run_auto_cleanup` runs at most once per `auto_cleanup_interval_hours`, min retention 1 day.
- `_merge_config` always re-adds default `advice_ignore_path_patterns`.

## Read Model

`refresh_session_index` recomputes a summary only when a profile's part signatures or the spike threshold change, drops entries for deleted profiles, and derives parent/child `relationship` labels (`parent:N`, `child-><id>`) from agent event metadata.

## Forbidden Shortcuts

Direct file writes to `<profile-dir>` from clients/adapters; non-atomic rewrites; deleting individual rotation parts.

## Dependency Direction

Depends on stdlib only (`session_index` additionally on `analysis.compute_stats` and `formatting`). `PROFILE_DIR` is bound at import from `Path.home()`; not configurable (tests patch module globals).

## Verification

`tests/test_storage.py` (rotation, cleanup, cursors), `tests/test_session_index.py` (index invalidation, relationships).

## Risks / Gaps

- No file locking: concurrent `append_event` (hook) and `write_profile` (importer) on the same Claude profile can drop appended events.
- `load_config()` called on every append.
- Event schema has no version field.

## Agent Work Log

Read `storage.py` fully, `session_index.py` refresh path, `config.py` fully.
