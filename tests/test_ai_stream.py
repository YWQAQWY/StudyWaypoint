"""Streaming chat and tool chunks use only fake upstream responses."""

import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ai_planner import AIPlanner
from tracker import TrackerError


class AIStreamTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def test_sse_content_and_tool_chunks_are_aggregated(self):
        planner = AIPlanner(self.root)
        events = [
            {"choices": [{"delta": {"content": "你好"}}]},
            {"choices": [{"delta": {"content": "，世界"}}]},
            {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "call-1",
                "function": {"name": "search_web", "arguments": '{"query":'}}]}}]},
            {"choices": [{"delta": {"tool_calls": [{"index": 0,
                "function": {"arguments": '"Python"}'}}]}, "finish_reason": "tool_calls"}]},
        ]
        body = b"".join(b"data: " + json.dumps(event).encode() + b"\n\n" for event in events) + b"data: [DONE]\n\n"
        partials = []
        with patch("urllib.request.urlopen", return_value=io.BytesIO(body)):
            result = planner._http_stream("https://example.org/chat/completions",
                                          {"Authorization": "Bearer fake"}, {"stream": True}, partials.append)
        self.assertEqual(partials, ["你好", "你好，世界"])
        choice = result["choices"][0]
        self.assertEqual(choice["finish_reason"], "tool_calls")
        self.assertEqual(choice["message"]["tool_calls"][0]["function"]["arguments"], '{"query":"Python"}')

    def test_chat_exposes_partial_text_then_saves_final_answer(self):
        seen = []

        def stream(_url, _headers, payload, callback):
            self.assertTrue(payload["stream"])
            callback("第一段")
            seen.append(planner.activity()["partial_text"])
            callback("第一段第二段")
            seen.append(planner.activity()["partial_text"])
            return {"choices": [{"finish_reason": "stop",
                                 "message": {"content": "第一段第二段"}}]}

        planner = AIPlanner(self.root, transport=lambda *_: self.fail("不应调用非流式接口"),
                            stream_transport=stream)
        planner.save_config({"api_key": "fake-secret"})
        result = planner.chat({"message": "什么是监督学习？"})
        self.assertEqual(seen, ["第一段", "第一段第二段"])
        self.assertEqual(result["answer"], "第一段第二段")
        self.assertEqual(planner.activity()["partial_text"], "")
        self.assertNotIn("fake-secret", json.dumps(planner.state()))

    def test_provider_rejecting_stream_falls_back_to_chat_completion(self):
        payloads = []

        def nonstream(_url, _headers, payload):
            payloads.append(payload)
            return {"choices": [{"finish_reason": "stop", "message": {"content": "可继续聊天"}}]}

        def unsupported(*_args):
            raise TrackerError("外部 API 返回 400：不支持流式", "upstream_http_400", 502)

        planner = AIPlanner(self.root, transport=nonstream, stream_transport=unsupported)
        planner.save_config({"api_key": "fake-secret"})
        self.assertEqual(planner.chat({"message": "你好"})["answer"], "可继续聊天")
        self.assertFalse(payloads[0]["stream"])


if __name__ == "__main__":
    unittest.main()
