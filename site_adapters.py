"""Small post metadata adapters for image notes not represented by video extractors."""
from __future__ import annotations

import json
import re
from urllib.parse import unquote

from media import allowed_media_url, session_for


def secure(url):
    if isinstance(url,str) and url.startswith('http://'):url='https://'+url[7:]
    return url if allowed_media_url(url) else None


def get_page(root,platform,url):
    from platforms import host_platform
    from urllib.parse import urljoin
    with session_for(root,platform) as session:
        for _ in range(6):
            if host_platform(url)!=platform:raise ValueError('帖子地址跳转异常，请复制完整分享链接。')
            with session.get(url,timeout=(10,25),allow_redirects=False,stream=True) as response:
                response.raise_for_status()
                if response.is_redirect:url=urljoin(url,response.headers['Location']);continue
                data=bytearray()
                for chunk in response.iter_content(65536):
                    data.extend(chunk)
                    if len(data)>8*1024**2:raise ValueError('帖子元数据过大。')
                return data.decode('utf-8',errors='replace')
    raise ValueError('帖子跳转过多。')


def xhs_images(html,key):
    from yt_dlp.utils import js_to_json
    match=re.search(r'window\.__INITIAL_STATE__\s*=\s*(.*?)</script>',html,re.S)
    if not match:raise ValueError('小红书需要有效的分享链接和 Cookie，请重新复制带 xsec_token 的完整分享链接。')
    raw=match[1].strip().rstrip(';')
    data=json.loads(js_to_json(raw))
    notes=(data.get('note') or {}).get('noteDetailMap') or {}
    note=(notes.get(key) or {}).get('note')
    if not note:
        note=next((n.get('note') for n in notes.values() if n.get('note',{}).get('noteId')==key),None)
    if not note:raise ValueError('小红书没有返回这条笔记，需要有效分享链接或 Cookie。')
    if note.get('type')=='video':return []
    files=[]
    for image in note.get('imageList') or []:
        variants={v.get('imageScene'):secure(v.get('url')) for v in image.get('infoList') or []}
        original=variants.get('WB_DFT') or secure(image.get('urlDefault'))
        # WB_PRV can be a heavily posterized placeholder. Generate a clear small
        # JPEG from the displayed image, releasing its response bytes afterwards.
        preview=original
        if not original:continue
        index=len(files)+1
        files.append({'kind':'image','order':index,'source_order':index,'name':f'{key}_{index:02}.jpg',
                      'original_url':original,'preview_url':preview,
                      'width':image.get('width') or 1,'height':image.get('height') or 1,
                      'title':note.get('title') or ''})
    if not files:raise ValueError('这条笔记没有返回可下载的图片，需要有效 Cookie。')
    return files


def xiaohongshu(root,key,url):
    return xhs_images(get_page(root,'xiaohongshu',url),key)


def tiktok_photos(root,key,url):
    # Public image posts expose their complete image list on the video web route;
    # the /photo/ shell can omit item data altogether.
    html=get_page(root,'tiktok',url.replace('/photo/','/video/'))
    match=re.search(r'<script[^>]+id="__UNIVERSAL_DATA_FOR_REHYDRATION__"[^>]*>(.*?)</script>',html,re.S)
    if not match:raise ValueError('TikTok 需要有效 Cookie，暂时没有返回图集信息。')
    scope=json.loads(match[1]).get('__DEFAULT_SCOPE__',{})
    item=scope.get('webapp.video-detail',{}).get('itemInfo',{}).get('itemStruct',{})
    files=[]
    for image in item.get('imagePost',{}).get('images',[]):
        original=next((secure(u) for u in image.get('imageURL',{}).get('urlList',[]) if secure(u)),None)
        preview=next((secure(u) for u in image.get('thumbnail',{}).get('urlList',[]) if secure(u)),original)
        if not original:continue
        n=len(files)+1
        files.append({'kind':'image','order':n,'source_order':n,'name':f'{key}_{n:02}.jpg',
                      'original_url':original,'preview_url':preview,
                      'width':image.get('imageWidth') or 1,'height':image.get('imageHeight') or 1})
    if not files:raise ValueError('TikTok 没有返回图集，需要有效 Cookie 或完整的图集分享链接。')
    return files
