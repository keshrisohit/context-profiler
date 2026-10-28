---
doc_type: domain-language
scope: context-profiler
last_audited_at: 2026-10-28T21:52:36Z
audited_by: repo-setup
source_commit: 9771c5bd4ba0f4697e2c4af48215d31ca6b55249
staleness_threshold_days: 30
---

# context-profiler — Domain Language

| Term | Meaning in this repo | Aliases | Source refs |
|---|---|---|---|
| Source | The agent harness a profile came from (`claude`, `codex`, or a custom configured name) | harness | `config.py` `sources`, `storage.profile_source` |
| Session | One observed agent conversation, identified by the harness session id | profile (logical) | `storage.py`, `session_index.py` |
| Profile | The normalized JSONL event log for one session; may span rotated parts | logical profile | `storage.profile_path`, `profile_part_paths` |
| Part | A physical overflow file `<stem>.part-NNNN.jsonl` of a profile | rotation part | `storage.profile_part_path` |
| Event | Normalized record: `session_start`, `turn_start`, `context_snapshot`, `tool_call`, `compaction`, `session_end` | | `hooks/*.py`, `importers/*.py` |
| Turn | Work between user requests; explicit (`turn_start`) or inferred; classified `normal`, `spike`, `compaction`, `agent-running`, `agent-heavy`, `file-heavy`, `tool-heavy` | request | `analysis.build_turns`, `classify_turn` |
| Spike | A tool call whose estimated tokens exceed `spike_threshold_tokens` (default 5000) | | `analysis.compute_stats` |
| Compaction / reset | Context compaction event, or a detected drop in context tokens; analysed in forensics | | `hooks/pre-compact.py`, `analysis.build_forensics` |
| Forensics | Top contributors since the previous compaction/reset | | `analysis.build_forensics` |
| Agent run | One subagent invocation with lifecycle status `requested` → `running` → `completed` (or failed) | subagent, child session | `analysis.build_agent_runs`, importers |
| Parent / child session | Session that spawned agents / session that is a spawned agent; shown as Role `parent:N` / `child-><id>` | | `session_index.session_relationship_label` |
| Advice | Heuristic recommendations with severity, title, detail, action | recommendations | `analysis.build_recommendations` |
| Ignored paths | Profiler/transcript paths hidden from high-usage views by default | advice ignore patterns | `config.advice_ignore_path_patterns` |
| Exactness | Whether token counts are exact (model usage fields) or estimated (bytes/4) | approximate accounting | `analysis.compute_stats`, `formatting.estimate_tokens` |
| Import cursor | Per-transcript signature record that lets unchanged transcripts be skipped | | `storage.mark_transcript_imported` |
| Pin | Restricting all dashboard views to one selected session | session filter | README, `visualize.py` |

Ambiguity: "session" is used both for the harness conversation and for a profile file; "agent" means a spawned subagent run, not the top-level assistant.

## Domain Model Evidence

| Concept | Classification | Identity / lifecycle evidence | Owner / canonical writer | Invariant / transition | Maturity | Source refs | Ontology disposition |
|---|---|---|---|---|---|---|---|
| Profile | entity | keyed by sanitized session id + source prefix | `storage.append_event` / `write_profile` | parts load in order as one logical session | implemented | `storage.py` | entity |
| Agent run | entity | keyed by agent/child id or raw tool use id | importers | status never downgrades (`_STATUS_RANK`) | implemented | `importers/claude.py`, `importers/codex.py`, `analysis.py` | entity |
| Event | value object | no own identity; ordered by `ts` | adapters | normalized schema before analysis | implemented | `storage.py` | attribute/pointer |
| Turn, Spike, Advice | projection / read model | derived each read | `analysis.py` | recomputed from events | implemented | `analysis.py` | attribute/pointer |

Coverage: all package modules and importers scanned; dashboard by symbols. No further domain-discovery gaps beyond those in `architecture.md`.

```json domain-ontology
{
  "entities": [
    {"id": "concept:profile", "type": "profile", "level": "module", "aliases": ["logical profile"]},
    {"id": "concept:session", "type": "session", "level": "module", "aliases": []},
    {"id": "concept:agent-run", "type": "agent_run", "level": "module", "aliases": ["subagent"]}
  ],
  "relations": [
    {"name": "records", "subject_type": "profile", "object_type": "session", "cardinality": "state", "archetype": "attribution"},
    {"name": "spawned_by", "subject_type": "session", "object_type": "session", "cardinality": "state", "archetype": "lineage"}
  ],
  "unresolved": [
    {"term": "session", "meanings": ["harness conversation", "profile file"]}
  ]
}
```

Relations: `records` — a profile (subject) records exactly one session (object), e.g. `codex-<sid>.jsonl` records Codex session `<sid>`. `spawned_by` — a child session (subject) was spawned by a parent session (object), evidenced by `parent_session_id` / `child_session_id` meta in `session_index._relationship_edges`.
