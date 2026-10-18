#!/bin/bash
set -e
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
fi
if ! .venv/bin/python -c 'import instaloader, gallery_dl, PIL, yt_dlp, imageio_ffmpeg, curl_cffi' 2>/dev/null; then
  .venv/bin/python -m pip install --disable-pip-version-check -r requirements.txt
fi
if ! .engines/f2/bin/python -c 'import f2' 2>/dev/null; then
  ./安装备用引擎.command || echo '备用引擎尚未就绪，抖音需要 Python 3.11+；其他已支持平台仍可使用。'
fi
if .venv/bin/python - <<'PY'
import json, sys, urllib.request, webbrowser
try:
    with urllib.request.urlopen('http://127.0.0.1:8767/api/state', timeout=1) as r:
        state = json.load(r)
    if state.get('app') == 'local-image-downloader':
        webbrowser.open('http://127.0.0.1:8767')
        sys.exit(0)
except Exception:
    pass
sys.exit(1)
PY
then
  exit 0
fi
exec .venv/bin/python server.py --open
