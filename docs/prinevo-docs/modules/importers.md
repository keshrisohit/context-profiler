---
doc_type: architecture
scope: context-profiler
last_audited_at: 2026-10-28T22:47:15Z
audited_by: repo-setup
source_commit: 9771c5bd4ba0f4697e2c4af48215d31ca6b55249
staleness_threshold_days: 30
---

# Module: Transcript importers (`context_profiler/importers/`)

| Dimension | Evidence |
|---|---|
| Purpose | Convert harness-native transcripts into normalized profile events; the only place harness-specific parsing lives (`AGENTS.md` source-neutrality rule). |
| Contract | `importers/base.py` `ProfileImporter` Protocol: `source: str`, `import_latest(limit) -> list[Path]`. Codex implements it via `CodexTranscriptImporter`; Claude exposes module functions. |
| Entrypoints | `import_latest_claude_profiles(limit)`, `import_claude_transcript(path)`, `normalize_claude_tool_event(payload, duration_ms)` (used by hooks); `import_latest_codex_profiles(limit)`, `import_codex_transcript(path)`, `latest_codex_transcripts(limit)`. Callers: `visualize.py` refresh, `analyze.sh` CLI, `codex-profiler.py`. |
| Inputs | Claude: `claude_projects_dir` (default `~/.claude/projects`) `**/*.jsonl` excluding `/subagents/`; side transcripts for child agents. Codex: `codex_sessions_dir` (default `~/.codex/sessions`) `**/*.jsonl` rollouts. |
| Writer | `storage.write_profile(session_id, events, source)` (whole-profile rewrite); cursor updates via `storage.mark_transcript_imported`. |
| Skip logic | `transcript_import_current(source, path)` compares stored signature; imports gated by `enabled` and presence of the source in `config.sources`. |
| Agent lifecycle semantics | Codex: `requested` (spawn_agent call, no output) → `running` (spawn returned `agent_id`) → `completed`/`failed` (wait_agent status, per-agent for multi-wait); events carry `parent_session_id`, `child_session_id(s)`. Claude: `requested` (Agent tool_use in parent) → `running` (side transcript exists) → `completed` (tool_result in parent); merged into hook profile by `raw_tool_use_id` or description; adds `subagent_agent_id`, `subagent_transcript_path`. Plain-text role mentions never create agents. |
| Skills | Codex skill usage inferred only from reads of `.../SKILL.md` (`_skill_name_from_path`, `_infer_skill_from_command`). |
| Failure / recovery | Unreadable file → `None`; malformed lines skipped. Re-import is idempotent (profile rewrite compares content). Deleting `.import-cursors.json` forces full re-import. |
| Verification | `tests/test_codex_importer.py` (requested, completed, multi-wait status), `tests/test_claude_importer.py` (parent→subagent link, backfill by description). |
| Change safety | Upstream transcript formats are vendor-controlled and undocumented; add fixture tests for any new row shape. Bump `IMPORT_CURSOR_VERSION` in `storage.py` when import semantics change so cached transcripts are re-parsed. |
| Runtime / deploy | not applicable (in-process library). |
