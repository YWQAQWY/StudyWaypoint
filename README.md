# StudyWaypoint 1.0

适用于 Ubuntu/Debian 的本地桌面学习追踪器。内置通用一周示例计划，也可导入同格式的自定义 v3 JSON 计划。公开包不包含任何个人课程。不同计划的 SQLite 学习记录独立保存。

## 安装

```bash
sudo apt install ./studywaypoint_1.0.0_all.deb
```

没有管理员权限但已安装 GTK 3、WebKitGTK 4.1 时，可从源码运行 `python3 packaging/install_user.py` 安装到当前用户。也可用 `./run-desktop.sh` 直接启动桌面窗口，或用 `python3 server.py` 启动本地浏览器版。

完整安装、使用、导入、备份及排错步骤见 [使用指南](USER_GUIDE.md)。计划结构可参考 [示例 v3 JSON](examples/sample_plan_v3.json)。

## 验证

```bash
python3 -m unittest discover -s tests -v
python3 packaging/build_deb.py
```

课程数据与个人进度分开保存。应用不编写或执行用户的核心学习实验。
# StudyWaypoint
