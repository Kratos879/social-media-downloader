"""Official TikTok embed metadata fallback for public, embeddable videos."""
from __future__ import annotations

import json
import re
from pathlib import Path

from media import allowed_media_url, session_for

EMBED_USER_AGENT='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36'


def parse_embed(html,key):
    match=re.search(r'<script\b[^>]*\bid=["\']__FRONTITY_CONNECT_STATE__["\'][^>]*>(.*?)</script>',html,re.S)
    if not match:raise ValueError('TikTok 官方嵌入页没有返回公开媒体信息。')
    data=json.loads(match[1]);sources=data.get('source',{}).get('data',{})
    item=next((v.get('videoData',{}).get('itemInfos',{}) for v in sources.values()
               if isinstance(v,dict) and str(v.get('videoData',{}).get('itemInfos',{}).get('id'))==str(key)),{})
    if not item:raise ValueError('TikTok 嵌入页没有返回该视频，可能不允许嵌入或需要会话。')
    video=item.get('video') or {};meta=video.get('videoMeta') or {}
    url=next((u for u in video.get('urls',[]) if allowed_media_url(u)),None)
    if not url:raise ValueError('TikTok 嵌入页没有提供受支持的播放地址。')
    covers=item.get('covers') or item.get('coversOrigin') or []
    cover=next((u for u in covers if isinstance(u,str) and allowed_media_url(u)),None)
    return {'id':str(key),'title':item.get('text') or str(key),'url':url,'ext':'mp4','protocol':'https',
            'width':int(meta.get('width') or 16),'height':int(meta.get('height') or 9),
            'duration':meta.get('duration'),'thumbnail':cover,'_embed_fallback':True,
            'http_headers':{'User-Agent':EMBED_USER_AGENT,'Referer':'https://www.tiktok.com/'}}


def resolve(root,key):
    if not re.fullmatch(r'\d{1,24}',str(key)):raise ValueError('无效的 TikTok 视频编号。')
    url=f'https://www.tiktok.com/embed/v2/{key}'
    with session_for(root,'tiktok') as session:
        session.headers['User-Agent']=EMBED_USER_AGENT
        session.headers.pop('Referer',None)
        with session.get(url,timeout=(10,20),stream=True,allow_redirects=False) as response:
            response.raise_for_status()
            if response.is_redirect:raise ValueError('TikTok 嵌入页要求跳转，当前会话无法读取。')
            content=bytearray()
            for chunk in response.iter_content(65536):
                content.extend(chunk)
                if len(content)>8*1024**2:raise ValueError('TikTok 嵌入页过大。')
    return parse_embed(content.decode('utf-8',errors='replace'),key)


def metadata(root,key,url,job_id):
    info=resolve(root,key);folder=root/'data'/'video-info'/job_id;folder.mkdir(parents=True,exist_ok=True)
    path=folder/'0.json';path.write_text(json.dumps(info,ensure_ascii=False),'utf-8')
    return [{'kind':'video','order':1,'source_order':1,'video_id':str(key),
             'original_url':url,'source_url':url,'video_info':str(path.relative_to(root/'data')),
             'preview_url':info.get('thumbnail'),'width':info['width'],'height':info['height'],
             'duration':info.get('duration'),'title':info['title'],'name':f'{key}.mp4',
             'quality':f"{min(info['width'],info['height'])}p",'download_engine':'TikTok 官方嵌入页'}]
