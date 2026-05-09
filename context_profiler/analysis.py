"""Context profile aggregation, forensics, and recommendations."""
from __future__ import annotations

import fnmatch
import time
from collections import defaultdict
from typing import Any

from .config import DEFAULT_MAX_CONTEXT_TOKENS, load_config
from .formatting import fmt_tokens, ts_to_epoch


def event_detail(event: dict[str, Any], limit: int = 80) -> str:
    meta = event.get("meta", {})
    detail = (
        meta.get("file_path")
        or meta.get("description_full")
        or meta.get("description")
        or meta.get("cmd_full")
        or meta.get("command")
        or meta.get("skill_name")
        or meta.get("url")
        or event.get("turn_id")
        or ""
    )
    detail = str(detail).replace("\n", " ")
    return detail[:limit]


def matches_advice_ignore_path(path: str, patterns: list[str]) -> bool:
    normalized = str(path or "")
    return any(fnmatch.fnmatch(normalized, pattern) for pattern in patterns)


def event_matches_advice_ignore(event: dict[str, Any], patterns: list[str]) -> bool:
    meta = event.get("meta", {})
    paths = [part.strip() for part in str(meta.get("file_path", "")).split(",") if part.strip()]
    if any(matches_advice_ignore_path(path, patterns) for path in paths):
        return True

    detail = event_detail(event, 500)
    for pattern in patterns:
        fragments = [fragment for fragment in pattern.split("*") if len(fragment) >= 6]
        if any(fragment in detail for fragment in fragments):
            return True
    return False


def filter_ignored_file_agg(
    file_agg: dict[str, dict[str, Any]],
    patterns: list[str],
) -> dict[str, dict[str, Any]]:
    return {
        fp: data for fp, data in file_agg.items()
        if matches_advice_ignore_path(fp, patterns)
    }


def filter_visible_file_agg(
    file_agg: dict[str, dict[str, Any]],
    patterns: list[str],
) -> dict[str, dict[str, Any]]:
    return {
        fp: data for fp, data in file_agg.items()
        if not matches_advice_ignore_path(fp, patterns)
    }


def filter_visible_tool_calls(
    tool_calls: list[dict[str, Any]],
    patterns: list[str],
) -> list[dict[str, Any]]:
    return [
        e for e in tool_calls
        if not event_matches_advice_ignore(e, patterns)
    ]


def _new_turn(index: int, event: dict[str, Any], boundary: str) -> dict[str, Any]:
    return {
        "index": index,
        "turn_id": event.get("turn_id") or f"turn-{index}",
        "start_ts": event.get("ts", ""),
        "end_ts": event.get("ts", ""),
        "boundary": boundary,
        "tool_calls": 0,
        "files": 0,
        "agents": 0,
        "tokens": 0,
        "input_bytes": 0,
        "output_bytes": 0,
        "start_context_tokens": None,
        "end_context_tokens": None,
        "largest": {},
        "tools": defaultdict(int),
        "file_paths": set(),
        "file_tokens": defaultdict(int),
        "agent_statuses": defaultdict(int),
        "agent_types": defaultdict(int),
        "agent_tokens": 0,
        "top_events": [],
        "compactions": 0,
    }


def turn_duration_seconds(turn: dict[str, Any]) -> int:
    start = ts_to_epoch(turn.get("start_ts", ""))
    end = ts_to_epoch(turn.get("end_ts", ""))
    if not start or not end or end < start:
        return 0
    return int(end - start)


def classify_turn(turn: dict[str, Any]) -> str:
    if turn.get("compactions", 0):
        return "compaction"
    if turn.get("tokens", 0) >= 20000:
        return "spike"
    agent_statuses = turn.get("agent_statuses", {})
    if agent_statuses.get("running") or agent_statuses.get("requested"):
        return "agent-running"
    if turn.get("agent_tokens", 0) >= 5000 or turn.get("agents", 0) >= 2:
        return "agent-heavy"
    top_file = max((item.get("tokens", 0) for item in turn.get("top_files", [])), default=0)
    if top_file >= 5000 or turn.get("files", 0) >= 8:
        return "file-heavy"
    if turn.get("tool_calls", 0) >= 10:
        return "tool-heavy"
    return "normal"


