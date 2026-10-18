# 图片与视频下载

中文 | [English](README.en.md)

下载社交媒体上的图片和视频的本地工具，粘贴链接即可自动识别来源，提供内容预览、选择下载、批量保存和历史记录功能，支持 Instagram、X（Twitter）、小红书、抖音、TikTok、哔哩哔哩、YouTube、微博和 Pinterest 九个平台。

A local tool for downloading images and videos from social media. Paste a link to automatically detect its source, preview content, choose items to download, save in batches, and view download history. Supports Instagram, X (Twitter), Xiaohongshu, Douyin, TikTok, Bilibili, YouTube, Weibo, and Pinterest.

## 功能

- 自动识别 Instagram、X / Twitter、小红书、抖音、TikTok、哔哩哔哩、YouTube、微博和 Pinterest。
- 一次粘贴多条链接，也能从分享文案中提取链接，不用手动选择平台。
- 先看预览，点击保存单项，或批量选择后一起保存；未选中的原文件不会写入下载目录。
- 支持图片和视频，视频可自动合并画面与音轨，显示解析用时、数量和下载进度。
- 保留图片比例的瀑布流、彩色平台图标、可滚动历史记录、跟随系统的明暗配色。
- 本地查看原图、播放已保存视频、打开文件夹、打包导出和清理预览缓存。

当前流程是：**粘贴 → 自动解析预览 → 点选或全选 → 保存**。目前处理具体帖子，不包含整账号、收藏夹或播放列表批量抓取。

## 启动

macOS 双击本目录的 `启动.command`。首次运行安装依赖，保持终端打开；Ctrl+C 停止服务。需要 Python 和可访问目标平台的网络。

