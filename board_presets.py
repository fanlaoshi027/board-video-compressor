from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class BoardPreset:
    key: str
    name: str
    description: str
    crf_h265: int
    crf_h264: int
    preset: str
    aq_strength: int
    deblock: str

PRESETS={
    'clear': BoardPreset('clear','清晰优先','文字边缘和细小笔迹优先',22,20,'slow',1,'-1:-1'),
    'balanced': BoardPreset('balanced','平衡','文件大小与板书清晰度平衡',25,23,'medium',1,'-1:-1'),
    'extreme': BoardPreset('extreme','极限压缩','静止白底板书优先压缩，适合大批量课程',28,26,'slow',1,'-2:-2'),
}

def get_preset(key: str) -> BoardPreset:
    return PRESETS.get(key, PRESETS['balanced'])
