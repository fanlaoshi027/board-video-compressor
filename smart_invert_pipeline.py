#!/usr/bin/env python3
from __future__ import annotations
import subprocess
import tempfile
from pathlib import Path
import av
import cv2
from invert_filter import apply_smart_invert

def run_smart_invert(src: str, out: str, *, ffmpeg='ffmpeg', strength=0.90, crf=25, codec='h265', preset='medium', width=None, height=None, cancel_event=None):
    """Frame-level smart inversion preserving source PTS/time_base, then remux source audio."""
    src_path=Path(src); out_path=Path(out); out_path.parent.mkdir(parents=True, exist_ok=True)
    vcodec={'h265':'libx265','h264':'libx264','av1':'libsvtav1'}.get(codec,'libx265')
    container=av.open(str(src_path)); in_stream=container.streams.video[0]
    target_w=int(width or in_stream.codec_context.width); target_h=int(height or in_stream.codec_context.height)
    fd,tmp_name=tempfile.mkstemp(prefix='board-invert-',suffix='.mp4',dir=str(out_path.parent)); Path(tmp_name).unlink(missing_ok=True); tmp_video=Path(tmp_name)
    out_container=None
    try:
        out_container=av.open(str(tmp_video),'w')
        out_stream=out_container.add_stream(vcodec,rate=None)
        out_stream.width=target_w; out_stream.height=target_h; out_stream.pix_fmt='yuv420p'; out_stream.time_base=in_stream.time_base
        out_stream.options={'crf':str(crf),'preset':preset}
        for frame in container.decode(in_stream):
            if cancel_event is not None and cancel_event.is_set(): raise InterruptedError
            img=frame.to_ndarray(format='bgr24')
            if (img.shape[1],img.shape[0])!=(target_w,target_h): img=cv2.resize(img,(target_w,target_h),interpolation=cv2.INTER_AREA)
            img=apply_smart_invert(img,strength)
            vf=av.VideoFrame.from_ndarray(img,format='bgr24').reformat(width=target_w,height=target_h,format='yuv420p')
            vf.pts=frame.pts; vf.time_base=frame.time_base
            for packet in out_stream.encode(vf): out_container.mux(packet)
        for packet in out_stream.encode(): out_container.mux(packet)
        out_container.close(); out_container=None; container.close()
        cmd=[ffmpeg,'-hide_banner','-loglevel','error','-y','-i',str(tmp_video),'-i',str(src),'-map','0:v:0','-map','1:a?','-c:v','copy','-c:a','copy','-shortest','-movflags','+faststart',str(out_path)]
        p=subprocess.run(cmd,check=False)
        if p.returncode!=0: raise RuntimeError(f'FFmpeg 音频复用失败: {p.returncode}')
        return out_path.exists() and out_path.stat().st_size>0
    except Exception:
        out_path.unlink(missing_ok=True); raise
    finally:
        try: container.close()
        except Exception: pass
        try:
            if out_container is not None: out_container.close()
        except Exception: pass
        tmp_video.unlink(missing_ok=True)
