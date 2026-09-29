from __future__ import annotations
from pathlib import Path
from board_motion import analyze_board_motion, board_fps


def build_profile(video_path: str, *, sample_fps=4.0, min_fps=15.0, max_fps=30.0):
    samples=analyze_board_motion(video_path,sample_fps=sample_fps)
    values=[]
    for s in samples:
        fps=board_fps(s,min_fps,max_fps)
        # Quantize to reduce unnecessary VFR churn.
        fps=round(fps*2)/2
        values.append((s.t,fps))
    return values


def build_select_filter(profile, *, min_fps=15.0, max_fps=30.0):
    """Create an FFmpeg select expression with piecewise time windows.

    FFmpeg keeps original timestamps; each window has its own sampling period.
    The expression intentionally uses simple arithmetic so it remains portable.
    """
    if not profile:
        return "select='1',setpts=PTS-STARTPTS"
    parts=[]
    for idx,(start,fps) in enumerate(profile):
        end=profile[idx+1][0] if idx+1<len(profile) else None
        fps=max(min_fps,min(max_fps,float(fps))); interval=1.0/fps
        time_cond=f"gte(t\\,{start:.3f})"
        if end is not None: time_cond=f"and({time_cond}\\,lt(t\\,{end:.3f}) )"
        parts.append((time_cond,interval))
    # Use select's previous_selected_t as the clock inside each piece.
    clauses=[]
    for cond,interval in parts:
        clauses.append(f"and({cond}\\,gte(t-prev_selected_t\\,{interval:.5f}))")
    expr="isnan(prev_selected_t)+"+"+".join(clauses)
    return f"select='{expr}',setpts=PTS-STARTPTS"


def write_profile(path: str, profile):
    Path(path).write_text("\n".join(f"{t:.3f}\t{fps:.1f}" for t,fps in profile),encoding="utf-8")
