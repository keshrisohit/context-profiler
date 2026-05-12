#!/usr/bin/env bash
# Context Profiler CLI
# Usage:
#   analyze.sh --watch [<source>|--source <source>] [--session <id>]  live dashboard
#   analyze.sh --codex-import            import recent Codex sessions once
#   analyze.sh --latest [--source <source>|--all] [--session <id>] top consumers
#   analyze.sh --summary [--source <source>|--all] [--session <id>] sessions overview
#   analyze.sh --session <id>            full event log for a session
#   analyze.sh --top [N] [--source <source>|--all] [--session <id>] top N tools across sessions/profile filter
#   analyze.sh --files [N] [--source <source>|--all] [--session <id>] [--include-ignored] top N file token consumers
#   analyze.sh --turns [--source <source>|--all] [--session <id>] turn-level context growth
#   analyze.sh --explain [--source <source>|--all] [--session <id>] [--include-ignored] concise context postmortem
#   analyze.sh --clean [--days N] [--dry-run] [--include-codex-transcripts] clean old profile files
#   analyze.sh --enable                  enable profiling
#   analyze.sh --disable                 disable profiling
#   analyze.sh --status                  show current profiling status

PLUGIN_DIR="${CTX_PROFILER_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
PROFILE_DIR="$HOME/.claude/context-profiles"
CONFIG="$PROFILE_DIR/config.json"
TEXTUAL_VENV="${CTX_PROFILER_TEXTUAL_VENV:-$PROFILE_DIR/textual-venv}"
TEXTUAL_PYTHON="$TEXTUAL_VENV/bin/python"

textual_python() {
  if python3 - <<'PY' >/dev/null 2>&1
import textual
PY
  then
    echo "python3"
    return 0
  fi
  if [[ -x "$TEXTUAL_PYTHON" ]] && "$TEXTUAL_PYTHON" - <<'PY' >/dev/null 2>&1
import textual
PY
  then
    echo "$TEXTUAL_PYTHON"
    return 0
  fi
  return 1
}

# Handle enable/disable/status before delegating to Python
if [[ "$1" == "--enable" ]]; then
  python3 -c "
import sys
sys.path.insert(0, '$PLUGIN_DIR')
from context_profiler_core import ensure_config, save_config
cfg = ensure_config()
cfg['enabled'] = True
save_config(cfg)
print('Profiling ENABLED')
"
  exit 0
fi

if [[ "$1" == "--disable" ]]; then
  python3 -c "
import sys
sys.path.insert(0, '$PLUGIN_DIR')
from context_profiler_core import ensure_config, save_config
cfg = ensure_config()
cfg['enabled'] = False
save_config(cfg)
print('Profiling DISABLED')
"
  exit 0
fi

if [[ "$1" == "--status" ]]; then
  python3 -c "
import json, sys
sys.path.insert(0, '$PLUGIN_DIR')
from context_profiler_core import CONFIG_PATH, ensure_config
cfg = ensure_config()
status = 'ENABLED' if cfg.get('enabled', True) else 'DISABLED'
print(f'Profiling: {status}')
print(f'Config: {CONFIG_PATH}')
print(json.dumps(cfg, indent=2))
"
  exit 0
fi

if [[ "$1" == "--codex-import" ]]; then
  shift
  exec python3 "$PLUGIN_DIR/codex-profiler.py" --latest "$@"
fi

