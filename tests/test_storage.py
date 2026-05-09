import unittest
import time
import tempfile
import json
from pathlib import Path
from unittest.mock import patch

from context_profiler.storage import (
    append_event,
    get_all_profiles,
    load_events,
    mark_transcript_imported,
    profile_matches_session,
    profile_part_paths,
    run_auto_cleanup,
    safe_session_id,
    transcript_import_current,
    write_profile,
)


class StorageTests(unittest.TestCase):
    def test_safe_session_id_removes_path_unsafe_characters(self):
        self.assertEqual(safe_session_id("abc/def ghi"), "abc_def_ghi")

    def test_profile_matches_plain_and_codex_prefixed_sessions(self):
        codex_path = "/tmp/codex-019e0c5b-4219-7192-8098-a99a2d9f9d96.jsonl"
        claude_path = "/tmp/81df4e61-b846-4500-b993-7169abc8ded9.jsonl"

        self.assertTrue(profile_matches_session(codex_path, "019e0c5b"))
        self.assertTrue(profile_matches_session(codex_path, "codex-019e0c5b"))
        self.assertTrue(profile_matches_session(claude_path, "81df4e61"))
        self.assertFalse(profile_matches_session(codex_path, "81df4e61"))

    def test_run_auto_cleanup_deletes_old_profiles_and_throttles(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            old_profile = root / "old.jsonl"
            new_profile = root / "new.jsonl"
            old_profile.write_text("{}\n")
            new_profile.write_text("{}\n")
            old_time = time.time() - (10 * 86400)
            now = time.time()
            old_profile.touch()
            new_profile.touch()
            import os

            os.utime(old_profile, (old_time, old_time))
            os.utime(new_profile, (now, now))

            cfg = {
                "auto_cleanup_enabled": True,
                "auto_cleanup_interval_hours": 24,
                "cleanup_retention_days": 5,
            }
            with patch("context_profiler.storage.PROFILE_DIR", root), patch(
                "context_profiler.storage.load_config", return_value=cfg
            ):
                result = run_auto_cleanup()
                self.assertIsNotNone(result)
                self.assertEqual(result["count"], 1)
                self.assertFalse(old_profile.exists())
                self.assertTrue(new_profile.exists())
                self.assertTrue((root / ".cleanup-state.json").exists())

                throttled = run_auto_cleanup()
                self.assertIsNone(throttled)

    def test_write_profile_rotates_and_loads_logical_session(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            events = [
                {"type": "session_start", "session_id": "s1", "payload": "a" * 40},
                {"type": "tool_call", "session_id": "s1", "tool": "Read", "payload": "b" * 40},
                {"type": "tool_call", "session_id": "s1", "tool": "Bash", "payload": "c" * 40},
            ]
            cfg = {"profile_rotation_enabled": True, "profile_max_part_bytes": 90}

            with patch("context_profiler.storage.PROFILE_DIR", root), patch(
                "context_profiler.storage.load_config", return_value=cfg
            ):
                path = write_profile("s1", events, "claude")
                parts = profile_part_paths(path)

                self.assertGreater(len(parts), 1)
                self.assertEqual(load_events(path), events)
                self.assertEqual(get_all_profiles(), [str(path)])

    def test_append_event_rotates_to_next_part(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            cfg = {"profile_rotation_enabled": True, "profile_max_part_bytes": 120}

            with patch("context_profiler.storage.PROFILE_DIR", root), patch(
                "context_profiler.storage.load_config", return_value=cfg
            ):
                append_event("s1", {"payload": "a" * 90}, "claude")
                append_event("s1", {"payload": "b" * 90}, "claude")
                path = root / "s1.jsonl"

                self.assertEqual(len(profile_part_paths(path)), 2)
                self.assertEqual(len(load_events(path)), 2)

    def test_import_cursor_detects_unchanged_transcript(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            transcript = root / "rollout.jsonl"
            profile = root / "codex-session.jsonl"
            transcript.write_text("{}\n")
            profile.write_text("{}\n")

            with patch("context_profiler.storage.PROFILE_DIR", root):
                self.assertFalse(transcript_import_current("codex", transcript))
                mark_transcript_imported("codex", transcript, profile)
                self.assertTrue(transcript_import_current("codex", transcript))
                transcript.write_text("{}\n{}\n")
                self.assertFalse(transcript_import_current("codex", transcript))

    def test_import_cursor_can_skip_unchanged_transcript_without_profile(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            transcript = root / "empty.jsonl"
            transcript.write_text("{}\n")

            with patch("context_profiler.storage.PROFILE_DIR", root):
                mark_transcript_imported("claude", transcript, None)
                self.assertTrue(transcript_import_current("claude", transcript))
                transcript.write_text("{}\n{}\n")
                self.assertFalse(transcript_import_current("claude", transcript))

    def test_import_cursor_version_invalidates_old_records(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            transcript = root / "rollout.jsonl"
            profile = root / "codex-session.jsonl"
            transcript.write_text("{}\n")
            profile.write_text("{}\n")

            with patch("context_profiler.storage.PROFILE_DIR", root):
                mark_transcript_imported("codex", transcript, profile)
                cursor_file = root / ".import-cursors.json"
                data = json.loads(cursor_file.read_text())
                data["codex"][str(transcript)]["cursor_version"] = -1
                cursor_file.write_text(json.dumps(data))

                self.assertFalse(transcript_import_current("codex", transcript))

    def test_cleanup_keeps_logical_profile_when_latest_part_is_recent(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            base = root / "s1.jsonl"
            part = root / "s1.part-0002.jsonl"
            base.write_text("{}\n")
            part.write_text("{}\n")
            old_time = time.time() - (10 * 86400)
            now = time.time()
            import os

            os.utime(base, (old_time, old_time))
            os.utime(part, (now, now))

            cfg = {
                "auto_cleanup_enabled": True,
                "auto_cleanup_interval_hours": 24,
                "cleanup_retention_days": 5,
            }
            with patch("context_profiler.storage.PROFILE_DIR", root), patch(
                "context_profiler.storage.load_config", return_value=cfg
            ):
                result = run_auto_cleanup()

            self.assertIsNotNone(result)
            self.assertEqual(result["count"], 0)
            self.assertTrue(base.exists())
            self.assertTrue(part.exists())


if __name__ == "__main__":
    unittest.main()
