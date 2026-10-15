"""Versioned internal planning state; final curriculum schema is tested elsewhere."""

import tempfile
import unittest
from pathlib import Path

from plan_draft import PlanDraftStore, blockers
from tracker import TrackerError


class PlanDraftTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "ai_plan_draft.json"
        self.store = PlanDraftStore(self.path)

    def test_partial_draft_local_updates_and_restart(self):
        self.assertEqual(self.store.get()["status"], "IDLE")
        self.store.begin("conversation-one")
        partial = self.store.apply("conversation-one", 0, {"set": {"title": "机器学习",
            "learning_goal": "完成机器学习实战", "weeks": 8, "weekly_hours": 10},
            "upsert_stages": [{"title": "基础", "upsert_tasks": [{"title": "Python 基础"}]},
                              {"title": "建模", "upsert_tasks": [{"title": "训练模型"}]}],
            "unresolved_questions": [{"text": "是否已有 Python 基础？", "blocking": True}],
            "rationale": "先建立部分路线"})
        self.assertEqual(partial["revision"], 1)
        self.assertEqual(partial["status"], "REFINING")
        self.assertEqual(round(sum(partial["daily_hours"]), 4), 10)
        self.assertEqual(len(partial["stages"]), 2)
        self.assertTrue(blockers(partial))
        stage, unchanged = partial["stages"]
        task_id = stage["tasks"][0]["id"]
        revised = self.store.apply("conversation-one", 1, {"upsert_stages": [{"id": stage["id"],
            "remove_task_ids": [task_id], "upsert_tasks": [{"title": "实践项目"}]}],
            "unresolved_questions": [], "rationale": "已掌握 Python"})
        self.assertEqual(revised["status"], "READY_FOR_CONFIRMATION")
        self.assertEqual(revised["stages"][1], unchanged)
        self.assertEqual(revised["stages"][0]["id"], stage["id"])
        with self.assertRaisesRegex(TrackerError, "版本"):
            self.store.apply("conversation-one", 1, {"set": {"title": "旧版本"}})
        self.assertEqual(PlanDraftStore(self.path).get()["revision"], 2)

    def test_invalid_patch_is_atomic_and_confirmation_idempotent(self):
        self.store.begin("one")
        with self.assertRaises(TrackerError):
            self.store.apply("one", 0, {"set": {"weeks": 80}})
        self.assertEqual(self.store.get()["revision"], 0)
        with self.assertRaisesRegex(TrackerError, "确认前"):
            self.store.confirm(self.store.get()["draft_id"], 0, "confirmation-123")
        ready = self.store.apply("one", 0, {"set": {"title": "A", "learning_goal": "B",
            "weeks": 1, "daily_hours": [1] * 7},
            "upsert_stages": [{"title": "第一阶段", "upsert_tasks": [{"title": "任务"}]}],
            "unresolved_questions": []})
        confirmed, started = self.store.confirm(ready["draft_id"], 1, "confirmation-123")
        self.assertTrue(started)
        self.assertEqual(confirmed["confirmed_snapshot"]["revision"], 1)
        _, started = self.store.confirm(ready["draft_id"], 1, "confirmation-123")
        self.assertFalse(started)
        with self.assertRaises(TrackerError):
            self.store.apply("one", 1, {"set": {"title": "不可覆盖"}})
        self.store.set_error("network failure")
        self.assertEqual(PlanDraftStore(self.path).get()["status"], "ERROR")
        _, started = self.store.confirm(ready["draft_id"], 1, "confirmation-123")
        self.assertTrue(started)
        self.store.complete({"active_plan_id": "test-plan"})
        completed, started = self.store.confirm(ready["draft_id"], 1, "confirmation-123")
        self.assertFalse(started)
        self.assertEqual(completed["import_result"]["active_plan_id"], "test-plan")

    def test_search_evidence_enriches_without_fabricating_url(self):
        self.store.begin("one")
        draft = self.store.apply("one", 0, {"upsert_stages": [{"title": "基础",
            "upsert_tasks": [{"title": "Python 教程"}]}]})
        enriched = self.store.enrich("one", [{"title": "Python 教程", "url": "https://example.org/python",
            "snippet": "Python 教程", "provider": "searxng", "verification_status": "search_result_only"}])
        self.assertEqual(enriched["revision"], draft["revision"] + 1)
        self.assertEqual(enriched["stages"][0]["tasks"][0]["resources"], ["https://example.org/python"])
        self.assertEqual(self.store.enrich("one", enriched["resources"])["revision"], enriched["revision"])

    def test_time_change_rescales_estimates_and_conflicts_are_rejected(self):
        self.store.begin("one")
        first = self.store.apply("one", 0, {"set": {"weekly_hours": 10},
            "upsert_stages": [{"title": "实践", "estimated_hours": 10,
                               "upsert_tasks": [{"title": "项目", "estimated_minutes": 120}]}]})
        second = self.store.apply("one", 1, {"set": {"weekly_hours": 5}})
        self.assertEqual(second["stages"][0]["estimated_hours"], 5)
        self.assertEqual(second["stages"][0]["tasks"][0]["estimated_minutes"], 60)
        with self.assertRaisesRegex(TrackerError, "冲突"):
            self.store.apply("one", second["revision"], {"set": {"weekly_hours": 10,
                                                              "daily_hours": [2] * 7}})
        self.assertEqual(self.store.get()["revision"], second["revision"])


if __name__ == "__main__":
    unittest.main()