手动启动（Python 3.11+ 推荐，当前本机 Python 3.10 仍可运行）：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python server.py --open
```

抖音使用独立 F2 引擎。首次运行“安装备用引擎.command”安装它（需要 Python 3.11+），然后仍在同一个页面粘贴链接。安装器使用项目中固定提交的 F2 源码包。

Windows 可用 `.venv\Scripts\python.exe` 替换上述 Python 路径启动核心服务；一键启动和抖音引擎安装脚本面向 macOS / Unix，Windows 尚未完成整体验收。

页面地址：http://127.0.0.1:8767 。端口冲突可使用 `--port 8768`；`--data-dir /private/tmp/下载验收` 可隔离测试数据，默认使用项目自己的 `data/` 和 `下载/`。

## 平台与验收

实测日期：2026-10-18。这些是公开样例在本机的结果，不能代表平台所有内容都能下载。页面平台标签可查看当前实测状态。

| 平台 | 本次实际验证 | 状态 |
|---|---|---|
| Instagram | 单图、轮播图解析和点选原文件保存 | 已通过 |
| X / Twitter | 4 图帖子只选 1 张保存 | 已通过 |
| 小红书 | 带有效分享参数和本地会话的 4 图笔记，预览 4 张，只保存第 3 张 | 已通过 |
| Pinterest | 图片预览、选中保存 | 已通过 |
| 微博 | 公开帖子图片预览、选中保存 | 已通过 |
| YouTube | 封面、时长、选中视频保存、音视频合并、页面播放 | 已通过 |
| 哔哩哔哩 | 封面、时长、视频保存与音视频合并 | 已通过 |
| TikTok | 图集 4/4 保存通过；完整视频曾保存成功，但发布前复测遭源站 429/503 限流，视频当前不保证成功 | 图集通过，视频受限 |
| 抖音 | 最新 F2 解析当前有效作品，封面预览和选中视频保存 | 已通过 |

发布前本轮的逐项结果见 [2026-10-18 验证记录](docs/verification-2026-10-18.md)。具体开源项目、固定版本、候选取舍、此前测试样例见 [开源项目与验证.md](开源项目与验证.md)。官方源代码发行包集中放在 `开源参考/`，来源与 SHA256 在 `开源参考/sources.json`。

## 使用

1. 直接粘贴多条分享链接或包含链接的分享文案，自动开始解析。不需要选平台。
2. 图片和视频封面按原帖顺序进入瀑布流，保留原比例；编号表示它在原帖中的顺序。视频另显示时长和解析所得清晰度。
3. **点击图片或视频封面才保存该项文件**。放大按钮在未保存时只看预览，不会开始下载完整视频。
4. “批量选择 → 保存所选”可保存多项。“已保存”中可查看原图、播放已保存视频、打开文件夹，或打包已保存内容。
5. 进度显示预览数 / 总数、解析用时、选中保存数及字节进度。视频下载后可能还需合并音轨与画面。
6. 支持小红书、抖音、TikTok、B站、Pinterest 的常见分享短链接路由；短链接是否可解析仍取决于平台返回，未对所有短链形式作成功承诺。

只处理具体帖子，不会自动抓取整个账号、收藏夹或播放列表。画质取决于平台当前会话提供的资源，不保证等同上传前母版；原画面自带的作者水印保留。视频优先选择 MP4 视频流和 M4A 音轨并由 FFmpeg 合并；源站限制会影响可用版本。

## 存储

- 解析读取清单、尺寸、时长和资源地址，不把完整视频、整组图片写入 `下载/`。
- 预览需要网络传输，优先取小图或封面，生成最长边 560 像素 JPEG 到 `data/previews/`。小红书低质占位预览不会使用，改从清晰显示图生成小预览。没有合适小图时可能临时读取较大图片响应；处理后释放，仍只留下小预览。
- 未选中的文件不会完整落盘。视频格式清单作为少量 JSON 保存在 `data/video-info/`，用于点选后的下载。
- 底部显示预览缓存大小，可清理；最多 100 MB、保留 24 小时。缓存清理保留已保存文件、历史和会话。浏览器显示图片也占一定内存。
- 点选后下载到 `下载/日期/平台_帖子编号_记录编号/`。视频中间文件位于 `data/video-parts/`，本次成功或失败后清理。
- 图片单文件上限 512 MB；视频引擎单流上限 2 GB。批量 ZIP 最多 300 项、总计 512 MB，大视频可直接打开下载文件夹。
- 旧版已下载文件不迁移、不删除，旧记录会备份并兼容。

## 本地会话

新安装的项目不包含任何人的 Cookie。内容需要登录时，程序使用自己配置的 `cookies/平台标识.txt` Netscape Cookie 文件，例如：

```text
cookies/xiaohongshu.txt
cookies/douyin.txt
cookies/weibo.txt
cookies/instagram.txt
cookies/twitter.txt
```

程序只读取手动配置的平台会话文件，不会自动导出浏览器 Cookie。会话失效后需要更新；小红书建议粘贴带 `xsec_token` 的完整分享链接。本机测试使用的会话不会随源码发布。

实际 Cookie、原文件、运行数据、虚拟环境均由 `.gitignore` 排除；发布源码时不要手工把这些目录加入压缩包。平台会话不发送到第三方解析网站。

## 实现和开源来源

- `platforms.py`：9 个平台的 URL 识别、规范化、分享短链的受限跳转。
- `worker.py` / `site_adapters.py`：元数据及小预览，小红书图文与 TikTok 图集适配。
- `tiktok_embed.py`：公开单条 TikTok 视频的官方嵌入页备用解析，主播放地址 403/404 时才尝试；503 过载时停止请求。
- `f2_worker.py` / `f2_bridge.py`：独立 Python 3.11+ 引擎仅提取抖音媒体清单，选中后交给同一下载队列。
- `video_engine.py`：yt-dlp 元数据和仅对选中项的视频下载，使用 imageio-ffmpeg 提供本地 FFmpeg。
- `downloader.py`：持久队列、缓存、真实进度、图片保存、旧记录兼容。
- `server.py`：仅监听本机，提供选择保存、打包、原文件流式读取及视频 Range 请求。
- `web/`：原生 HTML / CSS / JavaScript，系统明暗主题、按原比例瀑布流、品牌色图标。

使用 [Instaloader](https://github.com/instaloader/instaloader)（MIT）、[gallery-dl](https://github.com/mikf/gallery-dl)（GPL-2.0）、[yt-dlp](https://github.com/yt-dlp/yt-dlp)（Unlicense）作为安装依赖。源代码归档保留上游许可，详见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。平台图形来自 [Simple Icons](https://github.com/simple-icons/simple-icons)（CC0），另加背景和品牌色；FFmpeg 二进制的许可信息随 imageio-ffmpeg 分发。

本项目自行编写的代码使用 [MIT 许可](LICENSE)；第三方代码及归档适用各自上游许可。

## 检查

```bash
.venv/bin/python -m unittest discover -s tests -v
node --check web/app.js
```

真实联网验证使用独立临时数据目录，没有把测试文件混入用户下载记录。
