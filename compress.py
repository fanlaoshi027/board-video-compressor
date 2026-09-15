#!/usr/bin/env python3
"""樊老师板书视频压缩器 - 板书专用核心。

针对白底黑字数学板书：
- 可自定义输出帧率（如 15/20/24/30/60）
- 可自定义分辨率，并可锁定原始宽高比
- H.264 / H.265 / AV1
- 智能反色：仅反转黑白/低饱和度板书区域，彩色笔迹保持原色
- 长 GOP + HEVC，让长时间静止、局部写字的画面更省空间
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
    "board-balanced": {"crf": 27, "fps": 15, "preset": "slow"},
    "board-extreme": {"crf": 30, "fps": 15, "preset": "slow"},
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


def _parse_fraction(value: str | None) -> float | None:
    if not value or value == "0/0":
        return None
    try:
        if "/" in value:
            a, b = value.split("/", 1)
            return float(a) / float(b)
        return float(value)
    except (ValueError, ZeroDivisionError):
        return None


def detect_whiteboard(path: Path) -> bool:
    """用 FFmpeg 抽样读取画面四角，判断是否属于典型白底板书。"""
    info = probe(path)
    duration = float(info.get("format", {}).get("duration") or 0)
    if duration <= 0:
        return False

    timestamps = [duration * x for x in (0.10, 0.30, 0.50, 0.70, 0.90)]
    scores: list[float] = []
    for ts in timestamps:
        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "error",
            "-ss", f"{ts:.3f}", "-i", str(path),
            "-frames:v", "1", "-vf", "scale=64:36", "-f", "rawvideo", "-pix_fmt", "gray", "-",
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, check=True)
        except subprocess.CalledProcessError:
            continue
        data = result.stdout
        if len(data) != 64 * 36:
            continue
        w, h = 64, 36
        pts = []
        for x0, y0 in ((0, 0), (w - 8, 0), (0, h - 8), (w - 8, h - 8)):
            block = [data[y * w + x] for y in range(y0, y0 + 8) for x in range(x0, x0 + 8)]
            pts.extend(block)
        scores.append(sum(pts) / len(pts))

    return bool(scores) and sum(scores) / len(scores) >= 205


def calculate_output_size(width: int | None, height: int | None, src_w: int, src_h: int,
                          keep_aspect: bool) -> tuple[int, int] | None:
    if width is None and height is None:
        return None

    if keep_aspect:
        ratio = src_w / src_h
        if width and height:
            if width / height > ratio:
                width = round(height * ratio)
            else:
                height = round(width / ratio)
        elif width:
            height = round(width / ratio)
        elif height:
            width = round(height * ratio)

    assert width is not None and height is not None
    width = max(2, width - width % 2)
    height = max(2, height - height % 2)
    return width, height


def build_command(input_path: Path, output_path: Path, codec: str, preset_name: str,
                  fps: int | None = None, width: int | None = None, height: int | None = None,
                  keep_aspect: bool = True, invert: str = "off", src_w: int | None = None,
                  src_h: int | None = None) -> list[str]:
    p = PRESETS[preset_name]
    encoder = CODECS[codec]
    target_fps = fps or p["fps"]

    vf: list[str] = []
    if width or height:
        if not src_w or not src_h:
            raise ValueError("设置分辨率时需要原视频尺寸")
        size = calculate_output_size(width, height, src_w, src_h, keep_aspect)
        assert size is not None
        vf.append(f"scale={size[0]}:{size[1]}:flags=lanczos")
    if invert == "on":
        # 只反转低饱和度（黑/白/灰）区域；高饱和度彩色笔迹保持原色。
        # geq：根据 RGB 三通道差异近似判断饱和度，彩色区域直接保留原值，
        # 低饱和度区域按亮度反转，白底目标约为 10% 亮度（约90%黑）。
        vf.append("format=rgb24,geq=r='if(gt(abs(r(X,Y)-g(X,Y))+abs(g(X,Y)-b(X,Y)),36),r(X,Y),255-r(X,Y)*0.9)':g='if(gt(abs(r(X,Y)-g(X,Y))+abs(g(X,Y)-b(X,Y)),36),g(X,Y),255-g(X,Y)*0.9)':b='if(gt(abs(r(X,Y)-g(X,Y))+abs(g(X,Y)-b(X,Y)),36),b(X,Y),255-b(X,Y)*0.9)',format=yuv420p")

    # 板书画面“长时间静止 + 局部写字”，适合较长 GOP，让编码器充分利用前后帧相似度。
    gop = max(30, target_fps * 5)

    cmd = [
        "ffmpeg", "-hide_banner", "-y",
        "-i", str(input_path),
        "-map", "0:v:0",
        "-map", "0:a?",
        "-vf", ",".join(vf) if vf else "null",
        "-r", str(target_fps),
        "-fps_mode", "cfr",
        "-c:v", encoder,
        "-preset", p["preset"],
        "-crf", str(p["crf"]),
        "-g", str(gop),
        "-keyint_min", str(max(1, target_fps)),
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "64k",
        "-movflags", "+faststart",
        str(output_path),
    ]

    if codec == "av1":
        cmd[cmd.index("-preset") + 1] = "6"

    return cmd


def main() -> int:
    parser = argparse.ArgumentParser(description="樊老师板书视频压缩器")
    parser.add_argument("input", nargs="?", help="输入 MP4")
    parser.add_argument("--preset", choices=PRESETS, default="board-balanced")
    parser.add_argument("--codec", choices=CODECS, default="h265")
    parser.add_argument("--fps", type=int, choices=[15, 20, 24, 25, 30, 50, 60], help="输出帧率")
    parser.add_argument("--width", type=int, help="输出宽度")
    parser.add_argument("--height", type=int, help="输出高度")
    parser.add_argument("--no-keep-aspect", action="store_true", help="取消锁定宽高比，允许按指定尺寸拉伸")
    parser.add_argument("--invert", choices=["auto", "on", "off"], default="off", help="智能反色/强制反色/关闭")
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
    if not video:
        raise SystemExit("输入文件没有找到视频流")

    src_w, src_h = int(video.get("width") or 0), int(video.get("height") or 0)
    src_fps = _parse_fraction(video.get("avg_frame_rate")) or _parse_fraction(video.get("r_frame_rate"))
    target_fps = args.fps or PRESETS[args.preset]["fps"]

    do_invert = args.invert
    if do_invert == "auto":
        detected = detect_whiteboard(input_path)
        do_invert = "on" if detected else "off"
        print(f"智能反色：{'检测到白底板书，已开启' if detected else '未检测到典型白底，保持原色'}")

    size = calculate_output_size(args.width, args.height, src_w, src_h, not args.no_keep_aspect)
    size_text = f"{size[0]}×{size[1]}" if size else f"保持 {src_w}×{src_h}"

    print(f"输入：{input_path.name}")
    print(f"原分辨率：{src_w}×{src_h}  原帧率：{src_fps:.2f}fps" if src_fps else f"原分辨率：{src_w}×{src_h}")
    print(f"输出：{size_text}  {target_fps}fps  编码：{args.codec}  CRF：{PRESETS[args.preset]['crf']}")
    print(f"宽高比：{'锁定' if not args.no_keep_aspect else '不锁定'}  反色：{do_invert}")

    output_path = Path(args.output).expanduser().resolve() if args.output else input_path.with_name(
        f"{input_path.stem}_{args.codec}_{target_fps}fps_{args.preset}.mp4"
    )
    cmd = build_command(
        input_path, output_path, args.codec, args.preset,
        fps=target_fps, width=args.width, height=args.height,
        keep_aspect=not args.no_keep_aspect, invert=do_invert,
        src_w=src_w, src_h=src_h,
    )
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
