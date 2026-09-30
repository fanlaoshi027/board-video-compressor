from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Callable, Optional
import subprocess

try:
    from .vfr_engine import build_vfr_args
except ImportError:
    build_vfr_args = None


@dataclass
class CompressOptions:
    profile: str = "teacher_board"
    codec: str = "h265"
    max_fps: float = 15.0
    min_fps: float = 2.0
    smart_invert: bool = False
    crf: int = 25
    enable_vfr: bool = True


@dataclass
class CompressResult:
    input_file: str
    output_file: str
    success: bool
    message: str = ""

    def to_dict(self):
        return asdict(self)


def build_ffmpeg_command(input_file: str, output_file: str, options: CompressOptions):
    """生成板书视频专用 FFmpeg 命令。"""
    cmd = ["ffmpeg", "-y", "-i", str(input_file)]

    filters = []

    if options.enable_vfr and build_vfr_args:
        vfr_args = build_vfr_args(
            min_fps=options.min_fps,
            max_fps=options.max_fps,
        )
        filters.extend(vfr_args)

    if options.smart_invert:
        filters.append("smart_invert")

    if filters:
        cmd += ["-vf", ",".join(filters)]

    codec = "libx265" if options.codec == "h265" else "libx264"

    cmd += [
        "-c:v", codec,
        "-crf", str(options.crf),
        "-preset", "medium",
        "-c:a", "aac",
        "-b:a", "128k",
        "-movflags", "+faststart",
        "-fps_mode", "vfr" if options.enable_vfr else "cfr",
        str(output_file),
    ]

    return cmd


def compress_video(
    input_file: str,
    output_file: str,
    options: Optional[CompressOptions] = None,
    progress: Optional[Callable[[str], None]] = None,
) -> CompressResult:
    options = options or CompressOptions()

    src = Path(input_file)
    dst = Path(output_file)

    if not src.exists():
        return CompressResult(str(src), str(dst), False, "输入文件不存在")

    if progress:
        progress("生成板书 VFR 编码参数")

    cmd = build_ffmpeg_command(src, dst, options)

    if progress:
        progress("开始 H.265 板书压缩")

    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode != 0:
            return CompressResult(str(src), str(dst), False, result.stderr[-500:])
    except Exception as e:
        return CompressResult(str(src), str(dst), False, str(e))

    return CompressResult(str(src), str(dst), True, "压缩完成")
