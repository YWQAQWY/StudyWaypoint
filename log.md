# StudyWaypoint 开发日志

本文件记录逐次开发变更。每次新增、修改或删除项目内容时，在同一批变更中补充一条记录；写明日期、做了什么、涉及哪些文件，以及验证结果。不得记录个人计划、学习数据或 API 密钥。

## 2026-10-15

### 建立持续开发日志

- 更新 `README.md`，说明每次项目变更都必须同步记录在本日志，并区分开发日志与版本摘要。
- 新增 `log.md` 和 `AGENTS.md`，让后续开发继续遵守记录规则。
- 更新 `packaging/build_release.py` 和 `packaging/build_deb.py`，将开发日志纳入源码包与安装包，并将开发约定纳入源码包。
- 验证：`python3 -m unittest discover -s tests -v` 全部 21 项通过；打包脚本通过 Python 语法检查，`git diff --check` 无空白错误。源码包包含 `AGENTS.md` 和 `log.md`，安装包包含 `log.md`；校验和检查通过，文件清单未见个人数据文件。

### 既有里程碑补录

以下内容依据现有 `CHANGELOG.md`、`README.md` 与发行说明整理；原始完成日期未单独记录，不作为逐次变更明细。

- 1.0.0：桌面程序、通用示例计划、v3 JSON 导入与计划库、日历与每日任务、计时、步骤打卡、证据、验收、备份。
- 1.1.0：OpenAI 兼容 API 的 AI 规划、计划草稿生成与确认导入；联网检索可选择 Brave Search 或 SearXNG。
