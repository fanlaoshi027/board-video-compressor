from __future__ import annotations
from dataclasses import dataclass
import cv2
import numpy as np

@dataclass
class BoardMotion:
    t: float
    global_motion: float
    local_motion: float
    writing_motion: float


def analyze_board_motion(video_path: str, sample_fps: float = 4.0, max_samples: int = 1200) -> list[BoardMotion]:
    cap=cv2.VideoCapture(video_path)
    if not cap.isOpened(): raise RuntimeError(f"无法打开视频：{video_path}")
    src_fps=cap.get(cv2.CAP_PROP_FPS) or 60.0
    step=max(1,int(round(src_fps/sample_fps)))
    prev=None; result=[]; i=0
    while len(result)<max_samples:
        ok,frame=cap.read()
        if not ok: break
        if i % step: i+=1; continue
        small=cv2.resize(frame,(480,270),interpolation=cv2.INTER_AREA)
        gray=cv2.cvtColor(small,cv2.COLOR_BGR2GRAY)
        if prev is None:
            result.append(BoardMotion(i/src_fps,0,0,0)); prev=gray; i+=1; continue
        diff=cv2.absdiff(gray,prev)
        global_motion=float(np.mean(diff))/255.0
        # Ignore tiny compression noise. Writing strokes usually create coherent local edges.
        blur=cv2.GaussianBlur(diff,(5,5),0)
        local_mask=(blur>12).astype(np.uint8)
        local_motion=float(np.mean(local_mask))
        edges=cv2.Canny(gray,60,150)
        edge_change=cv2.bitwise_and(local_mask,edges)
        writing_motion=float(np.mean(edge_change))
        result.append(BoardMotion(i/src_fps,global_motion,local_motion,writing_motion)); prev=gray; i+=1
    cap.release(); return result


def board_fps(m: BoardMotion, min_fps=15.0, max_fps=30.0) -> float:
    # Favor coherent local edge changes over whole-frame motion.
    score=max(m.writing_motion*4.0, m.local_motion*0.8, m.global_motion*0.15)
    strength=max(0.0,min(1.0,(score-0.006)/0.08))
    return min_fps+(max_fps-min_fps)*(strength**0.6)
