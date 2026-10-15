"""Private, versioned editing state for the existing AI planning conversation.

This is deliberately separate from the importable v3 curriculum JSON.
"""

from __future__ import annotations

import copy
import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from tracker import PLAN_ID, TrackerError


ACTIVE = {"GENERATING_JSON", "VALIDATING", "IMPORTING"}
STATUSES = {"IDLE", "COLLECTING_REQUIREMENTS", "DRAFTING", "REFINING",
            "READY_FOR_CONFIRMATION", *ACTIVE, "COMPLETED", "ERROR", "CANCELLED"}
SET_FIELDS = {"title", "learning_goal", "plan_id", "weeks", "daily_hours",
              "weekly_hours", "language", "platform", "foundation"}


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _text(value, label, limit=300):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise TrackerError(f"{label} 必须是非空文字且不超过 {limit} 字")
    return value.strip()


def _save(path: Path, value: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    os.chmod(temp, 0o600)
    os.replace(temp, path)


def _new(conversation_id):
    return {"draft_id": uuid4().hex, "conversation_id": conversation_id, "revision": 0,
            "status": "COLLECTING_REQUIREMENTS", "title": None, "learning_goal": None,
            "plan_id": None, "weeks": None, "daily_hours": None, "weekly_hours": None,
            "language": None, "platform": None, "foundation": None,
            "user_constraints": [], "stages": [], "resources": [],
            "unresolved_questions": [], "validation_warnings": [], "last_changed_ids": [],
            "changes": [], "updated_at": now(), "error": None,
            "confirmation_id": None, "confirmed_revision": None,
            "confirmed_snapshot": None, "import_result": None}


def _hours_from_week(weekly):
    total = round(weekly * 60)
    base, remainder = divmod(total, 7)
    if base < 1 or total > 7 * 1440:
        raise TrackerError("每周学习时间须足以为七天各安排至少一分钟，且每日不超过 24 小时")
    return [round((base + (1 if day < remainder else 0)) / 60, 6) for day in range(7)]


def blockers(draft):
    missing = []
    if not draft.get("learning_goal"):
        missing.append("学习目标待确认")
    if not draft.get("title"):
        missing.append("计划名称待确认")
    if not draft.get("weeks"):
        missing.append("学习周期待确认")
    if not draft.get("daily_hours"):
        missing.append("学习时间待确认")
    if not draft.get("stages") or any(stage.get("title") == "待确认" or not stage.get("tasks")
                                      or any(task.get("title") == "待确认" for task in stage["tasks"])
                                      for stage in draft.get("stages", [])):
        missing.append("学习阶段或任务尚不完整")
    missing.extend(q["text"] for q in draft.get("unresolved_questions", []) if q.get("blocking"))
    return list(dict.fromkeys(missing))


class PlanDraftStore:
    def __init__(self, path):
        self.path = Path(path)
        self.lock = threading.RLock()
        if self.path.exists():
            data = self._read()
            if data.get("status") in ACTIVE or data.get("status") == "DRAFTING":
                data["status"] = "ERROR"
                data["error"] = "上次操作中断；草稿已保留，可重试或继续修改"
                _save(self.path, data)

    def _read(self):
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise TrackerError(f"无法读取规划草稿：{exc}") from exc
        if not isinstance(data, dict) or data.get("status") not in STATUSES:
            raise TrackerError("规划草稿格式无效")
        return data

    def get(self):
        with self.lock:
            return copy.deepcopy(self._read()) if self.path.exists() else {"status": "IDLE", "revision": 0}

    def clear(self):
        with self.lock:
            self.path.unlink(missing_ok=True)

    def begin(self, conversation_id):
        with self.lock:
            data = self._read() if self.path.exists() else _new(conversation_id)
            if data["conversation_id"] != conversation_id:
                raise TrackerError("规划草稿与当前对话不匹配；请先清空旧对话", "conversation_mismatch", 409)
            if data["status"] in ACTIVE:
                raise TrackerError("正在确认或导入计划，暂不能修改", "draft_busy", 409)
            data["status"] = "DRAFTING"
            data["error"] = None
            data["updated_at"] = now()
            _save(self.path, data)
            return copy.deepcopy(data)

    def apply(self, conversation_id, base_revision, patch):
        if not isinstance(patch, dict):
            raise TrackerError("结构化草稿更新必须是 JSON 对象")
        with self.lock:
            current = self._read() if self.path.exists() else _new(conversation_id)
            if current["conversation_id"] != conversation_id:
                raise TrackerError("草稿与当前对话不匹配", "conversation_mismatch", 409)
            if current["revision"] != base_revision:
                raise TrackerError("草稿版本已变化，请重新读取后修改", "stale_revision", 409)
            if current["status"] in ACTIVE:
                raise TrackerError("正在确认或导入计划", "draft_busy", 409)
            updated = copy.deepcopy(current)
            changed = []
            values = patch.get("set", {})
            if not isinstance(values, dict) or set(values) - SET_FIELDS:
                raise TrackerError("草稿更新包含未知字段")
            if "weekly_hours" in values and "daily_hours" in values and values["weekly_hours"] is not None \
                    and values["daily_hours"] is not None:
                provided = values["daily_hours"]
                if (type(values["weekly_hours"]) not in (int, float)
                        or not isinstance(provided, list) or len(provided) != 7
                        or any(type(hour) not in (int, float) for hour in provided)
                        or abs(round(values["weekly_hours"] * 60) -
                               sum(round(hour * 60) for hour in provided)) > 1):
                    raise TrackerError("每周与每日学习时间相互冲突")
            old_weekly = updated.get("weekly_hours")
            for key, value in values.items():
                if value is None:
                    updated[key] = None
                elif key in ("title", "learning_goal", "language", "platform", "foundation"):
                    updated[key] = _text(value, key, 2000 if key == "learning_goal" else 300)
                elif key == "plan_id":
                    if not isinstance(value, str) or not PLAN_ID.fullmatch(value):
                        raise TrackerError("plan_id 格式无效")
                    updated[key] = value
                elif key == "weeks":
                    if type(value) is not int or not 1 <= value <= 52:
                        raise TrackerError("周数须为 1–52")
                    updated[key] = value
                elif key == "weekly_hours":
                    if type(value) not in (int, float) or not 0 < value <= 168:
                        raise TrackerError("每周小时数无效")
                    updated[key] = value
                    updated["daily_hours"] = _hours_from_week(value)
                elif key == "daily_hours":
                    if (not isinstance(value, list) or len(value) != 7 or any(
                            type(hour) not in (int, float) or not 0 < hour <= 24
                            or round(hour * 60) < 1 for hour in value)):
                        raise TrackerError("每日小时数需为七个有效数字")
                    updated[key] = value
                    updated["weekly_hours"] = round(sum(round(hour * 60) for hour in value) / 60, 6)
                changed.append(key)
            if old_weekly and updated.get("weekly_hours") and old_weekly != updated["weekly_hours"]:
                ratio = updated["weekly_hours"] / old_weekly
                for stage in updated["stages"]:
                    if stage.get("estimated_hours"):
                        stage["estimated_hours"] = round(stage["estimated_hours"] * ratio, 2)
                        changed.append(stage["id"])
                    for task in stage["tasks"]:
                        if task.get("estimated_minutes"):
                            task["estimated_minutes"] = max(1, round(task["estimated_minutes"] * ratio))
                            changed.append(task["id"])
            additions = patch.get("constraints_add", [])
            if not isinstance(additions, list) or len(additions) > 10:
                raise TrackerError("用户约束更新无效")
            for item in additions:
                text = _text(item, "用户约束", 500)
                if text not in updated["user_constraints"]:
                    updated["user_constraints"].append(text)
            updated["user_constraints"] = updated["user_constraints"][-30:]
            stages = patch.get("upsert_stages", [])
            removed = patch.get("remove_stage_ids", [])
            if not isinstance(stages, list) or len(stages) > 12 or not isinstance(removed, list):
                raise TrackerError("阶段更新无效")
            if any(not isinstance(id_, str) for id_ in removed):
                raise TrackerError("移除阶段 ID 无效")
            for id_ in removed:
                if id_ not in {stage["id"] for stage in updated["stages"]}:
                    raise TrackerError("不能移除不存在的阶段")
            updated["stages"] = [stage for stage in updated["stages"] if stage["id"] not in removed]
            changed.extend(removed)
            for incoming in stages:
                if not isinstance(incoming, dict):
                    raise TrackerError("阶段必须是对象")
                id_ = incoming.get("id")
                stage = next((s for s in updated["stages"] if s["id"] == id_), None) if id_ else None
                if id_ and not stage:
                    raise TrackerError("阶段 ID 不存在；新阶段请省略 ID")
                if not stage:
                    stage = {"id": "s-" + uuid4().hex[:12], "title": "待确认", "summary": None,
                             "estimated_hours": None, "tasks": []}
                    updated["stages"].append(stage)
                for key in ("title", "summary"):
                    if key in incoming:
                        stage[key] = _text(incoming[key], key, 1000 if key == "summary" else 200)
                if "estimated_hours" in incoming:
                    hours = incoming["estimated_hours"]
                    if hours is not None and (type(hours) not in (int, float) or not 0 < hours <= 2000):
                        raise TrackerError("阶段预计小时数无效")
                    stage["estimated_hours"] = hours
                tasks = incoming.get("upsert_tasks", [])
                removed_tasks = incoming.get("remove_task_ids", [])
                if not isinstance(tasks, list) or len(tasks) > 20 or not isinstance(removed_tasks, list):
                    raise TrackerError("任务更新无效")
                for task_id in removed_tasks:
                    if task_id not in {task["id"] for task in stage["tasks"]}:
                        raise TrackerError("不能移除不存在的任务")
                stage["tasks"] = [task for task in stage["tasks"] if task["id"] not in removed_tasks]
                changed.extend(removed_tasks)
                for incoming_task in tasks:
                    if not isinstance(incoming_task, dict):
                        raise TrackerError("任务必须是对象")
                    task_id = incoming_task.get("id")
                    task = next((t for t in stage["tasks"] if t["id"] == task_id), None) if task_id else None
                    if task_id and not task:
                        raise TrackerError("任务 ID 不存在；新任务请省略 ID")
                    if not task:
                        task = {"id": "t-" + uuid4().hex[:12], "title": "待确认",
                                "description": None, "estimated_minutes": None, "resources": []}
                        stage["tasks"].append(task)
                    old_title = task["title"]
                    for key in ("title", "description"):
                        if key in incoming_task:
                            task[key] = _text(incoming_task[key], key, 1000 if key == "description" else 200)
                    if task["title"] != old_title:
                        task["resources"] = []
                    if "estimated_minutes" in incoming_task:
                        minutes = incoming_task["estimated_minutes"]
                        if minutes is not None and (type(minutes) is not int or not 1 <= minutes <= 100000):
                            raise TrackerError("任务预计分钟数无效")
                        task["estimated_minutes"] = minutes
                    changed.append(task["id"])
                changed.append(stage["id"])
            if len(updated["stages"]) > 20 or any(len(s["tasks"]) > 30 for s in updated["stages"]):
                raise TrackerError("草稿阶段或任务过多")
            questions = patch.get("unresolved_questions", updated["unresolved_questions"])
            if not isinstance(questions, list) or len(questions) > 12:
                raise TrackerError("待确认问题格式无效")
            normalized = []
            for question in questions:
                if isinstance(question, str):
                    normalized.append({"text": _text(question, "待确认问题"), "blocking": True})
                elif isinstance(question, dict) and type(question.get("blocking")) is bool:
                    normalized.append({"text": _text(question.get("text"), "待确认问题"),
                                       "blocking": question["blocking"]})
                else:
                    raise TrackerError("待确认问题格式无效")
            updated["unresolved_questions"] = normalized
            warnings = patch.get("validation_warnings", [])
            if not isinstance(warnings, list) or len(warnings) > 12:
                raise TrackerError("建议提示格式无效")
            updated["validation_warnings"] = [_text(w, "建议提示", 300) for w in warnings]
            updated["revision"] += 1
            updated["last_changed_ids"] = list(dict.fromkeys(changed))[:50]
            updated["status"] = "READY_FOR_CONFIRMATION" if not blockers(updated) else "REFINING"
            updated["error"] = None
            updated["confirmation_id"] = None
            updated["confirmed_revision"] = None
            updated["confirmed_snapshot"] = None
            updated["import_result"] = None
            updated["updated_at"] = now()
            updated["changes"] = (updated["changes"] + [{"revision": updated["revision"],
                "ids": updated["last_changed_ids"], "rationale": str(patch.get("rationale", ""))[:500],
                "at": updated["updated_at"]}])[-30:]
            _save(self.path, updated)
            return copy.deepcopy(updated)

    def no_change(self, conversation_id, base_revision):
        with self.lock:
            data = self._read()
            if data["conversation_id"] != conversation_id or data["revision"] != base_revision:
                raise TrackerError("草稿版本已变化", "stale_revision", 409)
            data["status"] = ("COMPLETED" if data.get("import_result") else
                              "READY_FOR_CONFIRMATION" if not blockers(data) else "REFINING")
            data["updated_at"] = now()
            _save(self.path, data)
            return copy.deepcopy(data)

    def enrich(self, conversation_id, resources):
        with self.lock:
            if not self.path.exists():
                return self.get()
            data = self._read()
            if data["conversation_id"] != conversation_id or data["status"] in ACTIVE | {"COMPLETED"}:
                return copy.deepcopy(data)
            existing = {r["url"]: r for r in data["resources"]}
            changed = []
            for resource in resources:
                if not isinstance(resource, dict) or not resource.get("provider") or not resource.get("url"):
                    continue
                item = {key: resource.get(key) for key in
                        ("title", "url", "snippet", "provider", "resource_type", "verification_status")}
                if existing.get(item["url"]) == item:
                    continue
                existing[item["url"]] = item
                changed.append(item["url"])
                for stage in data["stages"]:
                    for task in stage["tasks"]:
                        topic = task["title"].lower()
                        if topic != "待确认" and topic in (str(item["title"]) + " " + str(item["snippet"])).lower():
                            if item["url"] not in task["resources"]:
                                task["resources"].append(item["url"])
                                changed.append(task["id"])
            if changed:
                data["resources"] = list(existing.values())[-80:]
                data["revision"] += 1
                data["last_changed_ids"] = changed[:50]
                data["updated_at"] = now()
                data["changes"] = (data["changes"] + [{"revision": data["revision"],
                    "ids": changed[:50], "rationale": "补充可追溯学习资源", "at": data["updated_at"]}])[-30:]
                _save(self.path, data)
            return copy.deepcopy(data)

    def set_error(self, message, cancelled=False):
        with self.lock:
            if not self.path.exists():
                return self.get()
            data = self._read()
            data["status"] = "CANCELLED" if cancelled else "ERROR"
            data["error"] = str(message)[:500]
            data["updated_at"] = now()
            _save(self.path, data)
            return copy.deepcopy(data)

    def confirm(self, draft_id, revision, confirmation_id):
        with self.lock:
            data = self._read() if self.path.exists() else None
            if not data or data["draft_id"] != draft_id:
                raise TrackerError("规划草稿不存在或已变化", "stale_draft", 409)
            if not isinstance(confirmation_id, str) or len(confirmation_id) < 12 or len(confirmation_id) > 100:
                raise TrackerError("确认标识无效")
            if data["confirmation_id"] == confirmation_id and data["confirmed_revision"] == revision:
                if data["status"] in ACTIVE or data["status"] == "COMPLETED":
                    return copy.deepcopy(data), False
                if data["status"] in ("ERROR", "CANCELLED"):
                    data["status"] = "GENERATING_JSON"
                    data["error"] = None
                    data["updated_at"] = now()
                    _save(self.path, data)
                    return copy.deepcopy(data), True
            if data["revision"] != revision:
                raise TrackerError("草稿版本已变化，请检查最新内容后再次确认", "stale_revision", 409)
            if data["status"] in ACTIVE:
                raise TrackerError("确认任务仍在执行", "draft_busy", 409)
            issues = blockers(data)
            if issues:
                raise TrackerError("确认前需解决：" + "；".join(issues[:5]), "draft_incomplete", 409)
            data["confirmed_snapshot"] = {key: copy.deepcopy(data[key]) for key in
                ("draft_id", "conversation_id", "revision", "title", "learning_goal", "plan_id",
                 "weeks", "daily_hours", "weekly_hours", "language", "platform", "foundation",
                 "user_constraints", "stages", "resources")}
            data["confirmation_id"] = confirmation_id
            data["confirmed_revision"] = revision
            data["import_result"] = None
            data["status"] = "GENERATING_JSON"
            data["error"] = None
            data["updated_at"] = now()
            _save(self.path, data)
            return copy.deepcopy(data), True

    def advance(self, status):
        if status not in ACTIVE | {"COMPLETED"}:
            raise TrackerError("未知规划状态")
        with self.lock:
            data = self._read()
            data["status"] = status
            data["updated_at"] = now()
            _save(self.path, data)
            return copy.deepcopy(data)

    def complete(self, result):
        with self.lock:
            data = self._read()
            data["status"] = "COMPLETED"
            data["import_result"] = result
            data["error"] = None
            data["updated_at"] = now()
            _save(self.path, data)
            return copy.deepcopy(data)
