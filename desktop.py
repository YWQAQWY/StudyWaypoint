"""GTK desktop window for the local-first StudyWaypoint application."""

from __future__ import annotations

import os
import sys
import threading
import json
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("WebKit2", "4.1")
from gi.repository import Gio, Gtk, WebKit2  # noqa: E402

from server import Handler
from tracker import ROOT, TrackerError
from plan_library import PlanLibrary
from ai_planner import AIPlanner


APP_ID = "io.github.studywaypoint.App"


def user_data_dir() -> Path:
    override = os.getenv("TRACKER_DATA_DIR")
    if override:
        return Path(override).expanduser()
    existing = ROOT / "data" / "tracker.sqlite3"
    if existing.is_file() and os.access(existing.parent, os.W_OK):
        return existing.parent
    base = Path(os.getenv("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    renamed = base / "studywaypoint"
    legacy = base / "llm-study-tracker"
    return renamed if renamed.exists() or not legacy.exists() else legacy


class DesktopWindow(Gtk.Window):
    def __init__(self, base_url: str, server: ThreadingHTTPServer):
        super().__init__(title="StudyWaypoint")
        self.base_url = base_url
        self.server = server
        self.set_default_size(1180, 780)
        self.set_size_request(560, 480)
        self.set_position(Gtk.WindowPosition.CENTER)
        icon = ROOT / "assets" / "studywaypoint.svg"
        if icon.exists():
            self.set_icon_from_file(str(icon))

        header = Gtk.HeaderBar()
        header.set_show_close_button(True)
        header.props.title = "StudyWaypoint"
        header.props.subtitle = "可导入学习计划 · 本地保存"
        self.set_titlebar(header)

        refresh = Gtk.Button.new_from_icon_name("view-refresh-symbolic", Gtk.IconSize.BUTTON)
        refresh.set_tooltip_text("刷新页面")
        refresh.connect("clicked", lambda *_: self.webview.reload())
        header.pack_start(refresh)

        save = Gtk.Button.new_from_icon_name("document-save-symbolic", Gtk.IconSize.BUTTON)
        save.set_tooltip_text("导出完整备份")
        save.connect("clicked", self._export_backup)
        header.pack_end(save)

        restore = Gtk.Button.new_from_icon_name("document-open-symbolic", Gtk.IconSize.BUTTON)
        restore.set_tooltip_text("恢复备份")
        restore.connect("clicked", self._restore_backup)
        header.pack_end(restore)

        import_plan = Gtk.Button.new_from_icon_name("document-import-symbolic", Gtk.IconSize.BUTTON)
        import_plan.set_tooltip_text("导入 v3 JSON 计划")
        import_plan.connect("clicked", self._import_plan)
        header.pack_end(import_plan)

        self.webview = WebKit2.WebView()
        self.webview.set_hexpand(True)
        self.webview.set_vexpand(True)
        self.webview.connect("decide-policy", self._on_policy)
        self.webview.get_context().connect("download-started", self._on_download)
        self.webview.connect("load-failed", self._on_load_failed)
        self.add(self.webview)
        self.connect("destroy", self._on_destroy)
        self.webview.load_uri(base_url)

    def _on_policy(self, _view, decision, decision_type):
        if decision_type not in (WebKit2.PolicyDecisionType.NAVIGATION_ACTION,
                                 WebKit2.PolicyDecisionType.NEW_WINDOW_ACTION):
            return False
        action = decision.get_navigation_action()
        uri = action.get_request().get_uri()
        target = urlsplit(uri)
        local = urlsplit(self.base_url)
        if target.scheme in ("http", "https") and (target.hostname, target.port) == (local.hostname, local.port):
            return False
        if target.scheme in ("http", "https"):
            Gio.AppInfo.launch_default_for_uri(uri, None)
        decision.ignore()
        return True

    def _on_download(self, _context, download):
        download.connect("decide-destination", self._choose_download)

    def _message(self, title: str, detail: str, message_type=Gtk.MessageType.INFO):
        dialog = Gtk.MessageDialog(transient_for=self, flags=0, message_type=message_type,
                                   buttons=Gtk.ButtonsType.CLOSE, text=title)
        dialog.format_secondary_text(detail)
        dialog.run()
        dialog.destroy()

    def _export_backup(self, *_):
        chooser = Gtk.FileChooserDialog(
            title="导出 Tracker 备份", transient_for=self, action=Gtk.FileChooserAction.SAVE,
            buttons=("取消", Gtk.ResponseType.CANCEL, "保存", Gtk.ResponseType.ACCEPT),
        )
        chooser.set_do_overwrite_confirmation(True)
        chooser.set_current_name("studywaypoint-backup.json")
        chosen = chooser.run()
        filename = chooser.get_filename() if chosen == Gtk.ResponseType.ACCEPT else None
        chooser.destroy()
        if not filename:
            return
        try:
            Path(filename).write_text(json.dumps(Handler.tracker.export(), ensure_ascii=False, indent=2), encoding="utf-8")
            self._message("备份已保存", filename)
        except (OSError, ValueError) as exc:
            self._message("备份失败", str(exc), Gtk.MessageType.ERROR)

    def _restore_backup(self, *_):
        chooser = Gtk.FileChooserDialog(
            title="选择 Tracker 备份", transient_for=self, action=Gtk.FileChooserAction.OPEN,
            buttons=("取消", Gtk.ResponseType.CANCEL, "打开", Gtk.ResponseType.ACCEPT),
        )
        chosen = chooser.run()
        filename = chooser.get_filename() if chosen == Gtk.ResponseType.ACCEPT else None
        chooser.destroy()
        if not filename:
            return
        try:
            payload = json.loads(Path(filename).read_text(encoding="utf-8"))
            preview = Handler.tracker.restore_preview(payload)
        except (OSError, ValueError, TypeError, TrackerError) as exc:
            self._message("无法读取备份", str(exc), Gtk.MessageType.ERROR)
            return
        counts = preview["tables"]
        summary = "；".join(f"{name}: {value['current']} → {value['backup']}"
                           for name, value in counts.items() if value["current"] or value["backup"])
        confirm = Gtk.MessageDialog(
            transient_for=self, flags=0, message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.NONE, text="确认恢复备份？",
        )
        confirm.format_secondary_text("将用所选备份替换当前学习记录。当前数据会先自动备份。\n" + summary)
        confirm.add_buttons("取消", Gtk.ResponseType.CANCEL, "恢复", Gtk.ResponseType.ACCEPT)
        accepted = confirm.run() == Gtk.ResponseType.ACCEPT
        confirm.destroy()
        if not accepted:
            return
        try:
            Handler.tracker.restore(payload)
            self.webview.reload()
            self._message("备份已恢复", "当前记录已在恢复前自动备份。")
        except (OSError, ValueError, TypeError, TrackerError) as exc:
            self._message("恢复失败", str(exc), Gtk.MessageType.ERROR)

    def _import_plan(self, *_):
        chooser = Gtk.FileChooserDialog(
            title="选择 v3 JSON 学习计划", transient_for=self, action=Gtk.FileChooserAction.OPEN,
            buttons=("取消", Gtk.ResponseType.CANCEL, "打开", Gtk.ResponseType.ACCEPT),
        )
        chosen = chooser.run()
        filename = chooser.get_filename() if chosen == Gtk.ResponseType.ACCEPT else None
        chooser.destroy()
        if not filename:
            return
        try:
            data = json.loads(Path(filename).read_text(encoding="utf-8"))
            preview = Handler.tracker.preview_plan(data)
        except (OSError, ValueError, TypeError, TrackerError) as exc:
            self._message("计划无法导入", str(exc), Gtk.MessageType.ERROR)
            return
        summary = (f"{preview['plan_name']}（{preview['plan_id']}）\n"
                   f"{preview['weeks']} 周、{preview['days']} 天、{preview['minutes'] / 60:g} 小时\n"
                   f"新增 {len(preview['added'])} 天，变更 {len(preview['changed'])} 天，"
                   f"未变 {preview['unchanged']} 天，归档 {len(preview['removed'])} 天。\n"
                   "同一 plan_id 会保留原学习记录；不同 plan_id 的数据独立保存。")
        confirm = Gtk.MessageDialog(
            transient_for=self, flags=0, message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.NONE, text="导入并启用这个计划？",
        )
        confirm.format_secondary_text(summary)
        confirm.add_buttons("取消", Gtk.ResponseType.CANCEL, "导入", Gtk.ResponseType.ACCEPT)
        accepted = confirm.run() == Gtk.ResponseType.ACCEPT
        confirm.destroy()
        if not accepted:
            return
        try:
            Handler.tracker.apply_plan(data)
            self.webview.reload()
            self._message("计划已导入", preview["plan_name"])
        except (OSError, ValueError, TypeError, TrackerError) as exc:
            self._message("导入失败", str(exc), Gtk.MessageType.ERROR)

    def _choose_download(self, download, suggested_name):
        chooser = Gtk.FileChooserDialog(
            title="保存 Tracker 备份", transient_for=self,
            action=Gtk.FileChooserAction.SAVE,
            buttons=("取消", Gtk.ResponseType.CANCEL, "保存", Gtk.ResponseType.ACCEPT),
        )
        chooser.set_do_overwrite_confirmation(True)
        chooser.set_current_name(suggested_name or "studywaypoint-backup.json")
        chosen = chooser.run()
        filename = chooser.get_filename() if chosen == Gtk.ResponseType.ACCEPT else None
        chooser.destroy()
        if filename:
            download.set_destination(Gio.File.new_for_path(filename).get_uri())
        else:
            download.cancel()
        return True

    def _on_load_failed(self, _view, _event, _uri, error):
        dialog = Gtk.MessageDialog(
            transient_for=self, flags=0, message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.CLOSE,
            text="Tracker 页面加载失败",
        )
        dialog.format_secondary_text(str(error))
        dialog.run()
        dialog.destroy()
        return False

    def _on_destroy(self, *_):
        self.server.shutdown()
        self.server.server_close()
        if Gtk.main_level() > 0:
            Gtk.main_quit()


def main() -> int:
    if not Gtk.init_check()[0]:
        print("无法打开图形桌面，请在有 GTK 显示环境的会话中启动。", file=sys.stderr)
        return 1
    Handler.tracker = PlanLibrary(data_dir=user_data_dir())
    Handler.ai = AIPlanner(Handler.tracker.data_dir)
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}/"
    window = DesktopWindow(base_url, server)
    window.show_all()
    try:
        Gtk.main()
    except KeyboardInterrupt:
        window.destroy()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
