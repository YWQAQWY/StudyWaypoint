# StudyWaypoint 1.4.0

桌面工作区改用可折叠左侧导航、统一卡片和表单样式，并增加浅色、深色与跟随系统主题。菜单状态、主题、AI 计划栏宽度及阶段折叠状态会在本机恢复。导航、页面和计划更新使用克制的状态动画；系统偏好减少动态效果时会降低动画。

AI 规划继续使用同一聊天、搜索 Agent 和结构化 PlanDraft。聊天区与计划区可拖动分栏；阶段更新保留稳定 ID 与滚动位置，确认按钮固定在计划栏底部。兼容服务商支持流式 Chat Completions 时，普通回复和工具调用的文本可增量显示；拒绝流式请求时回退普通回复。

用户明确确认后仍由原有 v3 校验和导入模块处理。公开发行包只含通用示例，不含个人课程、数据库、对话或密钥。SearXNG 需用户自备实例，Brave 需主动启用。真实模型与外部搜索连接请在自己的配置下测试。

发行文件：`studywaypoint_1.4.0_all.deb`、`StudyWaypoint-1.4.0-source.zip`、`SHA256SUMS`，另增 `StudyWaypoint-1.4.0-windows-x64.zip` 及其 `.sha256`。Windows ZIP 自带 Python 运行时，以 Edge 应用窗口或默认浏览器运行；使用方法见 [Windows 使用指南](WINDOWS_GUIDE.md) 与 [完整使用指南](USER_GUIDE.md)。
