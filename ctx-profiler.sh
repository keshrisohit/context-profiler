#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_DIR="${CTX_PROFILER_DIR:-$SCRIPT_DIR}"
PROFILE_DIR="$HOME/.claude/context-profiles"
CONFIG="$PROFILE_DIR/config.json"
ANALYZE="$PLUGIN_DIR/analyze.sh"
TEXTUAL_VENV="${CTX_PROFILER_TEXTUAL_VENV:-$PROFILE_DIR/textual-venv}"
TEXTUAL_PYTHON="$TEXTUAL_VENV/bin/python"

usage() {
  cat <<'EOF'
Context Profiler

Usage:
  ctx-profile setup [--install-textual]
  ctx-profile watch [<source>|--source <source>] [--session <id>]
  ctx-profile status
  ctx-profile enable
  ctx-profile disable
  ctx-profile latest
  ctx-profile latest --session <id>
  ctx-profile summary [--session <id>]
  ctx-profile session <id>
  ctx-profile top [N] [--session <id>]
  ctx-profile files [N] [--session <id>]
  ctx-profile turns [--session <id>]
  ctx-profile explain [--session <id>]
  ctx-profile clean [--days N] [--dry-run] [--include-codex-transcripts]
  ctx-profile codex-import [--limit N]
  ctx-profile doctor

Alias:
  ctx-profiler is kept for backward compatibility.

Notes:
  watch starts the live Textual dashboard. Run it in a split terminal.
  setup is idempotent and installs Claude/Codex slash command shims.
EOF
}

ensure_config() {
  python3 - "$PLUGIN_DIR" <<'PY'
import sys
sys.path.insert(0, sys.argv[1])
from context_profiler_core import ensure_config
ensure_config()
PY
}

ensure_textual() {
  if textual_python >/dev/null 2>&1; then
    return 0
  fi
  if [[ "${1:-}" == "--install-textual" ]]; then
    mkdir -p "$PROFILE_DIR"
    if [[ ! -x "$TEXTUAL_PYTHON" ]]; then
      python3 -m venv "$TEXTUAL_VENV"
    fi
    "$TEXTUAL_PYTHON" -m pip install --upgrade pip textual
    "$TEXTUAL_PYTHON" - <<'PY' >/dev/null
import textual
PY
    return 0
  fi
  echo "textual is not installed. Run:"
  echo "  $0 setup --install-textual"
  return 1
}

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

install_claude_hooks() {
  python3 - "$PLUGIN_DIR" <<'PY'
import json
import sys
from pathlib import Path

plugin = Path(sys.argv[1])
settings = Path.home() / ".claude" / "settings.json"
settings.parent.mkdir(parents=True, exist_ok=True)
try:
    data = json.loads(settings.read_text()) if settings.exists() else {}
except Exception:
    data = {}

hooks = data.setdefault("hooks", {})
entries = {
    "SessionStart": "session-start.py",
    "PreToolUse": "pre-tool-use.py",
    "PostToolUse": "post-tool-use.py",
    "PreCompact": "pre-compact.py",
    "Stop": "session-end.py",
}

for event, script in entries.items():
    command = f'python3 "{plugin / "hooks" / script}"'
    bucket = hooks.setdefault(event, [])
    filtered = []
    exists = False
    for group in bucket:
        group_hooks = []
        for hook in group.get("hooks", []):
            hook_command = hook.get("command", "")
            if "context-profiler/hooks/" in hook_command and hook_command != command:
                continue
            if hook_command == command:
                exists = True
            group_hooks.append(hook)
        if group_hooks:
            group["hooks"] = group_hooks
            filtered.append(group)
    hooks[event] = filtered
    if not exists:
        hooks[event].insert(0, {"hooks": [{"type": "command", "command": command, "async": True}]})

settings.write_text(json.dumps(data, indent=2) + "\n")
print(settings)
PY
}

install_commands() {
  local claude_cmd="$HOME/.claude/commands/context-profiler.md"
  local codex_cmd="$HOME/.codex/commands/context-profiler.md"
  mkdir -p "$(dirname "$claude_cmd")" "$(dirname "$codex_cmd")"
  CTX_PROFILER_SOURCE="$PLUGIN_DIR" python3 - <<'PY' "$PLUGIN_DIR/commands/context-profiler.md" "$claude_cmd" "$codex_cmd"
import os
import sys
from pathlib import Path

src = Path(sys.argv[1]).read_text()
source = os.environ["CTX_PROFILER_SOURCE"]
rendered = src.replace("__CTX_PROFILER_SOURCE__", source)
for target in sys.argv[2:]:
    Path(target).write_text(rendered)
PY
  echo "$claude_cmd"
  echo "$codex_cmd"
}

