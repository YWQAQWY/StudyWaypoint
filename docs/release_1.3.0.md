# 1.3.0 本地构建与 GitHub 上传

在仓库根目录运行：

```bash
python3 -m unittest discover -s tests -v
STUDYWAYPOINT_OUTPUT_DIR="$PWD/dist" python3 packaging/build_release.py
cd dist && sha256sum -c SHA256SUMS
```

发行目录中应有 `studywaypoint_1.3.0_all.deb`、`StudyWaypoint-1.3.0-source.zip` 和 `SHA256SUMS`。用户自行将仓库与发行文件上传 GitHub，可参考 [发行说明](../RELEASE_NOTES_1.3.0.md)。

上传前检查压缩包与安装包不包含 `data/`、个人课程、SQLite 数据库、备份、`ai_config.json`、`ai_conversation.json`、`ai_plan_draft.json` 或 `ai_draft.json`。仓库中的 `examples/sample_plan_v3.json` 是通用示例。

安装命令：

```bash
sudo apt install ./studywaypoint_1.3.0_all.deb
```
