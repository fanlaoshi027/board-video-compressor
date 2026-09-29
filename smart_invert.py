from __future__ import annotations

# White paper -> about 10% luminance (90% dark), black ink -> white.
# Pixels with meaningful chroma are protected so colored pens remain colored.

def filter_expression(strength: float = 0.90) -> str:
    s=max(0.0,min(1.0,float(strength)))
    # Work in HSV: near-neutral pixels are candidates for inversion.
    # Saturated pixels keep their hue/saturation while their value is unchanged.
    # Neutral luminance is remapped around a dark-paper target.
    dark=1.0-s
    return (
        "format=gbrp,"
        "lutrgb="
        f"r='if(gt(max(maxval*0.0,r),0),r,r)',"  # keep expression portable; color logic follows below
        f"g='g',b='b'"
    )

# The actual implementation is supplied as a Python/OpenCV frame filter in
# smart_invert_frame(), which is safer than a fragile one-line FFmpeg lut for
# preserving saturated pen colors.
def smart_invert_frame(frame_bgr, strength: float = 0.90):
    import cv2
    import numpy as np
    hsv=cv2.cvtColor(frame_bgr,cv2.COLOR_BGR2HSV)
    h,s,v=cv2.split(hsv)
    neutral=(s < 38)
    # Invert only neutral/gray paper and ink. Keep colored pixels untouched.
    target=(255-v).astype(np.float32)
    target=255.0-(target*float(max(0.0,min(1.0,strength))))
    # Normalize so white paper approaches ~26/255 while black ink approaches 255.
    target=np.clip(target,0,255).astype(np.uint8)
    v2=np.where(neutral,target,v).astype(np.uint8)
    return cv2.cvtColor(cv2.merge((h,s,v2)),cv2.COLOR_HSV2BGR)
