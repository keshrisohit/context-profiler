"""JSONL profile storage and profile discovery."""
from __future__ import annotations

import glob
import json
import os
import time
from pathlib import Path
from typing import Any

from .config import CODEX_SESSIONS_DIR, PROFILE_DIR, load_config, read_json, utc_now

IMPORT_CURSOR_VERSION = 2


def safe_session_id(session_id: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in str(session_id or "unknown"))


def profile_path(session_id: str, source: str = "claude") -> Path:
    sid = safe_session_id(session_id)
    stem = f"codex-{sid}" if source == "codex" and not sid.startswith("codex-") else sid
    return PROFILE_DIR / f"{stem}.jsonl"


def _is_profile_part(path: str | Path) -> bool:
    return ".part-" in Path(path).stem


def _base_profile_path(path: str | Path) -> Path:
    path = Path(path)
    stem = path.stem
    if ".part-" not in stem:
        return path
    return path.with_name(f"{stem.split('.part-', 1)[0]}{path.suffix}")


def profile_part_path(base_path: str | Path, index: int) -> Path:
    base = _base_profile_path(base_path)
    if index <= 1:
        return base
    return base.with_name(f"{base.stem}.part-{index:04d}{base.suffix}")


def profile_part_paths(base_path: str | Path) -> list[Path]:
    base = _base_profile_path(base_path)
    paths = [base] if base.exists() else []
    paths.extend(sorted(base.parent.glob(f"{base.stem}.part-*{base.suffix}")))
    return paths


def profile_mtime(path: str | Path) -> float:
    mtimes = []
    for part in profile_part_paths(path):
        try:
            mtimes.append(part.stat().st_mtime)
        except Exception:
            pass
    if mtimes:
        return max(mtimes)
    try:
        return Path(path).stat().st_mtime
    except Exception:
        return 0.0


def set_profile_mtime(path: str | Path, atime: float, mtime: float) -> None:
    for part in profile_part_paths(path):
        try:
            os.utime(part, (atime, mtime))
        except Exception:
            pass


def file_signature(path: str | Path) -> dict[str, int]:
    stat = Path(path).stat()
    return {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns}


def _import_cursor_path() -> Path:
    return PROFILE_DIR / ".import-cursors.json"


def _load_import_cursors() -> dict[str, Any]:
    data = read_json(_import_cursor_path(), {})
    return data if isinstance(data, dict) else {}


