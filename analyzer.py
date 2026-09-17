#!/usr/bin/env python3
"""板书视频分析：识别白底、静止程度，并推荐压缩帧率。

只使用 FFmpeg/FFprobe + Python 标准库，便于 Windows/macOS 随软件打包。
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path


def probe(path: Path, ffprobe: str = "ffprobe") -> dict:
    p = subprocess.run(
        [ffprobe, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", check=True,
    )
    return json.loads(p.stdout)


def _frame(path: Path, ts: float, ffmpeg: str) -> bytes:
    cmd = [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-ss", f"{ts:.3f}", "-i", str(path),
        "-frames:v", "1", "-vf", "scale=96:54", "-f", "rawvideo", "-pix_fmt", "gray", "-",
    ]
    try:
        return subprocess.run(cmd, capture_output=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return b""


def _mean(data: bytes) -> float:
    return sum(data) / len(data) if data else 0.0


def analyze(path: Path, ffmpeg: str = "ffmpeg", ffprobe: str = "ffprobe") -> dict:
    info = probe(path, ffprobe)
    video = next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), {})
    width = int(video.get("width") or 0)
    height = int(video.get("height") or 0)
    duration = float(info.get("format", {}).get("duration") or 0)

    count = 8
    frames = []
    if duration > 0:
        for i in range(count):
            frames.append(_frame(path, duration * (i + 1) / (count + 1), ffmpeg))
    frames = [f for f in frames if len(f) == 96 * 54]

    white_scores = []
    changes = []
    for frame in frames:
        # 白底板书通常整体亮度很高；使用平均亮度作为第一层筛选。
        white_scores.append(sum(1 for x in frame if x >= 225) / len(frame))
    for a, b in zip(frames, frames[1:]):
        changes.append(sum(abs(x - y) for x, y in zip(a, b)) / len(a) / 255.0)

    white_ratio = sum(white_scores) / len(white_scores) if white_scores else 0.0
    change_ratio = sum(changes) / len(changes) if changes else 1.0
    still_ratio = max(0.0, min(1.0, 1.0 - change_ratio * 4.0))

    # 对典型白底、长时间静止的板书，15fps 优先；运动明显时提高到20/30fps。
    board_score = max(0.0, min(100.0, white_ratio * 65 + still_ratio * 35))
    if board_score >= 82 and still_ratio >= 0.72:
        recommended_fps = 15
    elif board_score >= 68 and still_ratio >= 0.55:
        recommended_fps = 20
    else:
        recommended_fps = 30

    return {
        "file": str(path),
        "width": width,
        "height": height,
        "duration": duration,
        "white_ratio": round(white_ratio, 4),
        "still_ratio": round(still_ratio, 4),
        "board_score": round(board_score, 1),
        "recommended_fps": recommended_fps,
        "samples": len(frames),
    }


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="分析数学板书视频并推荐输出帧率")
    parser.add_argument("input")
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument("--ffprobe", default="ffprobe")
    args = parser.parse_args()
    print(json.dumps(analyze(Path(args.input).expanduser().resolve(), args.ffmpeg, args.ffprobe), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
