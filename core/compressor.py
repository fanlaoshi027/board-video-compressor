from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Callable, Optional


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


def compress_video(
    input_file: str,
    output_file: str,
    options: Optional[CompressOptions] = None,
    progress: Optional[Callable[[str], None]] = None,
) -> CompressResult:
    """统一压缩入口。

    GUI、批量任务、命令行后续都调用这里。
    实际编码器保持与现有 smart_runner/compress 模块兼容，
    后续逐步迁移到 core 层。
    """
    options = options or CompressOptions()

    if progress:
        progress("准备分析板书视频")

    src = Path(input_file)
    dst = Path(output_file)

    if not src.exists():
        return CompressResult(str(src), str(dst), False, "输入文件不存在")

    # 这里暂时作为统一入口占位。
    # 下一步接入现有 smart_runner.run_compress。
    if progress:
        progress(f"等待编码模块接入: {options.profile}")

    return CompressResult(
        str(src),
        str(dst),
        False,
        "core compressor created; encoder migration pending",
    )
