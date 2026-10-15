# 1.2.0 本地构建与 GitHub 上传

在仓库根目录运行：

```bash
python3 -m unittest discover -s tests -v
python3 packaging/build_release.py
```

脚本默认在源码目录上一级生成 `studywaypoint_1.2.0_all.deb`、`StudyWaypoint-1.2.0-source.zip` 和 `SHA256SUMS`。需要指定输出目录时，设置 `STUDYWAYPOINT_OUTPUT_DIR`。用 `sha256sum -c SHA256SUMS` 校验文件。

上传 GitHub 前检查包内不含 `data/`、个人计划、SQLite 数据库、备份、`ai_config.json`、`ai_conversation.json` 或 `ai_draft.json`。仓库的 `examples/sample_plan_v3.json` 是通用示例。用户自行上传仓库与发行文件；可用 [发行说明](../RELEASE_NOTES_1.2.0.md) 作为 Release 描述。

安装命令：

```bash
sudo apt install ./studywaypoint_1.2.0_all.deb
```

联网搜索需用户自己的 SearXNG JSON 实例或主动启用 Brave Search API；发行包不内置搜索服务。
