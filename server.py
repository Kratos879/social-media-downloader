from __future__ import annotations

import argparse
import io
import json
import mimetypes
import os
import secrets
import subprocess
import sys
import threading
import webbrowser
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

from downloader import DownloadQueue, ROOT, parse_links
from platforms import PLATFORMS


def build_selected_archive(manager, items):
    """Export validated existing files only; leave originals and history intact."""
    if not isinstance(items, list) or not 1 <= len(items) <= 300:
        raise ValueError("请选择 1 至 300 项文件进行打包。")
    files, seen, total_bytes = [], set(), 0
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str) or type(item.get("index")) is not int:
            raise ValueError("所选文件无效，请刷新后重试。")
        identity = (item["id"], item["index"])
        if identity in seen:
            continue
        seen.add(identity)
        job = manager.get(item["id"])
        index = item["index"]
        if not job or not 0 <= index < len(job["files"]):
            raise ValueError("所选文件不存在，请刷新后重试。")
        info = job["files"][index]
        if not info.get('saved') or not info.get('path'):
            raise ValueError('请先保存所选文件，再打包原文件。')
        file = (manager.downloads / info["path"]).resolve()
        if not file.is_relative_to(manager.downloads.resolve()) or not file.is_file():
            raise ValueError("文件已移动或无法读取，请重新下载。")
        total_bytes += file.stat().st_size
        if total_bytes > 512 * 1024 * 1024:
            raise ValueError("所选文件超过 512 MB，请分批打包。")
        files.append((file, f"{job['platform']}_{job['key']}_{job['id']}/{file.name}"))
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_STORED) as output:
        for file, name in files:
            output.write(file, name)
    return archive.getvalue(), len(files)


