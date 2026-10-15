"""Plan library: one SQLite database per plan, keyed by stable plan_id."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock

from tracker import CURRICULUM, ROOT, Tracker, TrackerError, validate_curriculum


def _read_valid(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise TrackerError(f"无法读取计划文件: {exc}", "invalid_curriculum") from exc
    check = validate_curriculum(data)
    if not check["valid"]:
        raise TrackerError("计划校验失败: " + "; ".join(check["errors"]), "invalid_curriculum")
    return data


class PlanLibrary:
    def __init__(self, data_dir: str | Path | None = None):
        self.data_dir = Path(data_dir or os.getenv("TRACKER_DATA_DIR", ROOT / "data"))
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._built_in = _read_valid(CURRICULUM)
        self.default_id = self._built_in["plan_id"]
        self.index_path = self.data_dir / "plan_library.json"
        active_id = self.default_id
        if self.index_path.exists():
            try:
                active_id = json.loads(self.index_path.read_text(encoding="utf-8")).get("active_plan_id", self.default_id)
            except ValueError:
                active_id = self.default_id
        try:
            source, folder = self._locate(active_id)
        except TrackerError:
            active_id = self.default_id
            source, folder = self._locate(active_id)
        self.active_plan_id = active_id
        self.active = Tracker(data_dir=folder, curriculum_path=source)

    def _folder(self, plan_id: str) -> Path:
        if plan_id == self.default_id:
            return self.data_dir / "builtin"
        digest = hashlib.sha256(plan_id.encode("utf-8")).hexdigest()[:24]
        return self.data_dir / "plans" / digest

    def _locate(self, plan_id: str) -> tuple[Path, Path]:
        if plan_id == self.default_id:
            override = self.data_dir / "builtin" / "curriculum.json"
            return (override if override.exists() else CURRICULUM), self._folder(plan_id)
        folder = self._folder(plan_id)
        source = folder / "curriculum.json"
        if not source.exists():
            raise TrackerError("未找到该计划", "not_found", 404)
        if _read_valid(source)["plan_id"] != plan_id:
            raise TrackerError("计划目录与 plan_id 不匹配", "invalid_curriculum")
        return source, folder

    def _all_sources(self):
        default_source, _ = self._locate(self.default_id)
        yield default_source
        plan_dir = self.data_dir / "plans"
        if plan_dir.exists():
            for source in sorted(plan_dir.glob("*/curriculum.json")):
                yield source

    def list_plans(self):
        result = []
        for source in self._all_sources():
            try:
                data = _read_valid(source)
            except TrackerError:
                continue
            plan_id = data["plan_id"]
            result.append({"plan_id": plan_id, "plan_name": data.get("plan_name") or plan_id,
                           "curriculum_version": data["curriculum_version"], "weeks": data["weeks"],
                           "days": len(data["days"]), "total_planned_hours": data["total_planned_hours"],
                           "active": plan_id == self.active_plan_id,
                           "built_in": plan_id == self.default_id})
        return result

    def bootstrap(self, now=None):
        result = self.active.bootstrap(now)
        result["plans"] = self.list_plans()
        result["active_plan_id"] = self.active_plan_id
        return result

    def _existing_hashes(self, plan_id):
        db_path = self._folder(plan_id) / "tracker.sqlite3"
        if not db_path.exists():
            return {}
        with sqlite3.connect(f"{db_path.resolve().as_uri()}?mode=ro", uri=True) as db:
            columns = {row[1] for row in db.execute("PRAGMA table_info(curriculum_day)")}
            if not columns:
                return {}
            where = " WHERE is_active=1" if "is_active" in columns else ""
            return dict(db.execute("SELECT id,sha256 FROM curriculum_day" + where))

    def preview_plan(self, data: dict):
        check = validate_curriculum(data)
        if not check["valid"]:
            raise TrackerError("计划校验失败: " + "; ".join(check["errors"]), "invalid_curriculum")
        plan_id = data["plan_id"]
        old = self._existing_hashes(plan_id)
        incoming = {day["id"]: hashlib.sha256(json.dumps(day, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
                    for day in data["days"]}
        return {"plan_id": plan_id, "plan_name": data.get("plan_name") or plan_id,
                "curriculum_version": data["curriculum_version"], "weeks": data["weeks"],
                "days": len(data["days"]), "minutes": check["minutes"],
                "existing": bool(old) or plan_id == self.default_id,
                "added": sorted(set(incoming) - set(old)),
                "changed": sorted(key for key in set(incoming) & set(old) if incoming[key] != old[key]),
                "unchanged": sum(incoming[key] == old[key] for key in set(incoming) & set(old)),
                "removed": sorted(set(old) - set(incoming))}

    def _save_source(self, source: Path, data: dict):
        source.parent.mkdir(parents=True, exist_ok=True)
        if source.exists():
            backups = source.parent / "source_versions"
            backups.mkdir(exist_ok=True)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            shutil.copy2(source, backups / f"{stamp}.json")
            for old in sorted(backups.glob("*.json"), reverse=True)[5:]:
                old.unlink()
        temp = source.with_suffix(".json.tmp")
        temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temp, source)

    def _save_active(self):
        temp = self.index_path.with_suffix(".tmp")
        temp.write_text(json.dumps({"schema": 1, "active_plan_id": self.active_plan_id}, ensure_ascii=False))
        os.replace(temp, self.index_path)

    def apply_plan(self, data: dict):
        with self._lock:
            preview = self.preview_plan(data)
            if self.active.active_session():
                raise TrackerError("请先结束正在运行的计时，再导入或切换计划", "timer_active", 409)
            plan_id = data["plan_id"]
            folder = self._folder(plan_id)
            source = folder / "curriculum.json"
            self._save_source(source, data)
            target = Tracker(data_dir=folder, curriculum_path=source)
            self.active = target
            self.active_plan_id = plan_id
            self._save_active()
            return {**preview, "active_plan_id": self.active_plan_id}

    def select_plan(self, plan_id: str):
        with self._lock:
            if plan_id == self.active_plan_id:
                return {"active_plan_id": plan_id, "plans": self.list_plans()}
            if self.active.active_session():
                raise TrackerError("请先结束正在运行的计时，再切换计划", "timer_active", 409)
            source, folder = self._locate(plan_id)
            target = Tracker(data_dir=folder, curriculum_path=source)
            self.active = target
            self.active_plan_id = plan_id
            self._save_active()
            return {"active_plan_id": plan_id, "plans": self.list_plans()}

    def export(self):
        result = self.active.export()
        result["plan_id"] = self.active_plan_id
        return result

    def restore_preview(self, payload):
        if not isinstance(payload, dict) or not isinstance(payload.get("tables"), dict):
            raise TrackerError("备份格式无效")
        plan_id = payload.get("plan_id")
        if plan_id is None:
            rows = payload["tables"].get("curriculum_day", [])
            if not isinstance(rows, list):
                raise TrackerError("备份格式无效")
            backup_hashes = {row.get("id"): row.get("sha256") for row in rows if isinstance(row, dict)}
            current_hashes = self._existing_hashes(self.active_plan_id)
            if not backup_hashes or backup_hashes != current_hashes:
                raise TrackerError("旧版备份缺少 plan_id，课程快照与当前计划不匹配", "wrong_plan")
        elif plan_id != self.active_plan_id:
            raise TrackerError("备份属于另一计划，请先切换到对应计划", "wrong_plan")
        return self.active.restore_preview(payload)

    def restore(self, payload):
        with self._lock:
            self.restore_preview(payload)
            if self.active.active_session():
                raise TrackerError("请先结束计时再恢复备份", "timer_active", 409)
            return self.active.restore(payload)

    def __getattr__(self, name):
        return getattr(self.active, name)
