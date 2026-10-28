---
doc_type: architecture
scope: context-profiler/profile-ingestion
last_audited_at: 2026-10-28T18:57:09Z
audited_by: scanner
source_commit: 9771c5bd4ba0f4697e2c4af48215d31ca6b55249
staleness_threshold_days: 30
---

# Module: profile-ingestion

**Scope:** `hooks/*.py`, `context_profiler/importers/{base,claude,codex}.py`, `codex-profiler.py`. **Role:** source adapters that translate native harness telemetry into normalized profile events. Root guidance is not enough because this boundary has its own entrypoints (Claude hook runtime, refresh-time import), failure rules (never disrupt the observed session), and source-specific evidence rules for agent lifecycle.

## Entry / Triggers

| Trigger | Adapter | Writer call |
|---|---|---|
| Claude `SessionStart` | `hooks/session-start.py` | `append_event(session_start)` |
| Claude `PreToolUse` | `hooks/pre-tool-use.py` | writes `/tmp/ctx-profiler-start/<session>/<tool>-<epoch_ms>` only |
| Claude `PostToolUse` | `hooks/post-tool-use.py` → `normalize_claude_tool_event` | `append_event(tool_call)` with `duration_ms` |
| Claude `PreCompact` | `hooks/pre-compact.py` | `append_event(compaction)` |
| Claude `Stop` | `hooks/session-end.py` | `append_event(session_end)` totals |
| Dashboard/CLI refresh | `import_latest_claude_profiles`, `import_latest_codex_profiles` | `write_profile` (full rewrite) |
| `codex-profiler.py` / `ctx-profile codex-import` | `import_codex_transcript` | `write_profile` |

## Contracts

- Input: Claude hook stdin JSON; Claude parent transcripts (`$HOME/.claude/projects/**/*.jsonl`, excluding `/subagents/`) plus sidechain transcripts; Codex rollouts (`$HOME/.codex/sessions/**/*.jsonl`).
- Output: normalized events (schema in [architecture.md](../architecture.md#persistence-schemas)).
- Extension contract: `ProfileImporter` protocol (`source`, `import_latest(limit)`); new sources added to config `sources` (`README.md § Architecture`).

## State And Writers

Ingestion owns no durable state of its own; it writes through `context_profiler.storage` ([profile-store.md](profile-store.md)). Import idempotency uses `.import-cursors.json` (signature = size + mtime_ns, `IMPORT_CURSOR_VERSION=2`). Codex profiles are rebuilt wholesale from the transcript each import. Claude transcript import merges Agent events into an existing hook-written profile by `raw_tool_use_id` or description, with status rank `requested < running/started < completed` (`_merge_agent_metadata`).

## Invariants

- Agent runs require runtime evidence, not prose (`AGENTS.md § Parent/Child Agent Rules`): Codex `spawn_agent` without output = `requested`, with `agent_id` = `running`, `wait_agent` completed = `completed`; Claude Agent tool_use = `requested`, sidechain transcript present = `running`, tool_result = `completed`.
- Codex skill usage is inferred only from reads of `.../SKILL.md` (`_skill_name_from_path`, `_infer_skill_from_command`).
- All importers and hooks no-op when config `enabled` is false or the source is not in `sources`.
- Hooks swallow every exception.

## Forbidden Shortcuts

Writing profile files without `storage`; deleting or modifying raw transcripts; streaming transcript contents to stdout of agent sessions.

## Flows And Dependency Direction

`hooks/*` → `context_profiler_core` facade → `importers.claude` / `storage`. `importers/*` → `config`, `formatting`, `storage`. No dependency on `analysis` or Textual.

## Verification

`tests/test_claude_importer.py`, `tests/test_codex_importer.py` (transcript fixtures built inline). Hooks themselves have no direct tests (evidence absent).

## Risks / Gaps

- Hook `append_event` vs transcript-import `write_profile` lost-update race on Claude profiles (medium confidence; see root hotspots).
- Codex session id derived from filename tail when `session_meta` is missing (`path.stem...split("-")[-5:]`).
- Stamp directory uses unsanitized `session_id`.
- Token estimates are byte-derived for Claude hooks; Codex uses `token_count` snapshots.

## Agent Work Log

Read all hook scripts and importer entry functions; decisions and gaps as above.
