#!/usr/bin/env python3
"""Stop hook — appends a session_end summary to the profile."""
import json, sys, os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from context_profiler_core import append_event, is_enabled, profile_path, utc_now

try:
    if not is_enabled():
        sys.exit(0)

    d = json.load(sys.stdin)
    session_id = d.get("session_id", "unknown")

    path = profile_path(session_id, "claude")

    total_tool_calls = 0
    compaction_count = 0
    peak_transcript_bytes = 0
    total_est_tokens = 0

    if path.exists():
        with path.open() as f:
            for line in f:
                try:
                    ev = json.loads(line)
                    if ev.get("type") == "tool_call":
                        total_tool_calls += 1
                        total_est_tokens += ev.get("est_tokens", 0)
                        tb = ev.get("cumulative_transcript_bytes", 0)
                        if tb > peak_transcript_bytes:
                            peak_transcript_bytes = tb
                    elif ev.get("type") == "compaction":
                        compaction_count += 1
                        tb = ev.get("transcript_bytes_before", 0)
                        if tb > peak_transcript_bytes:
                            peak_transcript_bytes = tb
                except Exception:
                    pass

    event = {
        "type": "session_end",
        "ts": utc_now(),
        "source": "claude",
        "session_id": session_id,
        "total_tool_calls": total_tool_calls,
        "compaction_count": compaction_count,
        "peak_transcript_bytes": peak_transcript_bytes,
        "peak_est_tokens": peak_transcript_bytes // 4,
        "total_est_tokens_added": total_est_tokens,
    }

    append_event(session_id, event, "claude")
except Exception:
    pass