def make_handler(manager):
    token = secrets.token_urlsafe(32)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            if args and str(args[1] if len(args) > 1 else "") not in {"200", "304"}:
                super().log_message(fmt, *args)

        def respond(self, status, data, content_type="application/json; charset=utf-8", extra=None):
            body = json.dumps(data, ensure_ascii=False).encode() if isinstance(data, (dict, list)) else data
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; media-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
            for key, value in (extra or {}).items():
                self.send_header(key, value)
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def valid_host(self):
            return self.headers.get("Host") in {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}

        def stream_file(self,file):
            """Bounded memory, with byte ranges for seeking in saved local videos."""
            size=file.stat().st_size;start=0;end=size-1;status=200
            requested=self.headers.get('Range')
            if requested:
                import re
                match=re.fullmatch(r'bytes=(\d*)-(\d*)',requested)
                try:
                    if not match or not any(match.groups()):raise ValueError()
                    if not match[1]:start=max(0,size-int(match[2]))
                    else:start=int(match[1]);end=min(size-1,int(match[2])) if match[2] else size-1
                    if start>end or start>=size:raise ValueError()
                except ValueError:
                    return self.respond(416,b'','application/octet-stream',{'Content-Range':f'bytes */{size}'})
                status=206
            self.send_response(status)
            self.send_header('Content-Type',mimetypes.guess_type(file.name)[0] or 'application/octet-stream')
            self.send_header('Content-Length',str(end-start+1));self.send_header('Accept-Ranges','bytes')
            self.send_header('X-Content-Type-Options','nosniff');self.send_header('Cache-Control','no-store')
            if status==206:self.send_header('Content-Range',f'bytes {start}-{end}/{size}')
            self.end_headers()
            try:
                with file.open('rb') as source:
                    source.seek(start);remaining=end-start+1
                    while remaining:
                        chunk=source.read(min(65536,remaining))
                        if not chunk:break
                        self.wfile.write(chunk);remaining-=len(chunk)
            except (BrokenPipeError,ConnectionResetError):pass

        def do_GET(self):
            if not self.valid_host():
                return self.respond(403, {"error": "仅支持本机访问。"})
            path = unquote(urlsplit(self.path).path)
            if path == "/api/state":
                return self.respond(200, {"jobs": manager.state(), "token": token, "storage": manager.storage(),
                                          "folder": str(manager.downloads), "app": "local-image-downloader",
                                          "platforms":json.loads((ROOT/'platform-status.json').read_text('utf-8'))})
            if path == "/api/help":
                return self.respond(200, {"text": (ROOT / "README.md").read_text("utf-8")})
            parts = path.strip("/").split("/")
            if len(parts) == 3 and parts[0] in {"files", "thumbs"}:
                job = manager.get(parts[1])
                try:
                    index = int(parts[2])
                    if index < 0:
                        raise ValueError()
                    info = job["files"][index]
                    if parts[0] == 'files' and not info.get('saved'):
                        return self.respond(404, {'error':'这张原文件尚未保存。'})
                    file = manager.downloads / info["path"] if parts[0] == "files" else manager.preview_file(job,index)
                    if not file.resolve().is_relative_to((manager.downloads if parts[0] == "files" else manager.data).resolve()):
                        raise ValueError()
                    if parts[0]=='files':return self.stream_file(file)
                    return self.respond(200, file.read_bytes(), mimetypes.guess_type(file.name)[0] or "application/octet-stream")
                except (ValueError, IndexError, TypeError, KeyError, OSError):
                    return self.respond(404, {"error": "图片不存在。"})
            if len(parts) == 2 and parts[0] == "archive":
                job = manager.get(parts[1])
                if not job or not any(f.get('saved') for f in job['files']):
                    return self.respond(404, {"error": "没有可打包的图片。"})
                try:
                    archive,count=build_selected_archive(manager,[{'id':job['id'],'index':i} for i,f in enumerate(job['files']) if f.get('saved')])
                except (ValueError,OSError) as error:
                    return self.respond(400,{'error':str(error)})
                return self.respond(200,archive,'application/zip',{'Content-Disposition':f'attachment; filename="{job["platform"]}_{job["key"]}.zip"'})
            assets = {"/": "index.html", "/app.js": "app.js", "/style.css": "style.css", "/favicon.svg": "favicon.svg",
                      '/assets/instagram.svg':'assets/instagram.svg','/assets/x.svg':'assets/x.svg'}
            assets.update({f'/assets/{name}.svg':f'assets/{name}.svg' for name in PLATFORMS if name!='twitter'})
            if path in assets:
                file = ROOT / "web" / assets[path]
                return self.respond(200, file.read_bytes(), (mimetypes.guess_type(file.name)[0] or "text/plain") + "; charset=utf-8")
            self.respond(404, {"error": "页面不存在。"})

        def do_POST(self):
            if not self.valid_host() or self.headers.get("X-Local-Token") != token:
                return self.respond(403, {"error": "页面连接已失效，请刷新后重试。"})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 65536:
                    return self.respond(400, {"error": "输入内容过长或为空。"})
                body = json.loads(self.rfile.read(length))
                if not isinstance(body, dict):
                    raise ValueError("输入内容无效。")
                path = urlsplit(self.path).path
                if path == '/api/download':
                    return self.respond(202,manager.enqueue_download(body.get('items')))
                if path == '/api/cache/clear':
                    return self.respond(200,manager.clear_preview_cache())
                if path == "/api/archive":
                    archive, count = build_selected_archive(manager, body.get("items"))
                    return self.respond(200, archive, "application/zip", {
                        "Content-Disposition": 'attachment; filename="selected-images.zip"',
                        "X-Image-Count": str(count),
                    })
                if path == "/api/jobs":
                    if not isinstance(body.get("text"), str):
                        raise ValueError("请粘贴帖子链接。")
                    links, rejected = parse_links(body["text"])
                    if not links:
                        raise ValueError("请粘贴 Instagram、X、小红书、抖音、TikTok、B站、YouTube、微博或 Pinterest 的具体帖子链接。")
                    if len(links) > 30:
                        raise ValueError("一次最多添加 30 条帖子链接。")
                    jobs = []
                    for item in links:
                        job, duplicate = manager.submit(item)
                        jobs.append({"id": job["id"], "duplicate": duplicate})
                    return self.respond(202, {"jobs": jobs, "rejected": len(rejected)})
                if path == "/api/retry":
                    job, duplicate = manager.retry(body.get("id"))
                    return self.respond(202, {"id": job["id"], "duplicate": duplicate})
                if path == "/api/open-folder":
                    job = manager.get(body.get("id")) if body.get("id") else None
                    if body.get("id") and not job:
                        raise ValueError("下载记录不存在。")
                    folder = manager.downloads / job["folder"] if job else manager.downloads
                    folder.mkdir(parents=True, exist_ok=True)
                    if sys.platform == "darwin":
                        subprocess.Popen(["open", str(folder)])
                    elif os.name == "nt":
                        os.startfile(folder)
                    else:
                        subprocess.Popen(["xdg-open", str(folder)])
                    return self.respond(200, {"ok": True})
                return self.respond(404, {"error": "操作不存在。"})
            except (ValueError, TypeError, KeyError) as exc:
                return self.respond(400, {"error": str(exc) or "输入内容无效。"})
            except OSError:
                return self.respond(400, {"error": "本地文件无法读取，请检查图片是否已移动。"})

    return Handler


def main():
    parser = argparse.ArgumentParser(description="粘贴多平台链接先解析预览，点选后保存图片或视频。")
    parser.add_argument("--port", type=int, default=8767)
    parser.add_argument("--open", action="store_true")
    parser.add_argument('--data-dir',type=Path,default=ROOT,help='独立的数据和下载目录（可用于隔离测试）')
    args = parser.parse_args()
    manager = DownloadQueue(args.data_dir)
    try:
        server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(manager))
    except OSError as exc:
        print(f"无法启动：端口 {args.port} 已被占用。可运行 python server.py --port 8768", file=sys.stderr)
        raise SystemExit(1) from exc
    server.daemon_threads = True
    url = f"http://127.0.0.1:{server.server_port}"
    print(f"图片下载已启动：{url}\n图片保存位置：{manager.downloads}", flush=True)
    if args.open:
        threading.Timer(0.5, webbrowser.open, args=(url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。下载的图片和历史记录会保留。", flush=True)
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
