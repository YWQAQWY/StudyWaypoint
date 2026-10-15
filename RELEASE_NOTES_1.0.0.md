# StudyWaypoint v1.0.0

首个支持导入自定义课程计划的桌面发行版。公开包仅含通用一周示例，不含个人课程或学习记录。

## 新功能

- 导入同格式 v3 JSON 计划，导入前校验内容并预览新增、变更和移除的学习日。
- 计划库支持切换；每个计划独立保存学习时长、打卡、证据和验收。同一 `plan_id` 更新课程时保留原学习记录。
- 日历和首页按当前计划的周数、天数与小时数显示。
- 导出、恢复当前计划备份；恢复前自动保存现有数据。
- 附带一周示例计划及完整中文使用指南。

## 安装

Ubuntu/Debian 图形桌面下载 `studywaypoint_1.0.0_all.deb`，在文件所在目录运行：

```bash
sha256sum -c SHA256SUMS
sudo apt install ./studywaypoint_1.0.0_all.deb
```

系统需提供 Python 3.11+、GTK 3 与 WebKitGTK 4.1。无管理员权限时可下载源码包，解压后执行 `python3 packaging/install_user.py`，前提是系统依赖已安装。没有 Windows/macOS 安装包。详细说明见 [USER_GUIDE.md](USER_GUIDE.md)。

## 升级与数据

当前用户安装脚本会把旧桌面版的数据目录复制到新名称下，并将个人计划及数据库保存在独立目录，保留原始数据。通过 `.deb` 安装旧版的用户应在升级前保存课程 JSON 与备份，然后在新版中导入课程并恢复备份。数据默认位于 `~/.local/share/studywaypoint/`。

## 验证

14 项自动化测试、JavaScript 语法检查和桌面菜单项校验通过。发行包只包含应用与课程资源，不含用户记录。
