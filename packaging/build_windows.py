"""Build a self-contained Windows x64 portable ZIP on any build host.

Only the application allowlist below is packaged. Runtime downloads are pinned
to upstream SHA-256 checksums and never contain local user data.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import urllib.request
import zipfile
from pathlib import Path

from build_deb import ROOT, VERSION

PYTHON_VERSION = "3.13.16"
PYTHON_URL = f"https://www.python.org/ftp/python/{PYTHON_VERSION}/python-{PYTHON_VERSION}-embed-amd64.zip"
PYTHON_SHA256 = "97dae5274cc54867065e8d5a3226e48c35017ed332a0fdb0e27d5b5821961297"
TZDATA_VERSION = "2026.5"
TZDATA_SHA256 = "b683bd1b6659ddcd810ff02ad09ba821d4bf1065072805063eb35c49617905ac"
TZDATA_FILENAME = f"tzdata-{TZDATA_VERSION}-py2.py3-none-any.whl"
PYTHON_PTH = "python313._pth"
OUTPUT = Path(os.getenv("STUDYWAYPOINT_OUTPUT_DIR", ROOT.parent))
APP_FILES = (
    "server.py", "tracker.py", "plan_library.py", "ai_planner.py",
    "learning_resources.py", "plan_draft.py", "windows_launcher.py",
    "examples/sample_plan_v3.json",
)
DOC_FILES = ("README.md", "USER_GUIDE.md", "WINDOWS_GUIDE.md", "CHANGELOG.md", "log.md")
LAUNCHER = "@echo off\r\nsetlocal\r\ncd /d \"%~dp0\"\r\n\"runtime\\python.exe\" \"app\\windows_launcher.py\"\r\nif errorlevel 1 (\r\n  echo StudyWaypoint failed to start. See the error above.\r\n  pause\r\n)\r\n"
PTH = "python313.zip\n.\n.\\site-packages\n..\\app\n"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fetch_verified(url: str, checksum: str, cache_file: Path) -> bytes:
    if cache_file.exists():
        data = cache_file.read_bytes()
        if _sha256(data) == checksum:
            return data
    request = urllib.request.Request(url, headers={"User-Agent": "StudyWaypoint-release-builder/1.0"})
    with urllib.request.urlopen(request, timeout=45) as response:
        data = response.read(32 * 1024 * 1024 + 1)
    if len(data) > 32 * 1024 * 1024 or _sha256(data) != checksum:
        raise ValueError(f"下载文件校验失败：{url}")
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_bytes(data)
    return data


def tzdata_url() -> str:
    url = f"https://pypi.org/pypi/tzdata/{TZDATA_VERSION}/json"
    request = urllib.request.Request(url, headers={"User-Agent": "StudyWaypoint-release-builder/1.0"})
    with urllib.request.urlopen(request, timeout=20) as response:
        metadata = json.load(response)
    wheels = [item for item in metadata["urls"] if item["filename"] == TZDATA_FILENAME]
    if len(wheels) != 1 or wheels[0]["digests"]["sha256"] != TZDATA_SHA256:
        raise ValueError("PyPI tzdata 文件或校验值与固定版本不符")
    return wheels[0]["url"]


def _members(data: bytes):
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for entry in archive.infolist():
            path = Path(entry.filename)
            if entry.is_dir():
                continue
            if path.is_absolute() or ".." in path.parts or "\\" in entry.filename:
                raise ValueError("上游压缩包包含不安全路径")
            yield entry.filename, archive.read(entry)


def build(destination: Path | None = None, cache_dir: Path | None = None) -> Path:
    destination = destination or OUTPUT / f"StudyWaypoint-{VERSION}-windows-x64.zip"
    cache_dir = cache_dir or ROOT / "dist" / "windows-cache"
    python = fetch_verified(PYTHON_URL, PYTHON_SHA256, cache_dir / "python-embed-amd64.zip")
    tzdata = fetch_verified(tzdata_url(), TZDATA_SHA256, cache_dir / TZDATA_FILENAME)
    prefix = f"StudyWaypoint-{VERSION}-windows-x64"
    files: dict[str, bytes] = {}
    for name, content in _members(python):
        if "/" in name:
            raise ValueError("Python 嵌入版结构发生变化")
        files[f"runtime/{name}"] = content
    if f"runtime/{PYTHON_PTH}" not in files or "runtime/python.exe" not in files:
        raise ValueError("Python 嵌入版缺少启动文件")
    files[f"runtime/{PYTHON_PTH}"] = PTH.encode("ascii")
    for name, content in _members(tzdata):
        if not (name.startswith("tzdata/") or name.startswith(f"tzdata-{TZDATA_VERSION}.dist-info/")):
            raise ValueError("tzdata wheel 包含未知文件")
        files[f"runtime/site-packages/{name}"] = content
    for name in APP_FILES:
        files[f"app/{name}"] = (ROOT / name).read_bytes()
    for path in sorted((ROOT / "static").rglob("*")):
        if path.is_file():
            files[f"app/{path.relative_to(ROOT).as_posix()}"] = path.read_bytes()
    for name in DOC_FILES:
        files[name] = (ROOT / name).read_bytes()
    files["Start StudyWaypoint.cmd"] = LAUNCHER.encode("ascii")
    files["RUNTIME_SOURCES.txt"] = (
        f"Python {PYTHON_VERSION} Windows x64 embeddable package\n{PYTHON_URL}\nSHA-256: {PYTHON_SHA256}\n"
        f"tzdata {TZDATA_VERSION} (Apache-2.0)\nhttps://pypi.org/project/tzdata/{TZDATA_VERSION}/\n"
        f"SHA-256: {TZDATA_SHA256}\n"
        "Python license: runtime/LICENSE.txt\n"
        f"tzdata license: runtime/site-packages/tzdata-{TZDATA_VERSION}.dist-info/licenses/LICENSE\n"
    ).encode("utf-8")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, content in sorted(files.items()):
            info = zipfile.ZipInfo(f"{prefix}/{name}", date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, content, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    checksum = destination.with_suffix(destination.suffix + ".sha256")
    checksum.write_text(f"{_sha256(destination.read_bytes())}  {destination.name}\n", encoding="ascii")
    return destination


if __name__ == "__main__":
    result = build()
    print(result)
    print(result.with_suffix(result.suffix + ".sha256"))
