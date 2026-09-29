#!/usr/bin/env python3
from __future__ import annotations
from pathlib import Path


def run_smart_invert(src: str, out: str, *, strength=0.90, crf=25, codec='h265', preset='medium', width=None, height=None, cancel_event=None):
    """Smart-invert only neutral board pixels while preserving source frame PTS.

    PyAV is used here because a rawvideo pipe cannot carry variable timestamps.
    Audio is remuxed from the source after the processed VFR video is encoded.
    """
    try:
        import av
        import cv2
    except ImportError as exc:
        raise RuntimeError('智能反色需要 PyAV 和 OpenCV') from exc

    src_container=av.open(src)
    in_stream=src_container.streams.video[0]
    fps_num, fps_den = in_stream.time_base.numerator, in_stream.time_base.denominator
    out_container=av.open(out,'w')
    codec_name='libx265' if codec=='h265' else ('libx264' if codec=='h264' else 'libsvtav1')
    out_stream=out_container.add_stream(codec_name, rate=None)
    if width and height:
        out_stream.width=int(width); out_stream.height=int(height)
    else:
        out_stream.width=in_stream.codec_context.width; out_stream.height=in_stream.codec_context.height
    out_stream.pix_fmt='yuv420p'
    out_stream.time_base=in_stream.time_base
    out_stream.options={'crf':str(crf),'preset':preset}

    try:
        for frame in src_container.decode(in_stream):
            if cancel_event is not None and cancel_event.is_set():
                break
            img=frame.to_ndarray(format='bgr24')
            if img.shape[1] != out_stream.width or img.shape[0] != out_stream.height:
                img=cv2.resize(img,(out_stream.width,out_stream.height),interpolation=cv2.INTER_AREA)
            hsv=cv2.cvtColor(img,cv2.COLOR_BGR2HSV)
            h,s,v=cv2.split(hsv)
            neutral=s < 38
            inv=255.0-v.astype('float32')
            mapped=255.0-(inv*max(0.0,min(1.0,float(strength))))
            v2=v.copy(); v2[neutral]=mapped[neutral].clip(0,255).astype('uint8')
            processed=cv2.cvtColor(cv2.merge((h,s,v2)),cv2.COLOR_HSV2BGR)
            of=av.VideoFrame.from_ndarray(processed,format='bgr24').reformat(width=out_stream.width,height=out_stream.height,format='yuv420p')
            of.pts=frame.pts; of.time_base=frame.time_base
            for packet in out_stream.encode(of): out_container.mux(packet)
        for packet in out_stream.encode(): out_container.mux(packet)
    finally:
        src_container.close(); out_container.close()

    if cancel_event is not None and cancel_event.is_set():
        Path(out).unlink(missing_ok=True); return False
    return Path(out).exists() and Path(out).stat().st_size>0
