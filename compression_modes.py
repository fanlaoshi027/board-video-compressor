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
    "fixed15": CompressionMode("fixed15","固定 15 FPS","全程 15fps，作为基准对照",15,15),
    "smart_vfr": CompressionMode("smart_vfr","普通智能 VFR","画面变化少时降帧，变化明显时提高到 15fps",5,15),
    "board_vfr": CompressionMode("board_vfr","板书自适应 VFR","长时间静止段约 2fps，局部书写时动态提高，最高 15fps",2,15),
}

def get_mode(key: str) -> CompressionMode:
    return MODES.get(key, MODES["board_vfr"])
