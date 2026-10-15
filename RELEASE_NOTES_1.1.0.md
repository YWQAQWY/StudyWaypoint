# StudyWaypoint 1.1.0

本版新增“AI 规划”界面。用户可配置个人订阅的 OpenAI 兼容 Chat Completions API 地址、模型与密钥，讨论学习目标并生成 v3 JSON 课程草稿。`https://api.deepseek.com` 只是默认示例，可替换为其他兼容服务的 HTTPS 基础地址。

联网检索可选择 Brave Search API 或自备 SearXNG 实例。Brave 需要单独的 Search API Key；SearXNG 不需要 Brave Key，但实例必须可用并启用 JSON 搜索接口。未配置检索来源时，普通对话仍可使用。生成结果会逐周构建、通过现有 v3 校验器并展示导入差异，由用户确认后才写入计划库。

API 密钥、对话和草稿只存放在用户本机的数据目录中，不打入安装包，也不包含在学习计划备份中。使用 API 可能产生服务商费用。请在导入前核对 AI 生成的资料网址、任务和验收标准。

发行文件：`studywaypoint_1.1.0_all.deb`、`StudyWaypoint-1.1.0-source.zip`、`SHA256SUMS`。
