@echo off
setlocal
cd /d "%~dp0"
cls
where py >nul 2>nul
if %errorlevel%==0 (set PY=py) else (set PY=python)
%PY% -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
where ffmpeg >nul 2>nul
if errorlevel 1 (
  echo 未找到 FFmpeg，请先安装 FFmpeg 并加入 PATH。
  pause
  exit /b 1
)
python smart_gui.py
pause
