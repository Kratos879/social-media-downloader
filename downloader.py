"""URL routing and the local, serial download queue."""
from __future__ import annotations

import json
import os
import queue
import re
import signal
import subprocess
import sys
import threading
import time
import uuid
import shutil
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote, urlsplit
from zoneinfo import ZoneInfo

from PIL import Image, ImageOps
from media import session_for, open_media, write_thumbnail

ROOT = Path(__file__).resolve().parent
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".avif", ".gif"}
from platforms import parse_links


def friendly_error(log: str) -> str:
    log = log.lower()
    if '503' in log or 'overload-protect' in log:
        return '平台服务暂时繁忙，已停止本次请求。请稍后再试，已保存文件会保留。'
    if "429" in log or "too many requests" in log or "rate limit" in log:
        return "平台暂时限制了请求，请稍后重试。已经下载的图片会保留。"
    if any(x in log for x in ("login", "log in", "cookie", "分享链接", "checkpoint", "challenge_required", "private profile", "private account", "401")):
        return "这条内容需要有效的登录会话。可在使用说明中查看本地 Cookie 配置，再重试。"
    if '403' in log or 'forbidden' in log:
        return '平台拒绝了这次请求，可能是会话、网络或媒体地址限制。请更新会话或重新复制分享链接后重试。'
    if any(x in log for x in ("not found", "404", "does not exist", "notfound")):
        return "未找到这条帖子，可能已删除、设为私密，或当前会话无权查看。"
    if any(x in log for x in ("timed out", "timeout", "connection", "proxy", "ssl", "resolve")):
        return "连接平台失败，请检查网络后重试。"
    return "这次解析或下载没有完成，请稍后重试。已保存的文件会保留。"


