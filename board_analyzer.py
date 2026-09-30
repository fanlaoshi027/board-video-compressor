#!/usr/bin/env python3
"""板书视频分析器：针对白底黑字、局部书写的视频。"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from pathlib import Path
import json, subprocess

@dataclass
class BoardAnalysis:
    width:int; height:int; source_fps:float; duration:float
    white_ratio:float; mean_change:float; local_change_ratio:float
    still_ratio:float; writing_ratio:float; fast_writing_ratio:float
    min_fps:int; max_fps:int
    @property
    def mode(self)->str:
        if self.fast_writing_ratio >= .18: return "快速连续书写"
        if self.writing_ratio >= .20: return "普通连续书写"
        return "静止/讲解为主"
    def to_dict(self):
        d=asdict(self); d["mode"]=self.mode; return d

def _run(cmd, timeout=120):
    return subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=timeout)

def probe_video(path, ffprobe="ffprobe"):
    cmd=[ffprobe,"-v","error","-select_streams","v:0","-show_entries","stream=width,height,r_frame_rate,duration","-show_entries","format=duration","-of","json",str(path)]
    p=_run(cmd)
    if p.returncode: raise RuntimeError(p.stderr.strip() or "ffprobe failed")
    data=json.loads(p.stdout); s=data["streams"][0]; a,b=(s.get("r_frame_rate") or "0/1").split("/")
    fps=float(a)/float(b) if float(b) else 0.0; duration=float(s.get("duration") or data.get("format",{}).get("duration") or 0)
    return int(s["width"]),int(s["height"]),fps,duration

def analyze(path, ffmpeg="ffmpeg", ffprobe="ffprobe", sample_fps=5.0, max_seconds=180.0):
    width,height,source_fps,duration=probe_video(path,ffprobe); duration=min(duration,max_seconds) if duration else max_seconds
    small_w=320; small_h=max(2,int(round(height*small_w/width)))
    cmd=[ffmpeg,"-hide_banner","-loglevel","error","-i",str(path),"-t",str(duration),"-vf",f"fps={sample_fps},scale={small_w}:{small_h},format=gray","-f","rawvideo","pipe:1"]
    p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=300)
    if p.returncode: raise RuntimeError(p.stderr.decode("utf-8","ignore").strip() or "ffmpeg analysis failed")
    import numpy as np
    size=small_w*small_h; raw=np.frombuffer(p.stdout,dtype=np.uint8); count=len(raw)//size
    if count<2: raise RuntimeError("视频太短，无法分析")
    frames=raw[:count*size].reshape((count,small_h,small_w)); white_ratio=float((frames>235).mean())
    prev=frames[:-1].astype(np.int16); cur=frames[1:].astype(np.int16); diff=np.abs(cur-prev)
    mean_diff=diff.mean(axis=(1,2)); mean_change=float(mean_diff.mean()/255.0)
    changed=diff>12; changed_ratio=changed.mean(axis=(1,2)); local_change_ratio=float((changed_ratio<.12).mean())
    still=mean_change<.012; writing=(mean_change>=.012)&(mean_change<.045); fast=mean_change>=.045
    still_ratio=float(still.mean()); writing_ratio=float(writing.mean()); fast_ratio=float(fast.mean())
    # 局部变化越多，越允许降低静止段最低 FPS；快速全画面变化则保守提高最低 FPS。
    if fast_ratio>=.18: min_fps,max_fps=8,15
    elif writing_ratio>=.20: min_fps,max_fps=4,15
    else: min_fps,max_fps=2,15
    if local_change_ratio<.35: min_fps=min(6,min_fps+2)
    return BoardAnalysis(width,height,source_fps,duration,white_ratio,mean_change,local_change_ratio,still_ratio,writing_ratio,fast_ratio,min_fps,max_fps)

if __name__=="__main__":
    import argparse
    ap=argparse.ArgumentParser(); ap.add_argument("video"); ap.add_argument("--ffmpeg",default="ffmpeg"); ap.add_argument("--ffprobe",default="ffprobe"); args=ap.parse_args()
    print(json.dumps(analyze(args.video,args.ffmpeg,args.ffprobe).to_dict(),ensure_ascii=False,indent=2))
