#!/usr/bin/env python3
"""板书压缩器统一执行层：固定 FPS / 智能 VFR / 板书自适应 VFR。"""
from __future__ import annotations
import json, os, signal, subprocess
from pathlib import Path
from vfr import build_vfr_filter


def build_smart_command(src: str, out: str, *, preset="board-balanced", codec="h265", fps="智能 VFR", width=None, height=None, keep_aspect=True, board_opt=True, invert=False, ffmpeg="ffmpeg", src_w=None, src_h=None, encoder=None, min_fps=15, max_fps=30, has_audio=True, duration=0, custom_vf=None):
    from compress import build_command
    fixed = None if fps in ("智能 VFR", "smart", "vfr") else int(fps)
    base = build_command(src,out,codec,preset,fps=(fixed if fixed is not None else min_fps),width=width,height=height,keep_aspect=keep_aspect,invert=invert,src_w=src_w,src_h=src_h,encoder=encoder,ffmpeg=ffmpeg,board_optimized=board_opt,duration=duration,has_audio=has_audio)
    if fixed is not None and custom_vf is None:
        return base
    cleaned=[]; i=0
    while i<len(base):
        if base[i] in ("-r","-fps_mode","-g","-keyint_min") and i+1<len(base): i+=2; continue
        cleaned.append(base[i]); i+=1
    if "-vf" in cleaned:
        idx=cleaned.index("-vf")+1
        if custom_vf:
            cleaned[idx]=custom_vf
        else:
            cleaned[idx]=f"{cleaned[idx]},{build_vfr_filter(min_fps=min_fps,max_fps=max_fps)}"
    insert_at=cleaned.index("-c:v") if "-c:v" in cleaned else len(cleaned)
    cleaned[insert_at:insert_at]=["-fps_mode","vfr"]
    return cleaned


def parse_progress_line(line):
    if "=" not in line:return {}
    k,v=line.rstrip().split("=",1); return {k:v}


def terminate_process(p):
    if p.poll() is not None:return
    try:p.send_signal(signal.CTRL_BREAK_EVENT if os.name=="nt" else signal.SIGINT)
    except Exception:
        try:p.terminate()
        except Exception:pass


def run(args, *, duration=0, on_line=None, on_progress=None, cancel_event=None, on_process=None, cleanup_output=None):
    command=list(args); command[1:1]=["-progress","pipe:1","-nostats"]
    p=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding="utf-8",errors="replace",bufsize=1,creationflags=(subprocess.CREATE_NEW_PROCESS_GROUP if os.name=="nt" else 0))
    if on_process:on_process(p)
    assert p.stdout is not None; state={}; cancelled=False
    for raw in p.stdout:
        if cancel_event is not None and cancel_event.is_set() and not cancelled: cancelled=True; terminate_process(p)
        line=raw.rstrip(); item=parse_progress_line(line)
        if item:
            state.update(item)
            if on_progress:
                seconds=float(state.get("out_time_us","0") or 0)/1_000_000; percent=max(0,min(100,seconds/duration*100)) if duration>0 else 0
                if state.get("progress")=="end":percent=100
                on_progress(percent,dict(state))
        elif line and on_line:on_line(line)
    code=p.wait()
    if cancelled and cleanup_output:
        try:Path(cleanup_output).unlink(missing_ok=True)
        except Exception:pass
    return code,cancelled


def write_job(path,args):Path(path).write_text(json.dumps(args,ensure_ascii=False,indent=2),encoding="utf-8")
