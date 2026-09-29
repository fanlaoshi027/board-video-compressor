#!/bin/bash
set -e
cd "$(dirname "$0")"

if ! command -v python3 >/dev/null 2>&1; then
  echo "未找到 Python 3。"
  echo "请先安装 Python 3。"
  read -r -p "按回车退出..."
  exit 1
fi

if ! command -v ffmpeg >/dev/null 2>&1 || ! command -v ffprobe >/dev/null 2>&1; then
  echo "未找到 FFmpeg。"
  echo "macOS 可使用 Homebrew 安装：brew install ffmpeg"
  read -r -p "按回车退出..."
  exit 1
fi

if [ "$#" -eq 0 ]; then
  exec python3 macos_app.py
fi

python3 compress.py "$@"
