"""Isolated F2 adapter: return a single post's media list, without downloading files."""
from __future__ import annotations

import asyncio
import contextlib
import http.cookiejar
import io
import json
import sys
from pathlib import Path
from urllib.parse import urlsplit


def https(url):
    return 'https://'+url[7:] if url.startswith('http://') else url


def pick(urls):
    # The resulting URLs are checked against the application's CDN allowlist too.
    candidates=[https(u) for u in urls if isinstance(u,str) and u.startswith(('https://','http://'))]
    return next((u for u in candidates if urlsplit(u).hostname and 'douyinvod.com' in urlsplit(u).hostname),None) or next(iter(candidates),None)


def douyin_files(detail):
    key=detail.get('aweme_id');video=detail.get('video') or {};files=[]
    for image in detail.get('images') or []:
        original=pick(image.get('url_list') or [])
        if not original:continue
        files.append({'kind':'image','original_url':original,'preview_url':original,
                      'width':image.get('width') or 1,'height':image.get('height') or 1})
    if files:return files
    bitrates=[b for b in video.get('bit_rate') or [] if b.get('play_addr',{}).get('url_list') and not b.get('is_h265')]
    best=max(bitrates,key=lambda b:b.get('bit_rate') or 0,default={})
    addr=best.get('play_addr') or video.get('play_addr') or {}
    original=pick(addr.get('url_list') or [])
    if not original:return []
    cover=video.get('cover') or video.get('origin_cover') or {}
    return [{'kind':'video','original_url':original,'preview_url':pick(cover.get('url_list') or []),
             'video_id':key,'title':detail.get('desc') or '',
             'duration':(video.get('duration') or detail.get('duration') or 0)/1000,
             'width':addr.get('width') or video.get('width') or 16,
             'height':addr.get('height') or video.get('height') or 9,
             'estimated_bytes':addr.get('data_size'),'direct_video':True}]


async def extract(platform,key,root):
    if platform!='douyin':raise ValueError('Unsupported F2 adapter')
    from f2.apps.douyin.crawler import DouyinCrawler
    from f2.apps.douyin.model import PostDetail
    jar=http.cookiejar.MozillaCookieJar(str(root/'cookies'/'douyin.txt'))
    if Path(jar.filename).is_file():jar.load(ignore_discard=True,ignore_expires=False)
    cookies={cookie.name:cookie.value for cookie in jar}
    kwargs={'cookie':'; '.join(f'{k}={v}' for k,v in cookies.items()),'timeout':15,'max_retries':1}
    async with DouyinCrawler(kwargs) as crawler:
        data=await crawler.fetch_post_detail(PostDetail(aweme_id=key,msToken=cookies.get('msToken','')))
    detail=(data or {}).get('aweme_detail') or {}
    if str(detail.get('aweme_id'))!=str(key):
        raise ValueError('抖音没有返回该作品，可能已删除或需要更新会话。请换用当前可打开的分享链接。')
    return douyin_files(detail)


def main():
    platform,key,root,output=sys.argv[1:]
    try:
        # Third-party diagnostic logs must not expose session headers or signed API URLs.
        with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
            files=asyncio.run(asyncio.wait_for(extract(platform,key,Path(root)),timeout=60))
        Path(output).write_text(json.dumps(files,ensure_ascii=False),'utf-8')
    except Exception as error:
        print('F2 解析失败：'+('该作品没有返回可下载资源，请更新会话或分享链接。' if isinstance(error,ValueError) else type(error).__name__),file=sys.stderr)
        sys.exit(1)


if __name__=='__main__':main()
