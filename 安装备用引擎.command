#!/bin/bash
set -e
cd "$(dirname "$0")"
runtime_python=""
for candidate in python3.13 python3.12 python3.11 python3; do
  if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; assert sys.version_info >= (3,11)' 2>/dev/null; then
    runtime_python="$candidate"
    break
  fi
done
if [ -z "$runtime_python" ]; then
  echo '抖音备用引擎需要 Python 3.11 或更新版本，请先安装后再运行。'
  exit 1
fi
mkdir -p .engines
"$runtime_python" -m venv .engines/f2
.engines/f2/bin/python -m pip install --disable-pip-version-check 'f2 @ https://codeload.github.com/Johnserf-Seed/f2/tar.gz/f6be8c0ffba9a127075bbeafe4838716650b6325#sha256=37b499b2e343891c4112e6f204f0029fc2f9d35e15e5d7c5e1d23b8d470a2e65'
echo '备用引擎已安装，粘贴抖音链接后会自动使用。'
