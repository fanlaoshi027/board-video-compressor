#!/usr/bin/env python3
"""板书视频分析器。

针对 1920x1080/60fps 白底数学板书：
- 抽样分析相邻帧变化
- 区分全画面变化与局部变化
- 估算静止、普通书写、连续快速书写比例
- 给智能 VFR 提供保守的最低/最高 FPS 建议

这是分析层，不修改原视频，也不直接决定最终编码参数。
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
import json
import subprocess
from typing import Optional


@dataclass
class BoardAnalysis:
    width: int
    height: int
    source_fps: float
    duration: float
    white_ratio: float
    mean_change: float
    local_change_ratio: float
    still_ratio: float
    writing_ratio: float
    fast_writing_ratio: float
    min_fps: int
    max_fps: int

    @property
    def mode(self) -> str:
        if self.fast_writing_ratio >= 0.18:
            return "快速连续书写"
        if self.writing_ratio >= 0.20:
            return "普通连续书写"
        return "静止/讲解为主"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["mode"] = self.mode
        return d


def _run(cmd: list[str], timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          text=True, timeout=timeout)


def probe_video(path: str | Path, ffprobe: str = "ffprobe") -> tuple[int, int, float, float]:
    """读取视频基本参数。"""
    cmd = [ffprobe, "-v", "error", "-select_streams", "v:0",
           "-show_entries", "stream=width,height,r_frame_rate,duration",
           "-show_entries", "format=duration", "-of", "json", str(path)]
    p = _run(cmd)
    if p.returncode:
        raise RuntimeError(p.stderr.strip() or "ffprobe failed")
    data = json.loads(p.stdout)
    s = data["streams"][0]
    a, b = (s.get("r_frame_rate") or "0/1").split("/")
    fps = float(a) / float(b) if float(b) else 0.0
    duration = float(s.get("duration") or data.get("format", {}).get("duration") or 0)
    return int(s["width"]), int(s["height"]), fps, duration


def analyze(path: str | Path, ffmpeg: str = "ffmpeg", ffprobe: str = "ffprobe",
            sample_fps: float = 5.0, max_seconds: float = 180.0) -> BoardAnalysis:
    """对视频做轻量抽样分析。

    不读取所有 60fps 帧，而是先缩小到约 320px 宽并以 sample_fps 抽样，
    这样分析速度远快于完整逐帧扫描。局部变化通过边缘/亮度差异的空间分布估计。
    """
    width, height, source_fps, duration = probe_video(path, ffprobe)
    duration = min(duration, max_seconds) if duration else max_seconds

    # 输出灰度缩略帧到 rawvideo。缩小后的数据足够判断板书的大面积静止与局部书写。
    small_w = 320
    small_h = max(2, int(round(height * small_w / width)))
    cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-i", str(path),
           "-t", str(duration), "-vf", f"fps={sample_fps},scale={small_w}:{small_h},format=gray",
           "-f", "rawvideo", "pipe:1"]
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=300)
    if p.returncode:
        raise RuntimeError(p.stderr.decode("utf-8", "ignore").strip() or "ffmpeg analysis failed")

    import numpy as np
    frame_size = small_w * small_h
    frames = np.frombuffer(p.stdout, dtype=np.uint8)
    count = len(frames) // frame_size
    if count < 2:
        raise RuntimeError("视频太短，无法分析")
    frames = frames[:count * frame_size].reshape((count, small_h, small_w))

    # 白底比例：灰度值高的像素占比。
    white_ratio = float((frames > 235).mean())

    prev = frames[:-1].astype(np.int16)
    cur = frames[1:].astype(np.int16)
    diff = np.abs(cur - prev)
    mean_diff = diff.mean(axis=(1, 2))
    mean_change = float(mean_diff.mean() / 255.0)

    # 只看发生变化的像素，再估算变化是否集中在小区域。
    changed = diff > 12
    changed_ratio = changed.mean(axis=(1, 2))
    local_change_ratio = float((changed_ratio < 0.12).mean())

    # 阈值采用保守范围，后续用真实 60fps 原片校准。
    still = mean_change < 0.012
    writing = (mean_change >= 0.012) & (mean_change < 0.045)
    fast = mean_change >= 0.045

    still_ratio = float(still.mean())
    writing_ratio = float(writing.mean())
    fast_ratio = float(fast.mean())

    if fast_ratio >= 0.18:
        min_fps, max_fps = 20, 30
    elif writing_ratio >= 0.20:
        min_fps, max_fps = 15, 24
    else:
        min_fps, max_fps = 15, 20

    return BoardAnalysis(width, height, source_fps, duration, white_ratio,
                         mean_change, local_change_ratio, still_ratio,
                         writing_ratio, fast_ratio, min_fps, max_fps)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--ffmpeg", default="ffmpeg")
    ap.add_argument("--ffprobe", default="ffprobe")
    args = ap.parse_args()
    result = analyze(args.video, args.ffmpeg, args.ffprobe)
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
