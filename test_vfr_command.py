#!/usr/bin/env python3
"""快速检查生成的 VFR filter 是否能被 FFmpeg 接受。"""
from vfr import build_vfr_filter

if __name__ == '__main__':
    print(build_vfr_filter(min_fps=2, max_fps=15))
