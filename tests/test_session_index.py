import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from context_profiler.session_index import refresh_session_index
from context_profiler.storage import write_profile


class SessionIndexTests(unittest.TestCase):
    def test_refresh_session_index_reuses_cached_unchanged_profiles(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            events = [
                {
                    "type": "session_start",
                    "ts": "2026-05-09T10:00:00Z",
                    "session_id": "s1",
                    "source": "claude",
                    "cwd": "/repo",
                },
                {
                    "type": "tool_call",
                    "ts": "2026-05-09T10:00:01Z",
                    "session_id": "s1",
                    "source": "claude",
                    "tool": "Read",
                    "est_tokens": 42,
                },
            ]

            with patch("context_profiler.storage.PROFILE_DIR", root), patch(
                "context_profiler.session_index.PROFILE_DIR", root
            ), patch("context_profiler.storage.load_config", return_value={}), patch(
                "context_profiler.session_index.load_config", return_value={}
            ):
                write_profile("s1", events, "claude")
                rows = refresh_session_index(["claude"], 5000)
                index_file = root / ".session-index.json"
                first_mtime = index_file.stat().st_mtime_ns
                cached_rows = refresh_session_index(["claude"], 5000)

            self.assertEqual(rows, cached_rows)
            self.assertEqual(index_file.stat().st_mtime_ns, first_mtime)
            self.assertEqual(rows[0]["session_id"], "s1")
            self.assertEqual(rows[0]["calls"], 1)
            self.assertEqual(rows[0]["tokens"], 42)


if __name__ == "__main__":
    unittest.main()
