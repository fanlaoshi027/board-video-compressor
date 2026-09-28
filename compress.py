#!/usr/bin/env python3
"""樊老师板书视频压缩核心。"""
from __future__ import annotations
import argparse, json, re, shutil, subprocess
from pathlib import Path
from size_estimator import estimate_output_size, format_bytes

PRESETS={"board-high":{"crf":24,"fps":30,"preset":"slow"},"board-balanced":{"crf":27,"fps":15,"preset":"slow"},"board-extreme":{"crf":30,"fps":15,"preset":"slow"}}
CODECS={"h264":"libx264","h265":"libx265","av1":"libsvtav1"}; HARDWARE_CODECS={"h264_qsv":"h264_qsv","hevc_qsv":"hevc_qsv","av1_qsv":"av1_qsv"}

def _hidden_kwargs():
    if __import__('sys').platform.startswith('win'):
        si=subprocess.STARTUPINFO(); si.dwFlags |= subprocess.STARTF_USESHOWWINDOW; si.wShowWindow=0
        return {"startupinfo":si,"creationflags":subprocess.CREATE_NO_WINDOW}
    return {}

def require_binary(name):
    if shutil.which(name) is None: raise SystemExit(f"找不到 {name}。请确认 FFmpeg 已内置或已加入 PATH。")

def _guess_ffmpeg_from_ffprobe(ffprobe: str):
    p=Path(ffprobe)
    if p.is_absolute() or p.parent != Path('.'):
        candidate=p.with_name("ffmpeg.exe" if p.suffix.lower()==".exe" else "ffmpeg")
        if candidate.exists(): return str(candidate)
    return "ffmpeg"

def _parse_ffmpeg_video_info(text: str):
    video_lines=[line for line in (text or "").splitlines() if re.search(r"\bVideo:\s",line,re.I)]; candidates=[]
    for line in video_lines: candidates.extend(re.findall(r"(?<!\d)(\d{2,5})\s*[x×]\s*(\d{2,5})(?!\d)",line))
    if not candidates: candidates=re.findall(r"(?<!\d)(\d{2,5})\s*[x×]\s*(\d{2,5})(?!\d)",(text or ""))
    candidates=[(int(w),int(h)) for w,h in candidates if 64<=int(w)<=10000 and 64<=int(h)<=10000]
    if not candidates:return None
    w,h=candidates[0]; fps=30.0; m=re.search(r"(?:,|\s)(\d+(?:\.\d+)?)\s*fps(?:,|\s|$)",text or "",re.I)
    if m:
        try:fps=float(m.group(1))
        except:pass
    duration=0.0; dm=re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)",text or "",re.I)
    if dm:duration=int(dm.group(1))*3600+int(dm.group(2))*60+float(dm.group(3))
    return w,h,fps,duration

def _ffmpeg_fallback_probe(path: Path, ffprobe: str, ffmpeg: str | None = None):
    ffmpeg=ffmpeg or _guess_ffmpeg_from_ffprobe(ffprobe)
    try:r=subprocess.run([ffmpeg,"-hide_banner","-loglevel","info","-i",str(path),"-map","0:v:0","-frames:v","1","-f","null","-"],capture_output=True,text=True,encoding="utf-8",errors="replace",check=False,timeout=45,**_hidden_kwargs())
    except (OSError,subprocess.SubprocessError) as e:raise RuntimeError(f"FFmpeg 无法启动：{e}") from e
    text=(r.stderr or "")+(r.stdout or ""); parsed=_parse_ffmpeg_video_info(text)
    if not parsed:raise RuntimeError(f"FFmpeg 无法识别视频。返回码={r.returncode}\nFFmpeg 输出：\n{text[-5000:].strip()}")
    w,h,fps,duration=parsed; has_audio=bool(re.search(r"\bAudio:\s",text,re.I)); streams=[{"codec_type":"video","width":w,"height":h,"avg_frame_rate":f"{int(round(fps*1000))}/1000","r_frame_rate":f"{int(round(fps*1000))}/1000"}]
    if has_audio:streams.append({"codec_type":"audio"})
    return {"streams":streams,"format":{"duration":str(duration)}}

