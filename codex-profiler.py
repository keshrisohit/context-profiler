#!/usr/bin/env python3
"""Import Codex rollout JSONL transcripts into context-profiler JSONL profiles."""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from context_profiler_core import (
    ensure_config,
    import_codex_transcript,
    import_latest_codex_profiles,
    latest_codex_transcripts,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Codex context profiler importer")
    parser.add_argument("--watch", action="store_true", help="Poll Codex transcripts continuously")
    parser.add_argument("--once", action="store_true", help="Import once and exit")
    parser.add_argument("--latest", action="store_true", help="Import latest Codex transcripts")
    parser.add_argument("--session-file", help="Import one Codex rollout JSONL file")
    parser.add_argument("--limit", type=int, default=5, help="Recent transcripts to import")
    parser.add_argument("--interval", type=float, default=None, help="Polling interval in seconds")
    args = parser.parse_args()

    cfg = ensure_config()
    interval = args.interval or float(cfg.get("refresh_interval_seconds", 2))

    def import_once() -> list[Path]:
        if args.session_file:
            out = import_codex_transcript(args.session_file)
            return [out] if out else []
        return import_latest_codex_profiles(args.limit)

    if args.watch:
        seen = ""
        while True:
            imported = import_once()
            marker = "\n".join(str(p) for p in imported)
            if marker != seen:
                for p in imported:
                    print(f"imported {p}", flush=True)
                seen = marker
            time.sleep(interval)

    imported = import_once() if (args.once or args.latest or args.session_file or not args.watch) else []
    if not imported:
        transcripts = latest_codex_transcripts(args.limit)
        if not transcripts:
            print("No Codex transcripts found.", file=sys.stderr)
            return 1
    for p in imported:
        print(p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
