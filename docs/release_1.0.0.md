# 1.0.0 本地构建与 GitHub 上传

公开源码在 `StudyWaypoint/`；其中只有通用一周示例，没有个人课程。先在源码根目录运行：

```bash
python3 -m unittest discover -s tests -v
python3 packaging/build_release.py
cd ..
sha256sum -c SHA256SUMS
```

发行文件位于源码目录的上一级：`studywaypoint_1.0.0_all.deb`、`StudyWaypoint-1.0.0-source.zip`、`SHA256SUMS`。检查压缩包和安装包只包含应用、通用示例和文档，不应含 `data/`、SQLite 数据库、个人课程或备份。

若要把源码目录作为新仓库上传，可在该目录执行以下命令；先在 GitHub 创建空仓库，并将占位 URL 替换为实际地址：

```bash
cd StudyWaypoint
git init -b main
git add .
git status --short
git commit -m "Release v1.0.0"
git remote add origin YOUR_REPOSITORY_URL
git push -u origin main
git tag v1.0.0
git push origin v1.0.0
```

然后在该仓库创建 `v1.0.0` Release，上传上述三个发行文件，使用 `RELEASE_NOTES_1.0.0.md` 作为说明。用户指南已包含在源码包和 Debian 包中。公开上传前请再检查 `git status` 与待上传文件列表。

Ubuntu/Debian 安装命令：`sudo apt install ./studywaypoint_1.0.0_all.deb`。不使用管理员权限时，可从源码执行 `python3 packaging/install_user.py`，此方式不注册 Debian 系统软件包。
