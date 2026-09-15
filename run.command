#!/bin/bash
set -e

cd "$(dirname "$0")"

if ! command -v python3 >/dev/null 2>&1; then
  echo "未找到 Python 3。"
  echo "请先安装 Python 3，再重新运行。"
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
  echo "樊老师板书视频压缩器"
  echo "用法："
  echo "  ./run.command input.mp4"
  echo "  ./run.command input.mp4 --preset board-balanced --codec h265"
  echo
  read -r -p "按回车退出..."
  exit 0
fi

python3 compress.py "$@"
