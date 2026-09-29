#!/usr/bin/env python3
"""Cross-platform runner for the board-video compressor.

Keeps GUI concerns separate from FFmpeg execution.  It supports fixed FPS or
Smart VFR, resolution, H.264/H.265/AV1 and the selective board inversion hook.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Callable

from compress import build_command
from smart_vfr import build_smart_vfr_args


def build_smart_command(
    src: str,
    out: str,
    *,
    preset: str = "board-balanced",
    codec: str = "h265",
    fps: str = "智能 VFR",
    width: int | None = None,
    height: int | None = None,
    board_opt: bool = True,
    invert: bool = False,
    ffmpeg: str = "ffmpeg",
    min_fps: float = 15,
    max_fps: float = 30,
) -> list[str]:
    """Build the final FFmpeg command used by both desktop GUIs."""
    fixed = None if fps in ("智能 VFR", "smart", "vfr") else int(fps)
    args = build_command(
        src,
        out,
        preset=preset,
        codec=codec,
        fps=fixed,
        width=width,
        height=height,
        board_opt=board_opt,
        invert=invert,
        ffmpeg=ffmpeg,
    )
    if fixed is None:
        # Remove any fixed-rate option emitted by the base builder.
        cleaned: list[str] = []
        i = 0
        while i < len(args):
            if args[i] == "-r" and i + 1 < len(args):
                i += 2
                continue
            cleaned.append(args[i])
            i += 1
        vfr = build_smart_vfr_args(min_fps, max_fps)
        # Insert video filter arguments before output path.  The base command
        # always ends with the output path.
        output = cleaned.pop()
        cleaned.extend(vfr)
        cleaned.extend(["-fps_mode", "vfr", output])
        args = cleaned
    return args


def run(
    args: list[str],
    *,
    on_line: Callable[[str], None] | None = None,
) -> int:
    """Run FFmpeg and stream its output without opening a terminal window."""
    p = subprocess.Popen(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        universal_newlines=True,
    )
    assert p.stdout is not None
    for line in p.stdout:
        line = line.rstrip()
        if line and on_line:
            on_line(line)
    return p.wait()


def write_job(path: str, args: list[str]) -> None:
    Path(path).write_text(json.dumps(args, ensure_ascii=False, indent=2), encoding="utf-8")
