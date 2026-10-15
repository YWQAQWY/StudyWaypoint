"""AI planning uses fake upstream APIs; no personal key or network is required."""

import json
import stat
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

from ai_planner import AIPlanner
from plan_library import PlanLibrary
from server import Handler
from tracker import TrackerError, validate_curriculum


def fake_week():
    day = {
        "title": "阅读并实现小练习", "course_section": "基础与实践", "track": "Python",
        "readings": [{"title": "Python 教程", "url": "https://docs.python.org/3/tutorial/"}],
        "exercises": [{"title": "动手练习", "instructions": "自己编写并运行程序",
                       "expected_artifacts": ["代码文件"], "verification": "运行测试"}],
        "deliverables": ["代码文件和日志"],
        "acceptance_tests": [{"assertion": "程序运行通过", "evidence_required": True,
                              "pass_rule": "提供测试日志"}],
    }
    return {"theme": "Python 基础", "leetcode_weekly": [
        {"title": "Two Sum", "url": "https://leetcode.com/problems/two-sum/"},
        {"title": "Valid Parentheses", "url": "https://leetcode.com/problems/valid-parentheses/"}],
        "days": [day for _ in range(7)]}


class AIPlannerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.calls = []

        def completion(url, headers, payload, timeout=180):
            self.assertEqual(url, self.planner.public_config()["base_url"] + "/chat/completions")
            self.assertEqual(headers["Authorization"], "Bearer private-deepseek-key")
            self.calls.append(payload)
            prompt = payload["messages"][-1]["content"]
            if "规划 1 周主题" in prompt:
                answer = json.dumps({"themes": ["Python 基础"]})
            elif "生成第 1/1 周" in prompt:
                answer = json.dumps(fake_week(), ensure_ascii=False)
            elif "联网检索的学习资源证据" in prompt:
                answer = "建议先学习 Python 基础，再完成可测试的小项目。[1]"
            else:
                answer = "请先说明基础和时间安排。"
            return {"choices": [{"finish_reason": "stop", "message": {"content": answer}}]}

        def search(url, headers, payload=None, timeout=30):
            self.assertEqual(headers.get("X-Subscription-Token"), "private-search-key")
            return {"web": {"results": [{"title": "Python Tutorial",
                "url": "https://docs.python.org/3/tutorial/", "description": "Official tutorial"},
                {"title": "Two Sum", "url": "https://leetcode.com/problems/two-sum/", "description": "Practice"},
                {"title": "Valid Parentheses", "url": "https://leetcode.com/problems/valid-parentheses/",
                 "description": "Practice"}]}}

        self.planner = AIPlanner(self.root, transport=completion, search_transport=search)
        self.planner._agent.reader.read = lambda url: {"url": url, "title": "Python Tutorial",
            "description": "Official tutorial", "headings": ["Introduction"], "text": "Learn Python", "links": []}

    def test_config_chat_research_and_generated_plan(self):
        with self.assertRaises(TrackerError):
            self.planner.chat({"message": "学 Python"})
        self.planner.save_config({"api_key": "private-deepseek-key", "model": "deepseek-v4-pro",
                                  "search_api_key": "private-search-key", "third_party_enabled": True})
        self.assertEqual(stat.S_IMODE(self.planner.config_path.stat().st_mode), 0o600)
        self.assertNotIn("private-deepseek-key", json.dumps(self.planner.state()))
        self.assertNotIn("private-search-key", json.dumps(self.planner.state()))
        self.planner.chat({"message": "我想学习 Python，每天一小时"})
        research = self.planner.research()
        self.assertEqual(len(research["history"]["sources"]), 3)
        self.assertIn("[1]", research["answer"])
        job = self.planner.start_generation({"plan_id": "python-week", "plan_name": "Python 一周",
                                             "weeks": 1, "daily_hours": [1] * 7, "confirmed": True})
        for _ in range(100):
            if self.planner.state()["job"]["status"] != "running":
                break
            time.sleep(.01)
        self.assertEqual(self.planner.state()["job"]["status"], "complete")
        draft = self.planner.draft()
        self.assertEqual(draft["id"], job["id"])
        self.assertTrue(validate_curriculum(draft["plan"])["valid"])
        self.assertEqual(len(draft["plan"]["days"]), 7)
        self.assertEqual(draft["plan"]["total_planned_hours"], 7)
        library = PlanLibrary(self.root)
        self.assertNotIn("python-week", [p["plan_id"] for p in library.list_plans()])
        Handler.ai, Handler.tracker = self.planner, library
        handler = object.__new__(Handler)
        handler._json = lambda: {"id": "wrong"}
        with self.assertRaises(TrackerError):
            handler._dispatch_ai("POST", "/api/ai/draft/apply")
        handler._json = lambda: {"id": draft["id"]}
        handler._dispatch_ai("POST", "/api/ai/draft/apply")
        self.assertEqual(library.active_plan_id, "python-week")
        self.assertEqual(len(library.list_days()), 7)

    def test_default_research_requires_searxng(self):
        self.planner.save_config({"api_key": "private-deepseek-key"})
        self.planner.chat({"message": "学 Python"})
        with self.assertRaisesRegex(TrackerError, "SearXNG"):
            self.planner.research()
        self.planner.clear_history()
        self.assertEqual(self.planner.state()["history"]["messages"], [])

    def test_search_connection_states_and_generation_blocks_chat(self):
        self.planner.save_config({"api_key": "private-deepseek-key",
                                  "searxng_url": "https://search.example.org"})
        self.assertIsNone(self.planner.public_config()["searxng_tested_at"])

        def searxng(url, headers, payload=None, timeout=20):
            return {"results": []}

        self.planner._search_transport = searxng
        self.assertTrue(self.planner.test_search("searxng")["connected"])
        self.assertTrue(self.planner.public_config()["searxng_tested_at"])
        self.planner.save_config({"searxng_url": "https://other-search.example.org"})
        self.assertIsNone(self.planner.public_config()["searxng_tested_at"])
        self.planner._job = {"id": "active", "status": "running", "current_week": 0, "weeks": 1}
        with self.assertRaisesRegex(TrackerError, "生成结束"):
            self.planner.chat({"message": "继续"})
        with self.assertRaisesRegex(TrackerError, "生成结束"):
            self.planner.research()

    def test_latest_resource_preferences_and_new_goal_search(self):
        history = {"messages": [
            {"role": "user", "content": "优先 B站 中文视频"},
            {"role": "user", "content": "后来改成 YouTube 英文视频"}],
            "evidence": [{"url": "https://example.org/old"}]}
        self.assertEqual(self.planner._preferences(history, "继续找资料"),
                         {"language": "英文视频", "platform": "youtube"})
        self.assertTrue(self.planner._needs_search("帮我制定新的机器学习计划", history))
        self.assertFalse(self.planner._needs_search("这个课程怎么样", history))

    def test_searxng_research_without_brave_key(self):
        urls = []

        def searxng(url, headers, payload=None, timeout=30):
            urls.append(url)
            self.assertEqual(headers, {"Accept": "application/json"})
            return {"results": [{"title": "Python Tutorial",
                                  "url": "https://docs.python.org/3/tutorial/",
                                  "content": "Official tutorial"}]}

        self.planner._search_transport = searxng
        config = self.planner.save_config({"api_key": "private-deepseek-key",
                                           "search_provider": "searxng",
                                           "searxng_url": "http://127.0.0.1:8888/"})
        self.assertTrue(config["search_enabled"])
        self.assertFalse(config["brave_key_configured"])
        self.planner.chat({"message": "我想学 Python"})
        result = self.planner.research()
        self.assertEqual(result["history"]["sources"][0]["description"], "Official tutorial")
        self.assertEqual(len(urls), 3)
        self.assertTrue(all(url.startswith("http://127.0.0.1:8888/search?") for url in urls))
        self.assertTrue(all("format=json" in url for url in urls))
        with self.assertRaises(TrackerError):
            self.planner.save_config({"searxng_url": "http://search.example.org"})
        with self.assertRaises(TrackerError):
            self.planner.save_config({"searxng_url": "https://example.org/search"})
        self.planner.save_config({"clear_searxng_url": True})
        self.assertFalse(self.planner.public_config()["search_enabled"])

    def test_searxng_403_explains_json_setting(self):
        def forbidden(url, headers, payload=None, timeout=30):
            raise TrackerError("外部 API 返回 403：Forbidden", "upstream_error", 502)

        self.planner._search_transport = forbidden
        self.planner.save_config({"api_key": "private-deepseek-key", "search_provider": "searxng",
                                  "searxng_url": "https://search.example.org"})
        self.planner.chat({"message": "我想学 Python"})
        with self.assertRaisesRegex(TrackerError, "search.formats"):
            self.planner.research()

    def test_custom_openai_compatible_base_url(self):
        self.planner.save_config({"api_key": "private-deepseek-key", "model": "custom-model",
                                  "base_url": "https://example.org/v1/"})
        self.assertEqual(self.planner.public_config()["base_url"], "https://example.org/v1")
        self.planner.chat({"message": "测试兼容格式"})
        self.assertEqual(self.calls[-1]["model"], "custom-model")
        self.assertEqual(self.calls[-1]["reasoning_effort"], "high")
        self.planner.save_config({"reasoning_effort": "default"})
        self.planner.chat({"message": "继续"})
        self.assertNotIn("reasoning_effort", self.calls[-1])
        with self.assertRaises(TrackerError):
            self.planner.save_config({"base_url": "http://127.0.0.1:8000/v1"})
        with self.assertRaises(TrackerError):
            self.planner.save_config({"base_url": "https://example.org/v1/chat/completions"})

    def test_ai_api_rejects_foreign_browser_origin(self):
        handler = object.__new__(Handler)
        handler.server = SimpleNamespace(server_port=8765)
        handler.headers = {"Host": "127.0.0.1:8765", "Origin": "https://other.example"}
        with self.assertRaises(TrackerError):
            handler._require_ai_local()
        handler.headers = {"Host": "other.example:8765"}
        with self.assertRaises(TrackerError):
            handler._require_ai_local()
        handler.headers = {"Host": "127.0.0.1:8765", "Origin": "http://127.0.0.1:8765"}
        handler._require_ai_local()

    def test_json_mode_fallback_for_compatible_provider(self):
        self.planner.save_config({"api_key": "private-deepseek-key", "reasoning_effort": "default"})
        requests = []

        def provider(url, headers, payload, timeout=180):
            requests.append(payload.copy())
            if "response_format" in payload:
                raise TrackerError("外部 API 返回 400：unsupported response_format")
            return {"choices": [{"finish_reason": "stop", "message": {"content": '{"ok":true}'}}]}

        self.planner._transport = provider
        self.assertEqual(self.planner._completion([{"role": "user", "content": "只输出 JSON"}], json_mode=True), '{"ok":true}')
        self.assertEqual(len(requests), 2)
        self.assertNotIn("response_format", requests[1])

    def test_tool_call_search_respects_disabled_brave_and_keeps_key_out_of_model(self):
        model_payloads, search_calls = [], []

        def model(url, headers, payload, timeout=180):
            model_payloads.append(payload)
            if payload.get("tools") and not any(m.get("role") == "tool" for m in payload["messages"]):
                return {"choices": [{"finish_reason": "tool_calls", "message": {"content": None,
                    "tool_calls": [{"id": "call1", "type": "function", "function": {
                        "name": "search_courses", "arguments": json.dumps({"topic": "Python",
                        "provider": "brave"})}}]}}]}
            return {"choices": [{"finish_reason": "stop", "message": {
                "content": "Python 课程可从官方教程开始。[1]"}}]}

        def search(url, headers, payload=None, timeout=20):
            search_calls.append(url)
            self.assertNotIn("X-Subscription-Token", headers)
            return {"results": [{"title": "Python Tutorial", "url": "https://docs.python.org/3/tutorial/",
                                 "content": "Official tutorial"}]}

        self.planner._transport = model
        self.planner._search_transport = search
        self.planner.save_config({"api_key": "private-deepseek-key", "search_api_key": "private-search-key",
                                  "searxng_url": "https://search.example.org", "third_party_enabled": False})
        result = self.planner.chat({"message": "帮我制定 Python 学习计划"})
        self.assertIn("官方教程", result["answer"])
        self.assertGreater(len(search_calls), 0)
        self.assertTrue(all("search.example.org" in url for url in search_calls))
        self.assertNotIn("private-search-key", json.dumps(model_payloads))
        self.assertEqual(result["history"]["evidence"][0]["provider"], "searxng")

    def test_unsupported_tools_use_deterministic_search(self):
        calls = []

        def model(url, headers, payload, timeout=180):
            if payload.get("tools"):
                raise TrackerError("外部 API 返回 400：tools unsupported", "upstream_http_400", 502)
            return {"choices": [{"finish_reason": "stop", "message": {"content": "可用资料见 [1]。"}}]}

        def search(url, headers, payload=None, timeout=20):
            calls.append(url)
            return {"results": [{"title": "Python Tutorial", "url": "https://docs.python.org/3/tutorial/",
                                 "content": "Official tutorial"}]}

        self.planner._transport = model
        self.planner._search_transport = search
        self.planner.save_config({"api_key": "private-deepseek-key",
                                  "searxng_url": "https://search.example.org"})
        answer = self.planner.chat({"message": "帮我制定 Python 学习计划"})
        self.assertIn("[1]", answer["answer"])
        self.assertGreater(len(calls), 0)

    def test_generation_repairs_untraceable_url_and_preserves_schema(self):
        attempts = []

        def model(url, headers, payload, timeout=180):
            prompt = payload["messages"][-1]["content"]
            if "规划 1 周主题" in prompt:
                content = '{"themes":["Python 基础"]}'
            elif "生成第 1/1 周" in prompt:
                attempts.append(prompt)
                week = fake_week()
                if len(attempts) == 1:
                    week["days"][0]["readings"][0]["url"] = "https://made-up.example/course"
                content = json.dumps(week, ensure_ascii=False)
            else:
                content = "请继续。"
            return {"choices": [{"finish_reason": "stop", "message": {"content": content}}]}

        def search(url, headers, payload=None, timeout=20):
            return {"web": {"results": [
                {"title": "Python Tutorial", "url": "https://docs.python.org/3/tutorial/"},
                {"title": "Two Sum", "url": "https://leetcode.com/problems/two-sum/"},
                {"title": "Valid Parentheses", "url": "https://leetcode.com/problems/valid-parentheses/"}]}}

        self.planner._transport = model
        self.planner._search_transport = search
        self.planner.save_config({"api_key": "private-deepseek-key", "search_api_key": "private-search-key",
                                  "third_party_enabled": True})
        self.planner.chat({"message": "帮我制定 Python 学习计划"})
        self.planner.start_generation({"plan_id": "python-week", "plan_name": "Python 一周",
                                       "weeks": 1, "daily_hours": [1] * 7, "confirmed": True})
        for _ in range(100):
            if self.planner.state()["job"]["status"] != "running":
                break
            time.sleep(.01)
        self.assertEqual(self.planner.state()["job"]["status"], "complete")
        self.assertEqual(len(attempts), 2)
        plan = self.planner.draft()["plan"]
        self.assertEqual(set(plan), set(json.loads((Path(__file__).parents[1] /
            "examples/sample_plan_v3.json").read_text())))
        self.assertTrue(validate_curriculum(plan)["valid"])


if __name__ == "__main__":
    unittest.main()
