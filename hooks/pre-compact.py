#!/usr/bin/env python3
"""PreCompact hook — records a compaction marker with transcript size."""
import json, sys, os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from context_profiler_core import append_event, is_enabled, profile_path, utc_now

try:
    if not is_enabled():
        sys.exit(0)

    d = json.load(sys.stdin)
    session_id = d.get("session_id", "unknown")
    transcript_path = d.get("transcript_path", "")

    transcript_bytes = 0
    if transcript_path and os.path.exists(transcript_path):
        transcript_bytes = os.path.getsize(transcript_path)

    compaction_index = 0
    path = profile_path(session_id, "claude")
    if path.exists():
        with path.open() as f:
            for line in f:
                try:
                    if json.loads(line).get("type") == "compaction":
                        compaction_index += 1
                except Exception:
                    pass

    event = {
        "type": "compaction",
        "ts": utc_now(),
        "source": "claude",
        "session_id": session_id,
        "compaction_index": compaction_index + 1,
        "transcript_bytes_before": transcript_bytes,
        "est_tokens_before": transcript_bytes // 4,
    }
    append_event(session_id, event, "claude")
except Exception:
    pass
