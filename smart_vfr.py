#!/usr/bin/env python3
"""板书智能 VFR 压缩流水线。

先分析视频的书写强度，再在最低/最高 FPS 范围内输出 VFR。
这是实验模块，不改变原有固定 FPS 压缩流程。
"""
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from board_analyzer import analyze_video
from vfr import build_vfr_filter, recommend_range


def choose_range(report: dict, minimum: int = 15, maximum: int = 30) -> tuple[int, int]:
    intensity = float(report.get("write_intensity", 0.0))
    lo, hi = recommend_range(intensity)
    return max(minimum, lo), min(maximum, hi)


def build_command(src: Path, dst: Path, min_fps: int, max_fps: int, crf: int = 27) -> list[str]:
    vf = build_vfr_filter(min_fps=min_fps, max_fps=max_fps)
    return [
        "ffmpeg", "-hide_banner", "-y", "-i", str(src),
        "-vf", vf,
        "-fps_mode", "vfr",
        "-c:v", "libx265", "-preset", "slow", "-crf", str(crf),
        "-pix_fmt", "yuv420p",
        "-map", "0:v:0", "-map", "0:a?",
        "-c:a", "aac", "-b:a", "64k",
        "-movflags", "+faststart", str(dst),
    ]


def main() -> int:
    p = argparse.ArgumentParser(description="樊老师板书智能 VFR 压缩实验器")
    p.add_argument("input")
    p.add_argument("--output")
    p.add_argument("--min-fps", type=int, default=15)
    p.add_argument("--max-fps", type=int, default=30)
    p.add_argument("--crf", type=int, default=27)
    args = p.parse_args()

    src = Path(args.input).resolve()
    dst = Path(args.output).resolve() if args.output else src.with_name(src.stem + "_智能VFR.mp4")
    report = analyze_video(src)
    lo, hi = choose_range(report, args.min_fps, args.max_fps)
    print(f"板书分析：{report}")
    print(f"智能 VFR：{lo}～{hi} FPS")
    cmd = build_command(src, dst, lo, hi, args.crf)
    return subprocess.run(cmd).returncode


if __name__ == "__main__":
    raise SystemExit(main())
