"""yt-dlp metadata and selected-only video downloads, with a bundled FFmpeg."""
from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

import yt_dlp
from media import allowed_media_url


def options(root, platform):
    import imageio_ffmpeg
    opts={'quiet':True,'noprogress':True,'no_warnings':False,'noplaylist':True,'socket_timeout':20,
          'retries':1,'extractor_retries':0,'fragment_retries':1,'cachedir':str(root/'data'/'yt-cache'),
          'ffmpeg_location':imageio_ffmpeg.get_ffmpeg_exe(),'js_runtimes':{'node':{}},
          'format':'bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/bv*+ba/b','merge_output_format':'mp4',
          'max_filesize':2*1024**3,'concurrent_fragment_downloads':2,
          'remote_components':set()}
    cookie=root/'cookies'/f'{platform}.txt'
    if cookie.is_file():opts['cookiefile']=str(cookie)
    return opts


def flatten(info):
    if info.get('_type') in {'playlist','multi_video'}:
        return [entry for entry in info.get('entries',[]) if isinstance(entry,dict)]
    return [info]


def metadata(platform,url,root,job_id):
    opts=options(root,platform)
    with yt_dlp.YoutubeDL(opts) as ydl:
        info=ydl.extract_info(url,download=False)
        entries=flatten(info)
        files=[]
        for entry in entries[:100]:
            # Each selectable card owns its resolved format metadata. No video bytes are fetched here.
            if not entry.get('formats') and not entry.get('url'):continue
            index=len(files);folder=root/'data'/'video-info'/job_id;folder.mkdir(parents=True,exist_ok=True)
            path=folder/f'{index}.json'
            path.write_text(json.dumps(ydl.sanitize_info(entry)),encoding='utf-8')
            thumbs=[]
            for thumb in entry.get('thumbnails',[]):
                thumb=dict(thumb);candidate=thumb.get('url') or ''
                if candidate.startswith('http://'):candidate='https://'+candidate[7:]
                if allowed_media_url(candidate):thumb['url']=candidate;thumbs.append(thumb)
            small=[t for t in thumbs if 200<=(t.get('width') or 0)<=700]
            thumbnail=(small[-1] if small else thumbs[-1] if thumbs else {}).get('url') or entry.get('thumbnail')
            if thumbnail and thumbnail.startswith('http://'):thumbnail='https://'+thumbnail[7:]
            width=entry.get('width') or 16;height=entry.get('height') or 9
            files.append({'kind':'video','order':index+1,'source_order':index+1,
                          'original_url':url,'source_url':url,'video_id':entry.get('id'),
                          'video_info':str(path.relative_to(root/'data')),
                          'preview_url':thumbnail,'width':width,'height':height,
                          'duration':entry.get('duration'),'title':entry.get('title') or '',
                          'quality':f'{min(width,height)}p' if width>16 and height>9 else '',
                          'estimated_bytes':entry.get('filesize') or entry.get('filesize_approx'),
                          'name':f"{entry.get('id','video')}.{entry.get('ext','mp4')}"})
    return files


def download(root,job,index,progress):
    file=job['files'][index]
    info_path=(root/'data'/file['video_info']).resolve()
    if not info_path.is_relative_to((root/'data'/'video-info').resolve()):raise ValueError('Invalid video metadata path')
    info=json.loads(info_path.read_text('utf-8'))
    folder=root/'下载'/job['folder'];folder.mkdir(parents=True,exist_ok=True)
    staging=root/'data'/'video-parts'/job['id']/str(index);staging.mkdir(parents=True,exist_ok=True)
    opts=options(root,job['platform']);stamp=0
    def update(data):
        nonlocal stamp
        if time.monotonic()-stamp>.2 or data.get('status')=='finished':
            stamp=time.monotonic()
            progress(data.get('downloaded_bytes',0),data.get('total_bytes') or data.get('total_bytes_estimate'),
                     '正在合并音视频' if data.get('status')=='finished' else '正在下载视频')
    opts.update(outtmpl=str(staging/'media.%(ext)s'),progress_hooks=[update],overwrites=True,
                continuedl=True,keepvideo=False,restrictfilenames=True)
    try:
        used_embed=bool(info.get('_embed_fallback'))
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:ydl.process_info(info)
        except yt_dlp.utils.DownloadError as error:
            if job['platform']!='tiktok' or used_embed or not any(code in str(error) for code in ('403','404')):raise
            # Resolve an alternative official playback stream only for this selected video.
            from tiktok_embed import resolve
            progress(0,None,'正在获取 TikTok 备用播放地址')
            info=resolve(root,file['video_id']);used_embed=True
            shutil.rmtree(staging,ignore_errors=True);staging.mkdir(parents=True,exist_ok=True)
            with yt_dlp.YoutubeDL(opts) as ydl:ydl.process_info(info)
        candidates=[p for p in staging.iterdir() if p.suffix.lower() in {'.mp4','.webm','.mkv','.mov'} and not '.f' in p.stem]
        if len(candidates)!=1:raise ValueError('视频合并未完成，请重试。')
        source=candidates[0]
        if source.stat().st_size<128:raise ValueError('视频文件为空。')
        target=folder/f"{job['key']}_{index+1:02}{source.suffix.lower()}"
        source.replace(target)
        if used_embed:
            file.update(width=info.get('width') or file['width'],height=info.get('height') or file['height'],
                        duration=info.get('duration') or file.get('duration'),
                        quality=f"{min(info.get('width') or file['width'],info.get('height') or file['height'])}p",
                        download_engine='TikTok 官方嵌入页')
        return target
    finally:
        # Failed partial videos must not silently occupy the preview cache.
        shutil.rmtree(staging,ignore_errors=True)
