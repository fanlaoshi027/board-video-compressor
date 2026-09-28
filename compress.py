#!/usr/bin/env python3
"""樊老师板书视频压缩核心。"""
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
HARDWARE_CODECS={"h264_qsv":"h264_qsv","hevc_qsv":"hevc_qsv","av1_qsv":"av1_qsv"}


def require_binary(name):
    if shutil.which(name) is None:
        raise SystemExit(f"找不到 {name}。请确认 FFmpeg 已内置或已加入 PATH。")


def _guess_ffmpeg_from_ffprobe(ffprobe: str):
    p=Path(ffprobe)
    if p.is_absolute() or p.parent != Path('.'):
        candidate=p.with_name("ffmpeg.exe" if p.suffix.lower()==".exe" else "ffmpeg")
        if candidate.exists():
            return str(candidate)
    return "ffmpeg"


def _parse_ffmpeg_video_info(text: str):
    text=text or ""
    video_lines=[line for line in text.splitlines() if re.search(r"\bVideo:\s",line,re.I)]
    candidates=[]
    for line in video_lines:
        candidates.extend(re.findall(r"(?<!\d)(\d{2,5})\s*[x×]\s*(\d{2,5})(?!\d)",line))
    if not candidates:
        candidates=re.findall(r"(?<!\d)(\d{2,5})\s*[x×]\s*(\d{2,5})(?!\d)",text)
    candidates=[(int(w),int(h)) for w,h in candidates if 64<=int(w)<=10000 and 64<=int(h)<=10000]
    if not candidates:
        return None
    def score(item):
        w,h=item; ratio=w/h
        return min(abs(ratio-16/9),abs(ratio-4/3),abs(ratio-1.0),abs(ratio-9/16))
    w,h=min(candidates,key=score)
    fps=30.0
    fps_matches=re.findall(r"(?:,|\s)(\d+(?:\.\d+)?)\s*fps(?:,|\s|$)",text,re.I)
    if fps_matches:
        try: fps=float(fps_matches[0])
        except ValueError: pass
    duration=0.0
    dm=re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)",text,re.I)
    if dm:
        duration=int(dm.group(1))*3600+int(dm.group(2))*60+float(dm.group(3))
    return w,h,fps,duration


def _ffmpeg_fallback_probe(path: Path, ffprobe: str, ffmpeg: str | None = None):
    ffmpeg=ffmpeg or _guess_ffmpeg_from_ffprobe(ffprobe)
    try:
        r=subprocess.run(
            [ffmpeg,"-hide_banner","-loglevel","info","-i",str(path),"-map","0:v:0","-frames:v","1","-f","null","-"],
            capture_output=True,text=True,encoding="utf-8",errors="replace",check=False,timeout=45
        )
    except (OSError,subprocess.SubprocessError) as e:
        raise RuntimeError(f"FFmpeg 无法启动：{e}") from e
    text=(r.stderr or "")+(r.stdout or "")
    parsed=_parse_ffmpeg_video_info(text)
    if not parsed:
        tail=text[-5000:].strip()
        raise RuntimeError(f"FFmpeg 无法识别视频。返回码={r.returncode}\nFFmpeg 输出：\n{tail}")
    w,h,fps,duration=parsed
    return {"streams":[{"codec_type":"video","width":w,"height":h,"avg_frame_rate":f"{int(round(fps*1000))}/1000","r_frame_rate":f"{int(round(fps*1000))}/1000"}],"format":{"duration":str(duration)}}


def probe(path:Path,ffprobe="ffprobe",ffmpeg=None):
    """优先 FFprobe JSON；失败后自动使用同目录 FFmpeg，并返回统一结构。"""
    path=Path(path)
    ffmpeg=ffmpeg or _guess_ffmpeg_from_ffprobe(ffprobe)
    probe_error=""
    try:
        p=subprocess.run(
            [ffprobe,"-v","error","-select_streams","v:0",
             "-show_entries","stream=codec_type,codec_name,width,height,avg_frame_rate,r_frame_rate",
             "-show_entries","format=duration","-of","json",str(path)],
            capture_output=True,text=True,encoding="utf-8",errors="replace",check=False,timeout=30
        )
        raw=(p.stdout or "").strip()
        if p.returncode==0 and raw:
            try:
                data=json.loads(raw)
                streams=data.get("streams") or []
                if streams and streams[0].get("width") and streams[0].get("height"):
                    streams[0].setdefault("codec_type","video")
                    data["streams"]=streams
                    return data
                probe_error=f"FFprobe 返回空视频流；stderr={(p.stderr or '')[-1000:]}"
            except json.JSONDecodeError as e:
                probe_error=f"FFprobe JSON 无法解析：{e}；stdout={raw[-1000:]}"
        else:
            probe_error=f"FFprobe 返回码={p.returncode}；stderr={(p.stderr or '')[-1000:]}"
    except (OSError,subprocess.SubprocessError) as e:
        probe_error=f"FFprobe 无法启动：{e}"
    try:
        return _ffmpeg_fallback_probe(path,ffprobe,ffmpeg)
    except Exception as e:
        raise RuntimeError(f"{probe_error}\nFFmpeg 后备探测失败：{e}") from e


