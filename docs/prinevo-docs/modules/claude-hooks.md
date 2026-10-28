---
doc_type: architecture
scope: context-profiler
last_audited_at: 2026-10-28T22:47:15Z
audited_by: repo-setup
source_commit: 9771c5bd4ba0f4697e2c4af48215d31ca6b55249
staleness_threshold_days: 30
---

# Module: Claude hook adapters (`hooks/`)

| Dimension | Evidence |
|---|---|
| Purpose | Live capture of Claude Code session telemetry into the profile store. |
| Entrypoints | `session-start.py` (SessionStart), `pre-tool-use.py` (PreToolUse), `post-tool-use.py` (PostToolUse), `pre-compact.py` (PreCompact), `session-end.py` (Stop). Registered by `ctx-profiler.sh install_claude_hooks` as `python3 "<repo>/hooks/<script>"` with `"async": true`. |
| Input contract | Claude hook JSON on stdin: `session_id`, `tool_name`, tool input/response, `transcript_path`, `cwd`. |
| Output / writer | `context_profiler_core.append_event(session_id, event, "claude")` → `storage.append_event`. Events: `session_start` (with `cwd`, `git_branch`), `tool_call` (via `normalize_claude_tool_event`, with `duration_ms`), `compaction` (`compaction_index`, `transcript_bytes_before`, `est_tokens_before = bytes // 4`), `session_end` (totals, peak). |
| Transient state | `/tmp/ctx-profiler-start/<session_id>/<safe_tool>-<epoch_ms>` stamp files: written by pre hook, newest consumed by post hook, entries older than 60 s pruned by pre hook. |
| Failure / recovery | Each script checks `is_enabled()` first and wraps everything in `try/except Exception: pass`; never emits output or non-zero exit, so the observed session is unaffected. Lost events are not recoverable except Agent events, which the Claude transcript importer backfills. |
| Invariants | No stdout (context safety). Must import only through the facade (`sys.path` insert of repo root). |
| Dependencies | facade → storage/config/formatting/importers.claude; `git` for branch lookup. |
| Verification | No direct hook tests; `normalize_claude_tool_event` and storage covered indirectly by `tests/test_claude_importer.py`, `tests/test_storage.py`. Gap: hook stdin/duration pairing untested. |
| Change safety | Changing script names requires updating the `entries` map in `ctx-profiler.sh` and re-running setup; existing installs keep stale paths until setup runs. |
| Deploy | not applicable (installed into the user's Claude settings by setup). |
