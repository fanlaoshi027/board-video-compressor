from __future__ import annotations

"""板书视频 VFR 引擎。

根据最低/最高 FPS 生成 FFmpeg 参数，后续接入板书运动分析结果。
"""


def build_vfr_filter(min_fps: float = 2.0, max_fps: float = 15.0) -> str:
    min_fps = max(0.5, float(min_fps))
    max_fps = max(min_fps, float(max_fps))
    min_interval = 1.0 / max_fps
    max_interval = 1.0 / min_fps

    return (
        "select='isnan(prev_selected_t)"
        f"+gte(t-prev_selected_t\\,{max_interval:.5f})"
        f"+and(gte(t-prev_selected_t\\,{min_interval:.5f})\\,gt(scene\\,0.0015))'"
        ",setpts=PTS-STARTPTS"
    )


def build_vfr_args(min_fps: float = 2.0, max_fps: float = 15.0) -> list[str]:
    return [
        "-vf",
        build_vfr_filter(min_fps, max_fps),
        "-fps_mode",
        "vfr",
    ]


def recommend_fps(mode: str = "teacher_board") -> tuple[float, float]:
    profiles = {
        "teacher_board": (2.0, 15.0),
        "small_size": (1.5, 12.0),
        "high_quality": (5.0, 24.0),
    }
    return profiles.get(mode, profiles["teacher_board"])
