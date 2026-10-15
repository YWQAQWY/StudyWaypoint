# StudyWaypoint 开发日志

本文件记录逐次开发变更。每次新增、修改或删除项目内容时，在同一批变更中补充一条记录；写明日期、做了什么、涉及哪些文件，以及验证结果。不得记录个人计划、学习数据或 API 密钥。

## 2026-10-15

### 1.4.0：桌面工作区 UI 与 AI 规划交互升级

- 修改 `static/index.html`、`static/app.js`、`static/style.css`：左侧可折叠导航、单一滑动选中背景、工作区顶部工具栏、统一浅色/深色 Design Tokens 与 Motion Tokens、主题及导航状态本机保存、键盘与减少动态效果支持；统一日历、每日任务和设置页面的卡片与表单样式。
- 修改 `static/ai.js`：可拖动 AI 聊天/PlanDraft 双栏，独立消息与草稿滚动区、固定确认操作区；按稳定阶段/任务 ID 局部更新，保留折叠和滚动位置；展示生成、校验、导入、成功或失败状态。模型与搜索配置移至现有“设置与备份”页面，未配置模型时仍可从 AI 页面设置。
- 修改 `ai_planner.py`：为现有 OpenAI 兼容聊天加入 SSE 增量读取、工具调用分块聚合、取消与大小限制；提供本机活动文本供现有聊天窗口轮询显示；服务商拒绝流式请求时回退现有普通 Chat Completions。既定 v3 Schema、PlanDraft 确认快照和原计划导入器未改动。
- 修改 `server.py`、`static/app.js`、`static/ai.js` 和 `.gitignore`：新增私有 `ui_preferences.json` 与本机布局偏好 API，原子写入主题、导航、计划栏和阶段折叠状态，并在页面加载时注入，解决桌面窗口每次启动使用新端口导致浏览器存储无法恢复的问题。修复已收起的计划栏在重启后被草稿自动展开；页面切换时保留聊天和草稿阅读位置。
- 修改 `static/app.js`、`static/ai.js`：快速连续切页时取消上一次页面动画；草稿阶段和任务重复重排时取消旧位移动画，移除节点时清理对应动画。
- 新增 `tests/test_ai_stream.py`，扩展 `tests/test_ai_sidebar.py`；更新 `CURRENT_UI.txt`、`README.md`、`USER_GUIDE.md`、`CHANGELOG.md`。更新 `packaging/build_deb.py`、`packaging/build_release.py`、`packaging/install_user.py` 并新增 `RELEASE_NOTES_1.4.0.md`、`docs/release_1.4.0.md`，将此次界面与文档纳入 1.4.0 发行。
- 新增 `tests/test_ui_preferences.py`，验证字段拒绝、0600 文件权限、同一数据目录换端口恢复和跨站来源拒绝；更新 `README.md`、`USER_GUIDE.md`、`CURRENT_UI.txt` 与发行说明，标注布局偏好文件及发行排除要求。
- 修改 `server.py` 与 `tests/test_ui_preferences.py`：布局偏好文件损坏时回到默认界面设置，避免非核心配置损坏阻止应用启动；下一次正常保存会覆盖无效内容。
- 阶段验证：原有 44/44 回归通过；新增流式回复测试 3/3、布局偏好测试 2/2 通过。隔离数据目录下的本机浏览器实测导航收展、主题、AI 计划栏拖动与收展、阶段折叠、聊天和确认按钮；换端口 8879 → 8881 后仍恢复深色主题与展开导航。最终 `python3 -m unittest discover -s tests -q` 49/49 通过；Python 编译、JavaScriptCore 语法检查和 `git diff --check` 通过。1.4.0 `.deb` 与源码包构建成功，SHA-256 校验通过，包内只有通用示例，无数据目录、个人计划、布局偏好、数据库、备份或密钥文件。未进行可靠的逐帧性能分析，也未使用真实外部模型或搜索服务验收。

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
