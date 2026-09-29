#!/usr/bin/env python3
from __future__ import annotations
import subprocess
from pathlib import Path
from invert_filter import apply_smart_invert


def run_smart_invert(src: str, out: str, *, ffmpeg='ffmpeg', strength=0.90, crf=25, codec='h265', preset='medium', width=None, height=None, fps=None, cancel_event=None):
    """Process video frames through OpenCV, then mux source audio back in.

    This path is intentionally separate from the normal encoder because OpenCV
    gives us reliable per-pixel protection for colored pen strokes.
    """
    probe=['-hide_banner','-loglevel','error','-i',src,'-f','null','-']
    # Let FFmpeg perform scaling/fps before raw frames reach OpenCV.
    vf=[]
    if width and height: vf.append(f'scale={int(width)}:{int(height)}')
    if fps: vf.append(f'fps={int(fps)}')
    decode=[ffmpeg,'-hide_banner','-loglevel','error','-i',src]
    if vf: decode += ['-vf',','.join(vf)]
    decode += ['-f','rawvideo','-pix_fmt','bgr24','-']
    enc=[ffmpeg,'-hide_banner','-loglevel','error','-f','rawvideo','-pix_fmt','bgr24']
    # Width/height must describe the frames emitted by the decoder.
    import cv2
    cap=cv2.VideoCapture(src)
    w=int(width or cap.get(cv2.CAP_PROP_FRAME_WIDTH)); h=int(height or cap.get(cv2.CAP_PROP_FRAME_HEIGHT)); cap.release()
    enc += ['-s',f'{w}x{h}']
    if fps: enc += ['-r',str(int(fps))]
    enc += ['-i','-','-i',src,'-map','0:v:0','-map','1:a?','-c:v',('libx265' if codec=='h265' else 'libx264'),'-preset',preset,'-crf',str(crf),'-c:a','copy','-shortest','-y',out]
    dec=subprocess.Popen(decode,stdout=subprocess.PIPE)
    encp=subprocess.Popen(enc,stdin=subprocess.PIPE)
    frame_bytes=w*h*3
    try:
        while True:
            if cancel_event is not None and cancel_event.is_set(): break
            raw=dec.stdout.read(frame_bytes)
            if len(raw)!=frame_bytes: break
            import numpy as np
            frame=np.frombuffer(raw,dtype=np.uint8).reshape((h,w,3))
            encp.stdin.write(apply_smart_invert(frame,strength))
    finally:
        if encp.stdin:
            try: encp.stdin.close()
            except Exception: pass
        dec.wait(); encp.wait()
    if cancel_event is not None and cancel_event.is_set():
        Path(out).unlink(missing_ok=True)
        return False
    return encp.returncode==0 and Path(out).exists()
