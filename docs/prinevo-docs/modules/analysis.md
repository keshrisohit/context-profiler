---
doc_type: architecture
scope: context-profiler
last_audited_at: 2026-10-28T21:52:36Z
audited_by: repo-setup
source_commit: 9771c5bd4ba0f4697e2c4af48215d31ca6b55249
staleness_threshold_days: 30
---

# Module: Analysis

**Scope:** `context_profiler/analysis.py`, `context_profiler/formatting.py`.
**Role:** Shared, source-neutral read model. Derives stats, turns, forensics, agent runs, and recommendations from normalized events. Used by CLI (`analyze.sh`), dashboard (`visualize.py`), and session index.

## Contracts

- `compute_stats(events, spike_threshold=5000, advice_ignore_path_patterns=None)` → dict with tool calls, file/tool/agent/skill aggregates, spikes, turns, forensics, current tokens, exactness, recommendations.
- `build_turns(events)` — uses explicit `turn_start` boundaries when present, otherwise infers; each turn classified by `classify_turn`: `compaction`, `spike` (≥20k tokens), `agent-running`, `agent-heavy`, `file-heavy`, `tool-heavy`, `normal`.
- `build_forensics(events)` — per compaction, top 8 contributors since previous compaction; also detects resets where a context snapshot drops below 60% of a >20k predecessor.
- `build_agent_runs(events)` — one row per agent run keyed by agent/child id.
- `build_recommendations(...)` — max 10; rules: repeated expensive reads (>1 read, ≥3k tokens), single large result (≥20k), large agent return (≥15k), ≥3 spikes, any compaction, approximate accounting.
- Ignore filtering: `matches_advice_ignore_path` (fnmatch on `advice_ignore_path_patterns`), `filter_visible_*`.
- `formatting.estimate_tokens` — `Original token count:` override or `(in+out bytes)//4`.

## State

Stateless; reads config only for defaults/ignore patterns. `git_branch_for` shells out to `git` with 2 s timeout.

## Forbidden Shortcuts

Clients should not re-implement aggregation; currently `analyze.sh` duplicates `fmt_tokens`/`fmt_bytes` and some per-command aggregation (risk).

## Verification

`tests/test_analysis_turns.py` (turn agents/files/status/top contributors). Recommendations and forensics lack direct tests (LLD capture gap).