if [[ "$1" == "--watch" ]]; then
  shift
  if [[ ! -t 0 || ! -t 1 ]]; then
    echo "ctx-profile watch requires an interactive terminal. Run it yourself in a split terminal:"
    echo "  ctx-profile watch [claude|codex|all]"
    exit 0
  fi
  if ! WATCH_PYTHON="$(textual_python)"; then
    echo "ERROR: textual is not installed. Run:"
    echo "  ctx-profile setup --install-textual"
    exit 1
  fi
  SESSION_ARG=""
  SOURCE_ARG=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --session)
        if [[ -n "${2:-}" ]]; then
          SESSION_ARG="--session $2"
          shift 2
        else
          echo "Usage: analyze.sh --watch [<source>|--source <source>] [--session <id>]" >&2
          exit 2
        fi
        ;;
      --source)
        if [[ -n "${2:-}" ]]; then
          SOURCE_ARG="--source $2"
          shift 2
        else
          echo "Usage: analyze.sh --watch [<source>|--source <source>] [--session <id>]" >&2
          exit 2
        fi
        ;;
      --claude)
        SOURCE_ARG="--source claude"
        shift
        ;;
      --codex)
        SOURCE_ARG="--source codex"
        shift
        ;;
      --all)
        SOURCE_ARG="--source all"
        shift
        ;;
      --*)
        echo "Unknown watch argument: $1" >&2
        exit 2
        ;;
      *)
        SOURCE_ARG="--source $1"
        shift
        ;;
    esac
  done
  exec "$WATCH_PYTHON" "$PLUGIN_DIR/visualize.py" $SOURCE_ARG $SESSION_ARG
fi

# Everything else: delegate to inline Python (existing analyze logic)
CTX_PROFILER_DIR="$PLUGIN_DIR" python3 - "$@" <<'PYEOF'
import sys, os, json, glob, argparse
from collections import defaultdict

PLUGIN_DIR = os.environ["CTX_PROFILER_DIR"]
sys.path.insert(0, PLUGIN_DIR)
from context_profiler_core import (
    PROFILE_DIR,
    cleanup_old_codex_transcripts,
    cleanup_old_profiles,
    compute_stats,
    event_detail,
    filter_profiles_by_session,
    get_all_profiles as core_get_all_profiles,
    get_latest_session,
    import_latest_claude_profiles,
    import_latest_codex_profiles,
    load_config,
    load_events,
    profile_mtime,
    run_auto_cleanup,
)

def source_filter_from(args):
    if "--source" in args:
        idx = args.index("--source")
        if idx + 1 < len(args):
            return args[idx + 1]
    if "--claude" in args:
        return "claude"
    if "--codex" in args:
        return "codex"
    return "all"

source_filter = source_filter_from(sys.argv[1:])
source_list = None if source_filter == "all" else [source_filter]
run_auto_cleanup(sources=source_list)

if "--no-claude-import" not in sys.argv and source_filter in {"all", "claude"}:
    import_latest_claude_profiles()

if "--no-codex-import" not in sys.argv and source_filter in {"all", "codex"}:
    import_latest_codex_profiles()

def load_jsonl(path):
    return load_events(path)

def fmt_bytes(n):
    if n >= 1_000_000: return f"{n/1_000_000:.1f}MB"
    if n >= 1_000:     return f"{n/1_000:.1f}KB"
    return f"{n}B"

def fmt_tokens(n):
    return f"~{n//1000}k" if n >= 1000 else f"~{n}"

def session_filter_from(args):
    if "--session" in args:
        idx = args.index("--session")
        if idx + 1 < len(args):
            return args[idx + 1]
    return None

def include_ignored_from(args):
    return "--include-ignored" in args or "--raw" in args

def int_arg(args, flag, default):
    if flag not in args:
        return default
    idx = args.index(flag)
    if idx + 1 >= len(args):
        return default
    try:
        return int(args[idx + 1])
    except ValueError:
        return default

def get_all_profiles(session_filter=None):
    profiles = sorted(core_get_all_profiles(source_list), key=profile_mtime)
    return filter_profiles_by_session(profiles, session_filter)

def selected_profile(session_filter=None):
    if session_filter:
        return get_latest_session(session_filter, sources=source_list)
    profiles = get_all_profiles()
    return profiles[-1] if profiles else None

def session_summary(events):
    tool_calls  = [e for e in events if e.get("type") == "tool_call"]
    compactions = [e for e in events if e.get("type") == "compaction"]
    start = next((e for e in events if e.get("type") == "session_start"), {})
    stats = compute_stats(events)
    return {
        "cwd": start.get("cwd", ""), "git_branch": start.get("git_branch", ""),
        "tool_calls": len(tool_calls), "compactions": len(compactions),
        "peak_transcript_bytes": stats.get("peak_transcript", 0),
        "peak_est_tokens":       stats.get("peak_tokens", stats.get("current_tokens", 0)),
    }

