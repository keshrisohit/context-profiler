import unittest

from context_profiler.analysis import build_turns


class TurnAnalysisTests(unittest.TestCase):
    def test_turns_include_agents_files_status_and_top_contributors(self):
        events = [
            {
                "type": "turn_start",
                "ts": "2026-05-09T13:00:00Z",
                "turn_id": "turn-1",
            },
            {
                "type": "tool_call",
                "ts": "2026-05-09T13:00:05Z",
                "tool": "Read",
                "est_tokens": 7000,
                "input_bytes": 10,
                "output_bytes": 28000,
                "meta": {"file_path": "/tmp/large.py"},
            },
            {
                "type": "tool_call",
                "ts": "2026-05-09T13:00:10Z",
                "tool": "Agent",
                "est_tokens": 9000,
                "input_bytes": 100,
                "output_bytes": 36000,
                "meta": {
                    "subagent_type": "worker",
                    "status": "running",
                    "description": "Inspect implementation",
                },
            },
            {
                "type": "context_snapshot",
                "ts": "2026-05-09T13:00:30Z",
                "current_tokens": 16000,
                "est_tokens": 0,
            },
        ]

        turns = build_turns(events)

        self.assertEqual(len(turns), 1)
        turn = turns[0]
        self.assertEqual(turn["duration_seconds"], 30)
        self.assertEqual(turn["status"], "agent-running")
        self.assertEqual(turn["agent_statuses"], {"running": 1})
        self.assertEqual(turn["agent_types"], {"worker": 1})
        self.assertEqual(turn["top_files"][0]["path"], "/tmp/large.py")
        self.assertEqual(turn["top_files"][0]["tokens"], 7000)
        self.assertEqual(turn["top_events"][0]["tool"], "Agent")


if __name__ == "__main__":
    unittest.main()
