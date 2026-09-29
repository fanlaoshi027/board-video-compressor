#!/usr/bin/env python3
"""板书视频智能可变帧率（VFR）核心。

目标：针对“长时间静止 + 局部书写”的数学板书视频，
在静止段减少帧，在连续书写段提高保留密度。

注意：这里的智能帧率不是简单把 60fps 变成固定 15fps。
它保留原始时间戳，使用 FFmpeg 的 scene/change 指标辅助决定
何时提前保留新帧，并由 fps_mode=vfr 输出真正的 VFR。
"""
from __future__ import annotations


def adaptive_select(
    min_fps: float = 15.0,
    max_fps: float = 30.0,
    scene_threshold: float = 0.0015,
) -> str:
    """生成保守的板书 VFR select 表达式。

    min_fps：静止区域允许的最低采样密度。
    max_fps：连续变化时允许的最高采样密度。
    scene_threshold：对局部板书变化保持敏感。
    """
    min_fps = max(1.0, float(min_fps))
    max_fps = max(min_fps, float(max_fps))
    max_interval = 1.0 / min_fps
    min_interval = 1.0 / max_fps

    # 逻辑：
    # 1. 从未选过帧时先保留；
    # 2. 达到最低帧率间隔时保留；
    # 3. 在最低间隔与最高间隔之间，如果检测到变化，则提前保留。
    # 这样静止段趋近 min_fps，连续书写段可以提高到 max_fps。
    return (
        "select='isnan(prev_selected_t)"
        f"+gte(t-prev_selected_t\\,{max_interval:.6f})"
        f"+and(gte(t-prev_selected_t\\,{min_interval:.6f})\\,gt(scene\\,{scene_threshold:.6f}))'"
    )


def build_vfr_filter(
    min_fps: float = 15.0,
    max_fps: float = 30.0,
    scene_threshold: float = 0.0015,
) -> str:
    """生成板书 VFR 视频滤镜。"""
    return adaptive_select(min_fps, max_fps, scene_threshold) + ",setpts=PTS-STARTPTS"


def ffmpeg_vfr_args(
    min_fps: float = 15.0,
    max_fps: float = 30.0,
    scene_threshold: float = 0.0015,
) -> list[str]:
    """返回可直接追加到 FFmpeg 的 VFR 参数。"""
    return [
        "-vf",
        build_vfr_filter(min_fps, max_fps, scene_threshold),
        "-fps_mode",
        "vfr",
    ]


def recommend_range(write_intensity: float) -> tuple[int, int]:
    """根据板书书写强度给出保守的帧率范围建议。

    write_intensity 为 0~1：
    0~0.25：以静止/讲解为主 -> 15~20
    0.25~0.60：普通书写 -> 15~24
    0.60~0.85：连续书写 -> 18~30
    >0.85：快速连续书写 -> 20~30

    这里只生成建议，不直接替用户改变设置。
    """
    x = max(0.0, min(1.0, float(write_intensity)))
    if x <= 0.25:
        return 15, 20
    if x <= 0.60:
        return 15, 24
    if x <= 0.85:
        return 18, 30
    return 20, 30


if __name__ == "__main__":
    print(build_vfr_filter())
