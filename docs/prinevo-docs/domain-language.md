---
doc_type: domain-language
scope: context-profiler
last_audited_at: 2026-10-28T18:57:09Z
audited_by: scanner
source_commit: 9771c5bd4ba0f4697e2c4af48215d31ca6b55249
staleness_threshold_days: 30
---

# context-profiler Domain Language

| Term | Meaning | Aliases | Source refs |
|---|---|---|---|
| Source | A harness whose sessions are profiled (`claude`, `codex`, or custom name in config `sources`) | harness | `config.py`, `README.md` |
| Session | One harness conversation, identified by `session_id`; one logical profile | — | `storage.py` |
| Profile | The JSONL event log for one session, possibly split into rotation parts | profile file, logical profile | `storage.py`, `README.md` |
| Part | Overflow physical file `<stem>.part-NNNN.jsonl` of a profile | rotated part | `storage.profile_part_path` |
| Event | Normalized record: `session_start`, `turn_start`, `context_snapshot`, `tool_call`, `compaction`, `session_end` | profile event | `README.md § Architecture` |
| Turn | One user request span; boundary `exact` (from `turn_start`) or `estimated`/`estimated-gap` | — | `analysis.build_turns` |
| Turn status | `compaction`, `spike`, `agent-running`, `agent-heavy`, `file-heavy`, `tool-heavy`, `normal` | — | `analysis.classify_turn` |
| Spike | A single event whose token estimate ≥ `spike_threshold_tokens` | context spike | `analysis.compute_stats` |
| Compaction | Context compaction/reset marker | reset | `hooks/pre-compact.py`, `analysis.build_forensics` |
| Forensics | Contributors between compaction/reset events | compaction forensics | `analysis.build_forensics` |
| Agent run | One observed subagent invocation with lifecycle `requested → running → completed` (or failed) | subagent, child agent | `analysis.build_agent_runs`, importers |
| Parent / child session | Relationship between a spawning session and a spawned agent session; shown as Role `parent:N` / `child-><id>` | role | `session_index.session_relationship_label` |
| Advice | Heuristic recommendations (`severity`, `title`, `detail`, `action`) | recommendations | `analysis.build_recommendations` |
| Exactness | Token accounting quality: `exact`, `snapshot-based`, `estimated-byte-derived` | — | `analysis.compute_stats` |
| Ignored paths | Profiler/transcript paths hidden from high-usage views by default | advice ignore patterns | `config.DEFAULT_CONFIG` |
| Import cursor | Per-transcript signature preventing re-import of unchanged transcripts | — | `storage.mark_transcript_imported` |

Ambiguity: **session** means a harness conversation here, not an auth session. **Agent** means an observed subagent run in the profiled harness, not this tool.

## Domain Model Evidence

Behavior is analytic, not transactional; light lifecycle evidence only (agent status rank).

| Concept | Classification | Identity / lifecycle evidence | Owner / canonical writer | Invariant / transition | Maturity | Source refs | Ontology disposition |
|---|---|---|---|---|---|---|---|
| Session/Profile | entity | `session_id` → sanitized profile stem | `storage.append_event` / `write_profile` | one logical profile across parts | implemented | `storage.py`, `tests/test_storage.py` | entity |
| Agent run | entity (lifecycle) | `raw_tool_use_id` / Codex `agent_id` | importers | status only advances by rank; requires runtime evidence | implemented | `importers/claude.py::_merge_agent_metadata`, `tests/test_*_importer.py` | entity |
| Turn | projection/read model | ordinal within session | `analysis.build_turns` | derived, not persisted | implemented | `tests/test_analysis_turns.py` | attribute/pointer (derived) |
| Event | value record | none beyond position | storage | append-only per profile | implemented | `storage.py` | rejected as entity (no durable identity) |
| Source | domain concept | config name | config | — | implemented | `config.py` | entity |

Coverage: all package modules scanned; no unscanned domain areas.

```json domain-ontology
{
  "entities": [
    {"id": "concept:profiled-session", "type": "session", "level": "module", "aliases": ["profile", "logical profile"]},
    {"id": "concept:agent-run", "type": "agent_run", "level": "module", "aliases": ["subagent", "child agent"]},
    {"id": "concept:profile-source", "type": "source", "level": "module", "aliases": ["harness"]}
  ],
  "relations": [
    {"name": "recorded_from", "subject_type": "session", "object_type": "source", "cardinality": "state", "archetype": "attribution"},
    {"name": "spawned_by", "subject_type": "agent_run", "object_type": "session", "cardinality": "state", "archetype": "lineage"}
  ],
  "unresolved": []
}
```

Relation prose: `recorded_from` — a session's events come from exactly one source (profile stem / first event `source`). `spawned_by` — an agent run's `parent_session_id` names the session that requested it (`importers/codex.py`, `importers/claude.py`).

entities=3, relations=2, unresolved=0, rejected=1 (event: no durable identity).
