#!/usr/bin/env python3
"""樊老师板书视频压缩器 - 跨平台板书压缩核心。"""
from __future__ import annotations
import argparse, json, re, shutil, subprocess
from pathlib import Path
from size_estimator import estimate_output_size, format_bytes

PRESETS={
 "board-high":{"crf":24,"fps":30,"preset":"slow"},
 "board-balanced":{"crf":27,"fps":15,"preset":"slow"},
 "board-extreme":{"crf":30,"fps":15,"preset":"slow"},
}
CODECS={"h264":"libx264","h265":"libx265","av1":"libsvtav1"}
HARDWARE_CODECS={"h264_qsv":"h264_qsv","hevc_qsv":"hevc_qsv","av1_qsv":"av1_qsv","h264_videotoolbox":"h264_videotoolbox","hevc_videotoolbox":"hevc_videotoolbox"}


def require_binary(name):
    if shutil.which(name) is None:
        raise SystemExit(f"找不到 {name}。请确认 FFmpeg 已内置或已加入 PATH。")


def _guess_ffmpeg_from_ffprobe(ffprobe: str):
    p=Path(ffprobe)
    if p.parent != Path('.'):
        name="ffmpeg.exe" if p.suffix.lower()==".exe" else "ffmpeg"
        candidate=p.with_name(name)
        if candidate.exists():
            return str(candidate)
    return "ffmpeg"


def _ffmpeg_fallback_probe(path: Path, ffprobe: str, ffmpeg: str | None = None):
    """FFprobe 无法启动/返回数据时，用同目录 FFmpeg 探测视频。"""
    ffmpeg=ffmpeg or _guess_ffmpeg_from_ffprobe(ffprobe)
    try:
        r=subprocess.run(
            [ffmpeg,"-hide_banner","-i",str(path)],
            capture_output=True,text=True,encoding="utf-8",errors="replace",check=False,timeout=30
        )
    except (OSError,subprocess.SubprocessError) as e:
        raise RuntimeError(f"FFprobe 和 FFmpeg 都无法启动：{e}") from e

    text=(r.stderr or "")+(r.stdout or "")

    # 典型 FFmpeg 输出：Video: h264 ..., 1920x1080, ...
    video_lines=[line for line in text.splitlines() if "Video:" in line]
    dimensions=[]
    for line in video_lines:
        dimensions.extend(re.findall(r"(?<!\d)(\d{2,5})x(\d{2,5})(?!\d)",line))
    if not dimensions:
        dimensions=re.findall(r"(?<!\d)(\d{2,5})x(\d{2,5})(?!\d)",text)
    if not dimensions:
        raise RuntimeError(f"FFprobe/FFmpeg 都无法读取视频信息。FFmpeg 输出：{text[-1600:].strip()}")

    # 优先使用视频流行中的最后一个合理尺寸，避免把音频/其他数字误认为分辨率。
    w,h=map(int,dimensions[-1])
    fps=30.0
    fm=re.search(r"(?:,|\s)(\d+(?:\.\d+)?)\s*fps(?:,|\s|$)",text,re.I)
    if fm:
        try: fps=float(fm.group(1))
        except ValueError: pass

    duration=0.0
    dm=re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)",text,re.I)
    if dm:
        duration=int(dm.group(1))*3600+int(dm.group(2))*60+float(dm.group(3))

    return {
        "streams":[{
            "codec_type":"video",
            "width":w,
            "height":h,
            "avg_frame_rate":f"{int(round(fps*1000))}/1000",
            "r_frame_rate":f"{int(round(fps*1000))}/1000",
        }],
        "format":{"duration":str(duration)},
    }


def probe(path:Path,ffprobe="ffprobe",ffmpeg=None):
    """读取视频信息；FFprobe 任何异常都自动降级到 FFmpeg。"""
    path=Path(path)
    ffmpeg=ffmpeg or _guess_ffmpeg_from_ffprobe(ffprobe)
    probe_error=""
    try:
        p=subprocess.run(
            [ffprobe,"-v","error","-select_streams","v:0",
             "-show_entries","stream=codec_name,width,height,avg_frame_rate,r_frame_rate",
             "-show_entries","format=duration","-of","json",str(path)],
            capture_output=True,text=True,encoding="utf-8",errors="replace",check=False,timeout=30
        )
        raw=(p.stdout or "").strip()
        if p.returncode == 0 and raw:
            try:
                data=json.loads(raw)
                streams=data.get("streams") or []
                if streams and streams[0].get("width") and streams[0].get("height"):
                    return data
                probe_error=f"FFprobe 返回空视频流，stderr={p.stderr[-800:]}"
            except json.JSONDecodeError as e:
                probe_error=f"FFprobe JSON 无法解析：{e}"
        else:
            probe_error=f"FFprobe 返回码={p.returncode}，stderr={(p.stderr or '')[-800:]}"
    except (OSError,subprocess.SubprocessError) as e:
        probe_error=f"FFprobe 无法启动：{e}"

    try:
        return _ffmpeg_fallback_probe(path,ffprobe,ffmpeg)
    except Exception as e:
        raise RuntimeError(f"{probe_error}; FFmpeg 后备探测失败：{e}") from e