def cmd_latest(session_filter=None):
    if session_filter:
        path = get_latest_session(session_filter, sources=source_list)
        profiles = [path] if path else []
    else:
        profiles = get_all_profiles()
    if not profiles or not profiles[-1]:
        suffix = f" for session filter: {session_filter}" if session_filter else ""
        print(f"No context profiles found{suffix}.")
        return
    path = profiles[-1]
    session_id = os.path.basename(path).replace(".jsonl", "")
    events     = load_jsonl(path)
    tool_calls = [e for e in events if e.get("type") == "tool_call"]
    compactions= [e for e in events if e.get("type") == "compaction"]
    start      = next((e for e in events if e.get("type") == "session_start"), {})

    print(f"\n{'='*60}")
    print(f"  Session: {session_id[:20]}...")
    print(f"  CWD:    {start.get('cwd','')}")
    print(f"  Branch: {start.get('git_branch','') or 'n/a'}")
    print(f"  Calls:  {len(tool_calls)}  Compactions: {len(compactions)}")
    print(f"{'='*60}\n")

    for c in compactions:
        print(f"  ⚡ COMPACTION #{c.get('compaction_index',1)}: "
              f"{fmt_bytes(c.get('transcript_bytes_before',0))} before reset")

    if not tool_calls:
        print("  No tool calls recorded yet.")
        return

    top = sorted(tool_calls, key=lambda e: e.get("est_tokens",0), reverse=True)[:10]
    print(f"\n  Top {len(top)} context consumers:\n")
    print(f"  {'#':<3} {'Tool':<18} {'Est Tokens':>11} {'Output':>10} {'Detail'}")
    print(f"  {'-'*3} {'-'*18} {'-'*11} {'-'*10} {'-'*30}")
    for i, e in enumerate(top, 1):
        meta   = e.get("meta", {})
        detail = (meta.get("file_path") or meta.get("description","")[:40]
                  or meta.get("cmd_full","")[:40] or meta.get("skill_name","") or "")
        print(f"  {i:<3} {e.get('tool',''):<18} {fmt_tokens(e.get('est_tokens',0)):>11} "
              f"{fmt_bytes(e.get('output_bytes',0)):>10}  {detail}")
    print()

def cmd_summary(session_filter=None):
    profiles = get_all_profiles(session_filter)
    if not profiles:
        suffix = f" for session filter: {session_filter}" if session_filter else ""
        print(f"No context profiles found{suffix}.")
        return
    print(f"\n  {'Session ID':<22} {'Branch':<14} {'Tools':>6} {'Compact':>7} {'Peak':>10}")
    print(f"  {'-'*22} {'-'*14} {'-'*6} {'-'*7} {'-'*10}")
    for path in profiles[-20:]:
        sid = os.path.basename(path).replace(".jsonl","")
        try:
            s = session_summary(load_jsonl(path))
            print(f"  {sid[:20]:<22} {(s['git_branch'] or '')[:12]:<14} "
                  f"{s['tool_calls']:>6} {s['compactions']:>7} "
                  f"{fmt_tokens(s['peak_est_tokens']):>10}")
        except Exception as ex:
            print(f"  {sid[:20]:<22} [error: {ex}]")
    print()

