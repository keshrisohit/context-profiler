---
doc_type: architecture
scope: context-profiler
last_audited_at: 2026-10-28T21:52:36Z
audited_by: repo-setup
source_commit: 9771c5bd4ba0f4697e2c4af48215d31ca6b55249
staleness_threshold_days: 30
---

# Module: Capture & Import Adapters

**Scope:** `hooks/*.py`, `context_profiler/importers/{base,claude,codex}.py`, `codex-profiler.py`.
**Role:** Source-specific adapters that turn Claude hook payloads, Claude parent/side transcripts, and Codex rollout transcripts into normalized profile events. Root guidance is not enough because the two writer styles (live append vs full rewrite) and the agent-lifecycle evidence rules differ per source.

## Entry / Triggers

| Adapter | Trigger | Writes via |
|---|---|---|
| `hooks/session-start.py` | Claude `SessionStart` | `append_event` (`session_start`, cwd, git branch) |
| `hooks/pre-tool-use.py` | Claude `PreToolUse` | stamp file `/tmp/ctx-profiler-start/<sid>/<tool>-<ms>` only |
| `hooks/post-tool-use.py` | Claude `PostToolUse` | `normalize_claude_tool_event` → `append_event` (`tool_call`, duration) |
| `hooks/pre-compact.py` | Claude `PreCompact` | `append_event` (`compaction`, transcript bytes, bytes//4 tokens) |
| `hooks/session-end.py` | Claude `Stop` | `append_event` (`session_end` totals) |
| `import_latest_claude_profiles` | CLI command / dashboard refresh | `import_claude_transcript` → read existing profile, merge Agent events, `write_profile` |
| `import_latest_codex_profiles` | CLI command / dashboard refresh / `codex-profiler.py` | `import_codex_transcript` → full event list, `write_profile` (`codex-<sid>.jsonl`) |

All hooks: no-op when `enabled` is false; swallow every exception; installed `async: true`.

## Contracts

- Input: Claude hook stdin JSON (`session_id`, `tool_name`, `tool_input`, `tool_response`/`tool_result`, `transcript_path`, `cwd`); Claude transcript rows (`message.content[]` `tool_use` named `Agent`, side transcripts under `<transcript-stem>/subagents/*.jsonl`); Codex rollout rows (`session_meta`, `event_msg` `task_started`/`token_count`, function calls incl. `spawn_agent`, `wait_agent`, shell commands).
- Output: normalized event dicts (see `architecture.md` Data Models). Per-tool meta: Read/Write/Edit → `file_path`, `file_size_bytes`; Bash → `command`, `cmd_full`, `output_preview`; Agent → `subagent_type`, `description`, `prompt_preview`; Skill → `skill_name`; Glob/Grep → `pattern`, `path`; WebFetch/WebSearch → `url`.
- New-source contract: `ProfileImporter` protocol (`source`, `import_latest(limit)`) in `importers/base.py`; README "To add another harness".

## Agent Lifecycle Evidence Rules

- Codex: `requested` = `spawn_agent` call without output; `running` = output with `agent_id`; `completed` = `wait_agent` returned completed for that id. Meta: `parent_session_id`, `child_session_id`, `child_session_ids`.
- Codex skills inferred only from reads of `.../SKILL.md`.
- Claude: `requested` = parent transcript Agent tool_use; `running` = matching side transcript, no result; `completed` = tool result present. Status merge never downgrades (`_STATUS_RANK`).
- Plain text mentioning a "subagent" is not evidence (AGENTS.md).

## State And Writers

Writes only through `context_profiler.storage` (`append_event`, `write_profile`, `mark_transcript_imported`). Incremental skip via `transcript_import_current` (size + mtime_ns signature, cursor version 2). Imports skip when source not in `sources` or profiling disabled.

## Forbidden Shortcuts

Do not write profile files directly; do not delete or modify transcripts; do not emit hook output to stdout (would enter Claude context).

## Risks

- Claude importer rewrites `<sid>.jsonl` while hooks may append concurrently (no lock) → possible lost events (candidate).
- Hook duration pairing uses latest stamp per tool name → wrong durations for concurrent same-name tools.
- Codex importer reparses entire transcript when signature changes.
- Upstream transcript formats are unversioned.
- Claude token estimates are `bytes // 4` unless output contains `Original token count:`.

## Verification

`tests/test_claude_importer.py` (parent→subagent linking, backfill by description), `tests/test_codex_importer.py` (requested / completed / multi-wait status). Hook scripts have no direct tests (LLD capture gap).
