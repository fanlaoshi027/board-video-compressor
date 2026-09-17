from __future__ import annotations

def format_bytes(n: int | float) -> str:
    n=float(max(0,n)); units=("B","KB","MB","GB","TB")
    for u in units:
        if n < 1024 or u == units[-1]: return f"{n:.1f} {u}" if u != "B" else f"{int(n)} B"
        n /= 1024

def estimate_output_size(original_bytes: int, src_fps: float, dst_fps: int, src_w: int, src_h: int, dst_w: int, dst_h: int, codec: str, preset: str) -> tuple[int,int]:
    # Conservative estimate for UI only; actual encoded size depends on scene complexity.
    pixel_ratio=(dst_w*dst_h)/(src_w*src_h) if src_w and src_h else 1.0
    fps_ratio=dst_fps/max(src_fps,1.0)
    codec_factor={"h264":1.05,"h265":0.62,"av1":0.48}.get(codec,0.7)
    preset_factor={"board-high":1.15,"board-balanced":0.82,"board-extreme":0.62}.get(preset,0.82)
    factor=max(0.025,min(0.95,pixel_ratio*fps_ratio*codec_factor*preset_factor))
    mid=original_bytes*factor
    return int(mid*0.70), int(mid*1.35)
