#!/usr/bin/env python3
"""樊老师板书视频压缩器 - 第一阶段 CLI 核心。

针对白底黑字数学板书设计的 H.264 / H.265 / AV1 测试预设。
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

PRESETS = {
    "board-high": {"crf": 24, "fps": 30, "preset": "slow"},
    "board-balanced": {"crf": 27, "fps": 30, "preset": "slow"},
    "board-extreme": {"crf": 30, "fps": 30, "preset": "slow"},
}

CODECS = {
    "h264": "libx264",
    "h265": "libx265",
    "av1": "libsvtav1",
}


def require_binary(name: str) -> None:
    if shutil.which(name) is None:
        raise SystemExit(f"找不到 {name}。请先安装 FFmpeg，并把它加入 PATH。")


def probe(path: Path) -> dict:
    cmd = [
        "ffprobe", "-v", "error", "-print_format", "json",
        "-show_format", "-show_streams", str(path)
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def build_command(input_path: Path, output_path: Path, codec: str, preset_name: str) -> list[str]:
    p = PRESETS[preset_name]
    encoder = CODECS[codec]

    cmd = [
        "ffmpeg", "-hide_banner", "-y",
        "-i", str(input_path),
        "-map", "0:v:0",
        "-map", "0:a?",
        "-r", str(p["fps"]),
        "-c:v", encoder,
        "-preset", p["preset"],
        "-crf", str(p["crf"]),
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "64k",
        "-movflags", "+faststart",
        str(output_path),
    ]

    if codec == "av1":
        # SVT-AV1 的 preset 数值越小越慢、通常压缩效率越高。
        cmd[cmd.index("-preset") + 1] = "6"

    return cmd


def main() -> int:
    parser = argparse.ArgumentParser(description="樊老师板书视频压缩器")
    parser.add_argument("input", nargs="?", help="输入 MP4")
    parser.add_argument("--preset", choices=PRESETS, default="board-balanced")
    parser.add_argument("--codec", choices=CODECS, default="h265")
    parser.add_argument("--output", help="输出文件路径")
    args = parser.parse_args()

    require_binary("ffmpeg")
    require_binary("ffprobe")

    if not args.input:
        parser.error("请指定输入 MP4，例如：python compress.py lesson.mp4")

    input_path = Path(args.input).expanduser().resolve()
    if not input_path.exists():
        raise SystemExit(f"输入文件不存在：{input_path}")

    info = probe(input_path)
    video = next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), None)
    if video:
        print(f"输入：{input_path.name}")
        print(f"分辨率：{video.get('width')}×{video.get('height')}  原编码：{video.get('codec_name')}  原帧率：{video.get('r_frame_rate')}")
    print(f"预设：{args.preset}  编码：{args.codec}  CRF：{PRESETS[args.preset]['crf']}  输出帧率：30fps")

    output_path = Path(args.output).expanduser().resolve() if args.output else input_path.with_name(
        f"{input_path.stem}_{args.codec}_{args.preset}.mp4"
    )
    cmd = build_command(input_path, output_path, args.codec, args.preset)
    print("开始压缩……")
    print(" ".join(f'"{x}"' if " " in x else x for x in cmd))
    subprocess.run(cmd, check=True)

    before = input_path.stat().st_size
    after = output_path.stat().st_size
    saved = (1 - after / before) * 100 if before else 0
    print(f"完成：{output_path}")
    print(f"原大小：{before / 1024 / 1024:.1f} MB")
    print(f"新大小：{after / 1024 / 1024:.1f} MB")
    print(f"节省：{saved:.1f}%")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as exc:
        print(f"FFmpeg 执行失败，退出码：{exc.returncode}", file=sys.stderr)
        raise SystemExit(exc.returncode)
