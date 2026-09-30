from __future__ import annotations
from pathlib import Path
from board_motion import analyze_board_motion, board_fps


def build_profile(video_path: str, *, sample_fps=4.0, min_fps=2.0, max_fps=15.0):
    samples = analyze_board_motion(video_path, sample_fps=sample_fps)
    values=[]
    for s in samples:
        fps=board_fps(s,min_fps,max_fps)
        fps=round(max(min_fps,min(max_fps,fps))*2)/2
        values.append((s.t,fps))
    return values


def build_select_filter(profile, *, min_fps=2.0, max_fps=15.0):
    """根据局部书写运动强度生成真正的 VFR select 表达式。"""
    if not profile:
        return "select='1',setpts=PTS-STARTPTS"
    clauses=[]
    for idx,(start,fps) in enumerate(profile):
        end=profile[idx+1][0] if idx+1<len(profile) else None
        fps=max(min_fps,min(max_fps,float(fps))); interval=1.0/fps
        cond=f"gte(t\\,{start:.3f})"
        if end is not None: cond=f"and({cond}\\,lt(t\\,{end:.3f}))"
        clauses.append(f"and({cond}\\,gte(t-prev_selected_t\\,{interval:.5f}))")
    # 第一帧必须保留；后续帧按当前时间窗口的目标间隔选择。
    expr="isnan(prev_selected_t)+"+"+"+".join(clauses)
    return f"select='{expr}',setpts=PTS-STARTPTS"


def write_profile(path: str, profile):
    Path(path).write_text("\n".join(f"{t:.3f}\t{fps:.1f}" for t,fps in profile),encoding="utf-8")
