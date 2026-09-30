from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Callable, Optional
import subprocess


@dataclass
class CompressOptions:
    profile: str = "teacher_board"
    codec: str = "h265"
    max_fps: float = 15.0
    min_fps: float = 2.0
    smart_invert: bool = False
    crf: int = 25


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
    cmd = [
        "ffmpeg",
        "-y",
        "-i", str(input_file),
        "-c:v", "libx265",
        "-crf", str(options.crf),
        "-preset", "medium",
        "-c:a", "aac",
        "-b:a", "128k",
        "-movflags", "+faststart",
    ]

    # VFR 参数由后续 vfr_engine 注入，这里保持统一入口。
    if options.smart_invert:
        cmd += ["-vf", "smart_invert"]

    cmd.append(str(output_file))
    return cmd


def compress_video(
    input_file: str,
    output_file: str,
    options: Optional[CompressOptions] = None,
    progress: Optional[Callable[[str], None]] = None,
) -> CompressResult:
    """统一压缩入口。"""
    options = options or CompressOptions()

    src = Path(input_file)
    dst = Path(output_file)

    if not src.exists():
        return CompressResult(str(src), str(dst), False, "输入文件不存在")

    if progress:
        progress("生成 FFmpeg 编码参数")

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
