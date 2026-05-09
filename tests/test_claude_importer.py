import json
import tempfile
import unittest
from pathlib import Path

from context_profiler.analysis import compute_stats
from context_profiler.importers.claude import _agent_events_from_transcript
from context_profiler.importers.claude import import_claude_transcript
from context_profiler.storage import load_events


class ClaudeImporterTests(unittest.TestCase):
    def test_agent_event_links_parent_session_to_subagent_transcript(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            transcript = root / "session-123.jsonl"
            subagents = root / "session-123" / "subagents"
            subagents.mkdir(parents=True)
            subagent = subagents / "agent-a1.jsonl"
            subagent.write_text(
                json.dumps(
                    {
                        "timestamp": "2026-05-09T13:00:00.200Z",
                        "sessionId": "session-123",
                        "agentId": "agent-a1",
                        "isSidechain": True,
                        "message": {"role": "user", "content": "start"},
                    }
                )
                + "\n"
            )
            row = {
                "timestamp": "2026-05-09T13:00:00.000Z",
                "sessionId": "session-123",
                "message": {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "tool_use",
                            "name": "Agent",
                            "id": "toolu_1",
                            "input": {
                                "subagent_type": "Explore",
                                "description": "Inspect repo",
                            },
                        }
                    ],
                },
            }
            transcript.write_text(json.dumps(row) + "\n")

            session_id, events = _agent_events_from_transcript(transcript, [row])

        self.assertEqual(session_id, "session-123")
        self.assertEqual(len(events), 1)
        meta = events[0]["meta"]
        self.assertEqual(meta["status"], "running")
        self.assertEqual(meta["parent_session_id"], "session-123")
        self.assertEqual(meta["child_session_id"], "agent-a1")
        self.assertEqual(meta["subagent_agent_id"], "agent-a1")
        self.assertTrue(meta["subagent_transcript_path"].endswith("agent-a1.jsonl"))

        stats = compute_stats(events, advice_ignore_path_patterns=[])
        self.assertEqual(len(stats["agent_runs"]), 1)
        self.assertEqual(stats["agent_runs"][0]["status"], "running")
        self.assertEqual(stats["agent_runs"][0]["child_session_id"], "agent-a1")
        self.assertEqual(stats["agent_runs"][0]["subagent_type"], "Explore")

    def test_import_backfills_existing_hook_agent_by_description(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            transcript = root / "session-123.jsonl"
            subagents = root / "session-123" / "subagents"
            subagents.mkdir(parents=True)
            (subagents / "agent-a1.jsonl").write_text(
                json.dumps(
                    {
                        "timestamp": "2026-05-09T13:00:00.200Z",
                        "sessionId": "session-123",
                        "agentId": "agent-a1",
                        "isSidechain": True,
                        "message": {"role": "user", "content": "start"},
                    }
                )
                + "\n"
            )
            row = {
                "timestamp": "2026-05-09T13:00:00.000Z",
                "sessionId": "session-123",
                "cwd": str(root),
                "message": {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "tool_use",
                            "name": "Agent",
                            "id": "toolu_1",
                            "input": {
                                "subagent_type": "Explore",
                                "description": "Inspect repo",
                            },
                        }
                    ],
                },
            }
            transcript.write_text(json.dumps(row) + "\n")
            profile_dir = root / "profiles"
            profile_dir.mkdir()
            profile = profile_dir / "session-123.jsonl"
            profile.write_text(
                json.dumps({"type": "session_start", "session_id": "session-123"})
                + "\n"
                + json.dumps(
                    {
                        "type": "tool_call",
                        "tool": "Agent",
                        "session_id": "session-123",
                        "meta": {
                            "subagent_type": "",
                            "description_full": "Inspect repo",
                        },
                    }
                )
                + "\n"
            )

            import context_profiler.storage as storage
            import context_profiler.importers.claude as claude_importer

            old_storage_dir = storage.PROFILE_DIR
            old_importer_dir = claude_importer.PROFILE_DIR if hasattr(claude_importer, "PROFILE_DIR") else None
            try:
                storage.PROFILE_DIR = profile_dir
                if old_importer_dir is not None:
                    claude_importer.PROFILE_DIR = profile_dir
                out = import_claude_transcript(transcript)
            finally:
                storage.PROFILE_DIR = old_storage_dir
                if old_importer_dir is not None:
                    claude_importer.PROFILE_DIR = old_importer_dir

            events = load_events(out)
            agents = [event for event in events if event.get("tool") == "Agent"]

        self.assertEqual(len(agents), 1)
        meta = agents[0]["meta"]
        self.assertEqual(meta["subagent_type"], "Explore")
        self.assertEqual(meta["raw_tool_use_id"], "toolu_1")
        self.assertEqual(meta["parent_session_id"], "session-123")
        self.assertEqual(meta["child_session_id"], "agent-a1")


if __name__ == "__main__":
    unittest.main()
