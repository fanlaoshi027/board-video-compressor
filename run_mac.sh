#!/bin/bash
set -e
cd "$(dirname "$0")"
clear
PYTHON_BIN="$(command -v python3 || true)"
if [ -z "$PYTHON_BIN" ]; then
  echo "未找到 Python 3，请先安装 Python 3.11+。"
  exit 1
fi
"$PYTHON_BIN" -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "未找到 FFmpeg。"
  if command -v brew >/dev/null 2>&1; then
    brew install ffmpeg
  else
    echo "请先安装 Homebrew，再重新运行本脚本。"
    exit 1
  fi
fi
python smart_gui.py
