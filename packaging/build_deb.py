"""Build an installable Ubuntu/Debian desktop package from this source tree."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = "1.0.0"


def build(destination: Path | None = None) -> Path:
    destination = destination or ROOT.parent / f"studywaypoint_{VERSION}_all.deb"
    with tempfile.TemporaryDirectory(prefix="studywaypoint-deb-") as temp:
        staging = Path(temp) / "package"
        app = staging / "usr" / "share" / "studywaypoint"
        for relative in ["desktop.py", "server.py", "tracker.py", "plan_library.py", "static", "examples", "assets", "README.md", "USER_GUIDE.md", "CHANGELOG.md"]:
            source = ROOT / relative
            target = app / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if source.is_dir():
                shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            else:
                shutil.copy2(source, target)
        executable = staging / "usr" / "bin" / "studywaypoint"
        executable.parent.mkdir(parents=True, exist_ok=True)
        executable.write_text("#!/bin/sh\nexec /usr/bin/python3 /usr/share/studywaypoint/desktop.py \"$@\"\n")
        executable.chmod(0o755)
        desktop = staging / "usr" / "share" / "applications" / "studywaypoint.desktop"
        desktop.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / "packaging" / "studywaypoint.desktop", desktop)
        icon = staging / "usr" / "share" / "icons" / "hicolor" / "scalable" / "apps" / "studywaypoint.svg"
        icon.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / "assets" / "studywaypoint.svg", icon)
        control = staging / "DEBIAN" / "control"
        control.parent.mkdir(parents=True, exist_ok=True)
        control.write_text(
            f"Package: studywaypoint\nVersion: {VERSION}\nSection: education\nPriority: optional\nArchitecture: all\n"
            "Maintainer: Local User <local@localhost>\n"
            "Depends: python3 (>= 3.11), python3-gi, gir1.2-gtk-3.0, gir1.2-webkit2-4.1\n"
            "Description: StudyWaypoint local-first study plan tracker\n"
            " A single-user study tracker with importable v3 JSON plans,\n"
            " SQLite persistence and a GTK WebKit desktop window.\n"
        )
        for path in staging.rglob("*"):
            if path.is_dir():
                path.chmod(0o755)
            else:
                path.chmod(0o755 if path == executable else 0o644)
        destination.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["dpkg-deb", "--build", "--root-owner-group", str(staging), str(destination)], check=True)
    return destination


if __name__ == "__main__":
    print(build())
