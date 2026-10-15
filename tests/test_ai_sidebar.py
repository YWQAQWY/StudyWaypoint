"""Render the real AI sidebar in the desktop JavaScript engine when available."""

import json
import unittest
from pathlib import Path


class AISidebarTests(unittest.TestCase):
    def test_structured_draft_renders_from_state(self):
        try:
            import gi
            gi.require_version("JavaScriptCore", "4.1")
            from gi.repository import JavaScriptCore
        except (ImportError, ValueError):
            self.skipTest("JavaScriptCore 4.1 is not installed")
        ctx = JavaScriptCore.Context()
        ctx.evaluate("const document={addEventListener:()=>{},querySelector:()=>null};"
                     "const esc=x=>String(x);const hero=(a,b,c)=>a+b+c;"
                     "const state={bootstrap:{plans:[]}};", -1)
        ctx.evaluate((Path(__file__).resolve().parents[1] / "static" / "ai.js").read_text(), -1)
        self.assertIsNone(ctx.get_exception())
        config = {"enabled": True, "model": "fake", "base_url": "https://example.org",
                  "reasoning_effort": "default", "third_party_enabled": False, "searxng_url": "",
                  "brave_key_configured": False, "key_storage": "/tmp/config"}
        draft = {"draft_id": "draft", "revision": 2, "status": "READY_FOR_CONFIRMATION",
                 "title": "机器学习", "learning_goal": "完成项目", "weeks": 8,
                 "daily_hours": [2] * 7, "weekly_hours": 14, "stages": [{"id": "s1",
                 "title": "建模", "tasks": [{"id": "t1", "title": "训练模型", "resources": []}]}],
                 "resources": [], "unresolved_questions": [], "validation_warnings": []}
        ctx.evaluate("aiState.data=" + json.dumps({"config": config, "history": {"messages": [],
                     "sources": []}, "draft": None, "job": None}) + ";", -1)
        ctx.evaluate("aiState.planDraft=" + json.dumps(draft, ensure_ascii=False) + ";", -1)
        html = ctx.evaluate("aiView()", -1).to_string()
        self.assertIsNone(ctx.get_exception())
        self.assertIn("训练模型", html)
        self.assertIn("确认计划并导入", html)
        self.assertIn("修订 2", html)
        self.assertIn("data-plan-stage", html)
        self.assertIn('class="ai-resizer" role="separator"', html)
        self.assertIn('class="plan-confirm-bar"', html)
        self.assertIn('data-draft-id="draft"', html)
        self.assertNotIn('id="ai-config-form"', html)
        ctx.evaluate("aiState.partialText='正在整理回答';", -1)
        self.assertIn("AI · 正在回复", ctx.evaluate("aiView()", -1).to_string())
        self.assertIn("正在整理回答", ctx.evaluate("aiView()", -1).to_string())
        self.assertIn('id="ai-config-form"', ctx.evaluate("aiConfigPanel()", -1).to_string())


if __name__ == "__main__":
    unittest.main()
