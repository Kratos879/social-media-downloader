# Social Media Downloader

[中文](README.md) | English

A local tool for downloading images and videos from social media. Paste a link to automatically detect its source, preview content, choose items to download, save in batches, and view download history. Supports Instagram, X (Twitter), Xiaohongshu, Douyin, TikTok, Bilibili, YouTube, Weibo, and Pinterest.

## Features

- Automatically detects Instagram, X / Twitter, Xiaohongshu, Douyin, TikTok, Bilibili, YouTube, Weibo, and Pinterest links.
- Accepts multiple links or share text in a single paste.
- Shows previews before saving. Download one item or select several; unselected originals are not written to the download folder.
- Downloads images and videos, with automatic video/audio merging where needed.
- Shows parsing time, preview counts, saved counts, and byte progress.
- Keeps original image proportions in a masonry layout, with platform icons, scrollable history, and system light/dark themes.
- Opens saved files locally, plays saved videos, exports selected files as ZIP, and clears preview caches.

The workflow is **paste → automatic previews → select items → save**. The app currently handles individual posts. Account archives, saved collections, and playlists are not implemented.

## Run locally

Use a network connection that can access the target platform. **Python 3.11+ is recommended** and is required for the separate Douyin/F2 engine.

On macOS, double-click `启动.command` in the project folder. The first launch installs dependencies and attempts to install the optional Douyin engine. Keep the terminal open; press Ctrl+C to stop.

Manual setup:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python server.py --open
```

Open <http://127.0.0.1:8767>. The server listens on the local loopback interface only.

For Douyin, also run:

```bash
bash 安装备用引擎.command
```

The installer downloads a pinned commit from the official F2 repository and verifies its SHA256 checksum. An internet connection is required for the initial installation.

On Windows, use `.venv\Scripts\python.exe` for the core service. The bundled launcher and Douyin setup scripts target macOS / Unix; the complete Windows workflow has not been verified.

## Verified scope

Live tests on macOS, including pasting links in the browser and saving selected files, were repeated on **2026-10-18**. Passing samples do not mean every link or media type on a platform is supported.

| Platform | Verified content | Session requirements |
|---|---|---|
| Instagram | Public photos and photo carousels | Public samples worked without login; restricted posts may need a session |
| X / Twitter | Public photo posts, including selective saving | Public samples worked without login |
| Xiaohongshu | Image notes with selective saving | Valid full share link and local session required |
| Douyin | Individual public video | F2 and a valid session required; tested with visitor cookies |
| TikTok | All four images saved; a complete video passed earlier, but its pre-publication retest failed with upstream 429/503 responses | Photo posts passed; video availability is currently limited and is not guaranteed |
| Bilibili | Public video with audio/video merging | Restricted content or some quality levels may require a session |
| YouTube | Public video with audio/video merging | Restricted content may require a session |
| Weibo | Public photo post | Some posts require a session |
| Pinterest | Image Pin | Public sample worked without login |

Mixed photo/video carousels, Live Photos, and live streams have not been fully verified. Quality depends on the files returned by the platform for the current session. The app does not promise the pre-upload master file or remove watermarks embedded in the content.

## Local sessions

The repository **does not include anyone's cookies**. When a platform requires authentication, create a local directory and provide your own valid Netscape-format cookie file:

```bash
mkdir -p cookies
```

```text
cookies/xiaohongshu.txt
cookies/douyin.txt
cookies/weibo.txt
cookies/instagram.txt
cookies/twitter.txt
cookies/bilibili.txt
```

The app reads only the platform files you configure. It does not automatically export browser credentials or send sessions to third-party parsing services. Refresh expired sessions when needed. Xiaohongshu links should include the full `xsec_token` share parameter.

Cookie files, downloads, runtime data, and virtual environments are excluded from Git commits.

## Storage

- Originals go to `下载/date/platform_post_record/`; history and metadata go to `data/`.
- Parsing stores small previews with a maximum edge of 560 pixels. It does not save complete videos or every original image. When a small preview is unavailable, a larger image response may be read temporarily to generate a thumbnail.
- Preview caches are limited to 100 MB and 24 hours. Clearing previews preserves saved originals.
- Temporary video fragments are removed after the current task succeeds or fails.
- Limits: 512 MB per image, 2 GB per video stream, and 300 files / 512 MB per ZIP export. Open the download folder directly for large videos.
- Use `--port 8768` for another port or `--data-dir /path/to/test-data` for isolated data.

## Upstream projects

Built with [Instaloader](https://github.com/instaloader/instaloader), [gallery-dl](https://github.com/mikf/gallery-dl), [yt-dlp](https://github.com/yt-dlp/yt-dlp), [F2](https://github.com/Johnserf-Seed/f2), and small platform adapters. FFmpeg is supplied by imageio-ffmpeg. Platform artwork comes from [Simple Icons](https://github.com/simple-icons/simple-icons).

Dependencies are installed from their upstream sources. The Douyin installer pins the F2 commit and verifies its SHA256 checksum. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for upstream projects and licenses.

Original code written for this project is available under the [MIT license](LICENSE). Third-party code remains under its respective upstream license.

## Checks

```bash
.venv/bin/python -m unittest discover -s tests -v
node --check web/app.js
```

Live tests use separate temporary directories. Availability depends on valid links, sessions, network access, and platform changes.