def probe(path:Path,ffprobe="ffprobe",ffmpeg=None):
    path=Path(path); ffmpeg=ffmpeg or _guess_ffmpeg_from_ffprobe(ffprobe); probe_error=""
    try:
        p=subprocess.run([ffprobe,"-v","error","-show_streams","-show_format","-of","json",str(path)],capture_output=True,text=True,encoding="utf-8",errors="replace",check=False,timeout=30,**_hidden_kwargs()); raw=(p.stdout or "").strip()
        if p.returncode==0 and raw:
            try:
                data=json.loads(raw); streams=data.get("streams") or []; video=next((s for s in streams if s.get("codec_type")=="video"),None)
                if video and video.get("width") and video.get("height"):return data
                probe_error=f"FFprobe 返回空视频流；stderr={(p.stderr or '')[-1000:]}"
            except json.JSONDecodeError as e:probe_error=f"FFprobe JSON 无法解析：{e}；stdout={raw[-1000:]}"
        else:probe_error=f"FFprobe 返回码={p.returncode}；stderr={(p.stderr or '')[-1000:]}"
    except (OSError,subprocess.SubprocessError) as e:probe_error=f"FFprobe 无法启动：{e}"
    try:return _ffmpeg_fallback_probe(path,ffprobe,ffmpeg)
    except Exception as e:raise RuntimeError(f"{probe_error}\nFFmpeg 后备探测失败：{e}") from e

def available_encoders(ffmpeg="ffmpeg"):
    try:
        p=subprocess.run([ffmpeg,"-hide_banner","-encoders"],capture_output=True,text=True,encoding="utf-8",errors="replace",timeout=10,**_hidden_kwargs()); text=(p.stdout or "")+(p.stderr or "")
        return {n for n in set(HARDWARE_CODECS.values())|set(CODECS.values()) if n in text}
    except (OSError,subprocess.SubprocessError):return set()

def calculate_output_size(width,height,src_w,src_h,keep_aspect):
    if width is None and height is None:return None
    ratio=src_w/src_h; width=int(width) if width else None; height=int(height) if height else None
    if keep_aspect:
        if width and height:
            if width/height>ratio:width=round(height*ratio)
            else:height=round(width/ratio)
        elif width:height=round(width/ratio)
        elif height:width=round(height*ratio)
    if width is None or height is None:raise ValueError("宽度和高度必须至少指定一个")
    return max(2,width-width%2),max(2,height-height%2)

def _smart_invert_filter():
    # 板书场景：白底转约90%黑，黑字转白；保持色度通道，避免彩色变补色。
    return "lutyuv=y='235-(val*235/255)':u='val':v='val'"

def _board_filter():return "unsharp=5:5:0.45:5:5:0"

def _cut_filter(cuts,duration,has_audio=False):
    normalized=[]
    for a,b in cuts or []:
        a=max(0.0,float(a)); b=min(float(duration),float(b))
        if b>a:normalized.append((a,b))
    normalized.sort(); merged=[]
    for a,b in normalized:
        if not merged or a>merged[-1][1]:merged.append([a,b])
        else:merged[-1][1]=max(merged[-1][1],b)
    kept=[]; cur=0.0
    for a,b in merged:
        if a>cur:kept.append((cur,a))
        cur=max(cur,b)
    if cur<duration:kept.append((cur,duration))
    if not kept:raise ValueError("裁切后没有剩余视频内容")
    parts=[]
    for i,(a,b) in enumerate(kept):
        parts.append(f"[0:v]trim=start={a:.3f}:end={b:.3f},setpts=PTS-STARTPTS[v{i}]")
        if has_audio:parts.append(f"[0:a]atrim=start={a:.3f}:end={b:.3f},asetpts=PTS-STARTPTS[a{i}]")
    if has_audio:parts.append(''.join(f"[v{i}][a{i}]" for i in range(len(kept)))+f"concat=n={len(kept)}:v=1:a=1[outv][outa]")
    else:parts.append(''.join(f"[v{i}]" for i in range(len(kept)))+f"concat=n={len(kept)}:v=1:a=0[outv]")
    return ';'.join(parts)

