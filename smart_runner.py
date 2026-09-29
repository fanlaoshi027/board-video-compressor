#!/usr/bin/env python3
"""板书压缩器统一执行层。

GUI 不直接拼 FFmpeg 参数，固定帧率和智能 VFR 都从这里生成命令。
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Callable

from compress import build_command
from vfr import build_vfr_filter


def build_smart_command(
    src: str,
    out: str,
    *,
    preset: str = "board-balanced",
    codec: str = "h265",
    fps: str = "智能 VFR",
    width: int | None = None,
    height: int | None = None,
    keep_aspect: bool = True,
    board_opt: bool = True,
    invert: bool = False,
    ffmpeg: str = "ffmpeg",
    src_w: int | None = None,
    src_h: int | None = None,
    encoder: str | None = None,
    min_fps: float = 15,
    max_fps: float = 30,
    has_audio: bool = True,
    duration: float = 0,
) -> list[str]:
    """生成固定 FPS 或智能 VFR 的完整 FFmpeg 命令。"""
    fixed = None if fps in ("智能 VFR", "smart", "vfr") else int(fps)

    if fixed is not None:
        return build_command(
            src, out, codec, preset,
            fps=fixed, width=width, height=height,
            keep_aspect=keep_aspect, invert=invert,
            src_w=src_w, src_h=src_h, encoder=encoder,
            ffmpeg=ffmpeg, board_optimized=board_opt,
            duration=duration, has_audio=has_audio,
        )

    # 智能 VFR：复用基础编码参数，但取消固定 -r/-fps_mode=cfr，
    # 用板书运动自适应 select + fps_mode=vfr。
    base = build_command(
        src, out, codec, preset,
        fps=min_fps, width=width, height=height,
        keep_aspect=keep_aspect, invert=invert,
        src_w=src_w, src_h=src_h, encoder=encoder,
        ffmpeg=ffmpeg, board_optimized=board_opt,
        duration=duration, has_audio=has_audio,
    )

    cleaned: list[str] = []
    i = 0
    while i < len(base):
        if base[i] == "-r" and i + 1 < len(base):
            i += 2
            continue
        if base[i] == "-fps_mode" and i + 1 < len(base):
            i += 2
            continue
        if base[i] == "-g" and i + 1 < len(base):
            i += 2
            continue
        if base[i] == "-keyint_min" and i + 1 < len(base):
            i += 2
            continue
        cleaned.append(base[i])
        i += 1

    # 找到 -vf 并替换其表达式，把原有缩放/反色/锐化链放在 select 前。
    vf_index = cleaned.index("-vf")
    original_vf = cleaned[vf_index + 1]
    adaptive = build_vfr_filter(min_fps=min_fps, max_fps=max_fps)
    cleaned[vf_index + 1] = f"{original_vf},{adaptive}"

    # VFR 不需要固定 GOP 时间参数；保留编码器 preset/quality。
    cleaned.insert(cleaned.index("-c:v"), "-fps_mode")
    cleaned.insert(cleaned.index("-fps_mode") + 1, "vfr")
    return cleaned


def parse_progress_line(line: str) -> dict[str, str]:
    """解析 FFmpeg -progress 输出的一行。"""
    if "=" not in line:
        return {}
    key, value = line.rstrip().split("=", 1)
    return {key: value}


def run(
    args: list[str],
    *,
    duration: float = 0,
    on_line: Callable[[str], None] | None = None,
    on_progress: Callable[[float, dict[str, str]], None] | None = None,
) -> int:
    """执行 FFmpeg，同时向 GUI 回报进度。"""
    # -progress pipe:1 输出机器可读进度；日志仍然输出到 stderr。
    command = list(args)
    command[1:1] = ["-progress", "pipe:1", "-nostats"]
    p = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
    assert p.stdout is not None
    state: dict[str, str] = {}
    for raw in p.stdout:
        line = raw.rstrip()
        item = parse_progress_line(line)
        if item:
            state.update(item)
            if on_progress:
                seconds = float(state.get("out_time_us", "0") or 0) / 1_000_000
                percent = max(0.0, min(100.0, seconds / duration * 100.0)) if duration > 0 else 0.0
                if state.get("progress") == "end":
                    percent = 100.0
                on_progress(percent, dict(state))
        elif line and on_line:
            on_line(line)
    return p.wait()


def write_job(path: str, args: list[str]) -> None:
    Path(path).write_text(json.dumps(args, ensure_ascii=False, indent=2), encoding="utf-8")
