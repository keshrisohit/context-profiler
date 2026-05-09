"""Claude hook payload normalization."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from ..config import CLAUDE_PROJECTS_DIR, load_config, utc_now
from ..formatting import estimate_tokens, git_branch_for, ts_to_epoch
from ..storage import (
    load_events,
    mark_transcript_imported,
    profile_path,
    set_profile_mtime,
    transcript_import_current,
    write_profile,
)

_STATUS_RANK = {
    "requested": 1,
    "running": 2,
    "started": 2,
    "completed": 3,
}


def _merge_agent_metadata(current: dict[str, Any], incoming: dict[str, Any]) -> bool:
    changed = False
    current_meta = current.setdefault("meta", {})
    current_status = str(current_meta.get("status") or "")
    next_status = str(incoming.get("status") or "")
    if (
        next_status
        and current_status != next_status
        and _STATUS_RANK.get(next_status, 0) >= _STATUS_RANK.get(current_status, 0)
    ):
        current_meta["status"] = next_status
        changed = True

    for key in (
        "subagent_type",
        "raw_transcript_path",
        "raw_tool_use_id",
        "subagent_transcript_path",
        "subagent_agent_id",
        "child_session_id",
        "parent_session_id",
    ):
        if incoming.get(key) and current_meta.get(key) != incoming.get(key):
            current_meta[key] = incoming.get(key)
            changed = True
    return changed


def normalize_claude_tool_event(hook_payload: dict[str, Any], duration_ms: int | None = None) -> dict[str, Any]:
    tool_name = hook_payload.get("tool_name", "")
    tool_input = hook_payload.get("tool_input", {}) or {}
    tool_result = hook_payload.get("tool_response", hook_payload.get("tool_result", ""))
    transcript_path = hook_payload.get("transcript_path", "")

    input_str = json.dumps(tool_input, ensure_ascii=False)
    output_str = json.dumps(tool_result, ensure_ascii=False) if not isinstance(tool_result, str) else tool_result
    input_bytes = len(input_str.encode("utf-8"))
    output_bytes = len(output_str.encode("utf-8"))

    cumulative_transcript_bytes = 0
    if transcript_path and os.path.exists(transcript_path):
        cumulative_transcript_bytes = os.path.getsize(transcript_path)

    meta: dict[str, Any] = {}
    if tool_name in ("Read", "Write", "Edit", "NotebookEdit"):
        fp = tool_input.get("file_path", "")
        meta["file_path"] = fp
        if fp and os.path.exists(fp):
            meta["file_size_bytes"] = os.path.getsize(fp)
    elif tool_name == "Bash":
        cmd = tool_input.get("command", "")
        meta["command"] = cmd[:120]
        meta["cmd_full"] = cmd
        meta["output_preview"] = output_str[:300]
    elif tool_name == "Agent":
        meta["subagent_type"] = (
            tool_input.get("subagent_type")
            or tool_input.get("agent_type")
            or tool_input.get("type")
            or "default"
        )
        desc = (
            tool_input.get("description")
            or tool_input.get("description_full")
            or tool_input.get("prompt")
            or ""
        )
        meta["description"] = desc[:80]
        meta["description_full"] = desc
        prompt = tool_input.get("prompt", "") or ""
        if prompt:
            meta["prompt_preview"] = prompt[:300]
    elif tool_name in ("WebFetch", "WebSearch"):
        meta["url"] = (tool_input.get("url", "") or tool_input.get("query", ""))[:200]
    elif tool_name == "Skill":
        meta["skill_name"] = (
            tool_input.get("skill")
            or tool_input.get("skill_name")
            or tool_input.get("name")
            or "unknown"
        )
        meta["skill_args"] = (
            tool_input.get("args")
            or tool_input.get("arguments")
            or tool_input.get("input")
            or ""
        )
    elif tool_name in ("Glob", "Grep"):
        meta["pattern"] = tool_input.get("pattern", "")
        meta["path"] = tool_input.get("path", "")

    event: dict[str, Any] = {
        "type": "tool_call",
        "ts": utc_now(),
        "tool": tool_name,
        "input_bytes": input_bytes,
        "output_bytes": output_bytes,
        "est_tokens": estimate_tokens(input_bytes, output_bytes, output_str),
        "cumulative_transcript_bytes": cumulative_transcript_bytes,
        "meta": meta,
    }
    if duration_ms is not None:
        event["duration_ms"] = duration_ms
    return event


def _message_text(row: dict[str, Any]) -> str:
    message = row.get("message") or {}
    content = message.get("content") or []
    if isinstance(content, str):
        return content
    parts = []
    for item in content:
        if isinstance(item, dict) and item.get("type") == "tool_result":
            parts.append(str(item.get("content") or ""))
    return "\n".join(parts)


def _tool_results_by_id(rows: list[dict[str, Any]]) -> dict[str, str]:
    results: dict[str, str] = {}
    for row in rows:
        message = row.get("message") or {}
        content = message.get("content") or []
        if not isinstance(content, list):
            continue
        for item in content:
            if not isinstance(item, dict) or item.get("type") != "tool_result":
                continue
            tool_id = item.get("tool_use_id")
            if tool_id:
                results[str(tool_id)] = str(item.get("content") or _message_text(row))
    return results


def _subagent_starts_for_transcript(path: Path) -> list[dict[str, Any]]:
    subagents_dir = path.parent / path.stem / "subagents"
    if not subagents_dir.exists():
        return []

    starts: list[dict[str, Any]] = []
    for subagent_path in subagents_dir.glob("*.jsonl"):
        try:
            first_line = next(
                line for line in subagent_path.read_text(errors="ignore").splitlines()
                if line.strip()
            )
            first = json.loads(first_line)
        except Exception:
            continue
        ts = first.get("timestamp") or ""
        starts.append(
            {
                "ts": ts,
                "epoch": ts_to_epoch(ts),
                "path": str(subagent_path),
                "agent_id": first.get("agentId") or subagent_path.stem,
            }
        )
    return sorted(starts, key=lambda item: item.get("epoch") or 0)


def _match_subagent_start(
    starts: list[dict[str, Any]],
    used_indices: set[int],
    request_ts: str,
) -> dict[str, Any] | None:
    request_epoch = ts_to_epoch(request_ts)
    if not request_epoch:
        return None
    best_idx = None
    best_delta = None
    for idx, start in enumerate(starts):
        if idx in used_indices:
            continue
        start_epoch = start.get("epoch")
        if not start_epoch:
            continue
        delta = start_epoch - request_epoch
        if delta < -1 or delta > 10:
            continue
        if best_delta is None or delta < best_delta:
            best_idx = idx
            best_delta = delta
    if best_idx is None:
        return None
    used_indices.add(best_idx)
    return starts[best_idx]


def _agent_events_from_transcript(path: Path, rows: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    result_by_id = _tool_results_by_id(rows)
    subagent_starts = _subagent_starts_for_transcript(path)
    used_subagent_indices: set[int] = set()
    session_id = path.stem
    events: list[dict[str, Any]] = []
    transcript_bytes = path.stat().st_size if path.exists() else 0

    for row in rows:
        message = row.get("message") or {}
        if message.get("role") != "assistant":
            continue
        for item in message.get("content") or []:
            if not isinstance(item, dict) or item.get("type") != "tool_use" or item.get("name") != "Agent":
                continue
            tool_input = item.get("input") or {}
            tool_id = str(item.get("id") or "")
            output = result_by_id.get(tool_id, "")
            session_id = str(row.get("sessionId") or session_id)
            desc = str(tool_input.get("description") or tool_input.get("prompt") or "")
            subtype = (
                tool_input.get("subagent_type")
                or tool_input.get("agent_type")
                or tool_input.get("type")
                or tool_input.get("model")
                or "default"
            )
            input_str = json.dumps(tool_input, ensure_ascii=False)
            input_bytes = len(input_str.encode("utf-8"))
            output_bytes = len(output.encode("utf-8"))
            subagent_start = _match_subagent_start(
                subagent_starts,
                used_subagent_indices,
                row.get("timestamp") or "",
            )
            if tool_id in result_by_id:
                status = "completed"
            elif subagent_start:
                status = "running"
            else:
                status = "requested"
            meta = {
                "parent_session_id": session_id,
                "subagent_type": subtype,
                "description": desc[:80],
                "description_full": desc,
                "prompt_preview": str(tool_input.get("prompt") or "")[:300],
                "raw_transcript_path": str(path),
                "raw_tool_use_id": tool_id,
                "status": status,
            }
            if subagent_start:
                meta["subagent_transcript_path"] = subagent_start.get("path", "")
                meta["subagent_agent_id"] = subagent_start.get("agent_id", "")
                meta["child_session_id"] = subagent_start.get("agent_id", "")
            events.append(
                {
                    "type": "tool_call",
                    "ts": row.get("timestamp") or utc_now(),
                    "source": "claude",
                    "session_id": session_id,
                    "tool": "Agent",
                    "input_bytes": input_bytes,
                    "output_bytes": output_bytes,
                    "est_tokens": estimate_tokens(input_bytes, output_bytes, output),
                    "cumulative_transcript_bytes": transcript_bytes,
                    "meta": meta,
                }
            )
    return session_id, events


def import_claude_transcript(path: str | Path) -> Path | None:
    path = Path(path)
    try:
        rows = [json.loads(line) for line in path.read_text(errors="ignore").splitlines() if line.strip()]
    except Exception:
        return None

    if not rows:
        return None
    session_id, raw_agent_events = _agent_events_from_transcript(path, rows)
    if not raw_agent_events:
        return None

    out = profile_path(session_id, "claude")
    existing = load_events(out)
    if not existing:
        first = next((row for row in rows if row.get("sessionId")), rows[0])
        existing.append(
            {
                "type": "session_start",
                "ts": first.get("timestamp") or utc_now(),
                "source": "claude",
                "session_id": session_id,
                "cwd": first.get("cwd", ""),
                "git_branch": first.get("gitBranch") or git_branch_for(first.get("cwd", "")),
                "meta": {"transcript_path": str(path)},
            }
        )

    existing_raw_ids: dict[str, int] = {
        str((event.get("meta") or {}).get("raw_tool_use_id")): idx
        for idx, event in enumerate(existing)
        if (event.get("meta") or {}).get("raw_tool_use_id")
    }
    existing_descriptions: dict[str, int] = {
        str((event.get("meta") or {}).get("description_full") or (event.get("meta") or {}).get("description") or ""): idx
        for idx, event in enumerate(existing)
        if event.get("tool") == "Agent"
    }

    merged = list(existing)
    changed = False
    for event in raw_agent_events:
        meta = event.get("meta") or {}
        raw_id = str(meta.get("raw_tool_use_id") or "")
        desc = str(meta.get("description_full") or meta.get("description") or "")
        if raw_id and raw_id in existing_raw_ids:
            idx = existing_raw_ids[raw_id]
            current = merged[idx]
            if _merge_agent_metadata(current, meta):
                changed = True
            if event.get("output_bytes", 0) > current.get("output_bytes", 0):
                current["output_bytes"] = event.get("output_bytes", 0)
                current["est_tokens"] = event.get("est_tokens", current.get("est_tokens", 0))
                changed = True
            continue
        if desc and desc in existing_descriptions:
            idx = existing_descriptions[desc]
            if _merge_agent_metadata(merged[idx], meta):
                changed = True
            if raw_id:
                existing_raw_ids[raw_id] = idx
            continue
        merged.append(event)
        if raw_id:
            existing_raw_ids[raw_id] = len(merged) - 1
        existing_descriptions[desc] = len(merged) - 1
        changed = True

    if not changed:
        return out if out.exists() else None
    merged.sort(key=lambda event: event.get("ts", ""))
    written = write_profile(session_id, merged, "claude")
    try:
        set_profile_mtime(written, path.stat().st_atime, path.stat().st_mtime)
    except Exception:
        pass
    return written


def latest_claude_transcripts(limit: int = 5) -> list[Path]:
    root = Path(load_config().get("claude_projects_dir") or CLAUDE_PROJECTS_DIR).expanduser()
    if not root.exists():
        return []
    files = [
        path for path in root.rglob("*.jsonl")
        if "/subagents/" not in str(path)
    ]
    return sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)[:limit]


def import_latest_claude_profiles(limit: int | None = None) -> list[Path]:
    cfg = load_config()
    if not cfg.get("enabled", True):
        return []
    if "claude" not in cfg.get("sources", ["claude", "codex"]):
        return []
    if limit is None:
        limit = int(cfg.get("claude_import_limit", 25))
    imported = []
    for transcript in reversed(latest_claude_transcripts(limit)):
        if transcript_import_current("claude", transcript):
            continue
        out = import_claude_transcript(transcript)
        mark_transcript_imported("claude", transcript, out)
        if out:
            imported.append(out)
    return imported
