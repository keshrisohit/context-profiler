#!/usr/bin/env python3
"""Live Textual dashboard for Claude Code, Codex, and future profile sources."""
import os
import sys
import time
from pathlib import Path

# Shared implementation used by hooks, Codex transcript imports, and the TUI.
from context_profiler_core import (
    CONFIG_PATH,
    PROFILE_DIR,
    compute_stats,
    configured_sources,
    ensure_config,
    event_detail,
    fmt_bytes,
    fmt_tokens,
    get_all_profiles,
    get_latest_session,
    import_latest_claude_profiles,
    import_latest_codex_profiles,
    load_config,
    load_events,
    profile_mtime,
    profile_part_paths,
    profile_source,
    refresh_session_index,
    run_auto_cleanup,
    save_config,
    session_id_for_profile,
    session_relationship_label,
    session_relationship_maps,
    sort_session_rows_by_start,
    format_table_timestamp,
    timestamp_epoch,
    token_color,
)


# ── textual app ───────────────────────────────────────────────────────────────

from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, TabbedContent, TabPane, DataTable, Static, RichLog, Input
from textual.binding import Binding
from textual.reactive import reactive


def format_duration(seconds):
    seconds = int(seconds or 0)
    if seconds < 60:
        return f"{seconds}s"
    minutes, seconds = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m{seconds:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h{minutes:02d}m"


def collect_source_agent_rows(records, spike_threshold=5000, limit=100):
    rows = []
    for record in records:
        stats = compute_stats(record.get("events", []), spike_threshold)
        session_id = record.get("session_id", "")
        for run in stats.get("agent_runs", []):
            item = dict(run)
            item["_scope"] = "source"
            item["_profile_session_id"] = session_id
            rows.append(item)
    return sorted(rows, key=lambda row: row.get("last_ts", ""), reverse=True)[:limit]


class ContextProfilerApp(App):
    TITLE = "Context Profiler"
    TAB_IDS = [
        "overview",
        "timeline",
        "tools",
        "spikes",
        "agents",
        "skills",
        "files",
        "turns",
        "forensics",
        "advice",
        "sessions",
    ]

    CSS = """
    Screen { background: #0d1117; color: #c9d1d9; }
    #status-bar { height: 1; background: #161b22; padding: 0 1; }
    DataTable { height: 1fr; }
    #turns-table { height: 2fr; }
    #turn-detail-log { height: 1fr; border: solid #30363d; padding: 0 1; }
    DataTable > .datatable--header { background: #161b22; color: #7ec8e3; }
    DataTable > .datatable--row-highlighted { background: #1f2937; }
    TabPane { padding: 1; }
    #overview-content { padding: 1; }
    """

    BINDINGS = [
        Binding("1", "switch_tab('overview')", "Overview"),
        Binding("2", "switch_tab('timeline')", "Timeline"),
        Binding("3", "switch_tab('tools')",    "Tools"),
        Binding("4", "switch_tab('spikes')",   "Spikes"),
        Binding("5", "switch_tab('agents')",   "Agents"),
        Binding("6", "switch_tab('skills')",   "Skills"),
        Binding("7", "switch_tab('files')",    "Files"),
        Binding("8", "switch_tab('turns')",    "Turns"),
        Binding("9", "switch_tab('forensics')", "Forensics"),
        Binding("0", "switch_tab('advice')",   "Advice"),
        Binding("u", "switch_tab('sessions')", "Sessions"),
        Binding("tab", "next_dashboard_tab", "Next Tab", priority=True),
        Binding("shift+tab", "previous_dashboard_tab", "Previous Tab", priority=True),
        Binding("/", "focus_session_search",   "Search"),
        Binding("e", "toggle_profiling",       "Toggle Profiling"),
        Binding("r", "refresh_now",            "Refresh"),
        Binding("a", "toggle_all_sessions",    "All Sessions"),
        Binding("s", "cycle_source",           "Source"),
        Binding("o", "cycle_sort",             "Sort"),
        Binding("m", "cycle_group",            "Group"),
        Binding("i", "toggle_ignored_paths",   "Ignored Paths"),
        Binding("enter", "select_session",     "Select Session"),
        Binding("f", "follow_tail",            "Follow tail"),
        Binding("g", "jump_top",               "Jump top"),
        Binding("q", "quit",                   "Quit"),
    ]

    session_path:      reactive[str | None] = reactive(None)
    banner:            reactive[str]        = reactive("")
    is_live:           reactive[bool]       = reactive(False)
    profiling_enabled: reactive[bool]       = reactive(True)
    all_sessions_mode: reactive[bool]       = reactive(False)

    def __init__(self, pin_session=None, source_filter="all"):
        super().__init__()
        self.pinned_session = pin_session
        self.source_filter = source_filter
        self._stats  = {}
        self._config = load_config()
        self._events = []
        self.sort_mode = "tokens"
        self.group_mode = "file"
        self.show_ignored_paths = not bool(self._config.get("hide_ignored_paths_by_default", True))
        self.session_query = ""
        self._session_rows = {}
        self._session_paths = []
        self._session_summary_cache = []
        self._session_cache_signature = None
        self._turn_rows = []
        self._selected_turn_key = ""
        self._suppress_session_search_event = False
        self._prefer_session_search_focus = False
        self._events_signature = None
        self._panel_update_generation = 0

    def _sources(self):
        if self.source_filter and self.source_filter != "all":
            return [self.source_filter]
        return None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Static("", id="status-bar")
        with TabbedContent(id="tabs"):
            with TabPane("1 Overview", id="overview"):
                yield Static("", id="overview-content")
            with TabPane("2 Timeline", id="timeline"):
                yield RichLog(id="timeline-log", highlight=True, markup=True)
            with TabPane("3 Tools",    id="tools"):
                yield DataTable(id="tools-table",  cursor_type="row")
            with TabPane("4 Spikes",   id="spikes"):
                yield RichLog(id="spikes-log", highlight=True, markup=True)
            with TabPane("5 Agents",   id="agents"):
                yield DataTable(id="agents-table", cursor_type="row")
            with TabPane("6 Skills",   id="skills"):
                yield DataTable(id="skills-table", cursor_type="row")
            with TabPane("7 Files",    id="files"):
                yield DataTable(id="files-table",  cursor_type="row")
            with TabPane("8 Turns",    id="turns"):
                yield DataTable(id="turns-table",  cursor_type="row")
                yield RichLog(id="turn-detail-log", highlight=True, markup=True)
            with TabPane("9 Forensics", id="forensics"):
                yield RichLog(id="forensics-log", highlight=True, markup=True)
            with TabPane("0 Advice",   id="advice"):
                yield RichLog(id="advice-log", highlight=True, markup=True)
            with TabPane("Sessions", id="sessions"):
                yield Static(
                    "Use arrows to pick a session, / to search, Esc to leave search, "
                    "Enter to pin. After pinning, use u to choose another session, "
                    "a for all sessions, or s to switch source.",
                    id="sessions-help",
                )
                yield Input(placeholder="Search sessions...", id="session-search")
                yield DataTable(id="sessions-table", cursor_type="row")
        yield Footer()

    def on_mount(self):
        self._setup_tables()
        interval = self._config.get("refresh_interval_seconds", 2)
        self.set_interval(interval, self._refresh)
        self._refresh()

    def _setup_tables(self):
        self.query_one("#tools-table",  DataTable).add_columns(
            "Tool", "Calls", "Total Tokens", "Avg/Call", "Max Single", "% of calls")
        self.query_one("#agents-table", DataTable).add_columns(
            "Status", "Source", "Scope", "Type", "Agent ID", "Parent", "Start Time", "Last Seen", "Tokens", "Lifecycle", "Detail")
        self.query_one("#skills-table", DataTable).add_columns(
            "Skill", "Invocations", "Total Tokens", "Avg/Call", "Last Used")
        self.query_one("#files-table",  DataTable).add_columns(
            "File", "Reads", "Writes", "Total Tokens", "Max", "Total Bytes", "Flag")
        self.query_one("#turns-table",  DataTable).add_columns(
            "Turn", "Start", "Duration", "Status", "Tools", "Agents", "Files", "Top Contributor", "+Tokens", "Context")
        self.query_one("#sessions-table", DataTable).add_columns(
            "Session", "Source", "Role", "Started", "Calls", "Turns", "Tokens", "CWD")

    # ── data refresh ─────────────────────────────────────────────────────────

    def _refresh(self):
        self._config = load_config()
        sources = self._sources()
        run_auto_cleanup(sources=sources)
        if self._config.get("claude_import_on_refresh", True) and (sources is None or "claude" in sources):
            import_latest_claude_profiles()
        if self._config.get("codex_import_on_refresh", True) and (sources is None or "codex" in sources):
            import_latest_codex_profiles()
        self.profiling_enabled = self._config.get("enabled", True)

        latest = get_latest_session(self.pinned_session, sources=sources)
        if latest and latest != self.session_path:
            sid = Path(latest).stem[:16]
            self.banner = f"↻ NEW SESSION → {sid}"
            self.session_path = latest
            self.set_timer(3, lambda: setattr(self, "banner", ""))

        self._refresh_session_summary_cache(sources)

        if not self.session_path or not os.path.exists(self.session_path):
            self._update_status_bar()
            self._update_sessions()
            return

        mtime = profile_mtime(self.session_path)
        self.is_live = (time.time() - mtime) < 5

        signature_paths = get_all_profiles(sources) if self.all_sessions_mode else [self.session_path]
        events_signature = (
            self._config.get("spike_threshold_tokens", 5000),
            self._profile_data_signature(signature_paths),
        )

        if events_signature != self._events_signature:
            if self.all_sessions_mode:
                events = []
                for fp in get_all_profiles(sources):
                    if sources is not None and profile_source(fp) not in sources:
                        continue
                    events.extend(load_events(fp))
                events.sort(key=lambda e: e.get("ts", ""))
            else:
                events = load_events(self.session_path)

            self._events = events
            self._stats  = compute_stats(events, self._config.get("spike_threshold_tokens", 5000))
            self._events_signature = events_signature

        self._update_status_bar()
        self._schedule_active_panel_update(delay=0)

    def _profile_data_signature(self, paths):
        signature = []
        for path in paths:
            for part in profile_part_paths(path):
                try:
                    stat = Path(part).stat()
                except Exception:
                    continue
                signature.append((str(part), stat.st_size, stat.st_mtime_ns))
        return tuple(signature)

    # ── panel renderers ───────────────────────────────────────────────────────

    def _active_tab_id(self):
        try:
            return self.query_one(TabbedContent).active or "overview"
        except Exception:
            return "overview"

    def _update_active_panel(self):
        updates = {
            "overview": self._update_overview,
            "timeline": self._update_timeline,
            "tools": self._update_tools,
            "spikes": self._update_spikes,
            "agents": self._update_agents,
            "skills": self._update_skills,
            "files": self._update_files,
            "turns": self._update_turns,
            "forensics": self._update_forensics,
            "advice": self._update_advice,
            "sessions": self._update_sessions,
        }
        updates.get(self._active_tab_id(), self._update_overview)()

    def _schedule_active_panel_update(self, delay=0.08):
        self._panel_update_generation += 1
        generation = self._panel_update_generation
        self.set_timer(delay, lambda: self._run_scheduled_panel_update(generation))

    def _run_scheduled_panel_update(self, generation):
        if generation != self._panel_update_generation:
            return
        self._update_active_panel()

    def _update_status_bar(self):
        s      = self._stats
        live   = "[bold green]● LIVE[/]" if self.is_live else "[dim]○ idle[/]"
        en     = "[bold green][PROFILING ON][/]" if self.profiling_enabled else "[bold red][PROFILING OFF][/]"
        sid    = self._session_display_id(short=not bool(self.pinned_session))
        src    = profile_source(self.session_path or "", self._events) if self.session_path else ""
        branch = (s.get("session_start") or {}).get("git_branch", "") or ""
        mode   = "  [dim][all sessions][/]" if self.all_sessions_mode else ""
        source_mode = f"  [dim][source:{self.source_filter}][/]" if self.source_filter != "all" else ""
        pin_mode = "  [bold yellow]PINNED[/]" if self.pinned_session else ""
        ignored_mode = "raw" if self.show_ignored_paths else "filtered"
        sort_group = f"  [dim][sort:{self.sort_mode} group:{self.group_mode} {ignored_mode}][/]"
        bnr    = f"  [bold yellow]{self.banner}[/]" if self.banner else ""
        self.query_one("#status-bar").update(
            f"{live}  {pin_mode} {src} session:{sid}  {branch}{mode}{source_mode}{sort_group}  {en}  "
            f"[dim][tab]next [shift+tab]prev [u]sessions [/]search [esc]table [enter]select "
            f"[o]sort [m]group [i]ignored [s]source [q]quit[/]{bnr}"
        )

    def _update_overview(self):
        s     = self._stats
        pct   = s.get("pct", 0)
        cur   = s.get("current_tokens", 0)
        window = s.get("context_window", 200000)
        vel   = s.get("velocity", 0)
        eta   = s.get("eta_sec")
        large = self._display_largest()
        calls = self._display_tool_calls()
        comps = s.get("compactions", [])
        turns = s.get("turns", [])
        exact = s.get("exactness", "estimated")

        filled = int(pct / 100 * 42)
        color  = "bright_red" if pct > 85 else "yellow" if pct > 65 else "green"
        bar    = f"[{color}]{'█' * filled}[/][dim]{'░' * (42 - filled)}[/]"

        if eta is None:
            eta_str = "[dim]ETA unknown (no velocity)[/]"
        elif eta < 20:
            eta_str = f"[bold bright_red]⚡ compaction in ~{eta}s![/]"
        elif eta < 60:
            eta_str = f"[yellow]⚠ ~{eta}s to compaction[/]"
        else:
            m, sec = divmod(eta, 60)
            eta_str = f"[dim]~{m}m{sec}s to compaction at current rate[/]"

        lm = large.get("meta", {}) if large else {}
        ld = (lm.get("file_path") or lm.get("description", "")[:50]
              or lm.get("command", "")[:50] or lm.get("skill_name", "") or "")
        largest_str = (f"[yellow]{large.get('tool', '')}[/]  "
                       f"{fmt_tokens(large.get('est_tokens', 0))} tok  [dim]{ld}[/]"
                       ) if large else "[dim]none[/]"

        last = calls[-1] if calls else None
        if last:
            lm2 = last.get("meta", {})
            ld2 = (lm2.get("file_path") or lm2.get("description", "")[:50]
                   or lm2.get("command", "")[:50] or lm2.get("skill_name", "") or "")
            last_str = f"[cyan]{last.get('tool', '')}[/]  +{fmt_tokens(last.get('est_tokens', 0))}  [dim]{ld2}[/]"
        else:
            last_str = "[dim]none[/]"
        start = s.get("session_start") or {}
        overview_source = profile_source(self.session_path or "", self._events) if self.session_path else ""
        overview_session = self._session_display_id(short=False)
        overview_cwd = start.get("cwd", "") or ""
        overview_branch = start.get("git_branch", "") or ""

        self.query_one("#overview-content").update(f"""
[bold]Current Session[/]
[dim]Source:[/]        {overview_source or '-'}
[dim]Session ID:[/]    [cyan]{overview_session}[/]
[dim]Branch:[/]        {overview_branch or '-'}
[dim]CWD:[/]           {overview_cwd or '-'}

[bold]Context Window[/]
{bar} [bold]{pct}%[/]  {fmt_tokens(cur)} / {fmt_tokens(window)} tokens
{eta_str}

[bold]Token Velocity[/]
[cyan]+{fmt_tokens(vel)}/min[/]  (rolling 60s window)

[bold]Accounting[/]
[cyan]{exact}[/]

[bold]Display Filters[/]
[dim]Ignored profiler/transcript paths:[/] {'shown raw' if self.show_ignored_paths else 'hidden from high-usage views'}
[dim]Use [/]i[dim] to toggle raw evidence. Advice is computed after ignored-path filtering.[/]

[bold]Largest Single Call This Session[/]
{largest_str}

[bold]Last Event[/]
{last_str}

[bold]Session Stats[/]
[dim]Tool calls:[/]     {len(calls)}
[dim]Turns:[/]          {len(turns)}
[dim]Compactions:[/]    {len(comps)}
[dim]Peak transcript:[/] {fmt_bytes(s.get('peak_transcript', 0))}
""")

    def _update_timeline(self):
        log = self.query_one("#timeline-log", RichLog)
        log.clear()
        for e in self._events:
            t  = e.get("type", "")
            ts = (e.get("ts", "") or "")[-9:-4]
            if t == "session_start":
                log.write(f"[bold cyan][{ts}] SESSION START[/]  "
                          f"cwd={e.get('cwd', '')}  branch={e.get('git_branch', '')}")
            elif t == "tool_call":
                tok    = e.get("est_tokens", 0)
                color  = token_color(tok)
                meta   = e.get("meta", {})
                detail = (meta.get("file_path") or meta.get("description", "")[:60]
                          or meta.get("cmd_full", "")[:60] or meta.get("skill_name", "")
                          or meta.get("url", "")[:60] or "")
                cum    = fmt_bytes(e.get("cumulative_transcript_bytes", 0))
                dur    = f"  {e['duration_ms']}ms" if e.get("duration_ms") else ""
                log.write(f"[dim]{ts}[/] [{color}]{e.get('tool', ''):<16}[/] "
                          f"[bold]+{fmt_tokens(tok):>7}[/] {cum:>8}{dur}  [dim]{detail}[/]")
            elif t == "context_snapshot":
                current = e.get("current_tokens", 0)
                window = e.get("model_context_window", 0)
                log.write(f"[dim]{ts}[/] [cyan]{'Token Count':<16}[/] "
                          f"[bold]{fmt_tokens(current):>7}[/] / {fmt_tokens(window)}")
            elif t == "compaction":
                log.write(f"[bold yellow][{ts}] ⚡ COMPACTION #{e.get('compaction_index', 1)}[/]"
                          f"  was {fmt_bytes(e.get('transcript_bytes_before', 0))} before reset")
            elif t == "session_end":
                log.write(f"[bold cyan][{ts}] SESSION END[/]  "
                          f"calls={e.get('total_tool_calls', 0)}  "
                          f"compactions={e.get('compaction_count', 0)}")

    def _update_tools(self):
        t     = self.query_one("#tools-table", DataTable)
        t.clear()
        agg   = self._stats.get("tool_agg", {})
        total = sum(v["total_tokens"] for v in agg.values()) or 1
        for tool, data in self._sorted_tool_rows(agg):
            calls = data["calls"]
            tot   = data["total_tokens"]
            avg   = tot // calls if calls else 0
            pct   = int(tot / total * 100)
            values = [tool, str(calls), fmt_tokens(tot), fmt_tokens(avg), fmt_tokens(data["max_tokens"]), f"{pct}%"]
            t.add_row(*values)

    def _update_spikes(self):
        log        = self.query_one("#spikes-log", RichLog)
        log.clear()
        spikes     = self._display_spikes()
        tool_calls = self._display_tool_calls()
        all_tool_calls = self._stats.get("tool_calls", [])
        threshold  = self._config.get("spike_threshold_tokens", 5000)

        if not spikes:
            log.write(f"[dim]No spikes above {fmt_tokens(threshold)} tokens yet.[/]")
            return

        total = sum(e.get("est_tokens", 0) for e in tool_calls) or 1
        for rank, (idx, e) in enumerate(self._sorted_spike_rows(spikes), 1):
            tok   = e.get("est_tokens", 0)
            color = token_color(tok)
            pct   = int(tok / total * 100)
            ts    = (e.get("ts", "") or "")[-9:-4]
            meta  = e.get("meta", {})
            cum   = fmt_bytes(e.get("cumulative_transcript_bytes", 0))
            dur   = f"  duration: {e['duration_ms']}ms" if e.get("duration_ms") else ""
            detail = (
                meta.get("file_path") or meta.get("description_full") or meta.get("description")
                or meta.get("cmd_full") or meta.get("command") or meta.get("skill_name") or ""
            )

            log.write(f"\n[bold]#{rank}  [{color}]{e.get('tool', '')}[/]  "
                      f"+{fmt_tokens(tok)} tok  ({pct}% of context)  [{ts}]  "
                      f"cumulative: {cum}{dur}[/bold]")

            if meta.get("file_path"):
                sz = meta.get("file_size_bytes", e.get("output_bytes", 0))
                log.write(f"    file: [cyan]{meta['file_path']}[/]  size: {fmt_bytes(sz)}")
            desc = meta.get("description_full") or meta.get("description", "")
            if desc:
                log.write(f"    description: [dim]{desc[:140]}[/]")
            cmd = meta.get("cmd_full") or meta.get("command", "")
            if cmd:
                log.write(f"    command: [dim]{cmd[:140]}[/]")
            if meta.get("output_preview"):
                log.write(f"    output: [dim]{meta['output_preview'][:120]}[/]")
            log.write(f"    in: {fmt_bytes(e.get('input_bytes', 0))}  "
                      f"out: {fmt_bytes(e.get('output_bytes', 0))}")

            before = all_tool_calls[max(0, idx - 3):idx]
            after  = all_tool_calls[idx + 1:idx + 3]
            if before:
                log.write("    [dim]── 3 before ──[/]")
                for b in before:
                    bm = b.get("meta", {})
                    bd = (bm.get("file_path") or bm.get("description", "")[:40]
                          or bm.get("cmd_full", "")[:40] or "")
                    log.write(f"    [dim]{(b.get('ts', ''))[-9:-4]}  "
                              f"{b.get('tool', ''):<14} +{fmt_tokens(b.get('est_tokens', 0)):>6}  {bd}[/]")
            if after:
                log.write("    [dim]── 2 after ──[/]")
                for a in after:
                    am = a.get("meta", {})
                    ad = (am.get("file_path") or am.get("description", "")[:40]
                          or am.get("cmd_full", "")[:40] or "")
                    log.write(f"    [dim]{(a.get('ts', ''))[-9:-4]}  "
                              f"{a.get('tool', ''):<14} +{fmt_tokens(a.get('est_tokens', 0)):>6}  {ad}[/]")
            log.write("─" * 60)

    def _update_agents(self):
        t = self.query_one("#agents-table", DataTable)
        rows = self._agent_rows_for_display()
        t.clear()
        if not rows:
            t.add_row(
                "No Agent calls",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "Selected session has no Agent tool events. Press 'a' for all sessions or choose another session.",
            )
            return
        for run in rows:
            agent_id = run.get("child_session_id") or run.get("agent_id") or ""
            parent = run.get("parent_session_id", "")
            detail = run.get("description", "") or run.get("nickname", "")
            lifecycle = " -> ".join(run.get("lifecycle", []))
            values = [
                self._format_agent_status(run.get("status", "")),
                run.get("source", ""),
                run.get("_scope", ""),
                run.get("subagent_type", ""),
                self._short_id(agent_id, 18),
                self._short_id(parent, 14),
                format_table_timestamp(run.get("start_ts", "")),
                format_table_timestamp(run.get("last_ts", "")),
                fmt_tokens(run.get("total_tokens", 0)),
                lifecycle[:36],
                detail[:80],
            ]
            t.add_row(*values)

    def _agent_rows_for_display(self):
        rows = self._scoped_agent_rows(self._stats.get("agent_runs", []), "all" if self.all_sessions_mode else "session")
        if rows:
            return rows
        rows = self._related_agent_rows()
        if rows:
            return rows
        return self._source_agent_rows()

    def _scoped_agent_rows(self, rows, scope):
        scoped = []
        for run in rows:
            item = dict(run)
            item.setdefault("_scope", scope)
            scoped.append(item)
        return self._sorted_agent_rows(scoped)

    def _related_agent_rows(self):
        if self.all_sessions_mode or not self.session_path:
            return []
        current_id = session_id_for_profile(self.session_path, self._events)
        if not current_id:
            return []
        sources = self._sources()
        records = []
        for path in get_all_profiles(sources):
            events = load_events(path)
            records.append({
                "path": path,
                "events": events,
                "session_id": session_id_for_profile(path, events),
            })
        _, child_to_parent = session_relationship_maps(records)
        parent_id = child_to_parent.get(current_id)
        if not parent_id:
            return []
        parent = next((record for record in records if record["session_id"] == parent_id), None)
        if not parent:
            return []
        parent_stats = compute_stats(parent["events"], self._config.get("spike_threshold_tokens", 5000))
        related = []
        for run in parent_stats.get("agent_runs", []):
            ids = {run.get("child_session_id", ""), run.get("agent_id", "")}
            if current_id in ids:
                copy = dict(run)
                detail = copy.get("description", "")
                copy["description"] = f"parent session agent: {detail}".strip()
                copy["_scope"] = "parent"
                related.append(copy)
        return self._sorted_agent_rows(related)

    def _source_agent_rows(self):
        records = []
        sources = self._sources()
        for path in get_all_profiles(sources):
            events = load_events(path)
            records.append({
                "path": path,
                "events": events,
                "session_id": session_id_for_profile(path, events),
            })
        rows = collect_source_agent_rows(
            records,
            self._config.get("spike_threshold_tokens", 5000),
            limit=100,
        )
        current_id = session_id_for_profile(self.session_path, self._events) if self.session_path else ""
        filtered = [
            row for row in rows
            if row.get("_profile_session_id") != current_id
        ]
        for row in filtered:
            detail = row.get("description", "")
            row["description"] = f"recent source agent: {detail}".strip()
        return self._sorted_agent_rows(filtered)

    def _format_status_counts(self, statuses):
        if not statuses:
            return "completed"
        order = ["requested", "started", "running", "completed"]
        parts = [f"{name}:{statuses[name]}" for name in order if statuses.get(name)]
        parts.extend(f"{name}:{count}" for name, count in sorted(statuses.items()) if name not in order)
        return " ".join(parts)

    def _format_agent_status(self, status):
        status = status or "unknown"
        if status in {"running", "started"}:
            return f"[yellow]{status}[/]"
        if status == "completed":
            return f"[green]{status}[/]"
        if status in {"failed", "closed"}:
            return f"[red]{status}[/]"
        return status

    def _short_id(self, value, limit):
        value = str(value or "")
        if len(value) <= limit:
            return value
        return value[:limit]

    def _update_skills(self):
        t = self.query_one("#skills-table", DataTable)
        rows = self._sorted_skill_rows(self._stats.get("skill_agg", {}))
        t.clear()
        if not rows:
            t.add_row(
                "No Skill calls",
                "0",
                fmt_tokens(0),
                fmt_tokens(0),
                "Codex skills are inferred from SKILL.md reads; select all sessions if this session has none.",
            )
            return
        for skill, data in rows:
            calls = data["calls"]
            tot   = data["total_tokens"]
            avg   = tot // calls if calls else 0
            last  = (data.get("last_used") or "")[-9:-4]
            values = [skill, str(calls), fmt_tokens(tot), fmt_tokens(avg), last]
            t.add_row(*values)

    def _update_files(self):
        t = self.query_one("#files-table", DataTable)
        t.clear()
        for fp, data in self._grouped_file_rows():
            reads  = data["reads"]
            flag   = "[bold red]HOT[/]" if reads > 3 else "[yellow]repeated[/]" if reads > 1 else ""
            short  = ("…" + fp[-48:]) if len(fp) > 50 else fp
            values = [
                short,
                str(reads),
                str(data["writes"]),
                fmt_tokens(data.get("total_tokens", 0)),
                fmt_tokens(data.get("max_tokens", 0)),
                fmt_bytes(data["total_bytes"]),
                flag,
            ]
            t.add_row(*values)

    def _update_turns(self):
        t = self.query_one("#turns-table", DataTable)
        previous_key = self._selected_turn_key
        current_row = t.cursor_row if t.cursor_row is not None else -1
        if not previous_key and 0 <= current_row < len(self._turn_rows):
            previous_key = self._turn_key(self._turn_rows[current_row])
        t.clear()
        self._turn_rows = self._sorted_turn_rows(self._stats.get("turns", []))
        selected_row = 0
        for idx, turn in enumerate(self._turn_rows):
            key = self._turn_key(turn)
            if previous_key and key == previous_key:
                selected_row = idx
            largest = turn.get("largest", {}) or {}
            context = turn.get("end_context_tokens")
            context_str = fmt_tokens(context) if context is not None else ""
            detail = event_detail(largest, 55) if largest else ""
            agents = self._format_turn_agents(turn)
            files = self._format_turn_files(turn)
            top = f"{largest.get('tool', '')} {fmt_tokens(largest.get('est_tokens', 0))} {detail}".strip()
            values = [
                str(turn.get("index", "")),
                (turn.get("start_ts", "") or "")[-9:-4],
                format_duration(turn.get("duration_seconds", 0)),
                self._format_turn_status(turn.get("status", "")),
                str(turn.get("tool_calls", 0)),
                agents,
                files,
                top,
                fmt_tokens(turn.get("tokens", 0)),
                context_str,
            ]
            t.add_row(*values, key=key)
        if self._turn_rows:
            t.move_cursor(row=selected_row, animate=False)
            self._selected_turn_key = self._turn_key(self._turn_rows[min(selected_row, len(self._turn_rows) - 1)])
        else:
            self._selected_turn_key = ""
        self._update_turn_detail(selected_row)

    def _turn_key(self, turn):
        return str(turn.get("turn_id") or turn.get("index") or turn.get("start_ts") or "")

    def _format_turn_status(self, status):
        status = status or "normal"
        if status in {"spike", "compaction"}:
            return f"[red]{status}[/]"
        if status in {"agent-running", "agent-heavy", "file-heavy"}:
            return f"[yellow]{status}[/]"
        if status == "normal":
            return "[green]normal[/]"
        return status

    def _format_turn_agents(self, turn):
        count = turn.get("agents", 0)
        statuses = turn.get("agent_statuses", {})
        if not count:
            return "0"
        running = statuses.get("running", 0) + statuses.get("requested", 0)
        completed = statuses.get("completed", 0)
        parts = [str(count)]
        if running:
            parts.append(f"{running} running")
        if completed:
            parts.append(f"{completed} done")
        return ", ".join(parts)

    def _format_turn_files(self, turn):
        files = turn.get("files", 0)
        top_files = turn.get("top_files", [])
        if not files:
            return "0"
        if not top_files:
            return str(files)
        top = Path(top_files[0].get("path", "")).name or top_files[0].get("path", "")
        return f"{files} ({fmt_tokens(top_files[0].get('tokens', 0))} {top})"

    def _update_turn_detail(self, row=None):
        log = self.query_one("#turn-detail-log", RichLog)
        log.clear()
        if not self._turn_rows:
            log.write("[dim]No turns captured yet.[/]")
            return
        if row is None:
            table = self.query_one("#turns-table", DataTable)
            row = table.cursor_row if table.cursor_row is not None else 0
        if row is None or row < 0 or row >= len(self._turn_rows):
            row = 0
        turn = self._turn_rows[row]
        self._write_turn_detail(log, turn)

    def _write_turn_detail(self, log, turn):
        log.write(
            f"[bold]Turn {turn.get('index', '')}[/]  "
            f"[dim]{format_table_timestamp(turn.get('start_ts', ''))} -> "
            f"{format_table_timestamp(turn.get('end_ts', ''))}[/]  "
            f"{format_duration(turn.get('duration_seconds', 0))}  "
            f"{self._format_turn_status(turn.get('status', ''))}  "
            f"+{fmt_tokens(turn.get('tokens', 0))}"
        )
        log.write(
            f"Tools: {turn.get('tool_calls', 0)}  Files: {turn.get('files', 0)}  "
            f"Agents: {turn.get('agents', 0)}  Boundary: {turn.get('boundary', '')}"
        )

        agent_types = turn.get("agent_types", {})
        agent_statuses = turn.get("agent_statuses", {})
        if agent_types or agent_statuses:
            type_text = ", ".join(f"{name}:{count}" for name, count in sorted(agent_types.items()))
            status_text = ", ".join(f"{name}:{count}" for name, count in sorted(agent_statuses.items()))
            log.write(f"[bold]Agents[/]  types: {type_text or '-'}  statuses: {status_text or '-'}")

        top_events = turn.get("top_events", [])
        if top_events:
            log.write("[bold]Top Contributors[/]")
            for idx, event in enumerate(top_events, 1):
                meta = event.get("meta", {})
                status = f" [{meta.get('status')}]" if event.get("tool") == "Agent" and meta.get("status") else ""
                log.write(
                    f"  {idx}. [cyan]{event.get('tool', '')}[/]{status} "
                    f"{fmt_tokens(event.get('est_tokens', 0))}  [dim]{event_detail(event, 120)}[/]"
                )

        top_files = turn.get("top_files", [])
        if top_files:
            log.write("[bold]Top Files[/]")
            for idx, item in enumerate(top_files, 1):
                log.write(f"  {idx}. {fmt_tokens(item.get('tokens', 0))}  [dim]{item.get('path', '')}[/]")

    def _update_forensics(self):
        log = self.query_one("#forensics-log", RichLog)
        log.clear()
        items = self._stats.get("forensics", [])
        if not items:
            log.write("[dim]No compaction or sharp context reset detected.[/]")
            return
        for item in items:
            ts = (item.get("ts", "") or "")[-9:-4]
            before = item.get("tokens_before", 0)
            after = item.get("tokens_after")
            after_text = f" -> {fmt_tokens(after)}" if after is not None else ""
            log.write(f"\n[bold yellow]{item.get('type', '').replace('_', ' ').title()}[/] "
                      f"[{ts}]  {fmt_tokens(before)}{after_text}  [dim]{item.get('summary', '')}[/]")
            contributors = item.get("contributors", [])
            if not contributors:
                log.write("  [dim]No contributing tool calls found in the captured window.[/]")
                continue
            for rank, event in enumerate(contributors, 1):
                log.write(f"  {rank}. [cyan]{event.get('tool', '')}[/] "
                          f"{fmt_tokens(event.get('est_tokens', 0))}  [dim]{event_detail(event, 100)}[/]")

    def _update_advice(self):
        log = self.query_one("#advice-log", RichLog)
        log.clear()
        recs = self._stats.get("recommendations", [])
        log.write("[bold]How Advice Is Computed[/]")
        log.write("  [dim]1. Aggregate normalized events into tools, files, agents, spikes, turns, and resets.[/]")
        log.write("  [dim]2. Hide configured profiler/transcript noise unless raw mode is enabled with 'i'.[/]")
        log.write("  [dim]3. Emit recommendations for repeated expensive files, large tool output, large agents, spikes, and compaction/reset.[/]\n")
        if not recs:
            log.write("[green]No obvious context hygiene issues detected.[/]")
        ignored = self._stats.get("ignored_advice_files", {})
        if ignored:
            ignored_tokens = sum(v.get("total_tokens", 0) for v in ignored.values())
            log.write(f"[dim]Advice ignored {len(ignored)} known profiler/transcript path(s), "
                      f"{fmt_tokens(ignored_tokens)} tokens. Files/Spikes still show raw evidence.[/]")
        if not recs:
            return
        for idx, rec in enumerate(recs, 1):
            severity = rec.get("severity", "info")
            color = "red" if severity == "high" else "yellow" if severity == "medium" else "cyan"
            log.write(f"\n[bold {color}]#{idx} {severity.upper()} - {rec.get('title', '')}[/]")
            log.write(f"  {rec.get('detail', '')}")
            log.write(f"  [bold]Action:[/] {rec.get('action', '')}")

    def _update_sessions(self):
        try:
            table = self.query_one("#sessions-table", DataTable)
        except Exception:
            return
        previous_path = None
        current_row = table.cursor_row if table.cursor_row is not None else -1
        if 0 <= current_row < len(self._session_paths):
            previous_path = self._session_paths[current_row]
        table.clear()
        self._session_rows = {}
        self._session_paths = []
        rows = self._session_summaries()
        for idx, row in enumerate(rows):
            key = str(idx)
            self._session_rows[key] = row["path"]
            self._session_paths.append(row["path"])
            table.add_row(
                *[
                    row["session"],
                    row["source"],
                    row["relationship"],
                    row["started"],
                    str(row["calls"]),
                    str(row["turns"]),
                    fmt_tokens(row["tokens"]),
                    row["cwd"],
                ],
                key=key,
            )
        if self._session_paths:
            row = self._session_paths.index(previous_path) if previous_path in self._session_paths else 0
            table.move_cursor(row=row, animate=False)
        self._focus_sessions_table_if_active()

    # ── sorting/grouping helpers ─────────────────────────────────────────────

    def _sort_reverse(self):
        return self.sort_mode != "name"

    def _sorted_tool_rows(self, agg):
        key_map = {
            "tokens": lambda item: item[1].get("total_tokens", 0),
            "calls": lambda item: item[1].get("calls", 0),
            "name": lambda item: item[0].lower(),
            "time": lambda item: item[1].get("max_tokens", 0),
        }
        key = key_map.get(self.sort_mode, key_map["tokens"])
        return sorted(agg.items(), key=key, reverse=self._sort_reverse())

    def _sorted_agent_rows(self, rows):
        key_map = {
            "tokens": lambda row: row.get("total_tokens", 0),
            "calls": lambda row: row.get("events", 0),
            "name": lambda row: (row.get("subagent_type", "") + row.get("description", "")).lower(),
            "time": lambda row: row.get("last_ts", ""),
        }
        key = key_map.get(self.sort_mode, key_map["time"])
        return sorted(rows, key=key, reverse=self._sort_reverse())

    def _sorted_skill_rows(self, agg):
        key_map = {
            "tokens": lambda item: item[1].get("total_tokens", 0),
            "calls": lambda item: item[1].get("calls", 0),
            "name": lambda item: item[0].lower(),
            "time": lambda item: item[1].get("last_used", ""),
        }
        key = key_map.get(self.sort_mode, key_map["tokens"])
        return sorted(agg.items(), key=key, reverse=self._sort_reverse())

    def _sorted_spike_rows(self, spikes):
        key_map = {
            "tokens": lambda item: item[1].get("est_tokens", 0),
            "calls": lambda item: item[0],
            "name": lambda item: item[1].get("tool", "").lower(),
            "time": lambda item: item[1].get("ts", ""),
        }
        key = key_map.get(self.sort_mode, key_map["tokens"])
        return sorted(spikes, key=key, reverse=self._sort_reverse())

    def _grouped_file_rows(self):
        source = self._display_file_agg()
        grouped = {}
        for fp, data in source.items():
            key = self._file_group_key(fp)
            bucket = grouped.setdefault(
                key,
                {
                    "reads": 0,
                    "writes": 0,
                    "total_bytes": 0,
                    "total_tokens": 0,
                    "max_tokens": 0,
                },
            )
            bucket["reads"] += data.get("reads", 0)
            bucket["writes"] += data.get("writes", 0)
            bucket["total_bytes"] += data.get("total_bytes", 0)
            bucket["total_tokens"] += data.get("total_tokens", 0)
            bucket["max_tokens"] = max(bucket["max_tokens"], data.get("max_tokens", 0))

        key_map = {
            "tokens": lambda item: item[1].get("total_tokens", 0),
            "calls": lambda item: item[1].get("reads", 0) + item[1].get("writes", 0),
            "name": lambda item: item[0].lower(),
            "time": lambda item: item[1].get("max_tokens", 0),
        }
        key = key_map.get(self.sort_mode, key_map["tokens"])
        return sorted(grouped.items(), key=key, reverse=self._sort_reverse())

    def _file_group_key(self, fp):
        if self.group_mode == "directory":
            return str(Path(fp).parent)
        if self.group_mode == "extension":
            suffix = Path(fp).suffix
            return suffix or "[no extension]"
        return fp

    def _sorted_turn_rows(self, turns):
        key_map = {
            "tokens": lambda row: row.get("tokens", 0),
            "calls": lambda row: row.get("tool_calls", 0),
            "name": lambda row: str(row.get("turn_id", "")),
            "time": lambda row: row.get("start_ts", ""),
        }
        key = key_map.get(self.sort_mode, key_map["tokens"])
        return sorted(turns, key=key, reverse=self._sort_reverse())

    def _display_file_agg(self):
        if self.show_ignored_paths:
            return self._stats.get("file_agg", {})
        return self._stats.get("visible_file_agg", self._stats.get("file_agg", {}))

    def _display_tool_calls(self):
        if self.show_ignored_paths:
            return self._stats.get("tool_calls", [])
        return self._stats.get("visible_tool_calls", self._stats.get("tool_calls", []))

    def _display_spikes(self):
        if self.show_ignored_paths:
            return self._stats.get("spikes", [])
        return self._stats.get("visible_spikes", self._stats.get("spikes", []))

    def _display_largest(self):
        if self.show_ignored_paths:
            return self._stats.get("largest", {})
        return self._stats.get("visible_largest", self._stats.get("largest", {}))

    def _refresh_session_summary_cache(self, sources):
        signature = (
            tuple((path, self._profile_data_signature([path])) for path in get_all_profiles(sources)),
            self._config.get("spike_threshold_tokens", 5000),
        )
        if signature == self._session_cache_signature:
            return
        self._session_cache_signature = signature
        self._session_summary_cache = refresh_session_index(
            sources,
            self._config.get("spike_threshold_tokens", 5000),
        )

    def _session_summaries(self):
        query = self.session_query.lower()
        if not query:
            return list(self._session_summary_cache)
        rows = []
        for row in self._session_summary_cache:
            haystack = " ".join(
                str(row.get(key, ""))
                for key in ("session", "source", "relationship", "started", "cwd")
            ).lower()
            if query in haystack:
                rows.append(row)
        return rows

    # ── actions ───────────────────────────────────────────────────────────────

    def action_switch_tab(self, tab_id: str):
        tabs = self.query_one(TabbedContent)
        if tabs.active == "sessions" and tab_id != "sessions":
            self.set_focus(None)
        tabs.active = tab_id
        if tab_id == "sessions":
            self._focus_sessions_table()

    def action_next_dashboard_tab(self):
        self._cycle_dashboard_tab(1)

    def action_previous_dashboard_tab(self):
        self._cycle_dashboard_tab(-1)

    # Textual maps Tab/Shift+Tab to focus traversal by default. This dashboard
    # treats those keys as pane navigation, so keep the default actions aligned.
    def action_focus_next(self):
        self.action_next_dashboard_tab()

    def action_focus_previous(self):
        self.action_previous_dashboard_tab()

    def _cycle_dashboard_tab(self, step):
        tabs = self.query_one(TabbedContent)
        active = tabs.active or self.TAB_IDS[0]
        try:
            index = self.TAB_IDS.index(active)
        except ValueError:
            index = 0
        self.action_switch_tab(self.TAB_IDS[(index + step) % len(self.TAB_IDS)])

    def action_focus_session_search(self):
        self._prefer_session_search_focus = True
        self.query_one(TabbedContent).active = "sessions"
        self.call_after_refresh(self._focus_session_search)

    def action_focus_session_table(self):
        self.query_one(TabbedContent).active = "sessions"
        self._focus_sessions_table()

    def action_toggle_profiling(self):
        cfg = load_config()
        cfg["enabled"] = not cfg.get("enabled", True)
        save_config(cfg)
        self.profiling_enabled = cfg["enabled"]
        self._update_status_bar()

    def action_refresh_now(self):
        self._refresh()

    def action_toggle_all_sessions(self):
        self.all_sessions_mode = not self.all_sessions_mode
        if self.all_sessions_mode:
            self.pinned_session = None
            self._clear_session_search()
            self.banner = "showing all sessions"
        self._refresh()

    def action_cycle_source(self):
        order = configured_sources(include_all=True)
        if self.source_filter not in order:
            order.append(self.source_filter)
        self.source_filter = order[(order.index(self.source_filter) + 1) % len(order)]
        self.session_path = None
        self.pinned_session = None
        self._clear_session_search()
        self.banner = f"source: {self.source_filter}"
        self._refresh()

    def action_cycle_sort(self):
        order = ["tokens", "calls", "time", "name"]
        self.sort_mode = order[(order.index(self.sort_mode) + 1) % len(order)]
        self._refresh()

    def action_cycle_group(self):
        order = ["file", "directory", "extension"]
        self.group_mode = order[(order.index(self.group_mode) + 1) % len(order)]
        self._refresh()

    def action_toggle_ignored_paths(self):
        self.show_ignored_paths = not self.show_ignored_paths
        self._refresh()

    def action_follow_tail(self):
        self.query_one("#timeline-log", RichLog).scroll_end()

    def action_jump_top(self):
        self.query_one("#timeline-log", RichLog).scroll_home()

    def action_select_session(self):
        active = self.query_one(TabbedContent).active
        if active == "turns":
            table = self.query_one("#turns-table", DataTable)
            row = table.cursor_row
            if row is not None and 0 <= row < len(self._turn_rows):
                self._selected_turn_key = self._turn_key(self._turn_rows[row])
            self._update_turn_detail(row)
            return
        if active != "sessions":
            return
        table = self.query_one("#sessions-table", DataTable)
        row = table.cursor_row
        if row is None or row < 0 or row >= len(self._session_paths):
            return
        self._pin_session_path(self._session_paths[row])

    def on_data_table_row_selected(self, event):
        if event.data_table.id == "turns-table":
            row = event.data_table.cursor_row
            if row is not None and 0 <= row < len(self._turn_rows):
                self._selected_turn_key = self._turn_key(self._turn_rows[row])
            self._update_turn_detail(row)
            return
        if event.data_table.id != "sessions-table":
            return
        key = getattr(event.row_key, "value", str(event.row_key))
        path = self._session_rows.get(key)
        if not path:
            return
        self._pin_session_path(path)

    def on_input_changed(self, event: Input.Changed):
        if event.input.id != "session-search":
            return
        if self._suppress_session_search_event:
            return
        self.session_query = event.value.strip()
        self._update_sessions()

    def on_input_submitted(self, event: Input.Submitted):
        if event.input.id != "session-search":
            return
        if self._session_paths:
            self._pin_session_path(self._session_paths[0])

    def on_key(self, event):
        focused = self.focused
        if event.key == "escape" and getattr(focused, "id", "") == "session-search":
            self.action_focus_session_table()
            event.prevent_default()
            event.stop()

    def on_tabbed_content_tab_activated(self, event: TabbedContent.TabActivated):
        if getattr(event.pane, "id", "") == "sessions":
            if self._prefer_session_search_focus:
                self.call_after_refresh(self._focus_session_search)
            else:
                self.call_after_refresh(self._focus_sessions_table)
        self._schedule_active_panel_update()
        self._update_status_bar()

    def _focus_sessions_table_if_active(self):
        try:
            if self.query_one(TabbedContent).active != "sessions":
                return
            focused_id = getattr(self.focused, "id", "")
            if focused_id != "session-search":
                self._focus_sessions_table()
        except Exception:
            pass

    def _focus_sessions_table(self):
        try:
            table = self.query_one("#sessions-table", DataTable)
            cursor_row = table.cursor_row if table.cursor_row is not None else -1
            if self._session_paths and cursor_row < 0:
                table.move_cursor(row=0, animate=False)
            table.focus()
        except Exception:
            pass

    def _focus_session_search(self):
        try:
            self.query_one("#session-search", Input).focus()
        except Exception:
            pass
        finally:
            self._prefer_session_search_focus = False

    def _clear_session_search(self):
        self.session_query = ""
        self._suppress_session_search_event = True
        try:
            self.query_one("#session-search", Input).value = ""
        except Exception:
            pass
        finally:
            self._suppress_session_search_event = False

    def _session_display_id(self, short=True):
        if not self.session_path:
            return "no session"
        stem = Path(self.session_path).stem
        if stem.startswith("codex-"):
            stem = stem.removeprefix("codex-")
        if short and len(stem) > 14:
            return stem[:14]
        return stem

    def _pin_session_path(self, path):
        self.session_path = path
        stem = Path(path).stem
        self.pinned_session = stem.removeprefix("codex-")
        self.all_sessions_mode = False
        self._clear_session_search()
        self.banner = f"pinned session {self._session_display_id(short=False)}"
        self.query_one(TabbedContent).active = "overview"
        self.set_focus(None)
        self._refresh()


# ── entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    try:
        import textual  # noqa
    except ImportError:
        print("ERROR: textual not installed.\nRun: pip install textual")
        sys.exit(1)

    import argparse
    parser = argparse.ArgumentParser(description="Context Profiler dashboard")
    parser.add_argument("--session", help="Pin to a specific session ID (disables auto-follow)")
    parser.add_argument("--source", default="all",
                        help="Profile source to follow, for example all, claude, codex, or a custom source")
    args = parser.parse_args()

    ensure_config()
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    ContextProfilerApp(pin_session=args.session, source_filter=args.source).run()
