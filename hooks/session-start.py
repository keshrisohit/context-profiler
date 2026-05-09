#!/usr/bin/env python3
"""SessionStart hook — initializes a JSONL profile file for the new session."""
import json, sys, os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from context_profiler_core import append_event, git_branch_for, is_enabled, utc_now

try:
    if not is_enabled():
        sys.exit(0)

    d = json.load(sys.stdin)
    session_id = d.get("session_id", "unknown")
    cwd = d.get("cwd", "")

    event = {
        "type": "session_start",
        "ts": utc_now(),
        "session_id": session_id,
        "source": "claude",
        "cwd": cwd,
        "git_branch": git_branch_for(cwd),
    }
    append_event(session_id, event, "claude")
except Exception:
    pass
