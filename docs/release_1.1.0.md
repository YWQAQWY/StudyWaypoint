# 1.1.0 本地构建与 GitHub 上传

在项目根目录先运行：

```bash
python3 -m unittest discover -s tests -v
STUDYWAYPOINT_OUTPUT_DIR="$PWD/dist" python3 packaging/build_release.py
```

上述命令在项目的 `dist/` 目录生成 `studywaypoint_1.1.0_all.deb`、`StudyWaypoint-1.1.0-source.zip` 与 `SHA256SUMS`。上传前检查归档和安装包只包含应用代码、通用示例与文档，不能包含 `data/`、个人课程、SQLite 数据库、备份、`ai_config.json`、`ai_conversation.json` 或 `ai_draft.json`。不设置 `STUDYWAYPOINT_OUTPUT_DIR` 时，脚本仍默认输出到源码目录的上一级。

用户自行将仓库与这三个发行文件上传 GitHub。可使用 [发行说明](../RELEASE_NOTES_1.1.0.md) 作为 Release 描述。不要把个人 API Key 写入提交、Issue 或 Release。

安装命令：

```bash
sudo apt install ./studywaypoint_1.1.0_all.deb
```
