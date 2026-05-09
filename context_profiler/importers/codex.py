"""Codex rollout transcript importer."""
from __future__ import annotations

import json
import os
import re
import shlex
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..config import CODEX_SESSIONS_DIR, load_config, utc_now
from ..formatting import estimate_tokens, git_branch_for, ts_to_epoch
from ..storage import mark_transcript_imported, set_profile_mtime, transcript_import_current, write_profile


def _parse_args(raw: str | dict[str, Any] | None) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _parse_json_object(raw: str | dict[str, Any] | None) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _infer_file_from_command(args: dict[str, Any]) -> dict[str, Any]:
    cmd = str(args.get("cmd") or args.get("command") or "")
    workdir = str(args.get("workdir") or "")
    if not cmd:
        return {}
    try:
        parts = shlex.split(cmd)
    except Exception:
        return {}
    if not parts:
        return {}
    readers = {"cat", "sed", "head", "tail", "nl", "wc"}
    if Path(parts[0]).name not in readers:
        return {}
    candidates = [p for p in parts[1:] if not p.startswith("-") and not re.match(r"^[0-9,]+[a-z]?$", p)]
    for candidate in reversed(candidates):
        path = Path(candidate)
        if not path.is_absolute() and workdir:
            path = Path(workdir) / path
        if path.exists() and path.is_file():
            return {"file_path": str(path), "file_size_bytes": path.stat().st_size}
    return {}


def _skill_name_from_path(path: str) -> str:
    parts = Path(path).parts
    if not parts or parts[-1] != "SKILL.md":
        return ""
    try:
        return parts[-2]
    except IndexError:
        return ""


def _infer_skill_from_command(cmd: str) -> str:
    if not cmd:
        return ""
    try:
        parts = shlex.split(cmd)
    except Exception:
        parts = []
    if not parts:
        return ""
    readers = {"cat", "sed", "head", "tail", "nl"}
    if Path(parts[0]).name not in readers:
        return ""
    for part in parts[1:]:
        if part.endswith("/SKILL.md"):
            return _skill_name_from_path(part)
    return ""


def _codex_tool_name(name: str, args: dict[str, Any]) -> str:
    if name in {"exec_command", "write_stdin", "read_thread_terminal"}:
        return "Bash"
    if name in {"spawn_agent", "send_input", "wait_agent", "close_agent", "resume_agent"}:
        return "Agent"
    if name in {"apply_patch"}:
        return "Edit"
    if name in {"view_image"}:
        return "Read"
    return name or "tool"


