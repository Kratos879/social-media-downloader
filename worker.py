"""Resolve media metadata and fetch previews; never save original image files."""
from __future__ import annotations

import concurrent.futures
import json
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

import instaloader
from media import allowed_media_url, fetch_preview
from media import session_for
from platforms import normalize, resolve_link


def atomic_json(path, data):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')
    temporary.replace(path)


def instagram_items(shortcode):
    loader = instaloader.Instaloader(max_connection_attempts=1,request_timeout=25,
                                    fatal_status_codes=[429,403],download_videos=False)
    try:
        post = instaloader.Post.from_shortcode(loader.context,shortcode)
        node = post._node
        media = node.get('carousel_media') or [node]
        files=[]
        for source_order, item in enumerate(media,1):
            if item.get('media_type') == 2 or item.get('is_video'):
                continue
            candidates = (item.get('image_versions2') or {}).get('candidates') or []
            candidates = [c for c in candidates if allowed_media_url(c.get('url'))]
            if not candidates:
                resources = item.get('display_resources') or []
                candidates = [{'url':c['src'],'width':c.get('config_width',0),'height':c.get('config_height',0)} for c in resources if allowed_media_url(c.get('src'))]
            if not candidates and allowed_media_url(item.get('display_url')):
                dimensions=item.get('dimensions') or {}
                candidates=[{'url':item['display_url'],'width':item.get('original_width',dimensions.get('width',0)),
                             'height':item.get('original_height',dimensions.get('height',0))}]
            if not candidates:
                raise ValueError('No image URLs available in post metadata')
            area=lambda c:(c.get('width') or 0)*(c.get('height') or 0)
            original=max(candidates,key=area)
            ratio=(original.get('width') or 1)/(original.get('height') or 1)
            matching=[c for c in candidates if c.get('height') and abs(c.get('width',0)/c['height']-ratio)<.04]
            small=[c for c in matching if (c.get('width') or 0)>=300] or matching or candidates
            preview=min(small,key=area)
            files.append({'order':len(files)+1,'source_order':source_order,'name':f'{shortcode}_{len(files)+1:02}.jpg',
                          'original_url':original['url'],'preview_url':preview['url'],
                          'width':original.get('width') or item.get('original_width') or 1,
                          'height':original.get('height') or item.get('original_height') or 1})
        return files
    finally:
        loader.close()


def gallery_items(platform,url,root):
    args=[sys.executable,'-m','gallery_dl','--config-ignore','--no-input','--dump-json',
          '--cache-file',str(root/'data'/'gallery-cache.sqlite3'),'--retries','0','--http-timeout','25',
          '-o','videos=false','-o','twitter.retries-api=0','-o','twitter.ratelimit=abort']
    cookies=root/'cookies'/f'{platform}.txt'
    if cookies.is_file(): args.extend(['--cookies',str(cookies)])
    if platform=='tiktok':args.extend(['-o','tiktok.audio=false'])
    args.append(url)
    process=subprocess.run(args,capture_output=True,text=True,timeout=100)
    if process.returncode:
        print(process.stderr,file=sys.stderr)
        raise RuntimeError('Metadata extraction failed: '+process.stderr[-1200:])
    messages=json.loads(process.stdout)
    files=[]
    for entry in messages:
        if len(entry)<3 or entry[0]!=3 or not allowed_media_url(entry[1]): continue
        original,info=entry[1],entry[2]
        if (info.get('extension') or '').lower() not in {'jpg','jpeg','png','webp','avif','gif'}:continue
        preview=original
        if platform=='twitter':
            parts=urlsplit(original); query=parse_qs(parts.query)
            query['name']=['small']
            preview=urlunsplit((parts.scheme,parts.netloc,parts.path,urlencode(query,doseq=True),''))
        elif platform=='pinterest':
            preview=original.replace('/originals/','/564x/')
        elif platform=='weibo':
            preview=original.replace('/large/','/mw690/').replace('/oslarge/','/mw690/')
        files.append({'order':len(files)+1,'source_order':info.get('num',len(files)+1),
                      'name':f'{info.get("post_shortcode") or info.get("tweet_id") or "image"}_{len(files)+1:02}.{info.get("extension") or "jpg"}',
                      'kind':'image','original_url':original,'preview_url':preview,'width':info.get('width') or 1,'height':info.get('height') or 1})
    if not files:
        raise ValueError('No images returned; Cookie or another valid post link may be required. '+process.stderr[-800:])
    return files


