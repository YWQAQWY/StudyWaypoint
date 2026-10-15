# 1.4.0 本地构建与 GitHub 上传

在仓库根目录运行：

```bash
python3 -m unittest discover -s tests -q
STUDYWAYPOINT_OUTPUT_DIR="$PWD/dist" python3 packaging/build_release.py
cd dist && sha256sum -c SHA256SUMS
```

发行文件为 `studywaypoint_1.4.0_all.deb`、`StudyWaypoint-1.4.0-source.zip` 和 `SHA256SUMS`。用户自行上传 GitHub。上传前核对安装包和源码包不包含 `data/`、个人计划、SQLite 数据库、备份、`ui_preferences.json`、`ai_config.json`、`ai_conversation.json`、`ai_plan_draft.json` 或 `ai_draft.json`。`examples/sample_plan_v3.json` 是通用一周示例。

安装：

```bash
sudo apt install ./studywaypoint_1.4.0_all.deb
```