def _codex_tool_meta(
    name: str,
    args: dict[str, Any],
    output: str,
    parent_session_id: str = "",
    agent_types: dict[str, str] | None = None,
) -> dict[str, Any]:
    meta: dict[str, Any] = {"codex_tool": name}
    agent_types = agent_types or {}
    parsed_output = _parse_json_object(output)
    if name in {"exec_command", "write_stdin"}:
        cmd = str(args.get("cmd") or "")
        meta["command"] = cmd[:120]
        meta["cmd_full"] = cmd
        meta["workdir"] = args.get("workdir", "")
        meta["output_preview"] = output[:300]
        meta.update(_infer_file_from_command(args))
        skill_name = _skill_name_from_path(str(meta.get("file_path") or "")) or _infer_skill_from_command(cmd)
        if skill_name:
            meta["skill_name"] = skill_name
            meta["skill_args"] = {"command": cmd}
    elif name == "spawn_agent":
        meta["parent_session_id"] = parent_session_id
        meta["subagent_type"] = args.get("agent_type") or "default"
        desc = str(args.get("message") or args.get("items") or "")
        meta["description"] = desc[:80]
        meta["description_full"] = desc
        if desc:
            meta["prompt_preview"] = desc[:300]
        agent_id = str(parsed_output.get("agent_id") or "")
        if agent_id:
            meta["agent_id"] = agent_id
            meta["child_session_id"] = agent_id
            meta["nickname"] = parsed_output.get("nickname", "")
            meta["status"] = "running"
        else:
            meta["status"] = "requested"
    elif name == "send_input":
        target = str(args.get("target") or "")
        meta["parent_session_id"] = parent_session_id
        meta["agent_id"] = target
        meta["child_session_id"] = target
        meta["subagent_type"] = agent_types.get(target) or target or "unknown"
        desc = str(args.get("message") or args.get("items") or "")
        meta["description"] = desc[:80]
        meta["description_full"] = desc
        if desc:
            meta["prompt_preview"] = desc[:300]
        meta["status"] = "message_sent"
    elif name == "wait_agent":
        targets = [str(target) for target in args.get("targets", [])]
        types = sorted({agent_types.get(target, "") for target in targets if agent_types.get(target)})
        per_agent_status = _agent_statuses(parsed_output, targets)
        meta["parent_session_id"] = parent_session_id
        meta["agent_id"] = ",".join(targets)
        meta["child_session_ids"] = targets
        if len(targets) == 1:
            meta["child_session_id"] = targets[0]
        meta["subagent_type"] = types[0] if len(types) == 1 else "multiple" if len(types) > 1 else "unknown"
        meta["description"] = f"wait_agent: {len(targets)} target(s)"
        meta["agent_statuses"] = per_agent_status
        if targets and all(per_agent_status.get(target) == "completed" for target in targets):
            meta["status"] = "completed"
        elif any(status == "failed" for status in per_agent_status.values()):
            meta["status"] = "failed"
        else:
            meta["status"] = "running"
    elif name == "close_agent":
        target = str(args.get("target") or "")
        meta["parent_session_id"] = parent_session_id
        meta["agent_id"] = target
        meta["child_session_id"] = target
        meta["subagent_type"] = agent_types.get(target) or target or "unknown"
        meta["description"] = "close_agent"
        meta["status"] = "closed"
    elif name == "resume_agent":
        target = str(args.get("id") or args.get("target") or "")
        meta["parent_session_id"] = parent_session_id
        meta["agent_id"] = target
        meta["child_session_id"] = target
        meta["subagent_type"] = agent_types.get(target) or target or "unknown"
        meta["description"] = "resume_agent"
        meta["status"] = "running"
    elif name == "apply_patch":
        patch = str(args.get("input") or "")
        files = re.findall(r"^\*\*\* (?:Add|Update|Delete) File: (.+)$", patch, flags=re.MULTILINE)
        if files:
            meta["file_path"] = ", ".join(files[:3])
        meta["description"] = "apply_patch"
        meta["patch_preview"] = patch[:300]
    elif name == "view_image":
        meta["file_path"] = args.get("path", "")
    return meta


def _completed_agent_ids(parsed_output: dict[str, Any]) -> set[str]:
    statuses = parsed_output.get("status")
    if not isinstance(statuses, dict):
        return set()
    completed: set[str] = set()
    for agent_id, state in statuses.items():
        if isinstance(state, dict) and state.get("completed"):
            completed.add(str(agent_id))
    return completed


def _agent_statuses(parsed_output: dict[str, Any], targets: list[str]) -> dict[str, str]:
    statuses = parsed_output.get("status")
    if not isinstance(statuses, dict):
        return {target: "running" for target in targets}
    result: dict[str, str] = {}
    for target in targets:
        state = statuses.get(target)
        if isinstance(state, dict) and state.get("completed"):
            result[target] = "completed"
        elif isinstance(state, dict) and (state.get("failed") or state.get("error")):
            result[target] = "failed"
        else:
            result[target] = "running"
    return result


