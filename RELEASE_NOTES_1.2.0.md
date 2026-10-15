# StudyWaypoint 1.2.0

这一版让现有 AI 规划对话按需寻找系统课程、具体章节、视频和练习。搜索默认使用用户自行部署或控制的 SearXNG；Brave Search 只有在主动启用并填写 Key 后才会调用，失败时尝试回退 SearXNG。搜索证据带来源与核实状态，计划中的链接必须能追溯到搜索结果或用户提供的网址。

生成仍使用既有 v3 JSON 格式、校验器和计划导入流程。用户确认目标后才生成草稿，预览并确认后才导入。现有格式要求每周两条 LeetCode 链接和每日阅读资源；如果缺少可追溯网址，生成会失败，不会虚构链接。

SearXNG 不随应用安装。请按 [完整使用指南](USER_GUIDE.md) 启用 JSON 搜索接口并在 AI 规划页测试连接。普通 AI 对话无需搜索服务。

发行文件：`studywaypoint_1.2.0_all.deb`、`StudyWaypoint-1.2.0-source.zip`、`SHA256SUMS`。公开包仅含通用示例计划，不含个人课程、学习记录或 API Key。
