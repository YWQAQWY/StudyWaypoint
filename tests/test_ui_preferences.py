"""Desktop layout preferences persist across changing loopback ports."""

import json
import stat
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from plan_library import PlanLibrary
from server import Handler, read_ui_preferences, save_ui_preferences
from tracker import TrackerError


class UIPreferencesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.data_dir = Path(self.temp.name)

    def test_validation_and_private_atomic_save(self):
        self.assertEqual(read_ui_preferences(self.data_dir), {})
        (self.data_dir / "ui_preferences.json").write_text("{broken", encoding="utf-8")
        self.assertEqual(read_ui_preferences(self.data_dir), {})
        value = {"theme": "dark", "navCollapsed": True, "aiSidebarOpen": False,
                 "aiSplitWidth": 510, "closedStages": ["stage_1", "stage_1"]}
        saved = save_ui_preferences(self.data_dir, value)
        self.assertEqual(saved["closedStages"], ["stage_1"])
        self.assertEqual(read_ui_preferences(self.data_dir), saved)
        self.assertEqual(stat.S_IMODE((self.data_dir / "ui_preferences.json").stat().st_mode), 0o600)
        for invalid in ({"api_key": "never"}, {"theme": "blue"}, {"aiSplitWidth": 900},
                        {"navCollapsed": "true"}, {"closedStages": ["<script>"]}):
            with self.subTest(invalid=invalid), self.assertRaises(TrackerError):
                save_ui_preferences(self.data_dir, invalid)
            self.assertEqual(read_ui_preferences(self.data_dir), saved)

    def test_http_saved_preferences_are_embedded_after_port_change(self):
        Handler.tracker = PlanLibrary(self.data_dir)

        def start():
            server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            return server, worker

        server, worker = start()
        base = f"http://127.0.0.1:{server.server_port}"
        value = {"theme": "light", "navCollapsed": True, "aiSidebarOpen": False,
                 "aiSplitWidth": 525, "closedStages": ["stage_1"]}
        try:
            request = Request(base + "/api/ui/preferences", data=json.dumps(value).encode(),
                              headers={"Content-Type": "application/json"}, method="PUT")
            with urlopen(request) as response:
                self.assertEqual(json.load(response), value)
            with urlopen(base + "/api/ui/preferences") as response:
                self.assertEqual(json.load(response), value)
            foreign = Request(base + "/api/ui/preferences", headers={"Origin": "http://example.org"})
            with self.assertRaises(HTTPError) as caught:
                urlopen(foreign)
            self.assertEqual(caught.exception.code, 403)
        finally:
            server.shutdown()
            server.server_close()
            worker.join()

        server, worker = start()
        try:
            base = f"http://127.0.0.1:{server.server_port}"
            with urlopen(base + "/") as response:
                html = response.read().decode()
            self.assertIn('window.__initialUiPrefs={"theme": "light"', html)
            self.assertIn('"aiSplitWidth": 525', html)
            self.assertNotIn("/*__UI_PREFS__*/{}", html)
        finally:
            server.shutdown()
            server.server_close()
            worker.join()


if __name__ == "__main__":
    unittest.main()
