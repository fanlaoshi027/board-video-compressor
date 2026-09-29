#!/usr/bin/env python3
"""板书视频智能可变帧率（VFR）核心。

第一版采用保守策略：
- 输入保持原始时间戳
- 最高输出帧率限制为 max_fps
- 通过 select 的局部变化/时间间隔判断保留帧
- 最低保持间隔约为 1/min_fps，避免静止区产生大量重复帧
- 输出使用 VFR，不强制 CFR

后续可把运动分析升级为独立的局部运动检测器。
"""
from __future__ import annotations


def adaptive_select(min_fps: float = 15.0, max_fps: float = 30.0, scene_threshold: float = 0.0015) -> str:
    """返回 FFmpeg select 表达式。

    max_fps 通过时间间隔限制，min_fps 作为最长允许的帧间隔；
    scene_threshold 用于捕捉板书局部变化。这里故意采用较低阈值，
    因为数学板书往往只有很小区域发生变化。
    """
    min_fps = max(1.0, float(min_fps))
    max_fps = max(min_fps, float(max_fps))
    max_interval = 1.0 / min_fps
    min_interval = 1.0 / max_fps
    # prev_selected_t 是 select filter 的变量；scene 对局部笔迹变化提供补充触发。
    return (
        "select='isnan(prev_selected_t)"
        f"+gte(t-prev_selected_t\\,{max_interval:.6f})"
        f"+and(gte(t-prev_selected_t\\,{min_interval:.6f})\\,gt(scene\\,{scene_threshold:.6f}))'"
    )


def build_vfr_filter(min_fps: float = 15.0, max_fps: float = 30.0) -> str:
    """生成第一版板书 VFR 滤镜。"""
    return adaptive_select(min_fps, max_fps) + ",setpts=PTS-STARTPTS"


def ffmpeg_vfr_args(min_fps: float = 15.0, max_fps: float = 30.0) -> list[str]:
    """返回可直接追加到 FFmpeg 的 VFR 参数。"""
    return ["-vf", build_vfr_filter(min_fps, max_fps), "-fps_mode", "vfr"]


if __name__ == "__main__":
    print(build_vfr_filter())
