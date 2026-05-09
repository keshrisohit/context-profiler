#!/usr/bin/env python3
"""PreToolUse hook — stamps start timestamp so PostToolUse can compute duration."""
import json, sys, os, time

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from context_profiler_core import is_enabled

try:
    if not is_enabled():
        sys.exit(0)

    d = json.load(sys.stdin)
    session_id = d.get("session_id", "unknown")
    tool_name = d.get("tool_name", "unknown")
    safe_tool = "".join(c if c.isalnum() or c in "-_" else "_" for c in tool_name)

    # Write start timestamp to temp file keyed by session + tool + epoch_ms
    epoch_ms = int(time.time() * 1000)
    tmp_dir = f"/tmp/ctx-profiler-start/{session_id}"
    os.makedirs(tmp_dir, exist_ok=True)

    # Write current epoch_ms so PostToolUse can find the most recent one for this tool
    ts_file = os.path.join(tmp_dir, f"{safe_tool}-{epoch_ms}")
    with open(ts_file, "w") as f:
        f.write(str(epoch_ms))

    # Clean up files older than 60s for this session to prevent accumulation
    now = time.time()
    for fname in os.listdir(tmp_dir):
        fpath = os.path.join(tmp_dir, fname)
        if now - os.path.getmtime(fpath) > 60:
            try:
                os.remove(fpath)
            except Exception:
                pass
except Exception:
    pass