def build_command(input_path,output_path,codec,preset_name,fps=None,width=None,height=None,keep_aspect=True,invert="off",src_w=None,src_h=None,encoder=None,ffmpeg="ffmpeg",board_optimized=True,cuts=None,duration=0,has_audio=True):
    p=PRESETS[preset_name]; target_fps=fps or p["fps"]; encoder=encoder or CODECS[codec]; vf=[]
    if width or height:
        if not src_w or not src_h:raise ValueError("设置分辨率时需要原视频尺寸")
        size=calculate_output_size(width,height,src_w,src_h,keep_aspect); vf.append(f"scale={size[0]}:{size[1]}:flags=lanczos")
    if invert in (True,"on","1","true","yes"):vf.append(_smart_invert_filter())
    if board_optimized:vf.append(_board_filter())
    qsv=encoder in {"hevc_qsv","h264_qsv","av1_qsv"}
    if qsv:vf.append("format=nv12")
    gop=max(30,int(target_fps*5)); vf_expr=','.join(vf) if vf else "null"; pix_fmt="nv12" if qsv else "yuv420p"; cuts=cuts or []
    if cuts:
        graph=_cut_filter(cuts,float(duration),has_audio=has_audio); post=','.join(vf) if vf else "null"; graph+=f";[outv]{post}[vout]"; cmd=[ffmpeg,"-hide_banner","-loglevel","error","-y","-i",str(input_path),"-filter_complex",graph,"-map","[vout]"]
        if has_audio:cmd += ["-map","[outa]"]
    else:
        cmd=[ffmpeg,"-hide_banner","-loglevel","error","-y","-i",str(input_path),"-map","0:v:0"]
        if has_audio:cmd += ["-map","0:a?"]
        cmd += ["-vf",vf_expr,"-r",str(target_fps),"-fps_mode","cfr"]
    cmd += ["-c:v",encoder]
    if encoder in {"libx264","libx265"}:cmd += ["-preset",p["preset"],"-crf",str(p["crf"])]
    elif encoder=="libsvtav1":cmd += ["-preset","6","-crf",str(max(20,p["crf"]-2))]
    elif encoder in {"hevc_qsv","h264_qsv","av1_qsv"}:cmd += ["-global_quality",str({"board-high":20,"board-balanced":23,"board-extreme":27}[preset_name])]
    cmd += ["-r",str(target_fps),"-fps_mode","cfr","-g",str(gop),"-keyint_min",str(max(1,int(target_fps))),"-pix_fmt",pix_fmt]
    if has_audio:cmd += ["-c:a","aac","-b:a","64k"]
    else:cmd += ["-an"]
    cmd += ["-movflags","+faststart",str(output_path)]
    return cmd

def compress_video(src,dst,width,height,fps,codec="hevc_qsv",bitrate="2M",smart_invert=False,cuts=None,duration=0,has_audio=True):
    cmd=build_command(src,dst,codec,"board-balanced",fps=fps,width=width,height=height,keep_aspect=True,invert=smart_invert,encoder=codec,ffmpeg="ffmpeg",cuts=cuts,duration=duration,has_audio=has_audio); return subprocess.run(cmd,capture_output=True,text=True,encoding="utf-8",errors="replace",**_hidden_kwargs())

def main():
    parser=argparse.ArgumentParser(description="樊老师板书压缩器"); parser.add_argument("input"); parser.add_argument("--preset",choices=PRESETS,default="board-balanced"); parser.add_argument("--codec",choices=CODECS,default="h265"); parser.add_argument("--fps",type=int,choices=[15,20,24,25,30,50,60]); parser.add_argument("--output"); a=parser.parse_args(); require_binary("ffmpeg"); src=Path(a.input).resolve(); out=Path(a.output).resolve() if a.output else src.with_name(src.stem+"_压缩.mp4"); info=probe(src); v=next(s for s in info["streams"] if s.get("codec_type")=="video"); encs=available_encoders(); enc=CODECS[a.codec]
    if a.codec=="h265" and "hevc_qsv" in encs:enc="hevc_qsv"
    if a.codec=="av1" and "av1_qsv" in encs:enc="av1_qsv"
    has_audio=any(s.get("codec_type")=="audio" for s in info.get("streams",[])); subprocess.run(build_command(src,out,a.codec,a.preset,fps=a.fps,src_w=int(v["width"]),src_h=int(v["height"]),encoder=enc,has_audio=has_audio,duration=float(info.get("format",{}).get("duration") or 0)),check=True,**_hidden_kwargs())
if __name__=="__main__":main()
