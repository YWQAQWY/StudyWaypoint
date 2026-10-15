# StudyWaypoint 开发日志

本文件记录逐次开发变更。每次新增、修改或删除项目内容时，在同一批变更中补充一条记录；写明日期、做了什么、涉及哪些文件，以及验证结果。不得记录个人计划、学习数据或 API 密钥。

## 2026-10-15

### 当前前端 UI 文本说明

- 新增 `CURRENT_UI.txt`，依据当前 HTML、JavaScript、CSS 与桌面窗口代码，记录导航、主要页面、AI 侧栏、桌面按钮和窄屏布局；使用通用占位描述，不包含个人计划或学习记录。
- 验证：对照 `static/index.html`、`static/app.js`、`static/ai.js`、`static/style.css`、`desktop.py` 检查界面名称和控件；`git diff --check` 通过。本次仅新增文档，未改动运行代码。

### 1.3.0：交互式 AI 规划与自动导入

- 新增 `plan_draft.py` 与 `tests/test_plan_draft.py`：内部部分草稿、稳定阶段和任务 ID、版本冲突检查、局部合并、持久化、确认快照及幂等确认状态；与既有 v3 课程 JSON 分离。
- 修改 `ai_planner.py`、`server.py`：在原对话中请求结构化草稿补丁，搜索证据增量补充；新增草稿读取与确认导入 API，确认后复用原生成器、校验器及 `PlanLibrary.apply_plan`，失败保留草稿。
- 修改 `static/ai.js`、`static/style.css`：可折叠计划侧栏与小屏幕抽屉，展示部分草稿、阶段、任务、时间、来源、未解决问题、更新高亮、确认与导入状态；侧栏通过独立草稿 API 在检索期间轮询。
- 新增 `tests/test_interactive_planning.py`、`tests/test_ai_sidebar.py`；更新 `tests/test_plan_draft.py`，覆盖多轮反馈、时间重排、侧栏渲染、检索期间部分草稿、确认后自动导入、重复确认、失败重试和本机 HTTP 端到端流程。
- 更新 `README.md`、`USER_GUIDE.md`、`CHANGELOG.md`、`.gitignore`；新增 `RELEASE_NOTES_1.3.0.md`、`docs/release_1.3.0.md`；更新 `packaging/build_deb.py`、`packaging/build_release.py`、`packaging/install_user.py`，纳入 `plan_draft.py` 并升级发行版本。
- 最后补充了已有 `plan_id` 更新确认保护，涵盖用户填写及自动生成的 ID；涉及 `ai_planner.py`、`static/ai.js`、使用文档、`tests/test_interactive_planning.py` 与侧栏渲染测试。
- 周次映射补充按阶段预计小时数分配，修改 `ai_planner.py` 并扩展 `tests/test_interactive_planning.py`。
- 阶段验证：草稿模块 3/3、AI 集成与草稿模块 15/15、新增交互和侧栏 6/6 通过；最终 `python3 -m unittest discover -s tests -q` 44/44 通过，Python 语法检查与 `git diff --check` 通过。1.3.0 的 `.deb` 和源码包构建成功，`sha256sum -c SHA256SUMS` 通过；包内有新草稿模块和通用示例，没有个人计划、数据库、AI 配置、对话或草稿数据。外部 SearXNG/Brave 与真实模型未在本轮使用个人服务进行联机验收，交互链路由 Mock 服务和本机 HTTP 测试覆盖。

### 1.2.0：现有 AI 对话接入双层学习资源检索

- 新增 `learning_resources.py`：SearXNG 默认搜索、Brave 显式启用与失败回退、统一结果结构、有限重试/并发/预算、系统课程与任务级检索、证据去重和缓存、受限网页读取与公网地址检查。
- 修改 `ai_planner.py`、`server.py`、`static/ai.js`：在原 AI 对话中接入工具调用和不支持工具时的兼容检索；保留多轮约束与证据；增加连接测试、搜索状态和取消操作；生成草稿时只接受可追溯链接并复用既有 v3 校验与导入流程。
- 更新 `tests/test_ai_planner.py`，新增 `tests/test_learning_resources.py`，覆盖搜索路由、密钥隔离、工具调用、降级、资源证据、私有地址拦截、JSON 修正及原计划导入回归。
- 更新 `README.md`、`USER_GUIDE.md`、`CHANGELOG.md`；新增 `RELEASE_NOTES_1.2.0.md`、`docs/release_1.2.0.md`；更新 `packaging/build_deb.py`、`packaging/build_release.py`、`packaging/install_user.py`，纳入新模块并升级发行版本。
- 验证结果：搜索模块阶段 6/6、AI 流程阶段 10/10；最终 `python3 -m unittest discover -s tests -v` 32/32 通过，含既有示例计划、导入与显示回归。Python 语法检查和 `git diff --check` 通过；JavaScriptCore 成功解析并渲染 AI 页面。本机 HTTP 冒烟测试成功读取 AI 页面资源和默认配置。1.2.0 的 `.deb` 和源码包构建成功，文件清单未见个人计划、数据库或密钥文件，`sha256sum -c SHA256SUMS` 通过。本机未安装 Docker/Podman，也未配置 SearXNG 或 Brave Key，因此本轮没有真实外部搜索连接测试；界面提供连接测试入口。

### 建立持续开发日志

- 更新 `README.md`，说明每次项目变更都必须同步记录在本日志，并区分开发日志与版本摘要。
- 新增 `log.md` 和 `AGENTS.md`，让后续开发继续遵守记录规则。
- 更新 `packaging/build_release.py` 和 `packaging/build_deb.py`，将开发日志纳入源码包与安装包，并将开发约定纳入源码包。
- 验证：`python3 -m unittest discover -s tests -v` 全部 21 项通过；打包脚本通过 Python 语法检查，`git diff --check` 无空白错误。源码包包含 `AGENTS.md` 和 `log.md`，安装包包含 `log.md`；校验和检查通过，文件清单未见个人数据文件。

### 既有里程碑补录

以下内容依据现有 `CHANGELOG.md`、`README.md` 与发行说明整理；原始完成日期未单独记录，不作为逐次变更明细。

- 1.0.0：桌面程序、通用示例计划、v3 JSON 导入与计划库、日历与每日任务、计时、步骤打卡、证据、验收、备份。
- 1.1.0：OpenAI 兼容 API 的 AI 规划、计划草稿生成与确认导入；联网检索可选择 Brave Search 或 SearXNG。
