"""Interactive planning uses fake model/search APIs and the real v3 importer."""

import json
import tempfile
import threading
from http.server import ThreadingHTTPServer
from urllib.request import Request, urlopen
import time
import unittest
from pathlib import Path

from ai_planner import AIPlanner
from plan_library import PlanLibrary
from server import Handler
from tracker import TrackerError, validate_curriculum

from tests.test_ai_planner import fake_week


class InteractivePlanningTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.model_calls = []
        self.search_calls = []
        self.feedback = False

        def model(url, headers, payload, timeout=180):
            self.model_calls.append(payload)
            prompt = payload["messages"][-1]["content"]
            if "更新应用的内部学习规划草稿" in prompt:
                if not self.feedback:
                    patch = {"base_revision": 0, "set": {"title": "机器学习八周",
                        "learning_goal": "独立训练机器学习模型", "weeks": 1,
                        "daily_hours": [2] * 7, "language": "中文", "platform": "bilibili"},
                        "upsert_stages": [{"title": "基础", "upsert_tasks": [{"title": "Python 基础"}]},
                                          {"title": "建模", "upsert_tasks": [{"title": "训练模型"}]}],
                        "unresolved_questions": []}
                else:
                    current = self.planner.plan_draft_state()
                    first = current["stages"][0]
                    patch = {"base_revision": current["revision"], "set": {"weekly_hours": 10},
                        "upsert_stages": [{"id": first["id"],
                            "remove_task_ids": [first["tasks"][0]["id"]],
                            "upsert_tasks": [{"title": "实战项目"}]}],
                        "unresolved_questions": [], "rationale": "删去已掌握的基础，增加实战"}
                content = json.dumps(patch, ensure_ascii=False)
            elif "生成第 1/1 周" in prompt:
                week = fake_week()
                for day in week["days"]:
                    day["title"] = "实战项目和训练模型"
                content = json.dumps(week, ensure_ascii=False)
            elif "评估与学习主题" in prompt:
                content = '{"assessments":[]}'
            else:
                content = "已更新计划草稿，请在侧栏查看并继续反馈。"
            return {"choices": [{"finish_reason": "stop", "message": {"content": content}}]}

        def search(url, headers, payload=None, timeout=20):
            self.search_calls.append(url)
            return {"results": [
                {"title": "Python 基础", "url": "https://docs.python.org/3/tutorial/"},
                {"title": "Two Sum", "url": "https://leetcode.com/problems/two-sum/"},
                {"title": "Valid Parentheses", "url": "https://leetcode.com/problems/valid-parentheses/"}]}

        self.planner = AIPlanner(self.root, transport=model, search_transport=search)
        self.planner._agent.reader.read = lambda url: {"url": url, "title": "Course", "description": "",
            "headings": [], "text": "Course content", "links": []}
        self.planner.save_config({"api_key": "fake-model-key", "searxng_url": "https://search.example.org"})
        self.library = PlanLibrary(self.root)

    def wait_job(self):
        for _ in range(200):
            if self.planner.plan_draft_state()["status"] in ("COMPLETED", "ERROR", "CANCELLED"):
                return
            time.sleep(.01)
        self.fail("background import did not finish")

    def build_draft(self):
        self.planner.chat({"message": "帮我制定机器学习计划，每天两小时，优先 B 站视频"})
        initial = self.planner.plan_draft_state()
        self.assertEqual(initial["status"], "READY_FOR_CONFIRMATION")
        self.assertTrue(initial["resources"])
        self.assertTrue(self.search_calls)
        self.feedback = True
        self.planner.chat({"message": "我已经会 Python，删掉 Python 基础，增加一个实战项目，每周改为 10 小时"})
        return initial, self.planner.plan_draft_state()

    def test_feedback_preserves_other_stage_and_persists(self):
        initial, revised = self.build_draft()
        self.assertGreater(revised["revision"], initial["revision"])
        self.assertEqual(revised["stages"][1], initial["stages"][1])
        self.assertEqual(revised["stages"][0]["id"], initial["stages"][0]["id"])
        self.assertEqual(revised["stages"][0]["tasks"][0]["title"], "实战项目")
        self.assertEqual(round(sum(revised["daily_hours"]), 4), 10)
        self.assertEqual(AIPlanner(self.root).plan_draft_state()["revision"], revised["revision"])
        self.assertNotIn("机器学习八周", [p["plan_name"] for p in self.library.list_plans()])

    def test_confirm_generates_valid_json_auto_imports_and_is_idempotent(self):
        _, draft = self.build_draft()
        key = "confirmation-interactive-001"
        request = {"draft_id": draft["draft_id"], "revision": draft["revision"], "confirmation_id": key}
        self.planner.confirm_import(request, self.library)
        self.planner.confirm_import(request, self.library)
        self.wait_job()
        completed = self.planner.plan_draft_state()
        self.assertEqual(completed["status"], "COMPLETED", completed.get("error"))
        plan = self.planner.draft()["plan"]
        self.assertTrue(validate_curriculum(plan)["valid"])
        self.assertEqual(plan["weekly_themes"], ["基础 · 建模"])
        self.assertEqual(self.library.active_plan_id, plan["plan_id"])
        self.assertEqual(len(self.library.list_days()), 7)
        self.assertEqual(self.planner.confirm_import(request, self.library)["draft"]["status"], "COMPLETED")
        self.assertEqual(sum(p["plan_id"] == plan["plan_id"] for p in self.library.list_plans()), 1)
        edited = self.planner.plan_drafts.apply(completed["conversation_id"], completed["revision"],
                                                {"set": {"title": "机器学习修订版"}})
        with self.assertRaisesRegex(TrackerError, "已存在"):
            self.planner.confirm_import({"draft_id": edited["draft_id"],
                "revision": edited["revision"], "confirmation_id": "confirmation-second-001"},
                self.library)

    def test_failed_import_keeps_draft_and_retry_reuses_generated_json(self):
        _, draft = self.build_draft()
        request = {"draft_id": draft["draft_id"], "revision": draft["revision"],
                   "confirmation_id": "confirmation-retry-001"}
        original = self.library.apply_plan
        calls = []

        def fail_once(plan):
            calls.append(plan)
            if len(calls) == 1:
                raise TrackerError("模拟导入失败")
            return original(plan)

        self.library.apply_plan = fail_once
        self.planner.confirm_import(request, self.library)
        self.wait_job()
        self.assertEqual(self.planner.plan_draft_state()["status"], "ERROR")
        self.assertEqual(self.planner.plan_draft_state()["stages"], draft["stages"])
        generated = sum("生成第 1/1 周" in p["messages"][-1]["content"] for p in self.model_calls)
        self.planner.confirm_import(request, self.library)
        self.wait_job()
        self.assertEqual(self.planner.plan_draft_state()["status"], "COMPLETED")
        self.assertEqual(sum("生成第 1/1 周" in p["messages"][-1]["content"]
                             for p in self.model_calls), generated)
        self.assertEqual(len(calls), 2)

    def test_partial_draft_is_visible_while_search_is_waiting(self):
        entered, release = threading.Event(), threading.Event()

        def delayed_search(url, headers, payload=None, timeout=20):
            entered.set()
            release.wait(2)
            raise TrackerError("搜索暂不可用", "upstream_error", 502)

        self.planner._search_transport = delayed_search
        result = []

        def run():
            try:
                result.append(self.planner.chat({"message": "帮我制定机器学习计划，每天两小时"}))
            except Exception as exc:
                result.append(exc)

        worker = threading.Thread(target=run, daemon=True)
        worker.start()
        self.assertTrue(entered.wait(1))
        visible = self.planner.plan_draft_state()
        self.assertEqual(visible["title"], "机器学习八周")
        self.assertEqual(visible["status"], "READY_FOR_CONFIRMATION")
        release.set()
        worker.join(3)
        self.assertFalse(worker.is_alive())
        self.assertIsInstance(result[0], dict)
        self.assertEqual(self.planner.plan_draft_state()["title"], "机器学习八周")

    def test_http_confirmation_endpoint_imports_without_upload(self):
        _, draft = self.build_draft()
        Handler.ai, Handler.tracker = self.planner, self.library
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        base = f"http://127.0.0.1:{server.server_port}"
        try:
            with urlopen(base + "/api/ai/plan-draft") as response:
                self.assertEqual(json.load(response)["revision"], draft["revision"])
            body = json.dumps({"draft_id": draft["draft_id"], "revision": draft["revision"],
                "confirmation_id": "confirmation-http-001"}).encode()
            request = Request(base + "/api/ai/plan-draft/confirm", data=body,
                              headers={"Content-Type": "application/json"}, method="POST")
            with urlopen(request) as response:
                self.assertIn(json.load(response)["job"]["status"], ("running", "complete"))
            self.wait_job()
            with urlopen(base + "/api/bootstrap") as response:
                self.assertEqual(json.load(response)["active_plan_id"], self.library.active_plan_id)
            self.assertNotEqual(self.library.active_plan_id, self.library.default_id)
        finally:
            server.shutdown()
            server.server_close()
            worker.join()

    def test_existing_plan_id_requires_explicit_update_choice(self):
        _, draft = self.build_draft()
        updated = self.planner.plan_drafts.apply(draft["conversation_id"], draft["revision"],
            {"set": {"plan_id": self.library.default_id}})
        with self.assertRaisesRegex(TrackerError, "已存在"):
            self.planner.confirm_import({"draft_id": updated["draft_id"],
                "revision": updated["revision"], "confirmation_id": "confirmation-existing-001"},
                self.library)
        self.assertEqual(self.planner.plan_draft_state()["status"], "READY_FOR_CONFIRMATION")

    def test_stage_hours_guide_deterministic_week_mapping(self):
        specs = AIPlanner._draft_week_specs({"weeks": 4, "stages": [
            {"title": "短阶段", "estimated_hours": 1, "tasks": [{"title": "任务甲"}]},
            {"title": "长阶段", "estimated_hours": 7, "tasks": [{"title": "任务乙"}]}]})
        self.assertEqual(len(specs), 4)
        self.assertIn("短阶段", specs[0]["theme"])
        self.assertIn("长阶段", specs[-1]["theme"])
        self.assertTrue(all(spec["tasks"] for spec in specs))


if __name__ == "__main__":
    unittest.main()