def build_turns(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    turns: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    has_explicit_turns = any(e.get("type") == "turn_start" for e in events)
    last_epoch = 0.0

    def finish(turn: dict[str, Any] | None) -> None:
        if not turn:
            return
        turn["tools"] = dict(turn["tools"])
        turn["file_paths"] = sorted(turn["file_paths"])
        turn["files"] = len(turn["file_paths"])
        turn["file_tokens"] = dict(turn["file_tokens"])
        turn["top_files"] = [
            {"path": path, "tokens": tokens}
            for path, tokens in sorted(turn["file_tokens"].items(), key=lambda item: item[1], reverse=True)[:5]
        ]
        turn["agent_statuses"] = dict(turn["agent_statuses"])
        turn["agent_types"] = dict(turn["agent_types"])
        turn["top_events"] = sorted(
            turn.get("top_events", []),
            key=lambda e: e.get("est_tokens", 0),
            reverse=True,
        )[:5]
        turn["duration_seconds"] = turn_duration_seconds(turn)
        turn["status"] = classify_turn(turn)
        turns.append(turn)

    for event in sorted(events, key=lambda e: e.get("ts", "")):
        typ = event.get("type", "")
        epoch = ts_to_epoch(event.get("ts", ""))
        if typ == "turn_start":
            finish(current)
            current = _new_turn(len(turns) + 1, event, "exact")
        elif current is None:
            current = _new_turn(len(turns) + 1, event, "estimated")
        elif not has_explicit_turns and epoch and last_epoch and epoch - last_epoch > 120:
            finish(current)
            current = _new_turn(len(turns) + 1, event, "estimated-gap")

        current["end_ts"] = event.get("ts", current["end_ts"])
        if typ == "context_snapshot":
            current["end_context_tokens"] = event.get("current_tokens")
            if current["start_context_tokens"] is None:
                current["start_context_tokens"] = max(0, event.get("current_tokens", 0) - event.get("est_tokens", 0))
            current["tokens"] += event.get("est_tokens", 0)
        elif typ == "tool_call":
            tok = event.get("est_tokens", 0)
            current["tokens"] += tok
            current["tool_calls"] += 1
            current["input_bytes"] += event.get("input_bytes", 0)
            current["output_bytes"] += event.get("output_bytes", 0)
            current["tools"][event.get("tool", "unknown")] += tok
            current["top_events"].append(event)
            if event.get("tool") == "Agent":
                current["agents"] += 1
                current["agent_tokens"] += tok
                meta = event.get("meta", {})
                status = meta.get("status", "completed") or "completed"
                if isinstance(meta.get("agent_statuses"), dict):
                    for child_status in meta["agent_statuses"].values():
                        current["agent_statuses"][str(child_status or "unknown")] += 1
                else:
                    current["agent_statuses"][str(status)] += 1
                subtype = meta.get("subagent_type") or "default"
                current["agent_types"][str(subtype)] += 1
            fp = event.get("meta", {}).get("file_path")
            if fp:
                paths = [part.strip() for part in str(fp).split(",") if part.strip()]
                per_path_tokens = tok // max(1, len(paths))
                for part in paths:
                    current["file_paths"].add(part)
                    current["file_tokens"][part] += per_path_tokens
            if tok > current.get("largest", {}).get("est_tokens", 0):
                current["largest"] = event
        elif typ == "compaction":
            current["compactions"] += 1
        if epoch:
            last_epoch = epoch

    finish(current)
    return turns


def build_forensics(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = sorted(events, key=lambda e: e.get("ts", ""))
    tool_calls = [e for e in ordered if e.get("type") == "tool_call"]
    forensics: list[dict[str, Any]] = []
    previous_epoch = 0.0

    for event in ordered:
        if event.get("type") != "compaction":
            continue
        current_epoch = ts_to_epoch(event.get("ts", ""))
        contributors = [
            e for e in tool_calls
            if previous_epoch <= ts_to_epoch(e.get("ts", "")) <= current_epoch
        ]
        top = sorted(contributors, key=lambda e: e.get("est_tokens", 0), reverse=True)[:8]
        forensics.append({
            "type": "compaction",
            "ts": event.get("ts", ""),
            "tokens_before": event.get("est_tokens_before") or event.get("transcript_bytes_before", 0) // 4,
            "bytes_before": event.get("transcript_bytes_before", 0),
            "contributors": top,
            "summary": "largest context contributors since previous compaction",
        })
        previous_epoch = current_epoch

    snapshots = [e for e in ordered if e.get("type") == "context_snapshot" and e.get("current_tokens")]
    for prev, cur in zip(snapshots, snapshots[1:]):
        prev_tokens = prev.get("current_tokens", 0)
        cur_tokens = cur.get("current_tokens", 0)
        if prev_tokens > 20000 and cur_tokens < prev_tokens * 0.6:
            reset_epoch = ts_to_epoch(cur.get("ts", ""))
            prev_epoch = ts_to_epoch(prev.get("ts", ""))
            contributors = [
                e for e in tool_calls
                if prev_epoch <= ts_to_epoch(e.get("ts", "")) <= reset_epoch
            ]
            top = sorted(contributors, key=lambda e: e.get("est_tokens", 0), reverse=True)[:8]
            forensics.append({
                "type": "context_reset",
                "ts": cur.get("ts", ""),
                "tokens_before": prev_tokens,
                "tokens_after": cur_tokens,
                "contributors": top,
                "summary": "token snapshot dropped sharply; likely compaction/reset",
            })
    return forensics


_AGENT_STATUS_RANK = {
    "requested": 1,
    "message_sent": 2,
    "running": 3,
    "started": 3,
    "completed": 4,
    "failed": 4,
    "closed": 5,
}


def _agent_ids_from_meta(meta: dict[str, Any]) -> list[str]:
    ids: list[str] = []
    for key in ("child_session_id", "agent_id", "subagent_agent_id"):
        value = meta.get(key)
        if value:
            ids.extend(part.strip() for part in str(value).split(",") if part.strip())
    ids.extend(str(value) for value in meta.get("child_session_ids", []) if value)
    if not ids and meta.get("raw_tool_use_id"):
        ids.append(str(meta["raw_tool_use_id"]))
    deduped: list[str] = []
    for value in ids:
        if value and value not in deduped:
            deduped.append(value)
    return deduped


def _agent_run_key(event: dict[str, Any], agent_id: str = "") -> str:
    meta = event.get("meta", {})
    source = event.get("source") or ""
    parent = meta.get("parent_session_id") or event.get("session_id") or ""
    if agent_id:
        return f"{source}:{parent}:{agent_id}"
    desc = meta.get("description_full") or meta.get("description") or ""
    raw_tool = meta.get("raw_tool_use_id") or ""
    return f"{source}:{parent}:{raw_tool}:{event.get('ts', '')}:{desc}"


def _apply_agent_event_to_run(run: dict[str, Any], event: dict[str, Any], agent_id: str = "") -> None:
    meta = event.get("meta", {})
    per_agent_status = meta.get("agent_statuses") if isinstance(meta.get("agent_statuses"), dict) else {}
    status = str(per_agent_status.get(agent_id) or meta.get("status") or "completed")
    previous = str(run.get("status") or "")
    if _AGENT_STATUS_RANK.get(status, 0) >= _AGENT_STATUS_RANK.get(previous, 0):
        run["status"] = status

    event_start = event.get("start_ts") or event.get("ts", "")
    current_start = run.get("start_ts", "")
    if event_start and (
        not current_start
        or (ts_to_epoch(event_start) or 0) < (ts_to_epoch(current_start) or float("inf"))
    ):
        run["start_ts"] = event_start
    run["last_ts"] = event.get("ts", run.get("last_ts", ""))
    run["total_tokens"] += event.get("est_tokens", 0)
    run["input_bytes"] += event.get("input_bytes", 0)
    run["output_bytes"] += event.get("output_bytes", 0)
    run["events"] += 1

    if event.get("duration_ms") is not None:
        run["tool_duration_ms"] += int(event.get("duration_ms") or 0)

    lifecycle = meta.get("codex_tool") or "Agent"
    if lifecycle and lifecycle not in run["lifecycle"]:
        run["lifecycle"].append(lifecycle)

    for key, target in (
        ("source", event.get("source")),
        ("parent_session_id", meta.get("parent_session_id") or event.get("session_id")),
        ("child_session_id", meta.get("child_session_id") or agent_id),
        ("agent_id", meta.get("agent_id") or agent_id),
        ("subagent_type", meta.get("subagent_type")),
        ("nickname", meta.get("nickname")),
        ("description", meta.get("description_full") or meta.get("description")),
    ):
        if target and not run.get(key):
            run[key] = str(target)


def build_agent_runs(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return one row per observed agent invocation/lifecycle.

    Codex records lifecycle operations as separate Agent-like tool calls
    (spawn_agent, wait_agent, send_input, close_agent). Claude usually records a
    single Agent tool request and later enriches it from transcript evidence.
    This normalizes both shapes into invocation rows for the dashboard.
    """
    runs: dict[str, dict[str, Any]] = {}
    ordered = sorted(
        [event for event in events if event.get("type") == "tool_call" and event.get("tool") == "Agent"],
        key=lambda event: event.get("ts", ""),
    )

    for event in ordered:
        meta = event.get("meta", {})
        ids = _agent_ids_from_meta(meta) or [""]
        for agent_id in ids:
            key = _agent_run_key(event, agent_id)
            run = runs.setdefault(
                key,
                {
                    "source": event.get("source", ""),
                    "parent_session_id": meta.get("parent_session_id") or event.get("session_id", ""),
                    "child_session_id": agent_id or meta.get("child_session_id", ""),
                    "agent_id": agent_id or meta.get("agent_id", ""),
                    "subagent_type": meta.get("subagent_type") or "default",
                    "nickname": meta.get("nickname", ""),
                    "description": meta.get("description_full") or meta.get("description") or "",
                    "status": "",
                    "start_ts": event.get("start_ts") or event.get("ts", ""),
                    "last_ts": event.get("ts", ""),
                    "total_tokens": 0,
                    "input_bytes": 0,
                    "output_bytes": 0,
                    "tool_duration_ms": 0,
                    "events": 0,
                    "lifecycle": [],
                },
            )
            _apply_agent_event_to_run(run, event, agent_id)

    return sorted(runs.values(), key=lambda run: run.get("last_ts", ""), reverse=True)


def build_recommendations(
    tool_calls: list[dict[str, Any]],
    file_agg: dict[str, dict[str, Any]],
    agent_agg: dict[str, dict[str, Any]],
    spikes: list[tuple[int, dict[str, Any]]],
    forensics: list[dict[str, Any]],
    exactness: str,
    advice_ignore_path_patterns: list[str] | None = None,
) -> list[dict[str, Any]]:
    recs: list[dict[str, Any]] = []
    advice_ignore_path_patterns = advice_ignore_path_patterns or []
    actionable_file_agg = filter_visible_file_agg(file_agg, advice_ignore_path_patterns)
    actionable_tool_calls = filter_visible_tool_calls(tool_calls, advice_ignore_path_patterns)
    actionable_spikes = [
        (i, e) for i, e in spikes
        if not event_matches_advice_ignore(e, advice_ignore_path_patterns)
    ]

    for fp, data in sorted(actionable_file_agg.items(), key=lambda x: x[1].get("total_tokens", 0), reverse=True)[:8]:
        if data.get("reads", 0) > 1 and data.get("total_tokens", 0) >= 3000:
            recs.append({
                "severity": "high" if data.get("reads", 0) > 3 else "medium",
                "title": "Repeated expensive file reads",
                "detail": f"{fp} was read {data.get('reads', 0)} times and cost {fmt_tokens(data.get('total_tokens', 0))} tokens.",
                "action": "Cache or summarize this file once; avoid re-reading unchanged content.",
            })
    largest = max(actionable_tool_calls, key=lambda e: e.get("est_tokens", 0), default={})
    if largest and largest.get("est_tokens", 0) >= 20000:
        recs.append({
            "severity": "high",
            "title": "Single large tool result",
            "detail": f"{largest.get('tool')} added {fmt_tokens(largest.get('est_tokens', 0))} tokens: {event_detail(largest, 100)}",
            "action": "Narrow the command/read or ask for a structured summary instead of raw output.",
        })
    for subtype, data in sorted(agent_agg.items(), key=lambda x: x[1].get("max_tokens", 0), reverse=True)[:3]:
        if data.get("max_tokens", 0) >= 15000:
            recs.append({
                "severity": "medium",
                "title": "Large agent return",
                "detail": f"Agent {subtype} had a max call of {fmt_tokens(data.get('max_tokens', 0))} tokens.",
                "action": "Constrain agent output format and ask it to return findings, not raw evidence.",
            })
    if len(actionable_spikes) >= 3:
        recs.append({
            "severity": "medium",
            "title": "Multiple context spikes",
            "detail": f"{len(actionable_spikes)} events exceeded the spike threshold after advice ignore filters.",
            "action": "Review the Spikes and Turns tabs before continuing; compact after saving a summary.",
        })
    if forensics:
        recs.append({
            "severity": "high",
            "title": "Compaction/reset observed",
            "detail": f"{len(forensics)} compaction or reset event(s) were detected.",
            "action": "Use the Forensics tab to identify contributors since the previous reset.",
        })
    if exactness != "exact":
        recs.append({
            "severity": "info",
            "title": "Token accounting is approximate",
            "detail": f"This profile uses {exactness} accounting.",
            "action": "Treat small differences as directional; focus on largest contributors.",
        })
    return recs[:10]


def compute_stats(
    events: list[dict[str, Any]],
    spike_threshold: int = 5000,
    advice_ignore_path_patterns: list[str] | None = None,
) -> dict[str, Any]:
    tool_calls = [e for e in events if e.get("type") == "tool_call"]
    compactions = [e for e in events if e.get("type") == "compaction"]
    snapshots = [e for e in events if e.get("type") == "context_snapshot" and e.get("current_tokens")]
    session_start = next((e for e in events if e.get("type") == "session_start"), {})

    now = time.time()
    recent_calls = [e for e in tool_calls if ts_to_epoch(e.get("ts", "")) > now - 60]
    recent_snaps = [e for e in snapshots if ts_to_epoch(e.get("ts", "")) > now - 60]
    velocity = sum(e.get("est_tokens", 0) for e in recent_snaps) or sum(e.get("est_tokens", 0) for e in recent_calls)

    context_window = next((e.get("model_context_window") for e in reversed(snapshots) if e.get("model_context_window")), None)
    context_window = int(context_window or DEFAULT_MAX_CONTEXT_TOKENS)
    current_tokens = int(snapshots[-1].get("current_tokens", 0)) if snapshots else sum(e.get("est_tokens", 0) for e in tool_calls)
    pct = min(100, int(current_tokens / context_window * 100)) if context_window else 0

    eta_sec = None
    if velocity > 0:
        remaining = max(0, context_window - current_tokens)
        eta_sec = int(remaining / (velocity / 60)) if velocity else None

    largest = max(tool_calls, key=lambda e: e.get("est_tokens", 0), default={})
    peak_transcript = max(
        [e.get("cumulative_transcript_bytes", 0) for e in tool_calls]
        + [e.get("transcript_bytes_before", 0) for e in compactions],
        default=0,
    )
    peak_tokens = max((e.get("current_tokens", 0) for e in snapshots), default=current_tokens)

    tool_agg = defaultdict(lambda: {"calls": 0, "total_tokens": 0, "max_tokens": 0})
    for e in tool_calls:
        tool = e.get("tool", "unknown")
        tok = e.get("est_tokens", 0)
        tool_agg[tool]["calls"] += 1
        tool_agg[tool]["total_tokens"] += tok
        tool_agg[tool]["max_tokens"] = max(tool_agg[tool]["max_tokens"], tok)

    file_agg = defaultdict(
        lambda: {
            "reads": 0,
            "writes": 0,
            "total_bytes": 0,
            "total_tokens": 0,
            "read_tokens": 0,
            "write_tokens": 0,
            "max_tokens": 0,
        }
    )
    for e in tool_calls:
        fp = e.get("meta", {}).get("file_path", "")
        if not fp:
            continue
        paths = [part.strip() for part in str(fp).split(",") if part.strip()]
        ob = e.get("output_bytes", 0)
        tok = e.get("est_tokens", 0)
        per_path_bytes = ob // max(1, len(paths))
        per_path_tokens = tok // max(1, len(paths))
        for path in paths:
            file_agg[path]["total_tokens"] += per_path_tokens
            file_agg[path]["max_tokens"] = max(file_agg[path]["max_tokens"], per_path_tokens)
            if e.get("tool") in {"Read", "Bash"}:
                file_agg[path]["reads"] += 1
                file_agg[path]["total_bytes"] += per_path_bytes
                file_agg[path]["read_tokens"] += per_path_tokens
            elif e.get("tool") in {"Write", "Edit"}:
                file_agg[path]["writes"] += 1
                file_agg[path]["write_tokens"] += per_path_tokens

    idx_calls = list(enumerate(tool_calls))
    spikes = [(i, e) for i, e in idx_calls if e.get("est_tokens", 0) >= spike_threshold]

    agent_agg = defaultdict(
        lambda: {
            "calls": 0,
            "total_tokens": 0,
            "max_tokens": 0,
            "descriptions": [],
            "statuses": defaultdict(int),
        }
    )
    for e in tool_calls:
        if e.get("tool") == "Agent":
            meta = e.get("meta", {})
            subtype = meta.get("subagent_type", "default") or "default"
            status = meta.get("status", "completed") or "completed"
            codex_tool = meta.get("codex_tool")
            is_invocation = codex_tool in (None, "", "spawn_agent")
            tok = e.get("est_tokens", 0)
            desc = meta.get("description_full") or meta.get("description", "")
            if is_invocation:
                agent_agg[subtype]["calls"] += 1
                agent_agg[subtype]["statuses"][status] += 1
                if desc:
                    agent_agg[subtype]["descriptions"].append((tok, desc))
            agent_agg[subtype]["total_tokens"] += tok
            agent_agg[subtype]["max_tokens"] = max(agent_agg[subtype]["max_tokens"], tok)

    skill_agg = defaultdict(lambda: {"calls": 0, "total_tokens": 0, "last_used": ""})
    for e in tool_calls:
        meta = e.get("meta", {})
        if e.get("tool") == "Skill" or meta.get("skill_name"):
            skill = meta.get("skill_name", "unknown") or "unknown"
            tok = e.get("est_tokens", 0)
            skill_agg[skill]["calls"] += 1
            skill_agg[skill]["total_tokens"] += tok
            skill_agg[skill]["last_used"] = e.get("ts", "")

    sources = {e.get("source") for e in events if e.get("source")}
    if snapshots:
        exactness = "snapshot-based"
    elif sources == {"claude"}:
        exactness = "estimated-byte-derived"
    else:
        exactness = "estimated"
    if advice_ignore_path_patterns is None:
        advice_ignore_path_patterns = list(load_config().get("advice_ignore_path_patterns", []))
    ignored_advice_files = filter_ignored_file_agg(dict(file_agg), advice_ignore_path_patterns)
    visible_file_agg = filter_visible_file_agg(dict(file_agg), advice_ignore_path_patterns)
    visible_tool_calls = filter_visible_tool_calls(tool_calls, advice_ignore_path_patterns)
    visible_spikes = [
        (i, e) for i, e in spikes
        if not event_matches_advice_ignore(e, advice_ignore_path_patterns)
    ]
    visible_largest = max(visible_tool_calls, key=lambda e: e.get("est_tokens", 0), default={})
    hidden_usage_tokens = sum(data.get("total_tokens", 0) for data in ignored_advice_files.values())
    turns = build_turns(events)
    agent_runs = build_agent_runs(events)
    forensics = build_forensics(events)
    recommendations = build_recommendations(
        tool_calls,
        dict(file_agg),
        dict(agent_agg),
        spikes,
        forensics,
        exactness,
        advice_ignore_path_patterns,
    )

    return {
        "tool_calls": tool_calls,
        "compactions": compactions,
        "context_snapshots": snapshots,
        "session_start": session_start,
        "velocity": velocity,
        "current_tokens": current_tokens,
        "context_window": context_window,
        "pct": pct,
        "eta_sec": eta_sec,
        "largest": largest,
        "peak_transcript": peak_transcript,
        "peak_tokens": peak_tokens,
        "tool_agg": dict(tool_agg),
        "file_agg": dict(file_agg),
        "visible_file_agg": visible_file_agg,
        "spikes": spikes,
        "visible_spikes": visible_spikes,
        "agent_agg": {key: {**value, "statuses": dict(value.get("statuses", {}))} for key, value in agent_agg.items()},
        "agent_runs": agent_runs,
        "skill_agg": dict(skill_agg),
        "turns": turns,
        "forensics": forensics,
        "recommendations": recommendations,
        "ignored_advice_files": dict(ignored_advice_files),
        "visible_tool_calls": visible_tool_calls,
        "visible_largest": visible_largest,
        "hidden_usage_tokens": hidden_usage_tokens,
        "advice_ignore_path_patterns": advice_ignore_path_patterns,
        "exactness": exactness,
    }
