#!/usr/bin/env python3
"""检测本机可用的视频硬件编码器。

不依赖额外 Python 包；通过 FFmpeg 的 -encoders 输出判断 QSV / VideoToolbox。
"""
from __future__ import annotations

import platform
import subprocess


def ffmpeg_encoders(ffmpeg: str = "ffmpeg") -> str:
    try:
        p = subprocess.run([ffmpeg, "-hide_banner", "-encoders"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10)
        return p.stdout + p.stderr
    except (OSError, subprocess.SubprocessError):
        return ""


def detect(ffmpeg: str = "ffmpeg") -> dict:
    text = ffmpeg_encoders(ffmpeg)
    system = platform.system()
    result = {
        "platform": system,
        "qsv": "h264_qsv" in text or "hevc_qsv" in text or "av1_qsv" in text,
        "h264_qsv": "h264_qsv" in text,
        "hevc_qsv": "hevc_qsv" in text,
        "av1_qsv": "av1_qsv" in text,
        "videotoolbox": "h264_videotoolbox" in text or "hevc_videotoolbox" in text,
        "h264_videotoolbox": "h264_videotoolbox" in text,
        "hevc_videotoolbox": "hevc_videotoolbox" in text,
    }
    if system == "Windows" and result["hevc_qsv"]:
        result["recommended"] = "hevc_qsv"
        result["hardware"] = "Intel QSV / Arc"
    elif system == "Darwin" and result["hevc_videotoolbox"]:
        result["recommended"] = "hevc_videotoolbox"
        result["hardware"] = "Apple VideoToolbox"
    else:
        result["recommended"] = "libx265"
        result["hardware"] = "CPU"
    return result


if __name__ == "__main__":
    import json
    print(json.dumps(detect(), ensure_ascii=False, indent=2))
