"""Keep the optional Python 3.11+ F2 engine separate from the existing runtime."""
import json
import subprocess
from pathlib import Path

from media import allowed_media_url, USER_AGENT


def metadata(platform,key,url,root,job_id):
    project=Path(__file__).resolve().parent
    python=project/'.engines'/'f2'/'bin'/'python'
    if not python.is_file():raise ValueError('抖音备用引擎未安装，请运行“安装备用引擎.command”。')
    result=root/'data'/'results'/f'{job_id}-f2.json';result.parent.mkdir(parents=True,exist_ok=True)
    process=subprocess.run([str(python),str(project/'f2_worker.py'),platform,key,str(root),str(result)],
                           capture_output=True,text=True,timeout=75)
    if process.returncode:raise ValueError(process.stderr.strip() or 'F2 未返回有效作品信息。')
    files=json.loads(result.read_text('utf-8'));result.unlink(missing_ok=True)
    if not files:raise ValueError('该作品没有返回可下载媒体。')
    for index,file in enumerate(files):
        if not allowed_media_url(file.get('original_url')):raise ValueError('平台返回的媒体地址不受支持。')
        file.update(order=index+1,source_order=index+1,name=f'{key}_{index+1:02}.mp4' if file['kind']=='video' else f'{key}_{index+1:02}.jpg')
        if file['kind']=='video':
            folder=root/'data'/'video-info'/job_id;folder.mkdir(parents=True,exist_ok=True);info=folder/f'{index}.json'
            data={'id':str(file['video_id']),'title':file.get('title') or str(key),'url':file['original_url'],
                  'ext':'mp4','protocol':'https','width':file['width'],'height':file['height'],
                  'duration':file['duration'],'http_headers':{'User-Agent':USER_AGENT,'Referer':'https://www.douyin.com/'}}
            info.write_text(json.dumps(data,ensure_ascii=False),'utf-8')
            file.update(video_info=str(info.relative_to(root/'data')),source_url=url,
                        quality=f"{min(file['width'],file['height'])}p")
    return files
