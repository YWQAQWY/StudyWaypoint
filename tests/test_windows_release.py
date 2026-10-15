import io
import os
import sys
import tempfile
import unittest
import urllib.request
import zipfile
from pathlib import Path
from unittest.mock import Mock, patch

import windows_launcher

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packaging"))
import build_windows


def archive_bytes(files):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for name, contents in files.items():
            archive.writestr(name, contents)
    return output.getvalue()


class WindowsReleaseTests(unittest.TestCase):
    def test_edge_window_closes_server_and_instance_lock(self):
        with tempfile.TemporaryDirectory() as temp:
            server = Mock(server_port=12345)
            lock = Mock()
            edge = Path(temp) / "msedge.exe"
            process = Mock()
            process.wait.return_value = 0
            with patch.object(windows_launcher.sys, "platform", "win32"), \
                    patch.object(windows_launcher, "user_data_dir", return_value=Path(temp)), \
                    patch.object(windows_launcher, "acquire_instance_lock", return_value=lock), \
                    patch.object(windows_launcher, "serve", return_value=server), \
                    patch.object(windows_launcher, "find_edge", return_value=edge), \
                    patch.object(windows_launcher.subprocess, "Popen", return_value=process) as popen:
                self.assertEqual(windows_launcher.main(), 0)
            self.assertIn("--app=http://127.0.0.1:12345/", popen.call_args.args[0])
            server.shutdown.assert_called_once()
            server.server_close.assert_called_once()
            lock.close.assert_called_once()

    def test_failed_edge_uses_default_browser(self):
        with tempfile.TemporaryDirectory() as temp:
            server = Mock(server_port=12345)
            with patch.object(windows_launcher.sys, "platform", "win32"), \
                    patch.object(windows_launcher, "user_data_dir", return_value=Path(temp)), \
                    patch.object(windows_launcher, "acquire_instance_lock", return_value=Mock()), \
                    patch.object(windows_launcher, "serve", return_value=server), \
                    patch.object(windows_launcher, "find_edge", return_value=Path(temp) / "msedge.exe"), \
                    patch.object(windows_launcher.subprocess, "Popen", side_effect=OSError("Edge unavailable")), \
                    patch.object(windows_launcher.webbrowser, "open", return_value=True) as browser, \
                    patch("builtins.input", return_value=""):
                self.assertEqual(windows_launcher.main(), 0)
            browser.assert_called_once_with("http://127.0.0.1:12345/", new=1)
            server.shutdown.assert_called_once()

    def test_launcher_uses_separate_user_directory(self):
        with patch.dict(os.environ, {"LOCALAPPDATA": r"C:\Users\Test\AppData\Local"}, clear=True):
            self.assertEqual(windows_launcher.user_data_dir(),
                             Path(r"C:\Users\Test\AppData\Local") / "StudyWaypoint")
        with tempfile.TemporaryDirectory() as temp:
            with patch.dict(os.environ, {"TRACKER_DATA_DIR": temp}, clear=True):
                self.assertEqual(windows_launcher.user_data_dir(), Path(temp))

    def test_windows_server_uses_existing_handler_and_sample(self):
        with tempfile.TemporaryDirectory() as temp:
            server = windows_launcher.serve(Path(temp))
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{server.server_port}/", timeout=5) as response:
                    self.assertIn(b"StudyWaypoint", response.read())
                self.assertTrue((Path(temp) / "builtin" / "tracker.sqlite3").exists())
            finally:
                server.shutdown()
                server.server_close()

    def test_archive_rejects_traversal(self):
        with self.assertRaises(ValueError):
            list(build_windows._members(archive_bytes({"../secret": "no"})))

    def test_portable_archive_contains_only_public_app_files(self):
        python = archive_bytes({
            "python.exe": b"exe", "python313.zip": b"stdlib",
            "python313._pth": b"python313.zip\n.\n", "LICENSE.txt": b"Python License",
        })
        tzdata = archive_bytes({
            "tzdata/__init__.py": b"", "tzdata/zoneinfo/Asia/Shanghai": b"timezone",
            "tzdata-2026.5.dist-info/licenses/LICENSE": b"Apache License",
        })
        with tempfile.TemporaryDirectory() as temp, \
                patch.object(build_windows, "fetch_verified", side_effect=[python, tzdata]), \
                patch.object(build_windows, "tzdata_url", return_value="https://example.invalid/tzdata.whl"):
            target = Path(temp) / "StudyWaypoint-test-windows-x64.zip"
            build_windows.build(target, Path(temp) / "cache")
            with zipfile.ZipFile(target) as archive:
                names = archive.namelist()
                self.assertTrue(any(name.endswith("/app/examples/sample_plan_v3.json") for name in names))
                self.assertTrue(any(name.endswith("/app/static/index.html") for name in names))
                self.assertTrue(any(name.endswith("/Start StudyWaypoint.cmd") for name in names))
                self.assertFalse(any("/data/" in name or name.endswith(".sqlite3") or "ai_config.json" in name
                                     for name in names))
                pth = next(name for name in names if name.endswith("/runtime/python313._pth"))
                self.assertIn(b"..\\app", archive.read(pth))
            expected = target.with_suffix(target.suffix + ".sha256").read_text().split()[0]
            self.assertEqual(expected, build_windows._sha256(target.read_bytes()))


if __name__ == "__main__":
    unittest.main()
