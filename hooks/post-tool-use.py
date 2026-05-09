#!/usr/bin/env python3
"""PostToolUse hook — logs each tool call with estimated token impact and debug metadata."""
import json, sys, os, time, glob

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from context_profiler_core import append_event, is_enabled, normalize_claude_tool_event

try:
    if not is_enabled():
        sys.exit(0)

    d = json.load(sys.stdin)
    session_id = d.get("session_id", "unknown")
    tool_name = d.get("tool_name", "")

    # Duration: find most recent pre-tool-use timestamp file for this tool+session
    # pre-tool-use.py writes /tmp/ctx-profiler-start/{session_id}/{safe_tool}-{epoch_ms}
    duration_ms = None
    safe_tool = "".join(c if c.isalnum() or c in "-_" else "_" for c in tool_name)
    tmp_dir = f"/tmp/ctx-profiler-start/{session_id}"
    if os.path.isdir(tmp_dir):
        pattern = os.path.join(tmp_dir, f"{safe_tool}-*")
        candidates = sorted(glob.glob(pattern), key=os.path.getmtime)
        if candidates:
            latest_stamp_file = candidates[-1]
            try:
                start_ms = int(open(latest_stamp_file).read().strip())
                duration_ms = int(time.time() * 1000) - start_ms
                os.remove(latest_stamp_file)  # consume it
            except Exception:
                pass

    event = normalize_claude_tool_event(d, duration_ms)
    append_event(session_id, event, "claude")
except Exception:
    pass
