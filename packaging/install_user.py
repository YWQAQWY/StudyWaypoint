"""Install the desktop app for the current Linux user without administrator rights."""

from __future__ import annotations

import os
import shutil
import tempfile
import hashlib
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def migrate_legacy(old_app: Path, data_dir: Path) -> bool:
    """Copy the former bundled plan and root DB into a private per-plan folder."""
    source = old_app / "curriculum" / "curriculum_v3.json"
    old_db = data_dir / "tracker.sqlite3"
    if not source.is_file() or not old_db.is_file():
        return False
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from tracker import validate_curriculum
    data = json.loads(source.read_text(encoding="utf-8"))
    check = validate_curriculum(data)
    if not check["valid"]:
        raise ValueError("旧版课程文件校验失败: " + "; ".join(check["errors"]))
    plan_id = data["plan_id"]
    digest = hashlib.sha256(plan_id.encode("utf-8")).hexdigest()[:24]
    folder = data_dir / "plans" / digest
    folder.mkdir(parents=True, exist_ok=True)
    destination = folder / "curriculum.json"
    if not destination.exists():
        shutil.copy2(source, destination)
        destination.chmod(0o600)
    target_db = folder / "tracker.sqlite3"
    if not target_db.exists():
        with sqlite3.connect(old_db) as original, sqlite3.connect(target_db) as copied:
            original.backup(copied)
        target_db.chmod(0o600)
    index = data_dir / "plan_library.json"
    if not index.exists():
        index.write_text(json.dumps({"schema": 1, "active_plan_id": plan_id}, ensure_ascii=False))
        index.chmod(0o600)
    return True


def copy_legacy_data(legacy: Path, renamed: Path) -> bool:
    """Preserve the old data directory while preparing the renamed location."""
    if renamed.exists() or not legacy.is_dir():
        return False
    renamed.parent.mkdir(parents=True, exist_ok=True)
    staged = Path(tempfile.mkdtemp(prefix=".studywaypoint-data-", dir=renamed.parent))
    try:
        staged.rmdir()
        shutil.copytree(legacy, staged)
        os.replace(staged, renamed)
    except Exception:
        if staged.exists():
            shutil.rmtree(staged)
        raise
    return True


def install() -> dict[str, Path]:
    local = Path.home() / ".local"
    app_dir = local / "opt" / "StudyWaypoint"
    legacy_app = local / "opt" / "llm-study-tracker"
    launcher = local / "bin" / "studywaypoint"
    desktop = local / "share" / "applications" / "studywaypoint.desktop"
    icon = local / "share" / "icons" / "hicolor" / "scalable" / "apps" / "studywaypoint.svg"
    data_base = Path(os.getenv("XDG_DATA_HOME", local / "share")).expanduser()
    data_dir = Path(os.getenv("TRACKER_DATA_DIR", data_base / "studywaypoint")).expanduser()
    if not os.getenv("TRACKER_DATA_DIR"):
        copy_legacy_data(data_base / "llm-study-tracker", data_dir)
    migrate_legacy(legacy_app, data_dir)
    app_dir.parent.mkdir(parents=True, exist_ok=True)
    staged = Path(tempfile.mkdtemp(prefix=".studywaypoint-", dir=app_dir.parent))
    try:
        for relative in ("desktop.py", "server.py", "tracker.py", "plan_library.py", "static", "examples", "assets"):
            source = ROOT / relative
            target = staged / relative
            if source.is_dir():
                shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            else:
                shutil.copy2(source, target)
        staged.chmod(0o755)
        for item in staged.rglob("*"):
            item.chmod(0o755 if item.is_dir() else 0o644)
        previous = app_dir.with_name("StudyWaypoint.previous")
        if previous.exists():
            shutil.rmtree(previous)
        if app_dir.exists():
            os.replace(app_dir, previous)
        os.replace(staged, app_dir)
    except Exception:
        if staged.exists():
            shutil.rmtree(staged)
        raise

    launcher.parent.mkdir(parents=True, exist_ok=True)
    launcher.write_text(f'#!/bin/sh\nexec /usr/bin/python3 "{app_dir / "desktop.py"}" "$@"\n')
    launcher.chmod(0o755)
    desktop.parent.mkdir(parents=True, exist_ok=True)
    template = (ROOT / "packaging" / "studywaypoint.desktop").read_text()
    desktop.write_text(template.replace("Exec=studywaypoint", f"Exec={launcher}"))
    desktop.chmod(0o644)
    icon.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "assets" / "studywaypoint.svg", icon)
    icon.chmod(0o644)
    old_launcher = local / "bin" / "llm-study-tracker"
    old_desktop = local / "share" / "applications" / "llm-study-tracker.desktop"
    old_icon = local / "share" / "icons" / "hicolor" / "scalable" / "apps" / "llm-study-tracker.svg"
    if old_launcher.is_file() and "llm-study-tracker/desktop.py" in old_launcher.read_text():
        old_launcher.unlink()
    if old_desktop.is_file() and "llm-study-tracker" in old_desktop.read_text():
        old_desktop.unlink()
        old_icon.unlink(missing_ok=True)
    return {"application": app_dir, "launcher": launcher, "desktop_entry": desktop, "icon": icon, "data": data_dir}


if __name__ == "__main__":
    for name, path in install().items():
        print(f"{name}: {path}")
