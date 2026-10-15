"""Dependency-free local HTTP server for the study tracker."""

from __future__ import annotations

import json
import mimetypes
import os
import re
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

from tracker import ROOT, TrackerError
from plan_library import PlanLibrary
from ai_planner import AIPlanner

UI_PREF_LOCK = threading.RLock()


def read_ui_preferences(data_dir):
    path = Path(data_dir) / "ui_preferences.json"
    with UI_PREF_LOCK:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, ValueError):
            return {}
        except OSError as exc:
            raise TrackerError("无法读取桌面布局偏好", "ui_preferences_error", 500) from exc
    return value if isinstance(value, dict) else {}


def save_ui_preferences(data_dir, value):
    if not isinstance(value, dict):
        raise TrackerError("布局偏好必须是对象")
    unknown = set(value) - {"theme", "navCollapsed", "aiSidebarOpen", "aiSplitWidth", "closedStages"}
    if unknown or value.get("theme", "system") not in ("system", "light", "dark"):
        raise TrackerError("布局偏好字段无效")
    if any(key in value and type(value[key]) is not bool for key in ("navCollapsed", "aiSidebarOpen")):
        raise TrackerError("导航或计划栏状态无效")
    width = value.get("aiSplitWidth", 450)
    if type(width) is not int or not 320 <= width <= 620:
        raise TrackerError("计划栏宽度无效")
    stages = value.get("closedStages", [])
    if (not isinstance(stages, list) or len(stages) > 100 or any(
            not isinstance(item, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", item)
            for item in stages)):
        raise TrackerError("阶段折叠状态无效")
    normalized = {"theme": value.get("theme", "system"),
                  "navCollapsed": value.get("navCollapsed", False),
                  "aiSidebarOpen": value.get("aiSidebarOpen", True),
                  "aiSplitWidth": width, "closedStages": list(dict.fromkeys(stages))}
    path = Path(data_dir) / "ui_preferences.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    with UI_PREF_LOCK:
        fd, temporary = tempfile.mkstemp(prefix=".ui-preferences-", dir=path.parent, text=True)
        try:
            os.chmod(temporary, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(normalized, stream, ensure_ascii=False)
                stream.write("\n")
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
    return normalized


class Handler(BaseHTTPRequestHandler):
    tracker: PlanLibrary
    ai: AIPlanner

    def _send(self, status, data, content_type="application/json; charset=utf-8"):
        body = json.dumps(data, ensure_ascii=False).encode() if content_type.startswith("application/json") else data
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _json(self):
        size = int(self.headers.get("Content-Length", "0"))
        if size < 0 or size > 3_000_000:
            raise TrackerError("请求体过大")
        try:
            value = json.loads(self.rfile.read(size))
        except (ValueError, UnicodeDecodeError):
            raise TrackerError("JSON 格式无效")
        if not isinstance(value, dict):
            raise TrackerError("请求体必须是对象")
        return value

    def _handle(self, method):
        path = urlsplit(self.path).path
        try:
            if path.startswith("/api/ai/") or path == "/api/ui/preferences":
                self._require_ai_local()
            if not path.startswith("/api/"):
                if method != "GET":
                    raise TrackerError("不支持的方法", "method_not_allowed", 405)
                if path == "/":
                    path = "/index.html"
                if path not in ("/index.html", "/style.css", "/app.js", "/ai.js"):
                    raise TrackerError("未找到页面", "not_found", 404)
                file = ROOT / "static" / path.lstrip("/")
                body = file.read_bytes()
                if path == "/index.html":
                    preferences = json.dumps(read_ui_preferences(self.tracker.data_dir), ensure_ascii=False)
                    preferences = preferences.replace("<", "\\u003c")
                    body = body.replace(b"/*__UI_PREFS__*/{}", preferences.encode("utf-8"), 1)
                self._send(200, body, mimetypes.guess_type(file)[0] or "text/plain")
                return
            result = self._dispatch(method, path)
            self._send(200, result)
        except TrackerError as exc:
            self._send(exc.status, {"error": {"code": exc.code, "message": str(exc)}})
        except (KeyError, TypeError, ValueError) as exc:
            self._send(400, {"error": {"code": "invalid_input", "message": str(exc)}})
        except Exception:
            self.log_exception()
            self._send(500, {"error": {"code": "internal_error", "message": "服务器处理失败，请查看终端日志"}})

    def log_exception(self):
        import traceback
        traceback.print_exc()

    def _require_ai_local(self):
        """Keep credentials and paid AI calls bound to this local app origin."""
        host = urlsplit("http://" + self.headers.get("Host", ""))
        local_names = {"127.0.0.1", "localhost"}
        if host.hostname not in local_names or host.port != self.server.server_port:
            raise TrackerError("AI 功能只允许从本机访问", "forbidden_origin", 403)
        origin = self.headers.get("Origin")
        if origin:
            source = urlsplit(origin)
            if (source.scheme != "http" or source.hostname != host.hostname
                    or source.port != host.port):
                raise TrackerError("请求来源不匹配", "forbidden_origin", 403)

    def _dispatch(self, method, path):
        if path.startswith("/api/ai/"):
            return self._dispatch_ai(method, path)
        if path == "/api/ui/preferences":
            if method == "GET":
                return read_ui_preferences(self.tracker.data_dir)
            if method == "PUT":
                return save_ui_preferences(self.tracker.data_dir, self._json())
            raise TrackerError("不支持的方法", "method_not_allowed", 405)
        with self.tracker._lock:
            return self._dispatch_unlocked(method, path)

    def _dispatch_ai(self, method, path):
        ai = self.ai
        if method == "GET":
            if path == "/api/ai/state": return ai.state()
            if path == "/api/ai/plan-draft": return ai.plan_draft_state()
            if path == "/api/ai/draft": return ai.draft()
            if path == "/api/ai/activity": return ai.activity()
        if method == "POST":
            if path == "/api/ai/config": return ai.save_config(self._json())
            if path == "/api/ai/search/test": return ai.test_search(self._json().get("provider"))
            if path == "/api/ai/cancel": return ai.cancel()
            if path == "/api/ai/chat": return ai.chat(self._json())
            if path == "/api/ai/research": return ai.research()
            if path == "/api/ai/clear": return ai.clear_history()
            if path == "/api/ai/generate": return ai.start_generation(self._json())
            if path == "/api/ai/plan-draft/confirm":
                return ai.confirm_import(self._json(), self.tracker)
            if path == "/api/ai/draft/apply":
                draft_id = self._json().get("id")
                with self.tracker._lock:
                    draft = ai.draft()
                    if draft_id != draft["id"]:
                        raise TrackerError("草稿已变更，请重新预览", "stale_draft", 409)
                    return self.tracker.apply_plan(draft["plan"])
        raise TrackerError("未找到 AI API 或不支持的方法", "not_found", 404)

    def _dispatch_unlocked(self, method, path):
        t = self.tracker
        if method == "GET":
            if path == "/api/bootstrap": return t.bootstrap()
            if path == "/api/plans": return t.list_plans()
            if path == "/api/plans/template":
                return json.loads((ROOT / "examples" / "sample_plan_v3.json").read_text(encoding="utf-8"))
            if path == "/api/days": return t.list_days()
            if path == "/api/today":
                key = t.bootstrap()["today_id"]
                return {"today_id": key, "day": t.get_day(key) if key else None}
            if path == "/api/sessions/active": return {"session": t.active_session()}
            if path == "/api/import/preview": return t.import_preview()
            if path == "/api/export": return t.export()
            match = re.fullmatch(r"/api/days/(W\d\dD\d\d)", path)
            if match: return t.get_day(match.group(1))
        if method == "PATCH":
            if path == "/api/settings": return t.update_settings(self._json())
            match = re.fullmatch(r"/api/days/(W\d\dD\d\d)/(budget|progress)", path)
            if match:
                value = self._json()
                return t.update_budget(match.group(1), value) if match.group(2) == "budget" else t.update_progress(match.group(1), **value)
        if method == "POST":
            if path == "/api/plans/import/preview": return t.preview_plan(self._json())
            if path == "/api/plans/import/apply": return t.apply_plan(self._json())
            if path == "/api/plans/select": return t.select_plan(self._json()["plan_id"])
            if path == "/api/import/apply": return t.import_curriculum()
            if path == "/api/sessions/start": return t.start_session(self._json()["day_id"])
            if path == "/api/sessions/stop": return t.stop_session()
            if path == "/api/sessions/manual":
                value = self._json()
                return t.manual_session(value["day_id"], value)
            if path == "/api/restore/preview": return t.restore_preview(self._json())
            if path == "/api/restore/apply": return t.restore(self._json())
            match = re.fullmatch(r"/api/days/(W\d\dD\d\d)/evidence", path)
            if match: return t.add_evidence(match.group(1), self._json())
            match = re.fullmatch(r"/api/days/(W\d\dD\d\d)/acceptance/([A-Za-z0-9]+)/review", path)
            if match: return t.review(match.group(1), match.group(2), self._json())
            match = re.fullmatch(r"/api/days/(W\d\dD\d\d)/(readings|exercises)/([^/]+)/toggle", path)
            if match:
                kind = "reading" if match.group(2) == "readings" else "exercise"
                return t.toggle(match.group(1), kind, unquote(match.group(3)))
        if method == "PUT":
            match = re.fullmatch(r"/api/days/(W\d\dD\d\d)/reflection", path)
            if match: return t.save_reflection(match.group(1), self._json())
        raise TrackerError("未找到 API 或不支持的方法", "not_found", 404)

    def do_GET(self): self._handle("GET")
    def do_POST(self): self._handle("POST")
    def do_PATCH(self): self._handle("PATCH")
    def do_PUT(self): self._handle("PUT")


def run(host="127.0.0.1", port=8765, data_dir=None):
    Handler.tracker = PlanLibrary(data_dir=data_dir)
    Handler.ai = AIPlanner(Handler.tracker.data_dir)
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"StudyWaypoint: http://{host}:{server.server_port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    run(os.getenv("TRACKER_HOST", "127.0.0.1"), int(os.getenv("TRACKER_PORT", "8765")))
