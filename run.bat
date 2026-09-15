@echo off
setlocal
if "%~1"=="" (
  echo 请把 MP4 文件拖到 run.bat 上。
  pause
  exit /b 1
)

python compress.py "%~1" --preset board-balanced --codec h265
pause
