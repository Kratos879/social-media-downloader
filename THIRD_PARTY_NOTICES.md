# Third-party notices / 第三方来源

This repository installs third-party engines as dependencies and includes unmodified source archives for reference or installation. Each upstream project's own license applies to its code. Full license texts remain inside the corresponding source archives or installed distributions.

本仓库通过依赖调用第三方引擎，并保留未修改的源码归档用于参考或安装。各上游代码适用其各自许可，完整许可文本保留在相应源码包或安装包中。

| Project | Version or source | Upstream license | Use |
|---|---|---|---|
| [Instaloader](https://github.com/instaloader/instaloader) | 4.15.4 | MIT | Instagram metadata |
| [gallery-dl](https://github.com/mikf/gallery-dl) | 1.32.17 | GPL-2.0 | Image metadata through a subprocess |
| [yt-dlp](https://github.com/yt-dlp/yt-dlp) | 2026.8.19 | Unlicense | Video metadata, downloading, and merging |
| [F2](https://github.com/Johnserf-Seed/f2) | f6be8c0ffba9a127075bbeafe4838716650b6325 | Apache-2.0 | Optional isolated Douyin metadata engine |
| [Pillow](https://github.com/python-pillow/Pillow) | See requirements.txt | MIT-CMU | Image previews and validation |
| [imageio-ffmpeg](https://github.com/imageio/imageio-ffmpeg) | 0.6.0 | BSD-2-Clause | FFmpeg runtime provider |
| [FFmpeg](https://ffmpeg.org/) | Supplied by imageio-ffmpeg | Depends on the supplied build; see its bundled notices | Video/audio processing; binaries are not committed here |
| [curl-cffi](https://github.com/lexiforest/curl_cffi) | 0.16.3 | MIT | Platform request compatibility |
| [Simple Icons](https://github.com/simple-icons/simple-icons) | Selected SVG icons in web/assets/ | CC0-1.0 | Platform artwork; brand colors/backgrounds added locally |

Archive filenames, original source URLs, and SHA256 values are recorded in [开源参考/sources.json](开源参考/sources.json). Transitive dependencies retain their own notices in their distributions. Brand names and logos belong to their respective owners.
