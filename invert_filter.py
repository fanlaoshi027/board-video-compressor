from __future__ import annotations
import cv2
import numpy as np


def apply_smart_invert(frame_bgr: np.ndarray, strength: float = 0.90, saturation_threshold: int = 38) -> np.ndarray:
    """Invert neutral board pixels while leaving meaningful color unchanged.

    White paper approaches 10% luminance; black ink approaches white.
    Saturated pen colors are copied from the source frame unchanged.
    """
    hsv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)
    h, s, v = cv2.split(hsv)
    neutral = s < saturation_threshold
    inv = 255.0 - v.astype(np.float32)
    # strength=0.90 means white(255)->~26 and black(0)->~230.
    mapped = v.astype(np.float32) * (1.0 - strength) + inv * strength
    mapped = np.clip(mapped, 0, 255).astype(np.uint8)
    out_hsv = cv2.merge((h, s, np.where(neutral, mapped, v).astype(np.uint8)))
    return cv2.cvtColor(out_hsv, cv2.COLOR_HSV2BGR)
