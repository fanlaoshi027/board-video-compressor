from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class CompressionMode:
    key: str
    name: str
    description: str
    min_fps: int
    max_fps: int

MODES={
    "fixed15": CompressionMode("fixed15","固定 15 FPS","全程 15fps，文件最小化方向",15,15),
    "smart_vfr": CompressionMode("smart_vfr","普通智能 VFR","根据画面变化保留更多帧",15,30),
    "board_vfr": CompressionMode("board_vfr","板书自适应 VFR","重点识别局部书写运动，静止段降帧、书写段升帧",15,30),
}

def get_mode(key: str) -> CompressionMode:
    return MODES.get(key, MODES["board_vfr"])
