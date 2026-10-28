---
doc_type: architecture
scope: context-profiler
last_audited_at: 2026-10-28T21:52:36Z
audited_by: repo-setup
source_commit: 9771c5bd4ba0f4697e2c4af48215d31ca6b55249
staleness_threshold_days: 30
---

# Module: Profile Storage & Session Index

**Scope:** `context_profiler/storage.py`, `context_profiler/session_index.py`, `context_profiler/config.py`.
**Role:** Sole owner of on-disk profiler state: profiles, rotation, import cursors, cleanup, config, session index cache.

## Contracts (library API)

`profile_path`, `append_event`, `write_profile`, `load_events`, `profile_part_paths`, `get_all_profiles`, `get_latest_session`, `profile_matches_session` (prefix match, `codex-` aware), `transcript_import_current` / `mark_transcript_imported`, `cleanup_old_profiles`, `run_auto_cleanup`, `cleanup_old_codex_transcripts`, `refresh_session_index`, `load_config` / `save_config` / `ensure_config`. Re-exported through `context_profiler_core.py`.

## State And Source Of Truth

| State | Path (under `$HOME/.claude/context-profiles/`) | Kind |
|---|---|---|
| Logical profile | `<sid>.jsonl`, `codex-<sid>.jsonl` + `<stem>.part-NNNN.jsonl` | source of truth |
| Import cursors | `.import-cursors.json` | rebuildable cache |
| Session index | `.session-index.json` | rebuildable projection |
| Cleanup throttle | `.cleanup-state.json` | marker |
| Config | `config.json` | operator config |

Session ids are sanitized (`safe_session_id`: non `[A-Za-z0-9-_]` → `_`).

## Writer Rules / Invariants

- `append_event`: appends to last part; opens a new part when the line would exceed `profile_max_part_bytes` (0 disables rotation).
- `write_profile`: chunk lines into parts, skip if identical, write `*.tmp` then `replace`, delete surplus old parts. Atomic per part, not across parts.
- Cursor / index files written via tmp + replace.
- Cleanup deletes a logical profile (all parts) only when its newest part is older than retention; auto-cleanup throttled by `auto_cleanup_interval_hours`, min 1 day retention.
- Raw Codex transcripts deleted only by `cleanup_old_codex_transcripts`, reached only with `clean --include-codex-transcripts`.
- Config load merges defaults and always re-adds default ignore patterns.
- Session index entries are invalidated when part signatures or spike threshold change; entries for removed profiles are dropped.

## Failure / Staleness

Malformed JSON lines skipped; unreadable files ignored; malformed config/cursor/index treated as empty. Deleting cache files is safe (README).

## Risks

- No inter-process locking between appenders and rewriters.
- `PROFILE_DIR` is an import-time constant duplicated across modules and shell scripts; not configurable.

## Verification

`tests/test_storage.py` (sanitization, session match, auto-cleanup throttle, rotation on write and append, cursor current/skip/version, logical-profile cleanup), `tests/test_session_index.py` (cache reuse).
