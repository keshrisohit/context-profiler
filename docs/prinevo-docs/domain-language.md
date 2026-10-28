---
doc_type: architecture
scope: context-profiler
last_audited_at: 2026-10-28T22:47:15Z
audited_by: repo-setup
source_commit: 9771c5bd4ba0f4697e2c4af48215d31ca6b55249
staleness_threshold_days: 30
---

# context-profiler — Domain Language

Domain-discovery level capture: the domain is a telemetry/analysis pipeline,
not a behavior-rich business domain (no aggregates with invariants beyond
storage rules), so DDD classification was not forced.

| Term | Meaning | Aliases | Source refs |
|---|---|---|---|
| Source | The agent harness a profile came from (`claude`, `codex`, or a custom configured name). | harness, profile source | `config.py` `sources`; `AGENTS.md` Preserve source neutrality |
| Session | One observed agent conversation identified by `session_id`. | session id | `storage.profile_path`; hooks |
| Profile | Normalized JSONL event log for one session; one logical profile may span rotated parts. | profile file, logical session | `storage.py`; README § How Advice Works |
| Event | Normalized record with `type` in `session_start`, `turn_start`, `context_snapshot`, `tool_call`, `compaction`, `session_end`. | profile event | README § Architecture |
| Tool call | A tool invocation event with byte sizes and estimated tokens. | call | `importers/claude.normalize_claude_tool_event`; `analysis.compute_stats` |
| Turn | A user request and the events until the next boundary, with duration, status, and token growth. | user turn | `analysis.build_turns` |
| Spike | A single event whose estimated tokens exceed `spike_threshold_tokens` (5000). | context spike | `config.py`; `analysis.py` |
| Compaction | A context compaction/reset marker recorded before Claude compacts. | reset | `hooks/pre-compact.py`; `analysis.build_forensics` |
| Agent run | One child agent invocation with lifecycle status `requested` → `running` → `completed`/`failed`, linked by parent/child session ids. | subagent, child agent | `analysis.build_agent_runs`; importers |
| Parent / child session | Relationship between a session that spawned an agent and the agent's own session; shown as Role `parent:N` / `child-><id>`. | role | `session_index.session_relationship_label` |
| Skill | Loaded skill instructions; for Codex inferred from reads of `SKILL.md`. | skill load | `importers/codex._skill_name_from_path` |
| Advice | Heuristic recommendation derived from observed evidence. | recommendation | `analysis.build_recommendations` |
| Ignored path | Path matching `advice_ignore_path_patterns`, hidden from high-usage views by default. | profiler noise | `config.py`; `analysis.matches_advice_ignore_path` |

Relations: a session *belongs to* a source (state); a session *contains* events
and turns (event); an agent run is *spawned by* a parent session (state per run);
an agent run *has child* session (state).

```json domain-ontology
{
  "entities": [
    {"id": "concept:source", "type": "concept", "level": "repo", "aliases": ["harness", "profile source"]},
    {"id": "concept:session", "type": "concept", "level": "repo", "aliases": ["session id", "profile", "logical session"]},
    {"id": "concept:turn", "type": "concept", "level": "repo", "aliases": ["user turn"]},
    {"id": "concept:tool_call", "type": "concept", "level": "repo", "aliases": ["call"]},
    {"id": "concept:compaction", "type": "concept", "level": "repo", "aliases": ["reset"]},
    {"id": "concept:agent_run", "type": "concept", "level": "repo", "aliases": ["subagent", "child agent"]},
    {"id": "concept:advice", "type": "concept", "level": "repo", "aliases": ["recommendation"]}
  ],
  "relations": [
    {"name": "recorded_from", "subject_type": "session", "object_type": "source", "cardinality": "state", "archetype": "attribution"},
    {"name": "contains_turn", "subject_type": "session", "object_type": "turn", "cardinality": "event", "archetype": "containment"},
    {"name": "spawned_by", "subject_type": "agent_run", "object_type": "session", "cardinality": "state", "archetype": "lineage"}
  ],
  "unresolved": []
}
```

Report: entities=7, relations=3, unresolved=0, rejected=5 (spike, skill, event,
ignored path, parent/child label — attribute, threshold, or derived view rather
than a durable referent).
