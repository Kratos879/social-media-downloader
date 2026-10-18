"""Bounded CDN requests and small preview images. Originals are saved on selection only."""
from __future__ import annotations

import http.cookiejar
import io
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import requests
from PIL import Image, ImageOps

USER_AGENT = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36'
CDN_DOMAINS = ('twimg.com','cdninstagram.com','fbcdn.net','pinimg.com','xhscdn.com','xhscdn.net',
               'sinaimg.cn','sinaimg.com','weibocdn.com','hdslb.com','bilivideo.com',
               'ytimg.com','ggpht.com','googlevideo.com','douyinpic.com','douyincdn.com',
               'douyinvod.com','byteimg.com','pstatp.com','tiktokcdn.com','tiktokcdn-us.com',
               'tiktokcdn-eu.com','tiktok.com','tiktokv.com','ibytedtos.com','byteoversea.com')


def allowed_media_url(url):
    try:
        parsed = urlsplit(url)
        host = (parsed.hostname or '').lower()
        return parsed.scheme == 'https' and not parsed.username and not parsed.password and parsed.port in (None,443) and (
            any(host == domain or host.endswith('.'+domain) for domain in CDN_DOMAINS))
    except (ValueError, TypeError):
        return False


def session_for(root, platform):
    session = requests.Session()
    session.headers['User-Agent'] = USER_AGENT
    referers={'bilibili':'https://www.bilibili.com/','xiaohongshu':'https://www.xiaohongshu.com/',
              'weibo':'https://weibo.com/','douyin':'https://www.douyin.com/',
              'tiktok':'https://www.tiktok.com/','pinterest':'https://www.pinterest.com/'}
    if platform in referers:session.headers['Referer']=referers[platform]
    cookie_file = Path(root) / 'cookies' / f'{platform}.txt'
    if cookie_file.is_file():
        jar = http.cookiejar.MozillaCookieJar(str(cookie_file))
        jar.load(ignore_discard=True, ignore_expires=False)
        # Requests sends cookies only to the domains for which they were issued.
        session.cookies.update(jar)
    return session


def open_media(session, url):
    for _ in range(5):
        if not allowed_media_url(url):
            raise ValueError('图片地址不属于支持的平台资源域名。')
        response = session.get(url, timeout=(10,25), stream=True, allow_redirects=False)
        if response.is_redirect:
            target = urljoin(url, response.headers.get('Location',''))
            response.close()
            url = target
            continue
        try:
            response.raise_for_status()
        except Exception:
            response.close()
            raise
        return response
    raise ValueError('图片地址跳转次数过多。')


def write_thumbnail(content, destination, edge=560):
    with Image.open(io.BytesIO(content)) as source:
        source.load()
        preview = ImageOps.exif_transpose(source)
        preview.thumbnail((edge, edge))
        if preview.mode != 'RGB':
            background = Image.new('RGB', preview.size, 'white')
            if 'A' in preview.getbands():
                background.paste(preview, mask=preview.getchannel('A'))
            else:
                background.paste(preview.convert('RGB'))
            preview = background
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix('.tmp')
        preview.save(temporary, format='JPEG', quality=78, optimize=True)
        temporary.replace(destination)
        return destination.stat().st_size


def fetch_preview(root, platform, item, destination):
    with session_for(root, platform) as session:
        with open_media(session, item['preview_url']) as response:
            data = bytearray()
            for chunk in response.iter_content(32768):
                data.extend(chunk)
                if len(data) > 12 * 1024 * 1024:
                    raise ValueError('预览资源过大，已停止读取。')
        transferred = len(data)
        cached = write_thumbnail(data, destination)
        # The response bytes go out of scope; only the small JPEG preview remains.
        return cached, transferred
