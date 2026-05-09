import unittest

from visualize import (
    collect_source_agent_rows,
    format_table_timestamp,
    session_id_for_profile,
    session_relationship_label,
    session_relationship_maps,
    sort_session_rows_by_start,
    timestamp_epoch,
)


class SessionRelationshipTests(unittest.TestCase):
    def test_format_table_timestamp_shows_date_and_time(self):
        self.assertEqual(
            format_table_timestamp("2026-05-09T13:00:01Z"),
            "05-09 13:00:01",
        )

    def test_sessions_sort_newest_start_first(self):
        rows = [
            {"session": "old", "started_epoch": timestamp_epoch("2026-05-09T10:00:00Z")},
            {"session": "new", "started_epoch": timestamp_epoch("2026-05-09T12:00:00Z")},
            {"session": "middle", "started_epoch": timestamp_epoch("2026-05-09T11:00:00Z")},
        ]
        self.assertEqual(
            [row["session"] for row in sort_session_rows_by_start(rows)],
            ["new", "middle", "old"],
        )

    def test_collect_source_agent_rows_returns_recent_completed_agents(self):
        records = [
            {
                "session_id": "parent-1",
                "events": [
                    {
                        "type": "tool_call",
                        "ts": "2026-05-09T10:00:00Z",
                        "source": "codex",
                        "session_id": "parent-1",
                        "tool": "Agent",
                        "est_tokens": 100,
                        "meta": {
                            "status": "completed",
                            "subagent_type": "worker",
                            "child_session_id": "child-1",
                            "parent_session_id": "parent-1",
                        },
                    }
                ],
            },
            {"session_id": "latest-empty", "events": [{"type": "session_start"}]},
        ]

        rows = collect_source_agent_rows(records)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["_scope"], "source")
        self.assertEqual(rows[0]["status"], "completed")
        self.assertEqual(rows[0]["child_session_id"], "child-1")

    def test_session_id_for_profile_prefers_session_start(self):
        events = [{"type": "session_start", "session_id": "parent-1"}]
        self.assertEqual(session_id_for_profile("/tmp/codex-parent-1.jsonl", events), "parent-1")

    def test_relationship_label_marks_parent_and_child_sessions(self):
        records = [
            {
                "path": "/tmp/codex-parent-1.jsonl",
                "session_id": "parent-1",
                "events": [
                    {
                        "type": "tool_call",
                        "tool": "Agent",
                        "meta": {
                            "parent_session_id": "parent-1",
                            "child_session_id": "child-1",
                        },
                    },
                    {
                        "type": "tool_call",
                        "tool": "Agent",
                        "meta": {
                            "parent_session_id": "parent-1",
                            "child_session_ids": ["child-2"],
                        },
                    },
                ],
            },
            {"path": "/tmp/codex-child-1.jsonl", "session_id": "child-1", "events": []},
        ]
        parent_to_children, child_to_parent = session_relationship_maps(records)

        self.assertEqual(
            session_relationship_label("parent-1", parent_to_children, child_to_parent),
            "parent:2",
        )
        self.assertEqual(
            session_relationship_label("child-1", parent_to_children, child_to_parent),
            "child->parent-1",
        )
        self.assertEqual(
            session_relationship_label("other", parent_to_children, child_to_parent),
            "-",
        )


if __name__ == "__main__":
    unittest.main()
