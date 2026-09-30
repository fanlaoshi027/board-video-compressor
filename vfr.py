#!/usr/bin/env python3
"""真正面向板书的 VFR 帧选择。"""
from __future__ import annotations


def adaptive_select(min_fps: float = 2.0, max_fps: float = 15.0, scene_threshold: float = 0.0015) -> str:
    min_fps = max(0.5, float(min_fps))
    max_fps = max(min_fps, float(max_fps))
    min_interval = 1.0 / max_fps
    max_interval = 1.0 / min_fps
    return (
        "select='isnan(prev_selected_t)"
        f"+gte(t-prev_selected_t\\,{max_interval:.6f})"
        f"+and(gte(t-prev_selected_t\\,{min_interval:.6f})\\,gt(scene\\,{scene_threshold:.6f}))'"
    )


def build_vfr_filter(min_fps: float = 2.0, max_fps: float = 15.0, scene_threshold: float = 0.0015) -> str:
    return adaptive_select(min_fps, max_fps, scene_threshold) + ",setpts=PTS-STARTPTS"


def ffmpeg_vfr_args(min_fps: float = 2.0, max_fps: float = 15.0, scene_threshold: float = 0.0015) -> list[str]:
    return ["-vf", build_vfr_filter(min_fps, max_fps, scene_threshold), "-fps_mode", "vfr"]


def recommend_range(write_intensity: float) -> tuple[int, int]:
    x = max(0.0, min(1.0, float(write_intensity)))
    if x <= 0.25:
        return 2, 15
    if x <= 0.60:
        return 3, 15
    if x <= 0.85:
        return 5, 15
    return 8, 15