def _append_codex_tool_event(
    events: list[dict[str, Any]],
    path: Path,
    session_id: str,
    ts: str,
    name: str,
    args: dict[str, Any],
    output: str,
    start_ts: str | None,
    agent_types: dict[str, str],
) -> dict[str, Any]:
    input_str = json.dumps(args, ensure_ascii=False)
    input_bytes = len(input_str.encode("utf-8"))
    output_bytes = len(output.encode("utf-8"))
    duration_ms = None
    if start_ts:
        duration_ms = max(0, int((ts_to_epoch(ts) - ts_to_epoch(start_ts)) * 1000))
    event = {
        "type": "tool_call",
        "ts": ts,
        "source": "codex",
        "session_id": session_id,
        "tool": _codex_tool_name(name, args),
        "input_bytes": input_bytes,
        "output_bytes": output_bytes,
        "est_tokens": estimate_tokens(input_bytes, output_bytes, output),
        "duration_ms": duration_ms,
        "cumulative_transcript_bytes": path.stat().st_size if path.exists() else 0,
        "meta": _codex_tool_meta(name, args, output, session_id, agent_types),
    }
    if start_ts:
        event["start_ts"] = start_ts
    events.append(event)
    return event


def import_codex_transcript(path: str | Path) -> Path | None:
    path = Path(path)
    calls: dict[str, dict[str, Any]] = {}
    events: list[dict[str, Any]] = []
    session_id = path.stem.replace("rollout-", "").split("-")[-5:]
    session_id_str = "-".join(session_id) if session_id else path.stem
    cwd = ""
    context_window = None
    last_snapshot_tokens: int | None = None
    agent_types: dict[str, str] = {}
    spawn_events: dict[str, dict[str, Any]] = {}

    try:
        lines = path.read_text().splitlines()
    except Exception:
        return None

    for line in lines:
        try:
            row = json.loads(line)
        except Exception:
            continue
        ts = row.get("timestamp") or utc_now()
        typ = row.get("type")
        payload = row.get("payload") or {}
        ptype = payload.get("type")

        if typ == "session_meta":
            meta = payload
            session_id_str = meta.get("id") or session_id_str
            cwd = meta.get("cwd") or cwd
            events.append(
                {
                    "type": "session_start",
                    "ts": ts,
                    "source": "codex",
                    "session_id": session_id_str,
                    "cwd": cwd,
                    "git_branch": git_branch_for(cwd),
                    "meta": {
                        "originator": meta.get("originator", ""),
                        "cli_version": meta.get("cli_version", ""),
                        "model_provider": meta.get("model_provider", ""),
                        "transcript_path": str(path),
                    },
                }
            )
            continue

        if typ == "event_msg" and ptype == "task_started":
            context_window = payload.get("model_context_window") or context_window
            events.append(
                {
                    "type": "turn_start",
                    "ts": ts,
                    "source": "codex",
                    "session_id": session_id_str,
                    "turn_id": payload.get("turn_id", ""),
                    "model_context_window": context_window,
                }
            )
            continue

        if typ == "event_msg" and ptype == "token_count":
            info = payload.get("info") or {}
            total = info.get("total_token_usage") or {}
            last = info.get("last_token_usage") or total
            current = int(last.get("total_tokens") or 0)
            context_window = info.get("model_context_window") or context_window
            delta = max(0, current - last_snapshot_tokens) if last_snapshot_tokens is not None else 0
            last_snapshot_tokens = current or last_snapshot_tokens
            events.append(
                {
                    "type": "context_snapshot",
                    "ts": ts,
                    "source": "codex",
                    "session_id": session_id_str,
                    "current_tokens": current,
                    "cumulative_total_tokens": total.get("total_tokens", 0),
                    "est_tokens": delta,
                    "model_context_window": context_window,
                    "input_tokens": last.get("input_tokens", 0),
                    "cached_input_tokens": last.get("cached_input_tokens", 0),
                    "output_tokens": last.get("output_tokens", 0),
                    "reasoning_output_tokens": last.get("reasoning_output_tokens", 0),
                }
            )
            continue

        if typ == "response_item" and ptype in {"function_call", "custom_tool_call"}:
            call_id = payload.get("call_id") or payload.get("id") or f"call-{len(calls)}"
            raw_args = payload.get("arguments") if ptype == "function_call" else payload.get("input")
            args = _parse_args(raw_args)
            if ptype == "custom_tool_call" and not args and isinstance(raw_args, str):
                args = {"input": raw_args}
            calls[call_id] = {"ts": ts, "name": payload.get("name", ""), "args": args}
            continue

        if typ == "response_item" and ptype in {"function_call_output", "custom_tool_call_output"}:
            call_id = payload.get("call_id") or payload.get("id") or ""
            start = calls.pop(call_id, {})
            name = start.get("name", "")
            args = start.get("args", {})
            output = str(payload.get("output") or "")
            if ptype == "custom_tool_call_output" and not output:
                output = json.dumps(payload, ensure_ascii=False)
            start_ts = start.get("ts") or ts
            event = _append_codex_tool_event(
                events,
                path,
                session_id_str,
                ts,
                name,
                args,
                output,
                start_ts,
                agent_types,
            )
            parsed_output = _parse_json_object(output)
            if name == "spawn_agent":
                agent_id = str(parsed_output.get("agent_id") or "")
                if agent_id:
                    agent_type = str(args.get("agent_type") or "default")
                    agent_types[agent_id] = agent_type
                    spawn_events[agent_id] = event
            elif name == "wait_agent":
                for agent_id in _completed_agent_ids(parsed_output):
                    if agent_id in spawn_events:
                        spawn_events[agent_id].setdefault("meta", {})["status"] = "completed"
            continue

        if typ == "event_msg" and ptype == "task_complete":
            events.append(
                {
                    "type": "session_end",
                    "ts": ts,
                    "source": "codex",
                    "session_id": session_id_str,
                    "total_tool_calls": sum(1 for e in events if e.get("type") == "tool_call"),
                    "compaction_count": sum(1 for e in events if e.get("type") == "compaction"),
                    "peak_transcript_bytes": path.stat().st_size if path.exists() else 0,
                    "peak_est_tokens": max((e.get("current_tokens", 0) for e in events), default=0),
                    "total_est_tokens_added": sum(e.get("est_tokens", 0) for e in events if e.get("type") == "tool_call"),
                }
            )

    for start in calls.values():
        name = start.get("name", "")
        if name != "spawn_agent":
            continue
        _append_codex_tool_event(
            events,
            path,
            session_id_str,
            start.get("ts") or utc_now(),
            name,
            start.get("args", {}),
            "",
            start.get("ts"),
            agent_types,
        )

    if not events:
        return None
    if not any(e.get("type") == "session_start" for e in events):
        events.insert(
            0,
            {
                "type": "session_start",
                "ts": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).replace(tzinfo=None).isoformat() + "Z",
                "source": "codex",
                "session_id": session_id_str,
                "cwd": cwd,
                "git_branch": git_branch_for(cwd),
                "meta": {"transcript_path": str(path)},
            },
        )
    out = write_profile(session_id_str, events, "codex")
    try:
        set_profile_mtime(out, path.stat().st_atime, path.stat().st_mtime)
    except Exception:
        pass
    return out


def latest_codex_transcripts(limit: int = 5) -> list[Path]:
    root = Path(load_config().get("codex_sessions_dir") or CODEX_SESSIONS_DIR).expanduser()
    if not root.exists():
        return []
    files = sorted(root.rglob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[:limit]


def import_latest_codex_profiles(limit: int | None = None) -> list[Path]:
    cfg = load_config()
    if not cfg.get("enabled", True):
        return []
    if "codex" not in cfg.get("sources", ["claude", "codex"]):
        return []
    if limit is None:
        limit = int(cfg.get("codex_import_limit", 25))
    imported = []
    for transcript in reversed(latest_codex_transcripts(limit)):
        if transcript_import_current("codex", transcript):
            continue
        out = import_codex_transcript(transcript)
        mark_transcript_imported("codex", transcript, out)
        if out:
            imported.append(out)
    return imported


class CodexTranscriptImporter:
    source = "codex"

    def import_latest(self, limit: int = 5) -> list[Path]:
        return import_latest_codex_profiles(limit)
