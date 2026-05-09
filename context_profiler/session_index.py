"""Cached session summaries for dashboard session selection."""
from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from .analysis import compute_stats
from .config import PROFILE_DIR, load_config, read_json, utc_now
from .formatting import fmt_tokens
from .storage import get_all_profiles, load_events, profile_mtime, profile_part_paths, profile_source


def session_index_path() -> Path:
    return PROFILE_DIR / ".session-index.json"


def timestamp_epoch(value: str) -> float:
    if not value:
        return 0.0
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def format_table_timestamp(value: str) -> str:
    if not value:
        return ""
    raw = str(value)
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return parsed.strftime("%m-%d %H:%M:%S")
    except ValueError:
        return raw[-19:]


def sort_session_rows_by_start(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(rows, key=lambda row: row.get("started_epoch", 0.0), reverse=True)


def session_id_for_profile(path: str | Path, events: list[dict[str, Any]]) -> str:
    start = next((event for event in events if event.get("type") == "session_start"), {})
    session_id = start.get("session_id") or next((event.get("session_id") for event in events if event.get("session_id")), "")
    if session_id:
        return str(session_id)
    stem = Path(path).stem
    return stem.removeprefix("codex-")


def profile_signature(path: str | Path) -> list[dict[str, Any]]:
    signature = []
    for part in profile_part_paths(path):
        try:
            stat = part.stat()
        except Exception:
            continue
        signature.append({"path": str(part), "size": stat.st_size, "mtime_ns": stat.st_mtime_ns})
    return signature


def _relationship_edges(events: list[dict[str, Any]]) -> tuple[list[str], list[str]]:
    parents: set[str] = set()
    children: set[str] = set()
    for event in events:
        meta = event.get("meta", {})
        parent = meta.get("parent_session_id")
        if parent:
            parents.add(str(parent))
        if meta.get("child_session_id"):
            children.add(str(meta["child_session_id"]))
        children.update(str(child) for child in meta.get("child_session_ids", []) if child)
    return sorted(parents), sorted(children)


def session_relationship_maps(rows: list[dict[str, Any]]) -> tuple[dict[str, set[str]], dict[str, str]]:
    parent_to_children: dict[str, set[str]] = {}
    child_to_parent: dict[str, str] = {}
    for row in rows:
        if row.get("events"):
            parent_ids, child_ids = _relationship_edges(row.get("events", []))
        else:
            parent_ids = [str(parent) for parent in row.get("parent_session_ids", []) if parent]
            child_ids = [str(child) for child in row.get("child_session_ids", []) if child]
        for parent in parent_ids:
            for child in child_ids:
                parent_to_children.setdefault(str(parent), set()).add(str(child))
                child_to_parent.setdefault(str(child), str(parent))
    return parent_to_children, child_to_parent


def session_relationship_label(session_id: str, parent_to_children: dict[str, set[str]], child_to_parent: dict[str, str]) -> str:
    parts = []
    children = parent_to_children.get(session_id, set())
    if children:
        parts.append(f"parent:{len(children)}")
    parent = child_to_parent.get(session_id)
    if parent:
        parts.append(f"child->{parent[:8]}")
    return " ".join(parts) or "-"


def _summarize_profile(path: str, spike_threshold: int) -> dict[str, Any]:
    events = load_events(path)
    stats = compute_stats(events, spike_threshold)
    start = stats.get("session_start") or {}
    first_ts = next((event.get("ts") for event in events if event.get("ts")), "")
    started_ts = start.get("ts") or first_ts or ""
    started_epoch = timestamp_epoch(started_ts) or profile_mtime(path)
    session_id = session_id_for_profile(path, events)
    parent_ids, child_ids = _relationship_edges(events)
    return {
        "path": str(path),
        "session_id": session_id,
        "session": Path(path).stem[:28],
        "source": profile_source(path, events),
        "started": format_table_timestamp(started_ts) or time.strftime("%m-%d %H:%M:%S", time.localtime(profile_mtime(path))),
        "started_epoch": started_epoch,
        "calls": len(stats.get("tool_calls", [])),
        "turns": len(stats.get("turns", [])),
        "tokens": stats.get("current_tokens", 0),
        "tokens_label": fmt_tokens(stats.get("current_tokens", 0)),
        "cwd": (start.get("cwd", "") or "")[-56:],
        "parent_session_ids": parent_ids,
        "child_session_ids": child_ids,
        "signature": profile_signature(path),
        "indexed_at": utc_now(),
    }


def _read_index() -> dict[str, Any]:
    data = read_json(session_index_path(), {})
    if isinstance(data, dict) and isinstance(data.get("sessions"), dict):
        return data
    return {"version": 1, "sessions": {}}


def _write_index(data: dict[str, Any]) -> None:
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    path = session_index_path()
    tmp = path.with_name(f"{path.name}.tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    tmp.replace(path)


def refresh_session_index(sources: list[str] | None = None, spike_threshold: int | None = None) -> list[dict[str, Any]]:
    cfg = load_config()
    threshold = int(spike_threshold if spike_threshold is not None else cfg.get("spike_threshold_tokens", 5000))
    paths = get_all_profiles(sources)
    current_paths = {str(path) for path in paths}
    all_profile_paths = {str(path) for path in get_all_profiles(None)}
    data = _read_index()
    cached = data.setdefault("sessions", {})
    changed = False

    for path in paths:
        path = str(path)
        signature = profile_signature(path)
        existing = cached.get(path)
        if (
            isinstance(existing, dict)
            and existing.get("signature") == signature
            and existing.get("spike_threshold_tokens") == threshold
        ):
            continue
        summary = _summarize_profile(path, threshold)
        summary["spike_threshold_tokens"] = threshold
        cached[path] = summary
        changed = True

    for path in list(cached):
        if path not in all_profile_paths:
            del cached[path]
            changed = True

    rows = [dict(row) for row in cached.values() if row.get("path") in current_paths]
    parent_to_children, child_to_parent = session_relationship_maps(rows)
    for row in rows:
        row["relationship"] = session_relationship_label(str(row.get("session_id", "")), parent_to_children, child_to_parent)
        cached_row = cached.get(row.get("path", ""))
        if isinstance(cached_row, dict) and cached_row.get("relationship") != row["relationship"]:
            cached_row["relationship"] = row["relationship"]
            changed = True

    if changed:
        data["version"] = 1
        data["updated_at"] = utc_now()
        _write_index(data)
    return sort_session_rows_by_start(rows)
