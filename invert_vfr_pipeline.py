from __future__ import annotations
from pathlib import Path
import subprocess


def build_command(src: str, out: str, *, fps_filter: str, strength: float = 0.90, codec: str = 'h265', crf: int = 25, ffmpeg: str = 'ffmpeg') -> list[str]:
    # Keep timestamps from the VFR selection stage; inversion is a frame transform only.
    vf = f"{fps_filter},smartinverttmp=strength={max(0.0,min(1.0,strength))}"
    enc = 'libx265' if codec == 'h265' else ('libx264' if codec == 'h264' else 'libsvtav1')
    return [ffmpeg,'-y','-i',src,'-map','0:v:0','-map','0:a?','-vf',vf,'-fps_mode','vfr','-c:v',enc,'-crf',str(crf),'-preset','medium','-c:a','copy','-movflags','+faststart',out]


def validate_filter_available(ffmpeg: str = 'ffmpeg') -> bool:
    try:
        p=subprocess.run([ffmpeg,'-filters'],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=10)
        return 'smartinverttmp' in p.stdout
    except Exception:
        return False
