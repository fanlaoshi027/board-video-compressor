from __future__ import annotations
from board_presets import get_preset


def encoding_args(codec: str, preset_key: str) -> list[str]:
    p=get_preset(preset_key)
    if codec=='h265':
        return ['-preset',p.preset,'-crf',str(p.crf_h265),'-aq-mode','3','-aq-strength',str(p.aq_strength),'-deblock',p.deblock]
    if codec=='h264':
        return ['-preset',p.preset,'-crf',str(p.crf_h264),'-aq-mode','2','-aq-strength',str(p.aq_strength),'-deblock',p.deblock]
    if codec=='av1':
        return ['-preset','6','-crf',str(max(20,p.crf_h265-2))]
    return []