install_codex_plugin_copy() {
  local target="$HOME/.codex/plugins/context-profiler"
  mkdir -p "$target"
  mkdir -p "$target/commands" "$target/.codex-plugin"
  CTX_PROFILER_SOURCE="$PLUGIN_DIR" python3 - <<'PY' "$PLUGIN_DIR/commands/context-profiler.md" "$target/commands/context-profiler.md"
import os
import sys
from pathlib import Path

src = Path(sys.argv[1]).read_text()
Path(sys.argv[2]).write_text(src.replace("__CTX_PROFILER_SOURCE__", os.environ["CTX_PROFILER_SOURCE"]))
PY
  cp "$PLUGIN_DIR/.codex-plugin/plugin.json" "$target/.codex-plugin/plugin.json"
  echo "$target"
}

install_bin_shim() {
  local bindir="$HOME/.local/bin"
  local primary="$bindir/ctx-profile"
  local legacy="$bindir/ctx-profiler"
  mkdir -p "$bindir"
  cat > "$primary" <<EOF
#!/usr/bin/env bash
exec bash "$PLUGIN_DIR/ctx-profiler.sh" "\$@"
EOF
  chmod +x "$primary"
  cp "$primary" "$legacy"
  chmod +x "$legacy"
  echo "$primary"
  echo "$legacy"
  case ":$PATH:" in
    *":$bindir:"*) ;;
    *) echo "note: $bindir is not on PATH" ;;
  esac
}

doctor() {
  local textual_status="missing"
  local textual_runtime=""
  if textual_runtime="$(textual_python 2>/dev/null)"; then
    textual_status="ok ($textual_runtime)"
  fi
  echo "Plugin: $PLUGIN_DIR"
  test -x "$ANALYZE" && echo "analyze.sh: ok" || echo "analyze.sh: missing/not executable"
  test -f "$CONFIG" && echo "config: $CONFIG" || echo "config: missing"
  CTX_PROFILER_TEXTUAL_STATUS="$textual_status" python3 - "$PLUGIN_DIR" <<'PY'
import os
import sys
sys.path.insert(0, sys.argv[1])
from context_profiler_core import latest_codex_transcripts, load_config
print(f"textual: {os.environ['CTX_PROFILER_TEXTUAL_STATUS']}")
print(f"enabled: {load_config().get('enabled', True)}")
print(f"codex transcripts found: {len(latest_codex_transcripts(20))}")
PY
  test -f "$HOME/.claude/commands/context-profiler.md" && echo "claude command: ok" || echo "claude command: missing"
  test -f "$HOME/.codex/commands/context-profiler.md" && echo "codex command: ok" || echo "codex command: missing"
  test -x "$HOME/.local/bin/ctx-profile" && echo "bin shim ctx-profile: ok" || echo "bin shim ctx-profile: missing"
  test -x "$HOME/.local/bin/ctx-profiler" && echo "bin shim ctx-profiler: ok" || echo "bin shim ctx-profiler: missing"
}

cmd="${1:-}"
shift || true

case "$cmd" in
  setup)
    install_textual=""
    if [[ "${1:-}" == "--install-textual" ]]; then
      install_textual="--install-textual"
    fi
    ensure_config
    if [[ -n "$install_textual" ]]; then
      ensure_textual "$install_textual"
    else
      ensure_textual || true
    fi
    echo "Claude settings:"
    install_claude_hooks
    echo "Commands:"
    install_commands
    echo "Codex plugin copy:"
    install_codex_plugin_copy
    echo "Terminal shim:"
    install_bin_shim
    echo "Done. Use: $0 watch"
    ;;
  watch)
    if [[ ! -t 0 || ! -t 1 ]]; then
      echo "ctx-profile watch requires an interactive terminal. Run it yourself in a split terminal:"
      echo "  ctx-profile watch [claude|codex|all]"
      exit 0
    fi
    if [[ -n "${1:-}" && "${1:-}" != --* ]]; then
      source="$1"
      shift
      exec bash "$ANALYZE" --watch --source "$source" "$@"
    fi
    exec bash "$ANALYZE" --watch "$@"
    ;;
  status)
    exec bash "$ANALYZE" --status
    ;;
  enable)
    exec bash "$ANALYZE" --enable
    ;;
  disable)
    exec bash "$ANALYZE" --disable
    ;;
  latest)
    exec bash "$ANALYZE" --latest "$@"
    ;;
  summary)
    exec bash "$ANALYZE" --summary "$@"
    ;;
  session)
    if [[ -z "${1:-}" ]]; then
      echo "Usage: ctx-profile session <id>" >&2
      exit 2
    fi
    exec bash "$ANALYZE" --session "$1"
    ;;
  top)
    exec bash "$ANALYZE" --top "$@"
    ;;
  files)
    exec bash "$ANALYZE" --files "$@"
    ;;
  turns)
    exec bash "$ANALYZE" --turns "$@"
    ;;
  explain)
    exec bash "$ANALYZE" --explain "$@"
    ;;
  clean)
    exec bash "$ANALYZE" --clean "$@"
    ;;
  codex-import)
    exec bash "$ANALYZE" --codex-import "$@"
    ;;
  doctor)
    ensure_config
    doctor
    ;;
  "")
    exec bash "$ANALYZE" --status
    ;;
  help|--help|-h)
    usage
    ;;
  *)
    echo "Unknown command: $cmd" >&2
    usage >&2
    exit 2
    ;;
esac
