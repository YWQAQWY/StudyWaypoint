"""Start the existing local server in a Windows browser app window."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
import webbrowser
from http.server import ThreadingHTTPServer
from pathlib import Path

from ai_planner import AIPlanner
from plan_library import PlanLibrary
from server import Handler


def user_data_dir() -> Path:
    override = os.getenv("TRACKER_DATA_DIR")
    if override:
        return Path(override).expanduser()
    base = os.getenv("LOCALAPPDATA") or os.getenv("APPDATA")
    if not base:
        raise RuntimeError("LOCALAPPDATA and APPDATA are unavailable")
    return Path(base) / "StudyWaypoint"


def find_edge() -> Path | None:
    for variable in ("PROGRAMFILES(X86)", "PROGRAMFILES", "LOCALAPPDATA"):
        base = os.getenv(variable)
        if base:
            candidate = Path(base) / "Microsoft" / "Edge" / "Application" / "msedge.exe"
            if candidate.is_file():
                return candidate
    return None


def serve(data_dir: Path) -> ThreadingHTTPServer:
    Handler.tracker = PlanLibrary(data_dir=data_dir)
    Handler.ai = AIPlanner(Handler.tracker.data_dir)
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, name="studywaypoint-http", daemon=True)
    thread.start()
    return server


def acquire_instance_lock(data_dir: Path):
    import msvcrt

    path = data_dir / "instance.lock"
    if not path.exists():
        path.write_bytes(b"\0")
    lock = path.open("r+b")
    lock.seek(0)
    try:
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError as exc:
        lock.close()
        raise RuntimeError("StudyWaypoint is already using this data directory") from exc
    return lock


def main() -> int:
    # Windows console code pages differ; never fail to launch just because a
    # username or error message cannot be represented by the active page.
    sys.stdout.reconfigure(errors="backslashreplace")
    sys.stderr.reconfigure(errors="backslashreplace")
    if sys.platform != "win32":
        print("This launcher is for Windows. On Linux, use run-desktop.sh.", file=sys.stderr)
        return 1
    server = None
    lock = None
    try:
        data_dir = user_data_dir()
        data_dir.mkdir(parents=True, exist_ok=True)
        lock = acquire_instance_lock(data_dir)
        server = serve(data_dir)
        url = f"http://127.0.0.1:{server.server_port}/"
        print(f"StudyWaypoint is running: {url}")
        print(f"User data: {data_dir}")
        edge = find_edge()
        if edge:
            # A dedicated, per-launch profile keeps Edge from forwarding the
            # command to an existing process and exiting before this server.
            profile = data_dir / "browser_profiles" / str(os.getpid())
            profile.mkdir(parents=True, exist_ok=True)
            print("Opening Edge app window. Close it to stop the server.")
            try:
                process = subprocess.Popen([str(edge), f"--app={url}", f"--user-data-dir={profile}",
                                            "--no-first-run"])
                try:
                    result = process.wait()
                except KeyboardInterrupt:
                    process.terminate()
                    process.wait(timeout=5)
                    result = 0
                if result == 0:
                    return 0
                print("Edge could not open the app window; trying the default browser.")
            except OSError as exc:
                print(f"Edge launch failed ({exc}); trying the default browser.")
            finally:
                shutil.rmtree(profile, ignore_errors=True)
        try:
            opened = webbrowser.open(url, new=1)
        except (OSError, webbrowser.Error):
            opened = False
        if opened:
            print("Opened in your default browser. Press Enter here to stop the server.")
        else:
            print("Open the address above in a browser, then press Enter here to stop.")
        try:
            input()
        except (EOFError, KeyboardInterrupt):
            pass
        return 0
    except Exception as exc:
        print(f"Startup failed: {exc}", file=sys.stderr)
        return 1
    finally:
        if server is not None:
            server.shutdown()
            server.server_close()
        if lock is not None:
            lock.close()


if __name__ == "__main__":
    raise SystemExit(main())
