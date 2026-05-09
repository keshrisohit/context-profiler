---
description: Control the multi-harness context profiler dashboard and setup.
argument-hint: [setup|watch|status|enable|disable|latest|summary|session|top|files|turns|explain|clean|codex-import|doctor] [source|all] [--source <source>] [--session <id>] [--include-ignored] [--days N] [--dry-run]
---

You are controlling the local Context Profiler.

Use this deterministic command surface:

```bash
if command -v ctx-profile >/dev/null 2>&1; then
  ctx-profile ${ARGUMENTS:-status}
elif command -v ctx-profiler >/dev/null 2>&1; then
  ctx-profiler ${ARGUMENTS:-status}
else
  bash "__CTX_PROFILER_SOURCE__/ctx-profiler.sh" ${ARGUMENTS:-status}
fi
```

Default behavior:

- If `$ARGUMENTS` is empty, run `status`.
- For `setup`, run the command directly. It is idempotent and installs Claude hooks plus Claude/Codex slash command shims.
- For `watch`, do not try to stream the TUI through the agent transcript. Tell the operator to run `ctx-profile watch <source>` in a split terminal. The command itself refuses to run without an interactive TTY.
- For `doctor`, run it and report any missing dependency or command shim.

Common examples:

```bash
/context-profiler setup
/context-profiler setup --install-textual
/context-profiler watch
/context-profiler watch claude
/context-profiler watch codex
/context-profiler watch <custom-source>
/context-profiler watch --source claude --session <id>
/context-profiler status
/context-profiler disable
/context-profiler enable
/context-profiler latest
/context-profiler latest --session <id>
/context-profiler summary
/context-profiler summary --session <id>
/context-profiler session <id>
/context-profiler top 10 --session <id>
/context-profiler files 10 --session <id>
/context-profiler files 10 --session <id> --include-ignored
/context-profiler turns --session <id>
/context-profiler explain --session <id>
/context-profiler clean --dry-run
/context-profiler clean
/context-profiler clean --days 5 --dry-run
/context-profiler clean --days 5
/context-profiler codex-import --limit 5
/context-profiler doctor
```
