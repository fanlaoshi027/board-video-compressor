#!/usr/bin/env python3
"""樊老师板书视频压缩器 - 跨平台板书压缩核心。"""
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

CODECS = {"h264": "libx264", "h265": "libx265", "av1": "libsvtav1"}
HARDWARE_CODECS = {"h264_qsv": "h264_qsv", "h265_qsv": "hevc_qsv", "av1_qsv": "av1_qsv", "h264_vtb": "h264_videotoolbox", "h265_vtb": "hevc_videotoolbox"}


def require_binary(name: str) -> None:
    if shutil.which(name) is None:
        raise SystemExit(f"找不到 {name}。请确认 FFmpeg 已内置或已加入 PATH。")


def probe(path: Path, ffprobe: str = "ffprobe") -> dict:
    result = subprocess.run([ffprobe, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)], capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def available_encoders(ffmpeg: str = "ffmpeg") -> set[str]:
    try:
        p = subprocess.run([ffmpeg, "-hide_banner", "-encoders"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10)
        text = p.stdout + p.stderr
        return {name for name in set(HARDWARE_CODECS.values()) | set(CODECS.values()) if name in text}
    except (OSError, subprocess.SubprocessError):
        return set()


def _parse_fraction(value: str | None) -> float | None:
    if not value or value == "0/0": return None
    try:
        if "/" in value:
            a, b = value.split("/", 1); return float(a) / float(b)
        return float(value)
    except (ValueError, ZeroDivisionError): return None


def detect_whiteboard(path: Path, ffprobe: str = "ffprobe", ffmpeg: str = "ffmpeg") -> bool:
    info = probe(path, ffprobe); duration = float(info.get("format", {}).get("duration") or 0)
    if duration <= 0: return False
    scores: list[float] = []
    for ts in [duration*x for x in (0.10, 0.30, 0.50, 0.70, 0.90)]:
        cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-ss", f"{ts:.3f}", "-i", str(path), "-frames:v", "1", "-vf", "scale=64:36", "-f", "rawvideo", "-pix_fmt", "gray", "-"]
        try: data = subprocess.run(cmd, capture_output=True, check=True).stdout
        except subprocess.CalledProcessError: continue
        if len(data) != 2304: continue
        pts = []
        for x0, y0 in ((0,0),(56,0),(0,28),(56,28)):
            pts.extend(data[y*64+x] for y in range(y0,y0+8) for x in range(x0,x0+8))
        scores.append(sum(pts)/len(pts))
    return bool(scores) and sum(scores)/len(scores) >= 205


def calculate_output_size(width, height, src_w, src_h, keep_aspect):
    if width is None and height is None: return None
    if keep_aspect:
        ratio = src_w / src_h
        if width and height:
            if width / height > ratio: width = round(height * ratio)
            else: height = round(width / ratio)
        elif width: height = round(width / ratio)
        elif height: width = round(height * ratio)
    assert width is not None and height is not None
    return max(2,width-width%2), max(2,height-height%2)


def build_command(input_path, output_path, codec, preset_name, fps=None, width=None, height=None,
                  keep_aspect=True, invert="off", src_w=None, src_h=None, encoder=None,
                  ffmpeg="ffmpeg"):
    p = PRESETS[preset_name]; target_fps = fps or p["fps"]
    encoder = encoder or CODECS[codec]
    vf = []
    if width or height:
        if not src_w or not src_h: raise ValueError("设置分辨率时需要原视频尺寸")
        size = calculate_output_size(width,height,src_w,src_h,keep_aspect); vf.append(f"scale={size[0]}:{size[1]}:flags=lanczos")
    if invert == "on":
        vf.append("format=rgb24,geq=r='if(gt(abs(r(X,Y)-g(X,Y))+abs(g(X,Y)-b(X,Y)),36),r(X,Y),255-r(X,Y)*0.9)':g='if(gt(abs(r(X,Y)-g(X,Y))+abs(g(X,Y)-b(X,Y)),36),g(X,Y),255-g(X,Y)*0.9)':b='if(gt(abs(r(X,Y)-g(X,Y))+abs(g(X,Y)-b(X,Y)),36),b(X,Y),255-b(X,Y)*0.9)',format=yuv420p")
    gop = max(30, target_fps * 5)
    cmd = [ffmpeg,"-hide_banner","-y","-i",str(input_path),"-map","0:v:0","-map","0:a?","-vf",",".join(vf) if vf else "null","-r",str(target_fps),"-fps_mode","cfr","-c:v",encoder]
    if encoder in {"libx264","libx265"}: cmd += ["-preset",p["preset"],"-crf",str(p["crf"])]
    elif encoder in {"libsvtav1"}: cmd += ["-preset","6","-crf",str(max(20,p["crf"]-2))]
    elif encoder in {"hevc_qsv","h264_qsv","av1_qsv"}: cmd += ["-global_quality",str(p["crf"]),"-look_ahead","1"]
    elif encoder in {"hevc_videotoolbox","h264_videotoolbox"}: cmd += ["-q:v",str(min(70,max(1,p["crf"]+20)))]
    cmd += ["-g",str(gop),"-keyint_min",str(max(1,target_fps)),"-pix_fmt","yuv420p","-c:a","aac","-b:a","64k","-movflags","+faststart",str(output_path)]
    return cmd


def main():
    parser=argparse.ArgumentParser(description="樊老师板书视频压缩器")
    parser.add_argument("input", nargs="?"); parser.add_argument("--preset",choices=PRESETS,default="board-balanced"); parser.add_argument("--codec",choices=CODECS,default="h265"); parser.add_argument("--fps",type=int,choices=[15,20,24,25,30,50,60]); parser.add_argument("--width",type=int); parser.add_argument("--height",type=int); parser.add_argument("--no-keep-aspect",action="store_true"); parser.add_argument("--invert",choices=["auto","on","off"],default="off"); parser.add_argument("--output")
    args=parser.parse_args(); require_binary("ffmpeg"); require_binary("ffprobe")
    if not args.input: parser.error("请指定输入视频")
    src=Path(args.input).expanduser().resolve(); info=probe(src); video=next((s for s in info.get("streams",[]) if s.get("codec_type")=="video"),None)
    if not video: raise SystemExit("输入文件没有视频流")
    src_w,src_h=int(video.get("width") or 0),int(video.get("height") or 0); fps=args.fps or PRESETS[args.preset]["fps"]
    encs=available_encoders(); encoder=CODECS[args.codec]
    if args.codec=="h265" and "hevc_qsv" in encs: encoder="hevc_qsv"
    if args.codec=="av1" and "av1_qsv" in encs: encoder="av1_qsv"
    if args.invert=="auto": args.invert="on" if detect_whiteboard(src) else "off"
    out=Path(args.output).expanduser().resolve() if args.output else src.with_name(f"{src.stem}_压缩_{args.codec}_{fps}fps.mp4")
    cmd=build_command(src,out,args.codec,args.preset,fps=fps,width=args.width,height=args.height,keep_aspect=not args.no_keep_aspect,invert=args.invert,src_w=src_w,src_h=src_h,encoder=encoder)
    print(f"编码器：{encoder}\n输出：{out}\n开始压缩……"); subprocess.run(cmd,check=True); print(f"完成：{out}")

if __name__=="__main__":
    try: main()
    except subprocess.CalledProcessError as exc: raise SystemExit(exc.returncode)
