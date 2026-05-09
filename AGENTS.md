# AGENTS.md

Guidelines for agents working on this repository.

## Project Intent

Context Profiler is a lightweight observability tool for Claude and Codex sessions. Its job is to help humans and agents understand context growth, expensive turns, repeated file reads, compactions, and parent/child agent activity without adding meaningful load to the session being observed.

The profiler must stay out of the model context window. Treat that as the primary design constraint.

## Core Principles

1. Keep profiling separate from agent context.
   - Do not stream dashboard output, JSONL profiles, or raw Claude/Codex transcripts into assistant responses.
   - The Textual dashboard must run in an interactive TTY. If stdout is not a TTY, fail with a clear message instead of dumping UI output.
   - Agent-consumable commands should return compact summaries only.

2. Keep the code path portable.
   - Do not hard-code user-specific paths such as `/Users/<name>` in source code.
   - Resolve defaults through `Path.home()`, environment variables, CLI flags, or config.
   - Keep examples in documentation clearly marked as examples.

3. Preserve source neutrality.
   - Claude and Codex are profile sources, not separate products inside the codebase.
   - Shared storage, analysis, formatting, and visualization logic belongs in reusable modules.
   - Source-specific behavior belongs in importer or hook adapters.
   - Make it straightforward to add another harness later by implementing the same profile/event abstractions.

4. Use the right consumption surface.
   - Humans use `ctx-profile watch`, `ctx-profile watch claude`, and `ctx-profile watch codex`.
   - Agents use compact commands such as `ctx-profile explain`, `ctx-profile files`, `ctx-profile turns`, and `ctx-profile latest`.
   - Future machine access should be JSON or MCP-style output, not scraped terminal UI.

## Session And Filtering Rules

1. Session filters must apply consistently to these tabs:
   - Overview
   - Timeline
   - Tools
   - Spikes
   - Agents
   - Skills
   - Files
   - Turns
   - Forensics
   - Advice

2. The Sessions tab is the picker and should intentionally list available sessions.

3. Source filters must be explicit and visible.
   - `ctx-profile watch claude` should show Claude profiles.
   - `ctx-profile watch codex` should show Codex profiles.
   - `ctx-profile watch --session <id>` should pin that session and make the active session id visible in the header.

4. Navigation must not trap the user.
   - Tab and Shift+Tab should keep moving between tabs.
   - Session search mode must have an obvious exit path.
   - Arrow navigation in the Sessions tab should work immediately after entering the tab.

## Parent/Child Agent Rules

1. Do not label an agent as started from plain text alone.
   - Runtime evidence is required.

2. Codex parent/child evidence comes from real `spawn_agent` lifecycle events:
   - requested
   - running
   - completed or failed
   - parent session id
   - child session id

3. Claude parent/child evidence comes from Agent tool use and sidechain transcript data:
   - parent transcript Agent call
   - child sidechain transcript
   - subagent description/type when available
   - raw tool id or transcript path when useful for debugging

4. The Sessions tab should show a Role/relationship tag such as parent, child, or standalone when the data supports it.

5. If a current session appears to have no subagent call, inspect the raw lifecycle evidence before changing UI logic.

## Context Safety Rules

1. Profiler files must not be counted as normal user workload by default.
   - Hide profiler source files, profiler profile JSONL files, and raw transcript files from high-usage advice unless the user explicitly asks to include them.

2. Reading profile data must happen in the profiler process, not inside the observed agent conversation.

3. Cleanup must be conservative.
   - Default auto-cleanup applies to profiler profile JSONL files only.
   - Raw Codex and Claude transcripts should not be deleted by default.
   - Commands that clean raw transcripts must require an explicit flag.

4. Keep default retention small and configurable.
   - The expected default is 5 days for profiler profiles.
   - Support a user-supplied days value for cleanup.

## Dashboard Product Rules

1. Make debugging causes obvious.
   - Show largest calls, repeated file reads, high-token files, expensive turns, compactions/resets, and advice.
   - Advice should explain the observed evidence and the suggested action.

2. Make state visible.
   - Header should show source, active session id or all-sessions mode, profiling status, and live/idle status.
   - Session selection should show enough metadata to distinguish similar sessions.

3. Sorting and grouping should be user-controllable where it helps:
   - files by tokens, bytes, reads, writes, or path
   - sessions by recency, source, role, or size
   - tools by total tokens, calls, average, or max

4. Optimize for repeated engineering use, not a marketing page.
   - Dense tables are acceptable.
   - Avoid decorative UI that makes scanning harder.
   - Prefer stable keyboard behavior over visual novelty.

## Storage And Import Rules

1. Profile events should be normalized before analysis.

2. Preserve source-specific raw details only when they help debugging and do not bloat normal views.

3. Token accounting is approximate unless sourced from explicit model usage fields.
   - Label estimates clearly.
   - Focus advice on relative contributors and repeated patterns.

4. Importers should be incremental where practical.
   - Avoid rereading massive transcript trees on every refresh.
   - Prefer mtime checks, cached indexes, bounded scans, and source filters.

## Setup Rules

1. Keep setup minimal.
   - `bash ./ctx-profiler.sh setup` should be enough for the common path.
   - Optional dependencies such as Textual should have a clear install path.

2. The command surface should be consistent.
   - Use `ctx-profile` as the shell command.
   - Avoid making users remember separate Claude and Codex command names.

3. After behavior or installed-command changes, refresh the local setup:

```bash
bash ./ctx-profiler.sh setup
```

## Test And Verification Rules

Run the test suite before completing code changes:

```bash
python3 -m unittest discover -s tests -v
```

Compile the main Python entrypoints when touching Python code:

```bash
python3 -m py_compile visualize.py context_profiler_core.py context_profiler/*.py context_profiler/importers/*.py hooks/*.py
```

Remove `__pycache__` directories before committing.

Add or update tests when changing:
   - Claude import behavior
   - Codex import behavior
   - session filtering
   - parent/child relationship detection
   - cleanup behavior
   - dashboard helper logic that can be tested without a TTY

## Code Style

1. Keep modules small and purpose-specific.
   - `context_profiler/config.py`: config and paths
   - `context_profiler/storage.py`: profile persistence and cleanup
   - `context_profiler/analysis.py`: derived summaries and advice
   - `context_profiler/formatting.py`: display formatting helpers
   - `context_profiler/importers/*`: source-specific importers
   - `visualize.py`: TUI composition and interaction

2. Prefer standard library code unless a dependency is already justified.

3. Keep Textual-specific logic in the visualization layer.

4. Use structured parsing over ad hoc string parsing when raw data is JSON or JSONL.

5. Keep changes scoped. Do not mix unrelated refactors into feature or bug-fix commits.

6. Use ASCII unless the file already requires Unicode or the UI spec explicitly calls for a symbol.

## Git Rules

This repository has been maintained as a small, squashed history. If preserving that shape, amend the existing commit and force-push with lease instead of creating noisy incremental commits.

Use clear commit messages when history is not being squashed.