def available_encoders(ffmpeg="ffmpeg"):
    try:
        p=subprocess.run([ffmpeg,"-hide_banner","-encoders"],capture_output=True,text=True,encoding="utf-8",errors="replace",timeout=10)
        text=(p.stdout or "")+(p.stderr or "")
        return {n for n in set(HARDWARE_CODECS.values())|set(CODECS.values()) if n in text}
    except (OSError,subprocess.SubprocessError):
        return set()


def calculate_output_size(width,height,src_w,src_h,keep_aspect):
    if width is None and height is None:return None
    ratio=src_w/src_h
    width=int(width) if width else None; height=int(height) if height else None
    if keep_aspect:
        if width and height:
            if width/height>ratio: width=round(height*ratio)
            else: height=round(width/ratio)
        elif width: height=round(width/ratio)
        elif height: width=round(height*ratio)
    if width is None or height is None: raise ValueError("宽度和高度必须至少指定一个")
    return max(2,width-width%2),max(2,height-height%2)


def _gray_invert_filter():
    return ("lutrgb="
      "r='if(lt(abs(r(X,Y)-g(X,Y))+abs(g(X,Y)-b(X,Y)),84,255-r(X,Y)*0.9,r(X,Y))':"
      "g='if(lt(abs(r(X,Y)-g(X,Y))+abs(g(X,Y)-b(X,Y)),84,255-g(X,Y)*0.9,g(X,Y))':"
      "b='if(lt(abs(r(X,Y)-g(X,Y))+abs(g(X,Y)-b(X,Y)),84,255-b(X,Y)*0.9,b(X,Y))'")


def _board_filter():
    return "unsharp=5:5:0.45:5:5:0"


def build_command(input_path,output_path,codec,preset_name,fps=None,width=None,height=None,keep_aspect=True,invert="off",src_w=None,src_h=None,encoder=None,ffmpeg="ffmpeg",board_optimized=True):
    p=PRESETS[preset_name]; target_fps=fps or p["fps"]; encoder=encoder or CODECS[codec]; vf=[]
    if width or height:
        if not src_w or not src_h: raise ValueError("设置分辨率时需要原视频尺寸")
        size=calculate_output_size(width,height,src_w,src_h,keep_aspect); vf.append(f"scale={size[0]}:{size[1]}:flags=lanczos")
    if board_optimized: vf.append(_board_filter())
    if invert=="on": vf.append(_gray_invert_filter())
    qsv=encoder in {"hevc_qsv","h264_qsv","av1_qsv"}
    if qsv: vf.append("format=nv12")
    gop=max(30,int(target_fps*5)); vf_expr=','.join(vf) if vf else "null"
    pix_fmt="nv12" if qsv else "yuv420p"
    cmd=[ffmpeg,"-hide_banner","-y","-i",str(input_path),"-map","0:v:0","-map","0:a?","-vf",vf_expr,"-r",str(target_fps),"-fps_mode","cfr","-c:v",encoder]
    if encoder in {"libx264","libx265"}: cmd += ["-preset",p["preset"],"-crf",str(p["crf"])]
    elif encoder=="libsvtav1": cmd += ["-preset","6","-crf",str(max(20,p["crf"]-2))]
    elif qsv:
        icq={"board-high":20,"board-balanced":23,"board-extreme":27}[preset_name]
        cmd += ["-global_quality",str(icq)]
    elif encoder in {"hevc_videotoolbox","h264_videotoolbox"}:
        quality={"board-high":58,"board-balanced":48,"board-extreme":38}[preset_name]
        cmd += ["-q:v",str(quality)]
    cmd += ["-g",str(gop),"-keyint_min",str(max(1,int(target_fps))),"-pix_fmt",pix_fmt,"-c:a","aac","-b:a","64k","-movflags","+faststart",str(output_path)]
    return cmd


def main():
    parser=argparse.ArgumentParser(description="樊老师板书视频压缩器"); parser.add_argument("input"); parser.add_argument("--preset",choices=PRESETS,default="board-balanced"); parser.add_argument("--codec",choices=CODECS,default="h265"); parser.add_argument("--fps",type=int,choices=[15,20,24,25,30,50,60]); parser.add_argument("--output")
    a=parser.parse_args(); require_binary("ffmpeg"); src=Path(a.input).resolve(); out=Path(a.output).resolve() if a.output else src.with_name(src.stem+"_压缩.mp4"); info=probe(src); v=next(s for s in info["streams"] if s.get("codec_type")=="video"); encs=available_encoders(); enc=CODECS[a.codec]
    if a.codec=="h265" and "hevc_qsv" in encs:enc="hevc_qsv"
    if a.codec=="av1" and "av1_qsv" in encs:enc="av1_qsv"
    subprocess.run(build_command(src,out,a.codec,a.preset,fps=a.fps,src_w=int(v["width"]),src_h=int(v["height"]),encoder=enc),check=True)

if __name__=="__main__":main()