def cmd_session(session_id):
    path = get_latest_session(session_id)
    if not path:
        print(f"No profile for: {session_id}")
        return
    events = load_jsonl(path)
    print(f"\n  Full event log ({len(events)} events):\n")
    for e in events:
        t  = e.get("type","")
        ts = (e.get("ts","") or "")[-8:-1]
        if t == "session_start":
            print(f"  [{ts}] SESSION START  cwd={e.get('cwd','')}  branch={e.get('git_branch','')}")
        elif t == "tool_call":
            meta   = e.get("meta",{})
            detail = next((v for v in meta.values() if isinstance(v,str) and v),"")
            dur    = f"  {e['duration_ms']}ms" if e.get("duration_ms") else ""
            print(f"  [{ts}] {e.get('tool',''):<18} +{fmt_tokens(e.get('est_tokens',0)):>6}  "
                  f"{fmt_bytes(e.get('cumulative_transcript_bytes',0)):>8}{dur}  {str(detail)[:50]}")
        elif t == "compaction":
            print(f"  [{ts}] ⚡ COMPACTION #{e.get('compaction_index',1)}  "
                  f"before={fmt_bytes(e.get('transcript_bytes_before',0))}")
        elif t == "session_end":
            print(f"  [{ts}] SESSION END  tools={e.get('total_tool_calls',0)}  "
                  f"compactions={e.get('compaction_count',0)}  "
                  f"peak={fmt_bytes(e.get('peak_transcript_bytes',0))}")
    print()

def cmd_top(n, session_filter=None):
    profiles = get_all_profiles(session_filter)
    if not profiles:
        suffix = f" for session filter: {session_filter}" if session_filter else ""
        print(f"No context profiles found{suffix}.")
        return
    tool_totals = defaultdict(lambda: {"calls":0,"est_tokens":0,"output_bytes":0})
    for path in profiles:
        try:
            for e in load_jsonl(path):
                if e.get("type") == "tool_call":
                    tool = e.get("tool","unknown")
                    tool_totals[tool]["calls"]        += 1
                    tool_totals[tool]["est_tokens"]   += e.get("est_tokens",0)
                    tool_totals[tool]["output_bytes"] += e.get("output_bytes",0)
        except Exception:
            pass
    sorted_tools = sorted(tool_totals.items(), key=lambda x: x[1]["est_tokens"], reverse=True)[:n]
    label = f"{len(profiles)} sessions" if not session_filter else f"filter {session_filter}"
    print(f"\n  Top {n} tools ({label}):\n")
    print(f"  {'Tool':<20} {'Calls':>7} {'Total Tokens':>14} {'Total Output':>13}")
    print(f"  {'-'*20} {'-'*7} {'-'*14} {'-'*13}")
    for tool, stats in sorted_tools:
        print(f"  {tool:<20} {stats['calls']:>7} {fmt_tokens(stats['est_tokens']):>14} "
              f"{fmt_bytes(stats['output_bytes']):>13}")
    print()

def cmd_files(n, session_filter=None, include_ignored=False):
    profiles = get_all_profiles(session_filter)
    if not profiles:
        suffix = f" for session filter: {session_filter}" if session_filter else ""
        print(f"No context profiles found{suffix}.")
        return
    file_totals = defaultdict(lambda: {
        "reads": 0,
        "writes": 0,
        "total_tokens": 0,
        "max_tokens": 0,
        "total_bytes": 0,
    })
    for path in profiles:
        try:
            stats = compute_stats(load_jsonl(path))
            files_key = "file_agg" if include_ignored else "visible_file_agg"
            for fp, data in stats.get(files_key, stats.get("file_agg", {})).items():
                file_totals[fp]["reads"] += data.get("reads", 0)
                file_totals[fp]["writes"] += data.get("writes", 0)
                file_totals[fp]["total_tokens"] += data.get("total_tokens", 0)
                file_totals[fp]["total_bytes"] += data.get("total_bytes", 0)
                file_totals[fp]["max_tokens"] = max(file_totals[fp]["max_tokens"], data.get("max_tokens", 0))
        except Exception:
            pass
    rows = sorted(file_totals.items(), key=lambda x: x[1]["total_tokens"], reverse=True)[:n]
    label = f"{len(profiles)} sessions" if not session_filter else f"filter {session_filter}"
    if not include_ignored:
        label += ", ignored paths hidden"
    print(f"\n  Top {n} files by token impact ({label}):\n")
    print(f"  {'#':<3} {'Tokens':>10} {'Max':>8} {'Reads':>6} {'Writes':>6} {'Bytes':>10}  File")
    print(f"  {'-'*3} {'-'*10} {'-'*8} {'-'*6} {'-'*6} {'-'*10}  {'-'*40}")
    for i, (fp, data) in enumerate(rows, 1):
        print(f"  {i:<3} {fmt_tokens(data['total_tokens']):>10} {fmt_tokens(data['max_tokens']):>8} "
              f"{data['reads']:>6} {data['writes']:>6} {fmt_bytes(data['total_bytes']):>10}  {fp}")
    print()