def _save_import_cursors(data: dict[str, Any]) -> None:
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    path = _import_cursor_path()
    tmp = path.with_name(f"{path.name}.tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    tmp.replace(path)


def transcript_import_current(source: str, transcript: str | Path) -> bool:
    path = Path(transcript)
    try:
        signature = file_signature(path)
    except Exception:
        return False
    cursor = _load_import_cursors().get(source, {}).get(str(path))
    if not isinstance(cursor, dict) or cursor.get("signature") != signature:
        return False
    if cursor.get("cursor_version") != IMPORT_CURSOR_VERSION:
        return False
    if cursor.get("status") == "skipped":
        return True
    profile = cursor.get("profile")
    return bool(profile and Path(profile).exists())


def mark_transcript_imported(source: str, transcript: str | Path, profile: str | Path | None) -> None:
    path = Path(transcript)
    try:
        signature = file_signature(path)
    except Exception:
        return
    data = _load_import_cursors()
    source_data = data.setdefault(source, {})
    source_data[str(path)] = {
        "cursor_version": IMPORT_CURSOR_VERSION,
        "signature": signature,
        "profile": str(profile or ""),
        "status": "imported" if profile else "skipped",
        "imported_at": utc_now(),
    }
    _save_import_cursors(data)


def _rotation_limit_bytes() -> int:
    cfg = load_config()
    if not cfg.get("profile_rotation_enabled", True):
        return 0
    try:
        return max(0, int(cfg.get("profile_max_part_bytes", 10_000_000)))
    except Exception:
        return 10_000_000


def _chunk_jsonl_lines(lines: list[str], max_bytes: int) -> list[str]:
    if not lines:
        return [""]
    if max_bytes <= 0:
        return ["".join(lines)]
    chunks: list[str] = []
    current: list[str] = []
    current_bytes = 0
    for line in lines:
        line_bytes = len(line.encode("utf-8"))
        if current and current_bytes + line_bytes > max_bytes:
            chunks.append("".join(current))
            current = []
            current_bytes = 0
        current.append(line)
        current_bytes += line_bytes
    if current:
        chunks.append("".join(current))
    return chunks


def append_event(session_id: str, event: dict[str, Any], source: str = "claude") -> None:
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    event.setdefault("ts", utc_now())
    event.setdefault("source", source)
    event.setdefault("session_id", session_id)
    line = json.dumps(event, ensure_ascii=False) + "\n"
    base = profile_path(session_id, source)
    parts = profile_part_paths(base)
    target = parts[-1] if parts else base
    max_bytes = _rotation_limit_bytes()
    if max_bytes and target.exists() and target.stat().st_size > 0:
        if target.stat().st_size + len(line.encode("utf-8")) > max_bytes:
            target = profile_part_path(base, len(parts) + 1)
    with target.open("a") as f:
        f.write(line)


def write_profile(session_id: str, events: list[dict[str, Any]], source: str) -> Path:
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    path = profile_path(session_id, source)
    lines = [json.dumps(e, ensure_ascii=False) + "\n" for e in events]
    chunks = _chunk_jsonl_lines(lines, _rotation_limit_bytes())
    existing_parts = profile_part_paths(path)
    try:
        if existing_parts and len(existing_parts) == len(chunks):
            if all(part.read_text() == chunk for part, chunk in zip(existing_parts, chunks)):
                return path
    except Exception:
        pass
    temp_paths: list[Path] = []
    for index, chunk in enumerate(chunks, 1):
        part = profile_part_path(path, index)
        tmp = part.with_name(f"{part.name}.tmp")
        tmp.write_text(chunk)
        temp_paths.append(tmp)
    for index, tmp in enumerate(temp_paths, 1):
        tmp.replace(profile_part_path(path, index))
    for stale in existing_parts[len(chunks):]:
        try:
            stale.unlink()
        except Exception:
            pass
    return path


def load_events(path: str | Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for part in profile_part_paths(path) or [Path(path)]:
        try:
            with open(part) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        events.append(json.loads(line))
                    except Exception:
                        pass
        except Exception:
            pass
    return events


def profile_source(path: str | Path, events: list[dict[str, Any]] | None = None) -> str:
    stem = Path(path).stem
    if stem.startswith("codex-"):
        return "codex"
    if events:
        return str(events[0].get("source") or "claude")
    return "claude"


def get_all_profiles(sources: list[str] | None = None) -> list[str]:
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    files = [fp for fp in glob.glob(str(PROFILE_DIR / "*.jsonl")) if not _is_profile_part(fp)]
    if not sources:
        return sorted(files)
    allowed = set(sources)
    return sorted(fp for fp in files if profile_source(fp) in allowed)


def get_all_profile_files(sources: list[str] | None = None) -> list[str]:
    files: list[str] = []
    for base in get_all_profiles(sources):
        files.extend(str(part) for part in profile_part_paths(base))
    return sorted(files)


def profile_matches_session(path: str | Path, session_filter: str | None) -> bool:
    if not session_filter:
        return True
    needle = safe_session_id(session_filter)
    stem = Path(path).stem
    candidates = {
        stem,
        stem.removeprefix("codex-"),
        f"codex-{stem}",
    }
    return any(candidate == needle or candidate.startswith(needle) for candidate in candidates)


def filter_profiles_by_session(paths: list[str], session_filter: str | None) -> list[str]:
    return [p for p in paths if profile_matches_session(p, session_filter)]


def get_latest_session(pin: str | None = None, sources: list[str] | None = None) -> str | None:
    if pin:
        candidates = [
            PROFILE_DIR / f"{pin}.jsonl",
            PROFILE_DIR / f"codex-{pin}.jsonl",
        ]
        for candidate in candidates:
            if candidate.exists():
                return str(candidate)
        matches = filter_profiles_by_session(get_all_profiles(sources), pin)
        return max(matches, key=profile_mtime) if matches else None
    files = get_all_profiles(sources)
    return max(files, key=profile_mtime) if files else None


def _cleanup_paths(paths: list[str | Path], days: int, dry_run: bool) -> dict[str, Any]:
    cutoff = time.time() - (days * 86400)
    matched: list[dict[str, Any]] = []
    bytes_total = 0
    for raw_path in paths:
        path = Path(raw_path)
        try:
            if not path.is_file() or path.stat().st_mtime >= cutoff:
                continue
            size = path.stat().st_size
            matched.append({"path": str(path), "bytes": size, "mtime": path.stat().st_mtime})
            bytes_total += size
            if not dry_run:
                path.unlink()
        except Exception as exc:
            matched.append({"path": str(path), "bytes": 0, "error": str(exc)})
    return {
        "days": days,
        "dry_run": dry_run,
        "count": len(matched),
        "bytes": bytes_total,
        "paths": matched,
    }


def cleanup_old_profiles(
    days: int = 5,
    dry_run: bool = False,
    sources: list[str] | None = None,
) -> dict[str, Any]:
    cutoff = time.time() - (days * 86400)
    matched: list[dict[str, Any]] = []
    bytes_total = 0
    for base in get_all_profiles(sources):
        if profile_mtime(base) >= cutoff:
            continue
        for part in profile_part_paths(base):
            try:
                size = part.stat().st_size
                matched.append({"path": str(part), "bytes": size, "mtime": part.stat().st_mtime})
                bytes_total += size
                if not dry_run:
                    part.unlink()
            except Exception as exc:
                matched.append({"path": str(part), "bytes": 0, "error": str(exc)})
    return {
        "days": days,
        "dry_run": dry_run,
        "count": len(matched),
        "bytes": bytes_total,
        "paths": matched,
    }


def run_auto_cleanup(sources: list[str] | None = None) -> dict[str, Any] | None:
    cfg = load_config()
    if not cfg.get("auto_cleanup_enabled", True):
        return None

    state_path = PROFILE_DIR / ".cleanup-state.json"
    interval_hours = max(1, int(cfg.get("auto_cleanup_interval_hours", 24)))
    now = time.time()
    state = read_json(state_path, {})
    if isinstance(state, dict):
        last_run = float(state.get("last_profile_cleanup_ts", 0) or 0)
        if now - last_run < interval_hours * 3600:
            return None

    days = max(1, int(cfg.get("cleanup_retention_days", 5)))
    result = cleanup_old_profiles(days=days, dry_run=False, sources=sources)
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps({
        "last_profile_cleanup_ts": now,
        "retention_days": days,
        "deleted_profiles": result.get("count", 0),
    }, indent=2) + "\n")
    return result


def cleanup_old_codex_transcripts(
    days: int = 5,
    dry_run: bool = False,
    root: str | Path | None = None,
) -> dict[str, Any]:
    base = Path(root or CODEX_SESSIONS_DIR).expanduser()
    if not base.exists():
        return {"days": days, "dry_run": dry_run, "count": 0, "bytes": 0, "paths": []}
    return _cleanup_paths(list(base.rglob("*.jsonl")), days, dry_run)
