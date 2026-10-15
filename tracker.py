"""Local-first study tracker. Curriculum content and user progress stay separate."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
from uuid import uuid4
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

ROOT = Path(__file__).resolve().parent
CURRICULUM = ROOT / "examples" / "sample_plan_v3.json"
STATUSES = {"not_started", "in_progress", "submitted", "passed", "failed", "deferred", "skipped"}
EVIDENCE_TYPES = {"text", "url", "source_file", "git_commit", "test_log", "screenshot", "notes", "benchmark_result"}
DAY_ID = re.compile(r"W([0-4][0-9]|5[0-2])D(0[1-7])\Z")
PLAN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{2,79}\Z")


class TrackerError(Exception):
    def __init__(self, message: str, code: str = "invalid_input", status: int = 400):
        super().__init__(message)
        self.code, self.status = code, status


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds")


def validate_curriculum(data: dict) -> dict:
    errors = []
    if not isinstance(data, dict):
        return {"valid": False, "errors": ["计划文件必须是 JSON 对象"], "days": 0, "minutes": 0}
    version = data.get("schema_version")
    if not isinstance(version, str) or not version.startswith("3."):
        errors.append("schema_version 必须为 3.x")
    plan_id = data.get("plan_id")
    if not isinstance(plan_id, str) or not PLAN_ID.fullmatch(plan_id):
        errors.append("plan_id 必须为 3–80 位英文字母、数字、点、下划线或短横线")
    weeks = data.get("weeks")
    if type(weeks) is not int or not 1 <= weeks <= 52:
        errors.append("weeks 必须是 1–52 的整数")
        weeks = 0
    if data.get("days_per_week") != 7:
        errors.append("days_per_week 必须为 7")
    daily_hours = data.get("daily_hours")
    if not isinstance(daily_hours, list) or len(daily_hours) != 7 or any(
        not isinstance(h, (int, float)) or isinstance(h, bool) or not 0 <= h <= 24 for h in daily_hours
    ):
        errors.append("daily_hours 必须为 7 个 0–24 的数字")
        daily_hours = [0] * 7
    themes = data.get("weekly_themes")
    if not isinstance(themes, list) or len(themes) != weeks or any(not isinstance(t, str) or not t.strip() for t in themes):
        errors.append("weekly_themes 数量必须与 weeks 一致，且每项非空")
    if not isinstance(data.get("curriculum_version"), str) or not data["curriculum_version"].strip():
        errors.append("缺少 curriculum_version")
    days = data.get("days")
    if not isinstance(days, list):
        errors.append("days 必须是数组")
        days = []
    if len(days) != weeks * 7:
        errors.append(f"days 应有 {weeks * 7} 天，实际 {len(days)} 天")
    seen, exercise_ids, acceptance_ids = set(), set(), set()
    total_minutes = 0
    for day in days:
        if not isinstance(day, dict):
            errors.append("days 中有非对象项目")
            continue
        key = day.get("id")
        week, weekday = day.get("week"), day.get("day")
        if not isinstance(key, str) or not DAY_ID.fullmatch(key) or key in seen:
            errors.append(f"重复或无效的日 ID: {key}")
        if type(week) is not int or type(weekday) is not int or not 1 <= week <= weeks or not 1 <= weekday <= 7 or key != f"W{week:02d}D{weekday:02d}":
            errors.append(f"{key} 的 week/day 与 ID 不一致")
        seen.add(key)
        planned = day.get("planned_minutes")
        if type(planned) is not int or not 1 <= planned <= 1440:
            errors.append(f"{key} planned_minutes 必须是 1–1440 的整数")
            planned = 0
        total_minutes += planned
        if type(weekday) is int and 1 <= weekday <= 7 and planned != round(daily_hours[weekday - 1] * 60):
            errors.append(f"{key} planned_minutes 与 daily_hours 不一致")
        budget = day.get("time_budget")
        budget_keys = ("theory_minutes", "practice_minutes", "verification_minutes")
        if not isinstance(budget, dict) or any(type(budget.get(k)) is not int or budget[k] < 0 for k in budget_keys) or sum(budget[k] for k in budget_keys) != planned:
            errors.append(f"{key} 分钟预算不匹配")
        for field in ("title", "course_section", "track"):
            if not isinstance(day.get(field), str) or not day[field].strip():
                errors.append(f"{key} 缺少 {field}")
        for field in ("course_readings", "coding_exercises", "acceptance_tests", "deliverables"):
            if not isinstance(day.get(field), list) or not day[field]:
                errors.append(f"{key} 缺少 {field}")
        for reading in day.get("course_readings", []) if isinstance(day.get("course_readings"), list) else []:
            if not isinstance(reading, dict) or not reading.get("title") or not isinstance(reading.get("url"), str):
                errors.append(f"{key} 阅读资源格式无效")
                continue
            parsed = urlparse(reading["url"])
            if parsed.scheme not in ("http", "https") or not parsed.netloc:
                errors.append(f"{key} 无效阅读链接")
        for exercise in day.get("coding_exercises", []) if isinstance(day.get("coding_exercises"), list) else []:
            if not isinstance(exercise, dict) or not isinstance(exercise.get("id"), str) or not exercise.get("title") or not exercise.get("instructions") or not isinstance(exercise.get("expected_artifacts"), list):
                errors.append(f"{key} 练习格式无效")
                continue
            if exercise["id"] in exercise_ids:
                errors.append(f"重复练习 ID: {exercise['id']}")
            exercise_ids.add(exercise["id"])
        for criterion in day.get("acceptance_tests", []) if isinstance(day.get("acceptance_tests"), list) else []:
            if not isinstance(criterion, dict) or not isinstance(criterion.get("id"), str) or not criterion.get("assertion") or type(criterion.get("evidence_required")) is not bool:
                errors.append(f"{key} 验收格式无效")
                continue
            if criterion["id"] in acceptance_ids:
                errors.append(f"重复验收 ID: {criterion['id']}")
            acceptance_ids.add(criterion["id"])
    leetcode = data.get("leetcode_weekly")
    if not isinstance(leetcode, dict):
        leetcode = {}
    for week in range(1, weeks + 1):
        subset = [d for d in days if isinstance(d, dict) and d.get("week") == week]
        if len(subset) != 7 or {d.get("day") for d in subset} != set(range(1, 8)):
            errors.append(f"第 {week} 周日期不完整")
        questions = leetcode.get(str(week), [])
        if not isinstance(questions, list) or len(questions) < 2 or any(
            not isinstance(q, dict) or not q.get("title") or not isinstance(q.get("url"), str) or
            urlparse(q["url"]).scheme not in ("http", "https") or not urlparse(q["url"]).netloc
            for q in questions
        ):
            errors.append(f"第 {week} 周 LeetCode 至少两题且需有效 URL")
    hours = data.get("total_planned_hours")
    if not isinstance(hours, (int, float)) or isinstance(hours, bool) or abs(total_minutes - hours * 60) > 0.01:
        errors.append("total_planned_hours 与每日分钟总和不一致")
    return {"valid": not errors, "errors": errors[:50], "days": len(days), "minutes": total_minutes}


class Tracker:
    def __init__(self, data_dir: str | Path | None = None, curriculum_path: str | Path = CURRICULUM):
        self.data_dir = Path(data_dir or os.getenv("TRACKER_DATA_DIR", ROOT / "data"))
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.data_dir / "tracker.sqlite3"
        self.curriculum_path = Path(curriculum_path)
        self._create_schema()
        self.import_curriculum()

    def connect(self):
        db = sqlite3.connect(self.db_path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA journal_mode=WAL")
        return db

    def _create_schema(self):
        with self.connect() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS curriculum_day (
              id TEXT PRIMARY KEY, week INTEGER NOT NULL, day INTEGER NOT NULL,
              payload TEXT NOT NULL, sha256 TEXT NOT NULL, version TEXT NOT NULL,
              is_active INTEGER NOT NULL DEFAULT 1
            );
            CREATE INDEX IF NOT EXISTS ix_curriculum_week ON curriculum_day(week, day);
            CREATE TABLE IF NOT EXISTS task_progress (
              day_id TEXT PRIMARY KEY REFERENCES curriculum_day(id), status TEXT NOT NULL DEFAULT 'not_started',
              note TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS ix_task_status ON task_progress(status);
            CREATE TABLE IF NOT EXISTS reading_progress (
              item_id TEXT PRIMARY KEY, day_id TEXT NOT NULL REFERENCES curriculum_day(id), done INTEGER NOT NULL,
              updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS exercise_progress (
              item_id TEXT PRIMARY KEY, day_id TEXT NOT NULL REFERENCES curriculum_day(id), done INTEGER NOT NULL,
              updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS evidence (
              id INTEGER PRIMARY KEY AUTOINCREMENT, day_id TEXT NOT NULL REFERENCES curriculum_day(id),
              criterion_id TEXT, type TEXT NOT NULL, content TEXT NOT NULL, created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS ix_evidence_day ON evidence(day_id);
            CREATE TABLE IF NOT EXISTS acceptance_review (
              criterion_id TEXT PRIMARY KEY, day_id TEXT NOT NULL REFERENCES curriculum_day(id),
              status TEXT NOT NULL, evidence_id INTEGER REFERENCES evidence(id),
              note TEXT NOT NULL DEFAULT '', reviewed_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS study_session (
              id INTEGER PRIMARY KEY AUTOINCREMENT, day_id TEXT NOT NULL REFERENCES curriculum_day(id),
              started_at TEXT NOT NULL, ended_at TEXT, duration_seconds INTEGER,
              source TEXT NOT NULL, note TEXT NOT NULL DEFAULT ''
            );
            CREATE UNIQUE INDEX IF NOT EXISTS ix_one_active_session ON study_session((1)) WHERE ended_at IS NULL;
            CREATE INDEX IF NOT EXISTS ix_session_day ON study_session(day_id);
            CREATE TABLE IF NOT EXISTS day_budget (
              day_id TEXT PRIMARY KEY REFERENCES curriculum_day(id), theory_minutes INTEGER NOT NULL,
              practice_minutes INTEGER NOT NULL, verification_minutes INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS reflection (
              day_id TEXT PRIMARY KEY REFERENCES curriculum_day(id), achievements TEXT NOT NULL,
              tests TEXT NOT NULL, blockers TEXT NOT NULL, tomorrow TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS plan_change (
              id INTEGER PRIMARY KEY AUTOINCREMENT, entity TEXT NOT NULL, entity_id TEXT NOT NULL,
              old_value TEXT, new_value TEXT NOT NULL, reason TEXT NOT NULL, changed_at TEXT NOT NULL
            );
            """)
            db.execute("INSERT OR IGNORE INTO settings VALUES ('timezone','Asia/Shanghai')")
            db.execute("INSERT OR IGNORE INTO settings VALUES ('start_date','')")
            columns = {row["name"] for row in db.execute("PRAGMA table_info(curriculum_day)")}
            if "is_active" not in columns:
                db.execute("ALTER TABLE curriculum_day ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1")

    def _source(self):
        data = json.loads(self.curriculum_path.read_text(encoding="utf-8"))
        result = validate_curriculum(data)
        if not result["valid"]:
            raise TrackerError("课程校验失败: " + "; ".join(result["errors"]), "invalid_curriculum")
        return data

    def import_preview(self, data=None):
        data = data if data is not None else self._source()
        result = validate_curriculum(data)
        if not result["valid"]:
            raise TrackerError("课程校验失败: " + "; ".join(result["errors"]), "invalid_curriculum")
        with self.connect() as db:
            old = {r["id"]: r["sha256"] for r in db.execute("SELECT id, sha256 FROM curriculum_day WHERE is_active=1")}
        changed, added = [], []
        for day in data["days"]:
            digest = hashlib.sha256(json.dumps(day, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
            if day["id"] not in old:
                added.append(day["id"])
            elif old[day["id"]] != digest:
                changed.append(day["id"])
        return {"version": data["curriculum_version"], "added": added, "changed": changed,
                "unchanged": len(data["days"]) - len(added) - len(changed),
                "removed": sorted(set(old) - {d["id"] for d in data["days"]})}

    def import_curriculum(self, data=None):
        data = data if data is not None else self._source()
        preview = self.import_preview(data)
        with self.connect() as db:
            db.execute("UPDATE curriculum_day SET is_active=0")
            for day in data["days"]:
                payload = json.dumps(day, ensure_ascii=False, sort_keys=True)
                digest = hashlib.sha256(payload.encode()).hexdigest()
                db.execute("""INSERT INTO curriculum_day(id,week,day,payload,sha256,version,is_active)
                   VALUES (?,?,?,?,?,?,1) ON CONFLICT(id) DO UPDATE SET week=excluded.week,
                   day=excluded.day,payload=excluded.payload,sha256=excluded.sha256,
                   version=excluded.version,is_active=1""",
                   (day["id"], day["week"], day["day"], payload, digest, data["curriculum_version"]))
        return preview

    def settings(self):
        with self.connect() as db:
            return {r["key"]: r["value"] for r in db.execute("SELECT * FROM settings")}

    def update_settings(self, values: dict):
        if not values or set(values) - {"start_date", "timezone"}:
            raise TrackerError("仅可修改开始日期和时区")
        if "start_date" in values and values["start_date"]:
            try:
                date.fromisoformat(values["start_date"])
            except (ValueError, TypeError):
                raise TrackerError("开始日期必须是 YYYY-MM-DD")
        if "timezone" in values:
            try:
                ZoneInfo(values["timezone"])
            except (ZoneInfoNotFoundError, TypeError):
                raise TrackerError("无效时区")
        before = self.settings()
        with self.connect() as db:
            for key, value in values.items():
                if not isinstance(value, str):
                    raise TrackerError("设置值必须是文字")
                db.execute("UPDATE settings SET value=? WHERE key=?", (value, key))
                if before[key] != value:
                    db.execute("INSERT INTO plan_change(entity,entity_id,old_value,new_value,reason,changed_at) VALUES (?,?,?,?,?,?)",
                               ("settings", key, before[key], value, "用户修改", iso(utcnow())))
        return self.settings()

    def _day(self, db, day_id):
        row = db.execute("SELECT payload FROM curriculum_day WHERE id=? AND is_active=1", (day_id,)).fetchone()
        if not row:
            raise TrackerError("未找到课程日", "not_found", 404)
        return json.loads(row["payload"])

    def _today_id(self, now=None):
        settings = self.settings()
        if not settings["start_date"]:
            return None
        now = now or utcnow()
        local = now.astimezone(ZoneInfo(settings["timezone"]))
        offset = (local.date() - date.fromisoformat(settings["start_date"])).days
        source = self._source()
        if not 0 <= offset < source["weeks"] * 7:
            return None
        return f"W{offset // 7 + 1:02d}D{offset % 7 + 1:02d}"

    def bootstrap(self, now=None):
        data = self._source()
        return {"settings": self.settings(), "today_id": self._today_id(now),
                "plan_id": data["plan_id"], "plan_name": data.get("plan_name") or data["plan_id"],
                "weeks": data["weeks"], "total_planned_hours": data["total_planned_hours"],
                "curriculum_version": data["curriculum_version"], "weekly_themes": data["weekly_themes"],
                "leetcode_weekly": data["leetcode_weekly"], "validation": validate_curriculum(data)}

    def list_days(self):
        with self.connect() as db:
            rows = db.execute("""SELECT c.id,c.week,c.day,c.payload,p.status FROM curriculum_day c
                LEFT JOIN task_progress p ON p.day_id=c.id WHERE c.is_active=1 ORDER BY c.week,c.day""").fetchall()
            result = []
            for r in rows:
                payload = json.loads(r["payload"])
                required = {a["id"] for a in payload["acceptance_tests"]}
                passed = {a["criterion_id"] for a in db.execute(
                    "SELECT criterion_id FROM acceptance_review WHERE day_id=? AND status='passed'", (r["id"],))}
                result.append({"id": r["id"], "week": r["week"], "day": r["day"],
                               "title": payload["title"], "track": payload["track"],
                               "planned_minutes": payload["planned_minutes"],
                               "status": r["status"] or "not_started", "mastered": required <= passed})
            return result

    def get_day(self, day_id):
        with self.connect() as db:
            day = self._day(db, day_id)
            row = db.execute("SELECT * FROM task_progress WHERE day_id=?", (day_id,)).fetchone()
            day["progress"] = {"status": row["status"], "note": row["note"]} if row else {"status": "not_started", "note": ""}
            day["reading_progress"] = {r["item_id"]: bool(r["done"]) for r in db.execute("SELECT * FROM reading_progress WHERE day_id=?", (day_id,))}
            day["exercise_progress"] = {r["item_id"]: bool(r["done"]) for r in db.execute("SELECT * FROM exercise_progress WHERE day_id=?", (day_id,))}
            day["acceptance_progress"] = {r["criterion_id"]: {"status": r["status"], "evidence_id": r["evidence_id"], "note": r["note"]}
                                          for r in db.execute("SELECT * FROM acceptance_review WHERE day_id=?", (day_id,))}
            day["evidence_items"] = [dict(r) for r in db.execute("SELECT * FROM evidence WHERE day_id=? ORDER BY id DESC", (day_id,))]
            day["sessions"] = [dict(r) for r in db.execute("SELECT * FROM study_session WHERE day_id=? ORDER BY id DESC", (day_id,))]
            budget = db.execute("SELECT * FROM day_budget WHERE day_id=?", (day_id,)).fetchone()
            day["effective_budget"] = {k: budget[k] for k in ("theory_minutes", "practice_minutes", "verification_minutes")} if budget else day["time_budget"]
            day["effective_planned_minutes"] = sum(day["effective_budget"].values())
            reflection = db.execute("SELECT * FROM reflection WHERE day_id=?", (day_id,)).fetchone()
            day["reflection"] = dict(reflection) if reflection else None
            day["actual_seconds"] = sum(r["duration_seconds"] or 0 for r in day["sessions"])
            done = sum(day["reading_progress"].get(f"{day_id}:R{i}", False) for i in range(len(day["course_readings"])))
            done += sum(day["exercise_progress"].get(e["id"], False) for e in day["coding_exercises"])
            day["completion_rate"] = round(done / (len(day["course_readings"]) + len(day["coding_exercises"])) * 100)
            passed = sum(day["acceptance_progress"].get(a["id"], {}).get("status") == "passed" for a in day["acceptance_tests"])
            day["acceptance_rate"] = round(passed / len(day["acceptance_tests"]) * 100)
            return day

    def update_progress(self, day_id, status=None, note=None):
        if status is None and note is None:
            raise TrackerError("缺少更新内容")
        if status is not None and status not in STATUSES:
            raise TrackerError("无效任务状态")
        if note is not None and (not isinstance(note, str) or len(note) > 10000):
            raise TrackerError("笔记过长或格式错误")
        with self.connect() as db:
            self._day(db, day_id)
            old = db.execute("SELECT status,note FROM task_progress WHERE day_id=?", (day_id,)).fetchone()
            current_status = status if status is not None else (old["status"] if old else "not_started")
            current_note = note if note is not None else (old["note"] if old else "")
            db.execute("""INSERT INTO task_progress VALUES (?,?,?,?) ON CONFLICT(day_id) DO UPDATE SET
                status=excluded.status,note=excluded.note,updated_at=excluded.updated_at""",
                (day_id, current_status, current_note, iso(utcnow())))
        return self.get_day(day_id)

    def toggle(self, day_id, kind, item_id):
        with self.connect() as db:
            day = self._day(db, day_id)
            if kind == "reading":
                valid = {f"{day_id}:R{i}" for i in range(len(day["course_readings"]))}
                table = "reading_progress"
            elif kind == "exercise":
                valid = {x["id"] for x in day["coding_exercises"]}
                table = "exercise_progress"
            else:
                raise TrackerError("无效打卡类别")
            if item_id not in valid:
                raise TrackerError("项目不属于该课程日", "not_found", 404)
            row = db.execute(f"SELECT done FROM {table} WHERE item_id=?", (item_id,)).fetchone()
            done = 0 if row and row["done"] else 1
            db.execute(f"""INSERT INTO {table}(item_id,day_id,done,updated_at) VALUES (?,?,?,?)
                ON CONFLICT(item_id) DO UPDATE SET done=excluded.done,updated_at=excluded.updated_at""",
                (item_id, day_id, done, iso(utcnow())))
        return {"item_id": item_id, "done": bool(done)}

    def update_budget(self, day_id, values):
        keys = ("theory_minutes", "practice_minutes", "verification_minutes")
        if set(values) != set(keys) or any(type(values[k]) is not int or values[k] < 0 or values[k] > 1440 for k in keys):
            raise TrackerError("请填写三个非负分钟数，每项不超过 1440")
        if sum(values.values()) > 1440:
            raise TrackerError("单日计划不能超过 24 小时")
        old = self.get_day(day_id)["effective_budget"]
        with self.connect() as db:
            db.execute("INSERT INTO day_budget VALUES (?,?,?,?) ON CONFLICT(day_id) DO UPDATE SET theory_minutes=excluded.theory_minutes,practice_minutes=excluded.practice_minutes,verification_minutes=excluded.verification_minutes",
                       (day_id, *(values[k] for k in keys)))
            if old != values:
                db.execute("INSERT INTO plan_change(entity,entity_id,old_value,new_value,reason,changed_at) VALUES (?,?,?,?,?,?)",
                           ("day_budget", day_id, json.dumps(old), json.dumps(values), "用户调整", iso(utcnow())))
        return self.get_day(day_id)

    def add_evidence(self, day_id, values):
        kind, content, criterion_id = values.get("type"), values.get("content"), values.get("criterion_id")
        if kind not in EVIDENCE_TYPES or not isinstance(content, str) or not content.strip() or len(content) > 20000:
            raise TrackerError("证据类型或内容无效")
        if kind == "url" and urlparse(content).scheme not in ("http", "https"):
            raise TrackerError("URL 证据需以 http:// 或 https:// 开头")
        with self.connect() as db:
            day = self._day(db, day_id)
            if criterion_id is not None and criterion_id not in {a["id"] for a in day["acceptance_tests"]}:
                raise TrackerError("验收项不属于该课程日")
            cur = db.execute("INSERT INTO evidence(day_id,criterion_id,type,content,created_at) VALUES (?,?,?,?,?)",
                             (day_id, criterion_id, kind, content.strip(), iso(utcnow())))
            return {"id": cur.lastrowid, "day_id": day_id, "criterion_id": criterion_id, "type": kind, "content": content.strip()}

    def review(self, day_id, criterion_id, values):
        status = values.get("status")
        evidence_id = values.get("evidence_id")
        note = values.get("note", "")
        if status not in {"not_started", "in_progress", "submitted", "passed", "failed"} or not isinstance(note, str) or len(note) > 10000:
            raise TrackerError("验收状态或备注无效")
        with self.connect() as db:
            day = self._day(db, day_id)
            criterion = next((a for a in day["acceptance_tests"] if a["id"] == criterion_id), None)
            if not criterion:
                raise TrackerError("验收项不属于该课程日", "not_found", 404)
            if evidence_id is not None:
                evidence = db.execute("SELECT * FROM evidence WHERE id=? AND day_id=?", (evidence_id, day_id)).fetchone()
                if not evidence or evidence["criterion_id"] not in (None, criterion_id):
                    raise TrackerError("证据不属于该验收项")
            if status == "passed" and criterion.get("evidence_required", True) and evidence_id is None:
                raise TrackerError("必须先关联证据，才能标记通过", "evidence_required")
            db.execute("""INSERT INTO acceptance_review(criterion_id,day_id,status,evidence_id,note,reviewed_at)
                VALUES (?,?,?,?,?,?) ON CONFLICT(criterion_id) DO UPDATE SET status=excluded.status,
                evidence_id=excluded.evidence_id,note=excluded.note,reviewed_at=excluded.reviewed_at""",
                (criterion_id, day_id, status, evidence_id, note, iso(utcnow())))
        return self.get_day(day_id)["acceptance_progress"][criterion_id]

    def active_session(self):
        with self.connect() as db:
            row = db.execute("SELECT * FROM study_session WHERE ended_at IS NULL").fetchone()
            return dict(row) if row else None

    def start_session(self, day_id, now=None):
        now = now or utcnow()
        with self.connect() as db:
            self._day(db, day_id)
            row = db.execute("SELECT * FROM study_session WHERE ended_at IS NULL").fetchone()
            if row:
                if row["day_id"] != day_id:
                    raise TrackerError("已有其他课程日正在计时，请先结束", "timer_active", 409)
                return dict(row)
            cur = db.execute("INSERT INTO study_session(day_id,started_at,source) VALUES (?,?,?)", (day_id, iso(now), "timer"))
            return dict(db.execute("SELECT * FROM study_session WHERE id=?", (cur.lastrowid,)).fetchone())

    def stop_session(self, now=None):
        now = now or utcnow()
        with self.connect() as db:
            row = db.execute("SELECT * FROM study_session WHERE ended_at IS NULL").fetchone()
            if not row:
                return {"active": False}
            elapsed = max(0, int((now - datetime.fromisoformat(row["started_at"])).total_seconds()))
            db.execute("UPDATE study_session SET ended_at=?,duration_seconds=? WHERE id=?", (iso(now), elapsed, row["id"]))
            return {"active": False, "session_id": row["id"], "duration_seconds": elapsed}

    def manual_session(self, day_id, values):
        minutes, note = values.get("minutes"), values.get("note", "")
        if type(minutes) is not int or not 1 <= minutes <= 1440 or not isinstance(note, str) or len(note) > 1000:
            raise TrackerError("补录分钟必须是 1–1440 的整数")
        now = utcnow()
        from datetime import timedelta
        with self.connect() as db:
            self._day(db, day_id)
            cur = db.execute("INSERT INTO study_session(day_id,started_at,ended_at,duration_seconds,source,note) VALUES (?,?,?,?,?,?)",
                             (day_id, iso(now - timedelta(minutes=minutes)), iso(now), minutes * 60, "manual", note))
            return dict(db.execute("SELECT * FROM study_session WHERE id=?", (cur.lastrowid,)).fetchone())

    def save_reflection(self, day_id, values):
        keys = ("achievements", "tests", "blockers", "tomorrow")
        if set(values) != set(keys) or any(not isinstance(values[k], str) or len(values[k]) > 10000 for k in keys):
            raise TrackerError("复盘字段不完整或过长")
        with self.connect() as db:
            self._day(db, day_id)
            db.execute("""INSERT INTO reflection VALUES (?,?,?,?,?,?) ON CONFLICT(day_id) DO UPDATE SET
              achievements=excluded.achievements,tests=excluded.tests,blockers=excluded.blockers,
              tomorrow=excluded.tomorrow,updated_at=excluded.updated_at""",
              (day_id, *(values[k] for k in keys), iso(utcnow())))
        return self.get_day(day_id)["reflection"]

    def export(self):
        tables = ("settings", "curriculum_day", "task_progress", "reading_progress", "exercise_progress",
                  "evidence", "acceptance_review", "study_session", "day_budget", "reflection", "plan_change")
        with self.connect() as db:
            return {"format": "llm-study-tracker-backup-v1", "exported_at": iso(utcnow()),
                    "tables": {t: [dict(r) for r in db.execute(f"SELECT * FROM {t}")] for t in tables}}

    def restore_preview(self, payload):
        if payload.get("format") != "llm-study-tracker-backup-v1" or not isinstance(payload.get("tables"), dict):
            raise TrackerError("备份格式无效")
        tables = self.export()["tables"]
        if set(payload["tables"]) != set(tables):
            raise TrackerError("备份表不完整")
        return {"tables": {t: {"current": len(tables[t]), "backup": len(payload["tables"][t])} for t in tables}}

    def restore(self, payload):
        preview = self.restore_preview(payload)
        previous = self.export()
        backup_dir = self.data_dir / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup_file = backup_dir / f"pre_restore_{utcnow().strftime('%Y%m%dT%H%M%SZ')}_{uuid4().hex[:8]}.json"
        fd = os.open(backup_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            json.dump(previous, output, ensure_ascii=False, indent=2)
        order = list(self.export()["tables"])
        with self.connect() as db:
            for table in reversed(order):
                db.execute(f"DELETE FROM {table}")
            for table in order:
                for row in payload["tables"][table]:
                    cols = list(row)
                    if not cols or any(not re.fullmatch(r"[a-z_][a-z0-9_]*", c) for c in cols):
                        raise TrackerError("备份字段无效")
                    db.execute(f"INSERT INTO {table} ({','.join(cols)}) VALUES ({','.join('?' for _ in cols)})", tuple(row.values()))
        backups = sorted(backup_dir.glob("pre_restore_*.json"), reverse=True)
        for old in backups[5:]:
            old.unlink()
        return preview
