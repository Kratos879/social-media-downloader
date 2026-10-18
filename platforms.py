"""Explicit post URL routing. Short links are resolved in the metadata worker."""
from __future__ import annotations

import hashlib
import re
from urllib.parse import parse_qs, unquote, urlencode, urlsplit, urlunsplit

PLATFORMS = {
    'instagram': 'Instagram', 'twitter': 'X / Twitter', 'xiaohongshu': '小红书',
    'douyin': '抖音', 'tiktok': 'TikTok', 'bilibili': '哔哩哔哩',
    'youtube': 'YouTube', 'weibo': '微博', 'pinterest': 'Pinterest',
}
URL_PATTERN = re.compile(r'https?://[^\s<>"\'，。；！？、（）【】“”‘’《》]+', re.I)
HOSTS = {
    'instagram': {'instagram.com','www.instagram.com','m.instagram.com'},
    'twitter': {'x.com','www.x.com','twitter.com','www.twitter.com','mobile.twitter.com','m.twitter.com'},
    'xiaohongshu': {'xiaohongshu.com','www.xiaohongshu.com','xhslink.com','www.xhslink.com'},
    'douyin': {'douyin.com','www.douyin.com','v.douyin.com','iesdouyin.com','www.iesdouyin.com'},
    'tiktok': {'tiktok.com','www.tiktok.com','m.tiktok.com','vm.tiktok.com','vt.tiktok.com'},
    'bilibili': {'bilibili.com','www.bilibili.com','m.bilibili.com','b23.tv','www.b23.tv'},
    'youtube': {'youtube.com','www.youtube.com','m.youtube.com','music.youtube.com','youtu.be','www.youtu.be'},
    'weibo': {'weibo.com','www.weibo.com','m.weibo.cn','weibo.cn'},
    'pinterest': {'pinterest.com','www.pinterest.com','pinterest.ca','www.pinterest.ca',
                  'pinterest.co.uk','www.pinterest.co.uk','pin.it'},
}
SHORT_HOSTS = {'xhslink.com','www.xhslink.com','v.douyin.com','vm.tiktok.com','vt.tiktok.com','b23.tv','www.b23.tv','pin.it'}


def is_short(url):
    u=urlsplit(url)
    return u.hostname in SHORT_HOSTS or (host_platform(url)=='tiktok' and bool(re.fullmatch(r'/t/[A-Za-z0-9]+/?',u.path)))


def host_platform(url):
    try:
        u=urlsplit(url)
        if u.scheme not in {'https','http'} or u.username or u.password or u.port not in (None,80,443):
            return None
        return next((p for p,hosts in HOSTS.items() if (u.hostname or '').lower() in hosts),None)
    except (ValueError,TypeError):
        return None


def normalize(url):
    platform=host_platform(url)
    if not platform:raise ValueError('不支持的链接域名')
    u=urlsplit(url);host=u.hostname.lower();path=unquote(u.path);q=parse_qs(u.query)
    if is_short(url):
        if not re.fullmatch(r'/[A-Za-z0-9_/-]{2,200}/?',path):raise ValueError('无效的分享短链接')
        canonical=urlunsplit(('https',host,path,u.query,''))
        return {'platform':platform,'key':'share_'+hashlib.sha256(canonical.encode()).hexdigest()[:16],
                'url':canonical,'short_link':True}
    key=None;canonical=None
    if platform=='instagram':
        m=re.fullmatch(r'/(?:[A-Za-z0-9_.]+/)?(?:p|reel|reels|tv)/([A-Za-z0-9_-]+)/?',path)
        if m:key=m[1];canonical=f'https://www.instagram.com/p/{key}/'
    elif platform=='twitter':
        m=re.fullmatch(r'/(?:[A-Za-z0-9_]+|i/web|i)/status/(\d+)(?:/(?:photo|video)/\d+)?/?',path)
        if m:key=m[1];canonical=f'https://x.com/i/status/{key}'
    elif platform=='xiaohongshu':
        m=re.fullmatch(r'/(?:explore|discovery/item|user/profile/[a-fA-F0-9]+)/([a-fA-F0-9]{24})/?',path)
        if m:
            key=m[1];canonical=f'https://www.xiaohongshu.com/explore/{key}'
            params={k:q[k][0] for k in ('xsec_token','xsec_source') if q.get(k)}
            if params:canonical+='?'+urlencode(params)
    elif platform=='douyin':
        m=re.fullmatch(r'/(?:share/)?(?:video|note)/(\d+)/?',path)
        if m:key=m[1];canonical=f'https://www.douyin.com/{"note" if "/note/" in path else "video"}/{key}'
        elif path in {'/','/discover','/recommend'} and q.get('modal_id',[''])[0].isdigit():
            key=q['modal_id'][0];canonical=f'https://www.douyin.com/video/{key}'
    elif platform=='tiktok':
        m=re.fullmatch(r'/(@[^/]+)/(video|photo)/(\d+)/?',path)
        if m:key=m[3];canonical=f'https://www.tiktok.com/{m[1]}/{m[2]}/{key}'
    elif platform=='bilibili':
        m=re.fullmatch(r'/video/(BV[A-Za-z0-9]{10}|av\d+)/?',path)
        if m:
            key=m[1];canonical=f'https://www.bilibili.com/video/{key}'
            part=q.get('p',['1'])[0]
            if part.isdigit() and int(part)>1:key+=f'_p{part}';canonical+=f'?p={part}'
    elif platform=='youtube':
        m=re.fullmatch(r'/(?:shorts|embed|live)/([A-Za-z0-9_-]{11})/?',path)
        code=path.strip('/') if host.endswith('youtu.be') else m[1] if m else q.get('v',[''])[0] if path=='/watch' else ''
        if re.fullmatch(r'[A-Za-z0-9_-]{11}',code):key=code;canonical=f'https://www.youtube.com/watch?v={key}'
    elif platform=='weibo':
        m=re.fullmatch(r'/(?:detail|status|\d+)/([A-Za-z0-9]+)/?',path)
        if m:
            key=m[1];canonical=f'https://m.weibo.cn/detail/{key}' if host.endswith('weibo.cn') else f'https://weibo.com{path}'
    elif platform=='pinterest':
        m=re.fullmatch(r'/pin/(?:[a-zA-Z0-9-]+--)?(\d+)/?',path)
        if m:key=m[1];canonical=f'https://www.pinterest.com/pin/{key}/'
    if not key:raise ValueError('请使用具体帖子的分享链接')
    return {'platform':platform,'key':key,'url':canonical}


def parse_links(text):
    accepted,rejected,seen=[],[],set()
    for raw in URL_PATTERN.findall(text):
        raw=raw.rstrip('.,;!?)】]}')
        try:
            item=normalize(raw);identity=(item['platform'],item['key'])
            if identity not in seen:seen.add(identity);accepted.append(item)
        except (ValueError,UnicodeError):rejected.append(raw)
    return accepted,rejected


def resolve_link(url,platform,session):
    """Check every redirect before requesting it; never follow into an arbitrary host."""
    from urllib.parse import urljoin
    for _ in range(8):
        if host_platform(url)!=platform:raise ValueError('分享链接跳转到了其他网站，已停止解析。')
        u=urlsplit(url)
        if not is_short(url):return normalize(url)['url']
        with session.get(url,allow_redirects=False,timeout=(10,20),stream=True) as response:
            response.raise_for_status()
            if not response.is_redirect:raise ValueError('分享短链接没有返回帖子地址，请复制完整链接。')
            url=urljoin(url,response.headers.get('Location',''))
    raise ValueError('分享链接跳转过多，请复制完整链接。')