def available_encoders(ffmpeg="ffmpeg"):
    try:
        p=subprocess.run([ffmpeg,"-hide_banner","-encoders"],capture_output=True,text=True,encoding="utf-8",errors="replace",timeout=10)
        text=(p.stdout or "")+(p.stderr or "")
        return {n for n in set(HARDWARE_CODECS.values())|set(CODECS.values()) if n in text}
    except (OSError,subprocess.SubprocessError): return set()


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


def _smart_invert_filter():
    """板书智能反色：近灰/黑白像素反色，彩色像素保持原色。
    白色 255 -> 约 26（90%黑），黑色 0 -> 255。
    """
    expr_r="if(gt(max(max(r(X,Y),g(X,Y)),b(X,Y))-min(min(r(X,Y),g(X,Y)),b(X,Y)),18),r(X,Y),255-0.9*r(X,Y))"
    expr_g="if(gt(max(max(r(X,Y),g(X,Y)),b(X,Y))-min(min(r(X,Y),g(X,Y)),b(X,Y)),18),g(X,Y),255-0.9*g(X,Y))"
    expr_b="if(gt(max(max(r(X,Y),g(X,Y)),b(X,Y))-min(min(r(X,Y),g(X,Y)),b(X,Y)),18),b(X,Y),255-0.9*b(X,Y))"
    return f"format=rgb24,geq=r='{expr_r}':g='{expr_g}':b='{expr_b}'"


def _board_filter():
    return "unsharp=5:5:0.45:5:5:0"


def build_command(input_path,output_path,codec,preset_name,fps=None,width=None,height=None,keep_aspect=True,invert="off",src_w=None,src_h=None,encoder=None,ffmpeg="ffmpeg",board_optimized=True):
    p=PRESETS[preset_name]; target_fps=fps or p["fps"]; encoder=encoder or CODECS[codec]; vf=[]
    if width or height:
        if not src_w or not src_h: raise ValueError("设置分辨率时需要原视频尺寸")
        size=calculate_output_size(width,height,src_w,src_h,keep_aspect); vf.append(f"scale={size[0]}:{size[1]}:flags=lanczos")
    if invert in (True,"on","1","true","yes"):
        vf.append(_smart_invert_filter())
    if board_optimized: vf.append(_board_filter())
    qsv=encoder in {"hevc_qsv","h264_qsv","av1_qsv"}
    if qsv: vf.append("format=nv12")
    gop=max(30,int(target_fps*5)); vf_expr=','.join(vf) if vf else "null"
    pix_fmt="nv12" if qsv else "yuv420p"
    cmd=[ffmpeg,"-hide_banner","-y","-i",str(input_path),"-map","0:v:0","-map","0:a?","-vf",vf_expr,"-r",str(target_fps),"-fps_mode","cfr","-c:v",encoder]
    if encoder in {"libx264","libx265"}: cmd += ["-preset",p["preset"],"-crf",str(p["crf"])]
    elif encoder=="libsvtav1": cmd += ["-preset","6","-crf",str(max(20,p["crf"]-2))]
    elif qsv:
        icq={"board-high":20,"board-balanced":23,"board-extreme":27}[preset_name]; cmd += ["-global_quality",str(icq)]
    cmd += ["-g",str(gop),"-keyint_min",str(max(1,int(target_fps))),"-pix_fmt",pix_fmt,"-c:a","aac","-b:a","64k","-movflags","+faststart",str(output_path)]
    return cmd


def main():
    parser=argparse.ArgumentParser(description="樊老师板书压缩器"); parser.add_argument("input"); parser.add_argument("--preset",choices=PRESETS,default="board-balanced"); parser.add_argument("--codec",choices=CODECS,default="h265"); parser.add_argument("--fps",type=int,choices=[15,20,24,25,30,50,60]); parser.add_argument("--output")
    a=parser.parse_args(); require_binary("ffmpeg"); src=Path(a.input).resolve(); out=Path(a.output).resolve() if a.output else src.with_name(src.stem+"_压缩.mp4"); info=probe(src); v=next(s for s in info["streams"] if s.get("codec_type")=="video"); encs=available_encoders(); enc=CODECS[a.codec]
    if a.codec=="h265" and "hevc_qsv" in encs:enc="hevc_qsv"
    if a.codec=="av1" and "av1_qsv" in encs:enc="av1_qsv"
    subprocess.run(build_command(src,out,a.codec,a.preset,fps=a.fps,src_w=int(v["width"]),src_h=int(v["height"]),encoder=enc),check=True)

if __name__=="__main__":main()
