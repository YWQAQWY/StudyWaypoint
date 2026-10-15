# StudyWaypoint Windows x64 便携版

本包是现有 StudyWaypoint 1.4.0 的 Windows 增量发行形式，包含相同的本地服务、页面、v3 计划格式和导入逻辑。它是解压即用的便携包，不是 `.exe` 安装程序。包含官方 Windows x64 Python 嵌入运行时和时区数据；不需要另外安装 Python、GTK 或 WebKitGTK。主窗口使用 Microsoft Edge 的应用窗口模式；未找到 Edge 时在默认浏览器打开。

## 安装和启动

1. 下载 `StudyWaypoint-1.4.0-windows-x64.zip`，解压到一个可写位置，例如 `C:\Apps\StudyWaypoint`。请不要在 ZIP 压缩包内直接运行，也不要只复制其中的 `.cmd` 文件。
2. 双击解压目录中的 **`Start StudyWaypoint.cmd`**。首次启动可能稍慢；命令窗口会显示本地地址和数据位置。Edge 应用窗口关闭后，服务会自动停止。请保留命令窗口，勿在使用时关闭。
3. 如果电脑没有 Edge，应用在默认浏览器中打开；使用结束后回到命令窗口按 Enter 停止服务。如果浏览器没有自动打开，把命令窗口显示的 `http://127.0.0.1:端口/` 地址复制到浏览器。

程序只监听 `127.0.0.1`，每次使用空闲端口。首次启动展示通用一周示例，**发行包不含私人计划或学习记录**。

可选：在 PowerShell 中核对下载文件：

```powershell
(Get-FileHash .\StudyWaypoint-1.4.0-windows-x64.zip -Algorithm SHA256).Hash.ToLower()
Get-Content .\StudyWaypoint-1.4.0-windows-x64.zip.sha256
```

两处哈希应一致。运行环境需要 Windows 10/11 x64。压缩包没有代码签名；如系统或组织策略阻止运行，请按本机安全策略检查来源与校验值，不要关闭安全防护。

## 数据、升级和删除

- 用户计划、计时、证据、AI 配置和对话默认保存到 `%LOCALAPPDATA%\StudyWaypoint\`，与解压目录分离。关闭并重新打开应用会恢复这些数据；复制新的版本到另一个目录不会自动删除它们。
- 升级时先关闭旧版窗口和命令窗口，再解压新包并从新目录启动。不要把旧版目录中的 `data/`、配置文件或数据库复制进发行目录。
- 在“设置与备份”可逐个计划导出备份、导入 v3 JSON、恢复备份。换电脑时请先导出计划 JSON 和相应备份，再在新电脑导入计划并恢复备份。AI 对话和密钥不在课程备份中。
- 只删除解压目录不会清除用户数据。如需完全删除，请在备份后自行删除 `%LOCALAPPDATA%\StudyWaypoint\`。
- 高级用法：启动前设置 `TRACKER_DATA_DIR` 可改用其他数据目录；请选当前账户专用的本地目录。

## 使用计划和 AI 规划

“设置与备份”中的计划库支持预览、导入与切换 UTF-8 v3 JSON 计划。内置 `app\examples\sample_plan_v3.json` 是完整可用的通用模板；导入自己的新计划时先改 `plan_id`。格式、字段和具体操作见 [完整使用指南](USER_GUIDE.md)。

AI 对话需要用户自行配置 OpenAI 兼容 API；联网搜索默认需要用户提供可用的 SearXNG JSON 实例，Brave 需主动启用并配置 Key。Windows 包不内置搜索服务，也不含任何 API Key。AI 规划草稿经明确确认后才会校验并自动导入。

## 常见问题

- **双击后立刻关闭或出现错误：**在解压目录打开 PowerShell，运行 `& '.\Start StudyWaypoint.cmd'`，查看命令窗口的具体错误。检查是否完整解压、系统为 x64、`runtime\python.exe` 和 `app\windows_launcher.py` 都存在。
- **窗口没有打开：**查看命令窗口中的本地地址，在浏览器中手动打开；确认安全软件未拦截本机回环连接。
- **关闭 Edge 后命令窗口未退出：**按 `Ctrl+C` 停止服务。其他浏览器模式按 Enter。
- **数据没有出现：**确认是否切换到其他计划，并检查 `%LOCALAPPDATA%\StudyWaypoint\` 或自定义的 `TRACKER_DATA_DIR`。可以用旧版备份恢复。
- **联网搜索失败：**检查 SearXNG 地址、JSON 输出与连接测试；Brave Key 和模型 API Key 分别配置。普通本地学习功能不依赖联网搜索。

本包未在 Windows 真机上完成端到端验收；构建产物、运行时文件、Python 模块和本地服务已做自动化与兼容性检查。若发现 Windows 特有问题，请附命令窗口输出和 Windows 版本，不要附 API Key 或私人计划。
