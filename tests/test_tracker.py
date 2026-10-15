import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from tracker import CURRICULUM, Tracker, TrackerError, validate_curriculum


class CurriculumTests(unittest.TestCase):
    def test_starter_v3_curriculum(self):
        data = json.loads(CURRICULUM.read_text(encoding="utf-8"))
        result = validate_curriculum(data)
        self.assertTrue(result["valid"], result["errors"])
        self.assertEqual(result["days"], 7)
        self.assertEqual(result["minutes"], 420)


class TrackerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.tracker = Tracker(self.temp.name)

    def test_all_days_and_today_mapping(self):
        self.assertEqual(len(self.tracker.list_days()), 7)
        self.assertIsNone(self.tracker.bootstrap()["today_id"])
        self.tracker.update_settings({"start_date": "2026-10-15", "timezone": "Asia/Shanghai"})
        self.assertEqual(self.tracker.bootstrap(datetime(2026, 10, 14, 16, 30, tzinfo=timezone.utc))["today_id"], "W01D01")
        self.assertEqual(self.tracker.bootstrap(datetime(2026, 10, 20, 16, 30, tzinfo=timezone.utc))["today_id"], "W01D07")
        self.tracker.update_settings({"start_date": "2026-10-16"})
        self.assertIsNone(self.tracker.bootstrap(datetime(2026, 10, 14, 16, 30, tzinfo=timezone.utc))["today_id"])

    def test_progress_is_not_mastery_and_evidence_required(self):
        day = self.tracker.get_day("W01D01")
        exercise = day["coding_exercises"][0]["id"]
        criterion = day["acceptance_tests"][0]["id"]
        self.tracker.toggle("W01D01", "exercise", exercise)
        self.tracker.update_progress("W01D01", status="passed")
        self.assertFalse(self.tracker.list_days()[0]["mastered"])
        with self.assertRaises(TrackerError):
            self.tracker.review("W01D01", criterion, {"status": "passed"})
        self.tracker.review("W01D01", criterion, {"status": "submitted"})
        evidence = self.tracker.add_evidence("W01D01", {"type": "test_log", "content": "pytest passed", "criterion_id": criterion})
        self.tracker.review("W01D01", criterion, {"status": "passed", "evidence_id": evidence["id"]})
        self.assertEqual(self.tracker.get_day("W01D01")["acceptance_progress"][criterion]["status"], "passed")
        self.assertTrue(self.tracker.list_days()[0]["mastered"])

    def test_timer_idempotence_and_restart(self):
        start = datetime(2026, 10, 15, 15, 59, tzinfo=timezone.utc)
        first = self.tracker.start_session("W01D01", start)
        again = self.tracker.start_session("W01D01", start)
        self.assertEqual(first["id"], again["id"])
        restarted = Tracker(self.temp.name)
        self.assertEqual(restarted.active_session()["id"], first["id"])
        end = datetime(2026, 10, 15, 16, 1, tzinfo=timezone.utc)
        result = restarted.stop_session(end)
        self.assertEqual(result["duration_seconds"], 120)
        self.assertEqual(restarted.stop_session(end), {"active": False})
        self.assertEqual(restarted.get_day("W01D01")["actual_seconds"], 120)
        self.assertEqual(restarted.manual_session("W01D01", {"minutes": 10, "note": "offline"})["source"], "manual")
        self.assertEqual(restarted.get_day("W01D01")["actual_seconds"], 720)

    def test_import_and_backup_keep_progress(self):
        self.tracker.toggle("W01D07", "exercise", "W01D07E1")
        evidence = self.tracker.add_evidence("W01D07", {"type": "git_commit", "content": "abc123"})
        self.assertEqual(self.tracker.import_preview()["unchanged"], 7)
        self.tracker.import_curriculum()
        self.assertTrue(self.tracker.get_day("W01D07")["exercise_progress"]["W01D07E1"])
        self.assertEqual(len(self.tracker.get_day("W01D07")["evidence_items"]), 1)
        backup = self.tracker.export()
        self.assertEqual(self.tracker.restore_preview(backup)["tables"]["evidence"]["backup"], 1)
        self.tracker.toggle("W01D07", "exercise", "W01D07E1")
        self.tracker.restore(backup)
        self.assertTrue(self.tracker.get_day("W01D07")["exercise_progress"]["W01D07E1"])
        self.assertEqual(self.tracker.get_day("W01D07")["evidence_items"][0]["id"], evidence["id"])
        self.assertEqual(len(list((Path(self.temp.name) / "backups").glob("pre_restore_*.json"))), 1)

    def test_budget_and_reflection(self):
        self.tracker.update_budget("W01D01", {"theory_minutes": 10, "practice_minutes": 40, "verification_minutes": 10})
        day = self.tracker.get_day("W01D01")
        self.assertEqual(day["effective_planned_minutes"], 60)
        self.assertEqual(day["time_budget"]["theory_minutes"], 20)
        self.tracker.save_reflection("W01D01", {"achievements": "完成环境", "tests": "待测", "blockers": "无 GPU", "tomorrow": "继续"})
        self.assertEqual(self.tracker.get_day("W01D01")["reflection"]["blockers"], "无 GPU")


if __name__ == "__main__":
    unittest.main()
