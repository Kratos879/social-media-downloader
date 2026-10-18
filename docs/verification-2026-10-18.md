# 发布前验证 / Pre-publication verification

日期 / Date: 2026-10-18 (Asia/Shanghai)

在 macOS 的 Ego Lite 中一次粘贴 10 条分享链接，覆盖 9 个平台。页面自动识别来源并建立任务；在独立临时目录中完成预览、界面勾选和实际文件保存，没有使用用户的下载目录存放测试文件。

Ten links covering nine platforms were pasted together in Ego Lite on macOS. The app detected their sources and created jobs automatically. Previewing, UI selection, and saving used a separate temporary data directory.

## 本轮结果 / Results from this run

| 平台 / Platform | 实测内容 / Sample | 实际保存 / Saved output | 结果 / Result |
|---|---|---|---|
| Instagram | Public photo `DeWq0IMzwhS` | JPEG 2363×3147, 1,637,266 bytes | 通过 / Passed |
| X / Twitter | Four-photo post `894001459754180609` | Selected photo 1/4, 560,558 bytes; other originals not saved | 通过 / Passed |
| 小红书 / Xiaohongshu | Four-image note `6ab7ed45000000000a02349a` | Selected photo 3/4, 1080×1440, 279,534 bytes | 通过 / Passed with a valid share link and local session |
| 抖音 / Douyin | Video `7689731341721564658` | 89,361,750 bytes, 4:55.40, video + audio | 通过 / Passed with F2 and visitor cookies |
| TikTok photos | Four-image post `7466527368044088619` | All 4 saved, 2,856,759 bytes total | 有限重试后通过 / Passed after one retry |
| TikTok video | Video `7407465424998157600` | Metadata and cover parsed; original video not saved in this run | 本轮未通过 / Failed in this run: upstream 503; browser also returned 429 |
| 哔哩哔哩 / Bilibili | Video `BV13x41117TL` | 116,649,625 bytes, 9:14.12, video + audio | 通过 / Passed |
| YouTube | Video `jNQXAC9IVRw` | 533,931 bytes, 19.06 seconds, video + audio | 通过 / Passed |
| 微博 / Weibo | Photo post `4323047042991618` | JPEG 1334×750, 174,376 bytes | 通过 / Passed |
| Pinterest | Image Pin `664281013778109217` | JPEG 1080×1920, 198,318 bytes | 通过 / Passed |

- 共选择 13 项，保存成功 12 项；失败的 1 项为 TikTok 视频。9 个平台均有至少一个文件保存成功，这不代表 9 个平台的所有媒体类型都通过。
- 13 items selected, 12 saved. The failed item was the TikTok video. Every platform had at least one saved file; this does not mean every media type passed on every platform.
- 解析完成时原文件数量为 0；未选中的原文件没有保存。X 和小红书均验证了只保存所选图片。
- Parsing produced zero saved originals. Unselected originals were not saved; selective saving was checked on X and Xiaohongshu.
- 保存的图片经 Pillow 校验，视频经 FFmpeg 确认包含画面、声音，并成功解码开头片段。复测前已有下载文件按 SHA256 核对，保持不变。
- Saved images passed Pillow validation. Saved videos had both video and audio streams and decoded successfully for the opening segment. Existing downloads were unchanged by SHA256 comparison.
- 首次选取的一条小红书笔记在浏览器中也无法浏览；换用有效的完整分享链接后通过。TikTok 图集首次请求未返回数据，有限重试后通过。没有把这些失败隐藏为首次成功。
- One initial Xiaohongshu sample was unavailable in the browser as well; a valid full share link passed. The TikTok photo post returned no data initially and passed on a bounded retry.

## 自动检查 / Automated checks

- 30 个单元测试通过 / 30 unit tests passed.
- JavaScript 语法检查通过 / JavaScript syntax check passed.
- 两个启动脚本语法检查通过 / Both launcher scripts passed Bash syntax checks.
- 四个上游源码归档的 SHA256 与记录一致，归档内保留许可文件 / All four source archives matched their recorded SHA256 values and retained upstream license files.

未包含整账号、收藏夹或播放列表抓取；未对私密内容、混合图片视频轮播、Live Photo 或所有分享短链作成功承诺。发布文件不包含 Cookie、测试媒体和个人历史记录。

Account archives, saved collections, and playlists are not implemented. Private content, mixed photo/video carousels, Live Photos, and every short-link variant are not guaranteed. Cookie files, test media, and personal history are excluded from publication.