def cmd_turns(session_filter=None):
    path = selected_profile(session_filter)
    if not path:
        suffix = f" for session filter: {session_filter}" if session_filter else ""
        print(f"No context profiles found{suffix}.")
        return
    stats = compute_stats(load_jsonl(path))
    print(f"\n  Turns for {os.path.basename(path).replace('.jsonl', '')} ({stats.get('exactness', 'estimated')}):\n")
    print(f"  {'Turn':>4} {'Time':>6} {'Boundary':<13} {'Tools':>5} {'Files':>5} {'Agents':>6} {'Tokens':>10} {'Context':>10}  Largest")
    print(f"  {'-'*4} {'-'*6} {'-'*13} {'-'*5} {'-'*5} {'-'*6} {'-'*10} {'-'*10}  {'-'*40}")
    for turn in stats.get("turns", []):
        largest = turn.get("largest", {}) or {}
        context = turn.get("end_context_tokens")
        context_str = fmt_tokens(context) if context is not None else ""
        largest_str = ""
        if largest:
            largest_str = f"{largest.get('tool', '')} {fmt_tokens(largest.get('est_tokens', 0))} {event_detail(largest, 55)}"
        print(f"  {turn.get('index', 0):>4} {(turn.get('start_ts',''))[-9:-4]:>6} "
              f"{turn.get('boundary',''):<13} {turn.get('tool_calls',0):>5} {turn.get('files',0):>5} "
              f"{turn.get('agents',0):>6} {fmt_tokens(turn.get('tokens',0)):>10} {context_str:>10}  {largest_str}")
    print()

def cmd_explain(session_filter=None, include_ignored=False):
    path = selected_profile(session_filter)
    if not path:
        suffix = f" for session filter: {session_filter}" if session_filter else ""
        print(f"No context profiles found{suffix}.")
        return
    events = load_jsonl(path)
    stats = compute_stats(events)
    session_id = os.path.basename(path).replace(".jsonl", "")
    largest = stats.get("largest", {}) or {}
    print(f"\nContext profile explanation: {session_id}")
    print(f"Accounting: {stats.get('exactness', 'estimated')}")
    print(f"Current context: {fmt_tokens(stats.get('current_tokens', 0))} / {fmt_tokens(stats.get('context_window', 0))} ({stats.get('pct', 0)}%)")
    print(f"Tool calls: {len(stats.get('tool_calls', []))}  Turns: {len(stats.get('turns', []))}  Compactions/resets: {len(stats.get('forensics', []))}")
    if largest:
        print(f"Largest event: {largest.get('tool', '')} {fmt_tokens(largest.get('est_tokens', 0))} - {event_detail(largest, 120)}")

    top_turns = sorted(stats.get("turns", []), key=lambda t: t.get("tokens", 0), reverse=True)[:3]
    if top_turns:
        print("\nTop turns:")
        for turn in top_turns:
            lg = turn.get("largest", {}) or {}
            print(f"- Turn {turn.get('index')} added {fmt_tokens(turn.get('tokens', 0))}; "
                  f"largest: {lg.get('tool', '')} {fmt_tokens(lg.get('est_tokens', 0))} {event_detail(lg, 80)}")

    files_key = "file_agg" if include_ignored else "visible_file_agg"
    top_files = sorted(
        stats.get(files_key, stats.get("file_agg", {})).items(),
        key=lambda x: x[1].get("total_tokens", 0),
        reverse=True,
    )[:5]
    if top_files:
        suffix = "raw" if include_ignored else "ignored paths hidden"
        print(f"\nTop files ({suffix}):")
        for fp, data in top_files:
            print(f"- {fmt_tokens(data.get('total_tokens', 0))} tokens, reads={data.get('reads', 0)}, writes={data.get('writes', 0)}: {fp}")

    ignored = stats.get("ignored_advice_files", {})
    if ignored:
        ignored_tokens = sum(v.get("total_tokens", 0) for v in ignored.values())
        print(f"\nAdvice ignored {len(ignored)} known profiler/transcript path(s), {fmt_tokens(ignored_tokens)} tokens.")
        print("Raw Files/Spikes still include them for debugging.")

    recs = stats.get("recommendations", [])
    if recs:
        print("\nRecommendations:")
        for rec in recs:
            print(f"- [{rec.get('severity', 'info')}] {rec.get('title', '')}: {rec.get('detail', '')}")
            print(f"  Action: {rec.get('action', '')}")
    else:
        print("\nNo obvious context hygiene issues detected.")
    print()

