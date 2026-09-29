from __future__ import annotations
from dataclasses import dataclass
import cv2
import numpy as np

@dataclass
class MotionSample:
    t: float
    motion: float
    fps: float


def analyze_motion(video_path: str, *, sample_fps: float = 4.0, min_fps: float = 15.0, max_fps: float = 30.0, max_samples: int = 1200) -> list[MotionSample]:
    cap=cv2.VideoCapture(video_path)
    if not cap.isOpened(): raise RuntimeError(f"无法打开视频：{video_path}")
    src_fps=cap.get(cv2.CAP_PROP_FPS) or 60.0
    duration=(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)/src_fps
    step=max(1,int(round(src_fps/sample_fps)))
    prev=None; out=[]; i=0
    while len(out)<max_samples:
        ok,frame=cap.read()
        if not ok: break
        if i % step:
            i+=1; continue
        gray=cv2.cvtColor(frame,cv2.COLOR_BGR2GRAY)
        gray=cv2.resize(gray,(320,180),interpolation=cv2.INTER_AREA)
        if prev is None: motion=0.0
        else:
            diff=cv2.absdiff(gray,prev)
            motion=float(np.mean(diff))/255.0
        # Squash isolated compression noise but preserve stronger writing motion.
        strength=max(0.0,min(1.0,(motion-0.002)/0.08))
        fps=min_fps+(max_fps-min_fps)*(strength**0.65)
        out.append(MotionSample(i/src_fps,motion,fps)); prev=gray; i+=1
    cap.release()
    return out


def build_motion_profile(video_path: str, *, sample_fps=4.0, min_fps=15.0, max_fps=30.0) -> list[tuple[float,float]]:
    return [(x.t,x.fps) for x in analyze_motion(video_path,sample_fps=sample_fps,min_fps=min_fps,max_fps=max_fps)]
