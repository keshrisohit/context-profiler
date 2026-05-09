"""Configuration and process-wide defaults for Context Profiler."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROFILE_DIR = Path.home() / ".claude" / "context-profiles"
CONFIG_PATH = PROFILE_DIR / "config.json"
CODEX_SESSIONS_DIR = Path.home() / ".codex" / "sessions"
CLAUDE_PROJECTS_DIR = Path.home() / ".claude" / "projects"
DEFAULT_MAX_CONTEXT_TOKENS = 200_000

DEFAULT_CONFIG: dict[str, Any] = {
    "enabled": True,
    "spike_threshold_tokens": 5000,
    "refresh_interval_seconds": 2,
    "follow_latest_session": True,
    "sources": ["claude", "codex"],
    "codex_sessions_dir": str(CODEX_SESSIONS_DIR),
    "codex_import_on_refresh": True,
    "codex_import_limit": 25,
    "claude_projects_dir": str(CLAUDE_PROJECTS_DIR),
    "claude_import_on_refresh": True,
    "claude_import_limit": 25,
    "hide_ignored_paths_by_default": True,
    "profile_rotation_enabled": True,
    "profile_max_part_bytes": 10_000_000,
    "auto_cleanup_enabled": True,
    "auto_cleanup_interval_hours": 24,
    "cleanup_retention_days": 5,
    "advice_ignore_path_patterns": [
        "*/.codex/sessions/*.jsonl",
        "*/.codex/history.jsonl",
        "*/.claude/context-profiles/*.jsonl",
        "*/.local/bin/ctx-profile*",
        "*/context-profiler/*",
    ],
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z"


def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def _merge_config(existing: dict[str, Any]) -> dict[str, Any]:
    cfg = dict(DEFAULT_CONFIG)
    cfg.update(existing)
    default_ignores = DEFAULT_CONFIG["advice_ignore_path_patterns"]
    current_ignores = list(cfg.get("advice_ignore_path_patterns", []))
    for pattern in default_ignores:
        if pattern not in current_ignores:
            current_ignores.append(pattern)
    cfg["advice_ignore_path_patterns"] = current_ignores
    return cfg


def load_config() -> dict[str, Any]:
    existing = read_json(CONFIG_PATH, {})
    return _merge_config(existing if isinstance(existing, dict) else {})


def save_config(cfg: dict[str, Any]) -> None:
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    merged = _merge_config(cfg)
    CONFIG_PATH.write_text(json.dumps(merged, indent=2) + "\n")


def ensure_config() -> dict[str, Any]:
    existing = read_json(CONFIG_PATH, {}) if CONFIG_PATH.exists() else {}
    existing = existing if isinstance(existing, dict) else {}
    cfg = _merge_config(existing)
    if not CONFIG_PATH.exists() or cfg != existing:
        save_config(cfg)
    return cfg


def is_enabled() -> bool:
    return bool(load_config().get("enabled", True))


def configured_sources(include_all: bool = False) -> list[str]:
    sources = [str(s) for s in load_config().get("sources", DEFAULT_CONFIG["sources"]) if str(s)]
    deduped = list(dict.fromkeys(sources))
    return ["all", *deduped] if include_all else deduped
