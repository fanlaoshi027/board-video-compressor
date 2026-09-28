#!/usr/bin/env python3
"""Windows EXE 启动入口。"""
from __future__ import annotations

import subprocess

# 预览使用 rawvideo 管道时，必须按实时速度输出。
# 否则 FFmpeg 会尽可能快地解码，播放器看起来会“倍速播放”，
# 拖动、暂停和时间指针也会跟不上。单帧定位不加 -re，保证定位仍然迅速。
_original_popen = subprocess.Popen


def _preview_realtime_popen(*args, **kwargs):
    if args and isinstance(args[0], (list, tuple)):
        cmd = list(args[0])
        is_raw_preview = (
            "-f" in cmd
            and "rawvideo" in cmd
            and "pipe:1" in cmd
            and "-i" in cmd
            and "-frames:v" not in cmd
        )
        if is_raw_preview and "-re" not in cmd:
            try:
                i = cmd.index("-i")
                cmd.insert(i, "-re")
                args = (cmd, *args[1:])
            except ValueError:
                pass
    return _original_popen(*args, **kwargs)


subprocess.Popen = _preview_realtime_popen

from app import App

if __name__ == "__main__":
    App().mainloop()