def main():
    platform,key,url,result_path,root_path,job_id=sys.argv[1:]
    root,result=Path(root_path),Path(result_path)
    started=time.monotonic()
    with session_for(root,platform) as session:url=resolve_link(url,platform,session)
    resolved=normalize(url);source_key=resolved['key']
    engine='Instaloader' if platform=='instagram' else 'gallery-dl'
    if platform=='instagram':
        try:
            files=instagram_items(source_key)
            if not files:
                from video_engine import metadata
                files=metadata(platform,url,root,job_id);engine='yt-dlp'
        except Exception:
            if not (root/'cookies'/'instagram.txt').is_file(): raise
            files=gallery_items(platform,url,root);engine='gallery-dl'
    elif platform in {'twitter','pinterest','weibo'}:
        try:files=gallery_items(platform,url,root)
        except Exception:
            from video_engine import metadata
            files=metadata(platform,url,root,job_id);engine='yt-dlp'
    elif platform=='xiaohongshu':
        from site_adapters import xiaohongshu
        files=xiaohongshu(root,source_key,url);engine='小红书页面元数据'
        if not files:
            from video_engine import metadata
            files=metadata(platform,url,root,job_id);engine='yt-dlp'
    elif platform=='tiktok' and '/photo/' in url:
        try:files=gallery_items(platform,url,root);engine='gallery-dl'
        except Exception:
            from site_adapters import tiktok_photos
            files=tiktok_photos(root,source_key,url);engine='TikTok 页面元数据'
    elif platform=='tiktok':
        try:
            from video_engine import metadata
            files=metadata(platform,url,root,job_id);engine='yt-dlp'
        except Exception:
            from tiktok_embed import metadata
            files=metadata(root,source_key,url,job_id);engine='TikTok 官方嵌入页'
    elif platform=='douyin':
        from f2_bridge import metadata
        files=metadata(platform,source_key,url,root,job_id);engine='F2'
    else:
        from video_engine import metadata
        files=metadata(platform,url,root,job_id);engine='yt-dlp'
    if not files:raise ValueError('No media files returned; please use a valid post link.')
    for item in files:
        item.update(saved=False,status='available',bytes=0,preview_ready=False,preview_bytes=0)
    data={'files':files,'expected':len(files),'engine':engine,'resolved_url':url,'stage':'previews',
          'metadata_seconds':round(time.monotonic()-started,2),'preview_count':0}
    atomic_json(result,data)
    destination=root/'data'/'previews'/job_id
    destination.mkdir(parents=True,exist_ok=True)
    def preview(index):
        try:
            cached,transferred=fetch_preview(root,platform,files[index],destination/f'{index}.jpg')
            return index,{'preview_ready':True,'preview_bytes':cached,'preview_transfer_bytes':transferred}
        except Exception as error:
            print(f'Preview {index+1}: {type(error).__name__}',flush=True)
            return index,{'preview_error':'预览未加载，可重新解析后再选取。'}
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        futures=[pool.submit(preview,index) for index in range(len(files))]
        for future in concurrent.futures.as_completed(futures):
            index,values=future.result();files[index].update(values)
            data['preview_count']=sum(bool(f.get('preview_ready')) for f in files)
            atomic_json(result,data)
    data.update(stage='ready',parse_seconds=round(time.monotonic()-started,2))
    atomic_json(result,data)


if __name__=='__main__':main()
