import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from context_profiler.analysis import compute_stats
from context_profiler.importers.codex import import_codex_transcript
from context_profiler.storage import load_events


def _row(ts, typ, payload):
    return {"timestamp": ts, "type": typ, "payload": payload}


class CodexImporterTests(unittest.TestCase):
    def _import_rows(self, rows):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        transcript = root / "rollout-test.jsonl"
        transcript.write_text("\n".join(json.dumps(row) for row in rows) + "\n")
        profile_dir = root / "profiles"
        with patch("context_profiler.storage.PROFILE_DIR", profile_dir):
            out = import_codex_transcript(transcript)
            self.assertIsNotNone(out)
            return load_events(out)

    def test_pending_spawn_agent_is_requested(self):
        events = self._import_rows(
            [
                _row(
                    "2026-05-09T13:00:00Z",
                    "session_meta",
                    {"id": "codex-test", "cwd": "/tmp"},
                ),
                _row(
                    "2026-05-09T13:00:01Z",
                    "response_item",
                    {
                        "type": "function_call",
                        "name": "spawn_agent",
                        "call_id": "call_1",
                        "arguments": json.dumps(
                            {"agent_type": "worker", "message": "Spec subagent"}
                        ),
                    },
                ),
            ]
        )

        agents = [event for event in events if event.get("tool") == "Agent"]
        self.assertEqual(len(agents), 1)
        self.assertEqual(agents[0]["meta"]["status"], "requested")
        self.assertEqual(agents[0]["meta"]["subagent_type"], "worker")

        stats = compute_stats(events, advice_ignore_path_patterns=[])
        self.assertEqual(stats["agent_agg"]["worker"]["calls"], 1)
        self.assertEqual(stats["agent_agg"]["worker"]["statuses"], {"requested": 1})
        self.assertEqual(len(stats["agent_runs"]), 1)
        self.assertEqual(stats["agent_runs"][0]["status"], "requested")
        self.assertEqual(stats["agent_runs"][0]["subagent_type"], "worker")
        self.assertEqual(stats["agent_runs"][0]["start_ts"], "2026-05-09T13:00:01Z")

    def test_spawn_agent_is_completed_when_wait_returns_completion(self):
        events = self._import_rows(
            [
                _row(
                    "2026-05-09T13:00:00Z",
                    "session_meta",
                    {"id": "codex-test", "cwd": "/tmp"},
                ),
                _row(
                    "2026-05-09T13:00:01Z",
                    "response_item",
                    {
                        "type": "function_call",
                        "name": "spawn_agent",
                        "call_id": "call_spawn",
                        "arguments": json.dumps(
                            {"agent_type": "worker", "message": "Implement feature"}
                        ),
                    },
                ),
                _row(
                    "2026-05-09T13:00:02Z",
                    "response_item",
                    {
                        "type": "function_call_output",
                        "call_id": "call_spawn",
                        "output": json.dumps(
                            {"agent_id": "agent-1", "nickname": "Worker 1"}
                        ),
                    },
                ),
                _row(
                    "2026-05-09T13:00:03Z",
                    "response_item",
                    {
                        "type": "function_call",
                        "name": "wait_agent",
                        "call_id": "call_wait",
                        "arguments": json.dumps(
                            {"targets": ["agent-1"], "timeout_ms": 10000}
                        ),
                    },
                ),
                _row(
                    "2026-05-09T13:00:04Z",
                    "response_item",
                    {
                        "type": "function_call_output",
                        "call_id": "call_wait",
                        "output": json.dumps(
                            {
                                "status": {
                                    "agent-1": {"completed": "changed files"}
                                },
                                "timed_out": False,
                            }
                        ),
                    },
                ),
            ]
        )

        agent_events = [event for event in events if event.get("tool") == "Agent"]
        spawn_event = next(
            event for event in agent_events if event["meta"]["codex_tool"] == "spawn_agent"
        )
        wait_event = next(
            event for event in agent_events if event["meta"]["codex_tool"] == "wait_agent"
        )

        self.assertEqual(spawn_event["meta"]["status"], "completed")
        self.assertEqual(spawn_event["meta"]["agent_id"], "agent-1")
        self.assertEqual(spawn_event["meta"]["parent_session_id"], "codex-test")
        self.assertEqual(spawn_event["meta"]["child_session_id"], "agent-1")
        self.assertEqual(wait_event["meta"]["status"], "completed")
        self.assertEqual(wait_event["meta"]["subagent_type"], "worker")
        self.assertEqual(wait_event["meta"]["parent_session_id"], "codex-test")
        self.assertEqual(wait_event["meta"]["child_session_id"], "agent-1")

        stats = compute_stats(events, advice_ignore_path_patterns=[])
        self.assertEqual(stats["agent_agg"]["worker"]["calls"], 1)
        self.assertEqual(stats["agent_agg"]["worker"]["statuses"], {"completed": 1})
        self.assertGreater(stats["agent_agg"]["worker"]["total_tokens"], 0)
        self.assertEqual(len(stats["agent_runs"]), 1)
        run = stats["agent_runs"][0]
        self.assertEqual(run["status"], "completed")
        self.assertEqual(run["child_session_id"], "agent-1")
        self.assertEqual(run["parent_session_id"], "codex-test")
        self.assertEqual(run["subagent_type"], "worker")
        self.assertEqual(run["start_ts"], "2026-05-09T13:00:01Z")
        self.assertEqual(run["lifecycle"], ["spawn_agent", "wait_agent"])
        self.assertEqual(run["events"], 2)

    def test_multi_wait_preserves_per_agent_status(self):
        events = self._import_rows(
            [
                _row(
                    "2026-05-09T13:00:00Z",
                    "session_meta",
                    {"id": "codex-test", "cwd": "/tmp"},
                ),
                _row(
                    "2026-05-09T13:00:01Z",
                    "response_item",
                    {
                        "type": "function_call",
                        "name": "wait_agent",
                        "call_id": "call_wait",
                        "arguments": json.dumps({"targets": ["agent-1", "agent-2"]}),
                    },
                ),
                _row(
                    "2026-05-09T13:00:02Z",
                    "response_item",
                    {
                        "type": "function_call_output",
                        "call_id": "call_wait",
                        "output": json.dumps(
                            {
                                "status": {
                                    "agent-1": {"completed": "done"},
                                    "agent-2": {},
                                },
                                "timed_out": True,
                            }
                        ),
                    },
                ),
            ]
        )

        runs = {
            run["child_session_id"]: run
            for run in compute_stats(events, advice_ignore_path_patterns=[])["agent_runs"]
        }
        self.assertEqual(runs["agent-1"]["status"], "completed")
        self.assertEqual(runs["agent-2"]["status"], "running")


if __name__ == "__main__":
    unittest.main()