def cmd_clean(args):
    cfg = load_config()
    days = max(1, int_arg(args, "--days", int(cfg.get("cleanup_retention_days", 5))))
    dry_run = "--dry-run" in args
    include_codex_transcripts = "--include-codex-transcripts" in args
    profile_result = cleanup_old_profiles(days=days, dry_run=dry_run, sources=source_list)
    verb = "Would delete" if dry_run else "Deleted"
    print(f"\n{verb} {profile_result['count']} profiler profile(s) older than {days} day(s), "
          f"{fmt_bytes(profile_result['bytes'])}.")
    for item in profile_result["paths"][:20]:
        suffix = f" [error: {item['error']}]" if item.get("error") else ""
        print(f"- {item['path']}{suffix}")
    if len(profile_result["paths"]) > 20:
        print(f"- ... {len(profile_result['paths']) - 20} more")

    if include_codex_transcripts:
        codex_result = cleanup_old_codex_transcripts(
            days=days,
            dry_run=dry_run,
            root=cfg.get("codex_sessions_dir"),
        )
        print(f"\n{verb} {codex_result['count']} raw Codex transcript(s) older than {days} day(s), "
              f"{fmt_bytes(codex_result['bytes'])}.")
        for item in codex_result["paths"][:20]:
            suffix = f" [error: {item['error']}]" if item.get("error") else ""
            print(f"- {item['path']}{suffix}")
        if len(codex_result["paths"]) > 20:
            print(f"- ... {len(codex_result['paths']) - 20} more")
    else:
        print("\nRaw Codex transcripts were not touched. Add --include-codex-transcripts to clean them too.")
    print()

# dispatch
args = sys.argv[1:]
session_filter = session_filter_from(args)
include_ignored = include_ignored_from(args)
if not args or "--latest" in args:
    cmd_latest(session_filter)
elif "--summary" in args:
    cmd_summary(session_filter)
elif "--top" in args:
    idx = args.index("--top")
    n = 10
    if idx + 1 < len(args):
        try: n = int(args[idx+1])
        except ValueError: pass
    cmd_top(n, session_filter)
elif "--files" in args:
    idx = args.index("--files")
    n = 10
    if idx + 1 < len(args):
        try: n = int(args[idx+1])
        except ValueError: pass
    cmd_files(n, session_filter, include_ignored)
elif "--turns" in args:
    cmd_turns(session_filter)
elif "--explain" in args:
    cmd_explain(session_filter, include_ignored)
elif "--clean" in args:
    cmd_clean(args)
elif "--session" in args:
    idx = args.index("--session")
    if idx + 1 < len(args):
        cmd_session(args[idx+1])
    else:
        print("Usage: analyze.sh --session <id>")
else:
    print("Usage: analyze.sh [--watch [<source>|--source <source>] [--session <id>] | --codex-import | --latest [--source <source>|--all] [--session <id>] | --summary [--source <source>|--all] [--session <id>] | --session <id> | --top [N] [--source <source>|--all] [--session <id>] | --files [N] [--source <source>|--all] [--session <id>] | --turns [--source <source>|--all] [--session <id>] | --explain [--source <source>|--all] [--session <id>] | --clean [--days N] [--dry-run] | --enable | --disable | --status]")
PYEOF