class DownloadQueue:
    def __init__(self, root: Path = ROOT):
        self.root = Path(root)
        self.data = self.root / 'data'
        self.downloads = self.root / '下载'
        self.data.mkdir(parents=True,exist_ok=True)
        self.downloads.mkdir(parents=True,exist_ok=True)
        (self.data/'results').mkdir(exist_ok=True)
        self.history_file = self.data/'history.json'
        self.lock = threading.RLock()
        self.jobs = self._load()
        self.pending = queue.Queue()
        self._prune_cache()
        self.thread = threading.Thread(target=self._work,daemon=True,name='media-queue')
        self.thread.start()

    def _load(self):
        if not self.history_file.exists():return []
        try:jobs=json.loads(self.history_file.read_text('utf-8'))
        except (OSError,ValueError):
            self.history_file.rename(self.data/f'history-unreadable-{int(time.time())}.json')
            return []
        if any('mode' not in j for j in jobs):
            backup=self.data/'history-before-selective-preview.json'
            if not backup.exists():shutil.copy2(self.history_file,backup)
        for job in jobs:
            if 'mode' not in job:
                job['mode']='legacy'
                indexed=list(enumerate(job.get('files',[])))
                def natural(pair):
                    return [int(s) if s.isdigit() else s for s in re.split(r'(\d+)',pair[1]['name'])]
                job['files']=[]
                for order,(old_index,file) in enumerate(sorted(indexed,key=natural),1):
                    file.update(saved=True,status='saved',order=order,source_order=order,
                                preview_ready=True,preview_index=old_index,preview_bytes=0)
                    job['files'].append(file)
                job['expected']=len(job['files'])
            if job['status'] in {'running','queued','parsing','downloading'}:
                job.update(status='failed',message='上次操作中断，可重新解析或重试保存。')
                for file in job.get('files',[]):
                    if file.get('status') in {'queued','downloading'}:file['status']='available'
            job.setdefault('parse_seconds',None)
        return jobs

    def _save(self):
        temporary=self.history_file.with_suffix('.tmp')
        temporary.write_text(json.dumps(self.jobs,ensure_ascii=False,indent=2),'utf-8')
        temporary.replace(self.history_file)

    def state(self):
        with self.lock:
            state=json.loads(json.dumps(self.jobs))
        for job in state:
            for index,file in enumerate(job.get('files',[])):
                file['preview_ready']=self.preview_file(job,index).is_file()
                for key in ('original_url','preview_url','source_url','video_info'):file.pop(key,None)
            job['preview_count']=sum(bool(f['preview_ready']) for f in job['files'])
            job['saved_count']=sum(bool(f.get('saved')) for f in job['files'])
        return state

    def storage(self):
        cache=self.data/'previews'
        preview_bytes=0
        for path in cache.rglob('*.jpg') if cache.exists() else []:
            try:preview_bytes+=path.stat().st_size
            except FileNotFoundError:pass
        with self.lock:
            saved_bytes=sum(f.get('bytes',0) for j in self.jobs for f in j['files'] if f.get('saved'))
        return {'preview_bytes':preview_bytes,'saved_bytes':saved_bytes,'preview_limit_bytes':100*1024*1024,'preview_ttl_hours':24}

    def get(self,job_id):
        with self.lock:return next((j for j in self.jobs if j['id']==job_id),None)

    def submit(self,item,force=False):
        with self.lock:
            existing=next((j for j in reversed(self.jobs) if j['platform']==item['platform'] and j['key']==item['key']
                           and j['mode']=='selective' and j['status'] not in {'failed'}),None)
            if existing and not force:return existing,True
            now=datetime.now(ZoneInfo('Asia/Shanghai'))
            job_id=uuid.uuid4().hex[:12]
            job={**item,'id':job_id,'mode':'selective','status':'queued','message':'等待解析',
                 'created_at':now.isoformat(),'folder':f"{now:%Y-%m-%d}/{item['platform']}_{item['key']}_{job_id[:6]}",
                 'files':[],'expected':None,'count':0,'bytes':0,'elapsed':0,'parse_seconds':None,
                 'preview_count':0,'download_requested':0,'download_done':0}
            self.jobs.append(job);self._save();self.pending.put(('parse',job_id,[]))
            return job,False

    def retry(self,job_id):
        job=self.get(job_id)
        if not job:raise ValueError('找不到这条记录。')
        return self.submit({k:job[k] for k in ('platform','key','url')},force=True)

    def enqueue_download(self,items):
        if not isinstance(items,list) or not 1<=len(items)<=300:raise ValueError('请选择 1 至 300 张图片。')
        groups=defaultdict(list);seen=set();skipped=0
        with self.lock:
            # Validate every item before making any changes.
            resolved=[]
            for item in items:
                if not isinstance(item,dict) or not isinstance(item.get('id'),str) or type(item.get('index')) is not int:
                    raise ValueError('所选图片无效。')
                identity=(item['id'],item['index'])
                if identity in seen:continue
                seen.add(identity);job=self.get(item['id']);index=item['index']
                if not job or not 0<=index<len(job['files']):raise ValueError('找不到所选图片。')
                file=job['files'][index]
                if file.get('saved') and (self.downloads/file.get('path','')).is_file():skipped+=1;continue
                if file.get('status') in {'queued','downloading'}:skipped+=1;continue
                if not file.get('original_url') and not file.get('video_info'):raise ValueError('图片地址已失效，请重新解析这条链接。')
                resolved.append((job,index))
            for job,index in resolved:
                job['files'][index].update(status='queued',error=None,downloaded_bytes=0,total_bytes=None)
                groups[job['id']].append(index)
            self._save()
            for job_id,indices in groups.items():self.pending.put(('download',job_id,indices))
        return {'queued':sum(map(len,groups.values())),'skipped':skipped}

    def preview_file(self,job,index):
        preview=self.data/'previews'/job['id']/f'{index}.jpg'
        if preview.is_file():return preview
        file=job['files'][index]
        return self.data/'thumbs'/job['id']/f"{file.get('preview_index',index)}.jpg"

    def _update(self,job,**values):
        with self.lock:job.update(values);self._save()

    def _prune_cache(self):
        cache=self.data/'previews';cache.mkdir(exist_ok=True)
        files=sorted((p for p in cache.rglob('*.jpg') if p.is_file()),key=lambda p:p.stat().st_mtime)
        total=sum(p.stat().st_size for p in files)
        for file in files:
            if file.stat().st_mtime<time.time()-86400 or total>100*1024*1024:
                total-=file.stat().st_size;file.unlink()

    def clear_preview_cache(self):
        with self.lock:
            if any(j['status']=='parsing' for j in self.jobs):raise ValueError('正在加载预览，请解析结束后再清理。')
            cache=self.data/'previews'
            removed=sum(p.stat().st_size for p in cache.rglob('*.jpg') if p.is_file())
            for file in cache.rglob('*.jpg'):file.unlink()
            for job in self.jobs:
                if job['mode']=='selective':
                    for file in job['files']:
                        if not file.get('saved'):file['preview_ready']=False
            self._save()
        return {'removed_bytes':removed}

    def _work(self):
        while True:
            operation,job_id,indices=self.pending.get();job=self.get(job_id)
            try:
                if operation=='parse':self._parse(job)
                else:self._download(job,indices)
            except Exception as error:
                self._update(job,status='failed',message=friendly_error(str(error)))
                print(f'{operation} {job_id}: {type(error).__name__}',flush=True)
            finally:self.pending.task_done()

    def _merge_parse(self,job,data):
        with self.lock:
            def identity(file):
                return ('video',file.get('video_id'),file.get('source_order')) if file.get('kind')=='video' else ('image',urlsplit(file.get('original_url','')).path)
            old={identity(f):f for f in job['files'] if f.get('original_url')}
            files=[]
            for item in data.get('files',[]):
                item.setdefault('kind','image')
                previous=old.get(identity(item),{})
                for key in ('saved','path','bytes','status','downloaded_bytes','total_bytes','error'):
                    if key in previous and (previous.get('saved') or previous.get('status') in {'queued','downloading'}):
                        item[key]=previous[key]
                files.append(item)
            job.update(files=files,expected=data.get('expected'),preview_count=data.get('preview_count',0),
                       engine=data.get('engine'),metadata_seconds=data.get('metadata_seconds'),resolved_url=data.get('resolved_url'),
                       count=sum(bool(f.get('saved')) for f in files))
            self._save()

    def _parse(self,job):
        self._prune_cache();started=time.monotonic()
        result=self.data/'results'/f"{job['id']}.json";log=self.data/f"{job['id']}.log"
        self._update(job,status='parsing',message='正在获取媒体清单',elapsed=0)
        args=[sys.executable,'-u',str(ROOT/'worker.py'),job['platform'],job['key'],job['url'],str(result),str(self.root),job['id']]
        timed_out=False;stamp=None
        with log.open('w',encoding='utf-8') as output:
            process=subprocess.Popen(args,stdout=output,stderr=subprocess.STDOUT,start_new_session=(os.name!='nt'))
            try:
                while process.poll() is None:
                    elapsed=round(time.monotonic()-started,1)
                    if elapsed>150:
                        timed_out=True
                        os.killpg(process.pid,signal.SIGTERM) if os.name!='nt' else process.terminate()
                        break
                    if result.exists() and result.stat().st_mtime_ns!=stamp:
                        try:
                            data=json.loads(result.read_text('utf-8'));stamp=result.stat().st_mtime_ns
                            self._merge_parse(job,data)
                        except (OSError,ValueError):pass
                    expected=job.get('expected');ready=job.get('preview_count',0)
                    self._update(job,elapsed=elapsed,message=f'预览 {ready} / {expected} 项' if expected else '正在获取媒体清单')
                    time.sleep(.2)
                process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid,signal.SIGKILL) if os.name!='nt' else process.kill()
                process.wait()
        if result.exists():
            data=json.loads(result.read_text('utf-8'));self._merge_parse(job,data)
        seconds=round(time.monotonic()-started,1)
        if process.returncode or timed_out:
            self._update(job,status='failed',elapsed=seconds,message='解析等待过久，请检查网络后重试。' if timed_out else friendly_error(log.read_text('utf-8',errors='replace')))
            return
        count=len(job['files']);ready=job.get('preview_count',0)
        self._update(job,status='ready',elapsed=seconds,parse_seconds=seconds,resolved_at=time.time(),
                     message=f'解析完成，{ready}/{count} 项预览可用，点选后保存' if count else '这条帖子没有返回可下载的图片或视频，请检查分享链接或登录会话。')
        self._prune_cache()

    def _download(self,job,indices):
        if job.get('resolved_at') and time.time()-job['resolved_at']>20*60:
            self._parse(job)
            if job['status']=='failed':
                with self.lock:
                    for index in indices:
                        if index<len(job['files']):job['files'][index].update(status='error',error=job['message'])
                    self._save()
                return
        self._update(job,status='downloading',download_requested=len(indices),download_done=0,download_errors=0)
        started=time.monotonic();folder=self.downloads/job['folder'];folder.mkdir(parents=True,exist_ok=True)
        done=0;errors=0
        for index in indices:
            if not 0<=index<len(job['files']):continue
            file=job['files'][index]
            temporary=folder/f'.{index+1}.part'
            with self.lock:file.update(status='downloading',error=None);self._save()
            self._update(job,current_index=index,elapsed=round(time.monotonic()-started,1),message=f'正在保存第 {index+1} 张，本次 {done}/{len(indices)}')
            try:
                file_started=time.monotonic()
                if file.get('saved') and (self.downloads/file['path']).is_file():
                    done+=1;continue
                if file.get('kind')=='video':
                    from video_engine import download as download_video
                    def progress(received,total,phase):
                        with self.lock:
                            file.update(downloaded_bytes=received,total_bytes=total,phase=phase)
                            job['elapsed']=round(time.monotonic()-started,1)
                            self._save()
                    target=download_video(self.root,job,index,progress)
                    width,height=file.get('width',16),file.get('height',9)
                    preview=self.preview_file(job,index)
                    if preview.is_file():
                        thumb=self.data/'thumbs'/job['id']/f'{index}.jpg'
                        thumb.parent.mkdir(parents=True,exist_ok=True)
                        shutil.copy2(preview,thumb)
                else:
                    with session_for(self.root,job['platform']) as session:
                        with open_media(session,file['original_url']) as response:
                            total=int(response.headers.get('Content-Length','0')) or None
                            if total and total>512*1024*1024:raise ValueError('图片文件过大。')
                            received=0;updated=0
                            with temporary.open('wb') as output:
                                for chunk in response.iter_content(65536):
                                    if time.monotonic()-file_started>180:raise TimeoutError('Download timed out')
                                    output.write(chunk);received+=len(chunk)
                                    if received>512*1024*1024:raise ValueError('图片文件过大。')
                                    if time.monotonic()-updated>.15:
                                        updated=time.monotonic()
                                        with self.lock:file.update(downloaded_bytes=received,total_bytes=total);self._save()
                    with Image.open(temporary) as image:
                        image.verify()
                    with Image.open(temporary) as image:
                        width,height=image.size;fmt=(image.format or 'JPEG').upper()
                    extension={'JPEG':'jpg','PNG':'png','WEBP':'webp','GIF':'gif','AVIF':'avif'}.get(fmt,'jpg')
                    target=folder/f"{job['key']}_{index+1:02}.{extension}"
                    temporary.replace(target)
                    thumb=self.data/'thumbs'/job['id']/f'{index}.jpg'
                    write_thumbnail(target.read_bytes(),thumb)
                with self.lock:
                    file.update(saved=True,status='saved',path=str(target.relative_to(self.downloads)),name=target.name,
                                bytes=target.stat().st_size,width=width,height=height,downloaded_bytes=target.stat().st_size,
                                total_bytes=target.stat().st_size,preview_ready=True)
                    self._save()
                done+=1
            except Exception as error:
                temporary.unlink(missing_ok=True);errors+=1
                with self.lock:file.update(status='error',error=friendly_error(str(error)));self._save()
            self._update(job,download_done=done,download_errors=errors,
                         count=sum(bool(f.get('saved')) for f in job['files']),
                         bytes=sum(f.get('bytes',0) for f in job['files'] if f.get('saved')),
                         message=f'本次已保存 {done}/{len(indices)} 张'+(f'，{errors} 张未完成' if errors else ''))
        saved=sum(bool(f.get('saved')) for f in job['files'])
        self._update(job,status='ready',elapsed=round(time.monotonic()-started,1),
                     download_done=done,download_errors=errors,message=f'已保存 {saved}/{len(job["files"])} 项，其余未下载')

    def _images(self,folder,job_id):
        """Index existing local files (used only for legacy import and tests)."""
        files=[]
        for path in sorted(folder.iterdir()):
            if path.suffix.lower() not in IMAGE_SUFFIXES:continue
            try:
                with Image.open(path) as image:image.verify()
                with Image.open(path) as image:width,height=image.size
                index=len(files);write_thumbnail(path.read_bytes(),self.data/'thumbs'/job_id/f'{index}.jpg')
                files.append({'name':path.name,'path':str(path.relative_to(self.downloads)),'width':width,'height':height,
                              'bytes':path.stat().st_size,'saved':True,'status':'saved','order':index+1,'preview_ready':True})
            except (OSError,ValueError,Image.DecompressionBombError):continue
        return files
