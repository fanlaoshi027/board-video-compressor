from __future__ import annotations
import os, subprocess, sys, threading, tkinter as tk
from pathlib import Path
from tkinter import messagebox
try:
    from PIL import Image, ImageTk
except ImportError:
    Image = ImageTk = None

def _app_dir():
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))

def bundled_binary(name):
    suffix = ".exe" if sys.platform.startswith("win") else ""
    p = _app_dir() / "bin" / f"{name}{suffix}"
    return str(p) if p.exists() else name

def hidden_kwargs():
    if sys.platform.startswith("win"):
        si = subprocess.STARTUPINFO(); si.dwFlags |= subprocess.STARTF_USESHOWWINDOW; si.wShowWindow = 0
        return {"startupinfo": si, "creationflags": subprocess.CREATE_NO_WINDOW}
    return {}

class PreviewWindow(tk.Toplevel):
    FPS = 10
    def __init__(self, app, path, duration, info):
        super().__init__(app); self.app=app; self.path=Path(path); self.duration=max(0,float(duration)); self.pos=0.0
        self.playing=False; self.was_playing=False; self.proc=None; self.generation=0; self.photo=None
        v=next(s for s in info.get("streams",[]) if s.get("codec_type")=="video"); sw,sh=int(v["width"]),int(v["height"])
        self.frame_w=min(800,max(320,sw)); self.frame_h=max(2,int(round(self.frame_w*sh/sw))); self.frame_h-=self.frame_h%2; self.frame_bytes=self.frame_w*self.frame_h*3
        self.title("视频预览与删除区间"); self.geometry("900x650"); self.minsize(760,560); self.configure(bg="#111"); self.protocol("WM_DELETE_WINDOW",self.close)
        self.canvas=tk.Label(self,bg="#111",fg="white",text="正在加载预览…"); self.canvas.pack(fill="both",expand=True,padx=10,pady=10)
        bar=tk.Frame(self,bg="#111"); bar.pack(fill="x",padx=12); self.time_label=tk.Label(bar,text="00:00 / 00:00",bg="#111",fg="white"); self.time_label.pack(side="left")
        self.scale=tk.Scale(bar,from_=0,to=max(.1,self.duration),orient="horizontal",resolution=.1,showvalue=0,bg="#111",fg="white",highlightthickness=0,troughcolor="#555",command=self.on_seek); self.scale.pack(side="left",fill="x",expand=True,padx=12); self.scale.bind("<ButtonPress-1>",self.on_seek_press); self.scale.bind("<ButtonRelease-1>",self.on_seek_release)
        controls=tk.Frame(self,bg="#111"); controls.pack(fill="x",padx=12,pady=(4,12)); self.play_btn=tk.Button(controls,text="▶ 播放",command=self.toggle_play,width=10); self.play_btn.pack(side="left",padx=4); tk.Button(controls,text="设置开始",command=self.set_start,width=10).pack(side="left",padx=4); tk.Button(controls,text="设置结束",command=self.set_end,width=10).pack(side="left",padx=4); tk.Button(controls,text="清除当前选择",command=self.clear_selection,width=12).pack(side="left",padx=4); self.selection=tk.Label(controls,text="未选择删除区间",bg="#111",fg="#ddd"); self.selection.pack(side="left",padx=12)
        self.status=tk.Label(self,text="预览就绪",bg="#111",fg="#aaa",anchor="w"); self.status.pack(fill="x",padx=12,pady=(0,8)); self.update_time(); self._show_single_frame(0)
    def fmt(self,x):
        x=max(0,float(x)); h=int(x//3600); m=int((x%3600)//60); s=int(x%60); return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"
    def update_time(self):
        if self.winfo_exists(): self.scale.set(min(self.duration,max(0,self.pos))); self.time_label.config(text=f"{self.fmt(self.pos)} / {self.fmt(self.duration)}")
    def _stop(self):
        self.generation+=1; p=self.proc; self.proc=None
        if p and p.poll() is None:
            try:p.terminate(); p.wait(timeout=.3)
            except Exception:
                try:p.kill()
                except Exception:pass
    def _read(self,stream,n):
        b=bytearray()
        while len(b)<n:
            c=stream.read(n-len(b))
            if not c:return None
            b.extend(c)
        return bytes(b)
    def toggle_play(self):
        if self.playing: self.playing=False; self.play_btn.config(text="▶ 播放"); self._stop(); self.status.config(text="已暂停"); return
        if self.pos>=self.duration-.05:self.pos=0
        self.playing=True; self.play_btn.config(text="⏸ 暂停"); self.status.config(text="正在播放…"); self._start_play(self.pos)
    def _start_play(self,start):
        self._stop(); gen=self.generation; cmd=[bundled_binary("ffmpeg"),"-hide_banner","-loglevel","error","-re","-ss",f"{start:.3f}","-i",str(self.path),"-an","-vf",f"scale={self.frame_w}:{self.frame_h},fps={self.FPS}","-pix_fmt","rgb24","-f","rawvideo","pipe:1"]
        try:p=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,bufsize=self.frame_bytes*2,**hidden_kwargs())
        except Exception as e:self.playing=False; self.play_btn.config(text="▶ 播放"); self.status.config(text=f"预览启动失败：{e}"); return
        self.proc=p; threading.Thread(target=self._reader,args=(p,gen,start),daemon=True).start()
    def _reader(self,p,gen,start):
        i=0
        try:
            while gen==self.generation and p.poll() is None:
                raw=self._read(p.stdout,self.frame_bytes)
                if raw is None:break
                pos=min(self.duration,start+i/self.FPS); i+=1
                if self.winfo_exists(): self.after(0,lambda raw=raw,pos=pos,gen=gen:self._frame(raw,pos,gen))
        except Exception:pass
        finally:
            if gen==self.generation and self.winfo_exists(): self.after(0,lambda gen=gen:self._finished(gen))
    def _frame(self,raw,pos,gen):
        if gen!=self.generation or not self.playing or not Image:return
        try: img=Image.frombytes("RGB",(self.frame_w,self.frame_h),raw); self.photo=ImageTk.PhotoImage(img); self.canvas.config(image=self.photo,text=""); self.pos=pos; self.update_time()
        except Exception:pass
    def _finished(self,gen):
        if gen!=self.generation:return
        self.proc=None; self.playing=False; self.play_btn.config(text="▶ 播放"); self.status.config(text="预览结束"); self.update_time()
    def on_seek_press(self,_=None): self.was_playing=self.playing; self.playing=False; self.play_btn.config(text="▶ 播放"); self._stop(); self.status.config(text="拖动中…")
    def on_seek(self,value): self.pos=min(self.duration,max(0,float(value))); self.update_time()
    def on_seek_release(self,_=None): was=self.was_playing; self.was_playing=False; self._seek_now(self.pos,was)
    def _seek_now(self,pos,autoplay=False):
        self._stop(); self.pos=min(self.duration,max(0,float(pos))); self.update_time()
        if autoplay: self.playing=True; self.play_btn.config(text="⏸ 暂停"); self.status.config(text="正在播放…"); self._start_play(self.pos)
        else: self._show_single_frame(self.pos)
    def _show_single_frame(self,pos):
        self._stop(); gen=self.generation; cmd=[bundled_binary("ffmpeg"),"-hide_banner","-loglevel","error","-ss",f"{pos:.3f}","-i",str(self.path),"-frames:v","1","-vf",f"scale={self.frame_w}:{self.frame_h}","-pix_fmt","rgb24","-f","rawvideo","pipe:1"]
        try:p=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,**hidden_kwargs())
        except Exception as e:self.status.config(text=f"定位失败：{e}"); return
        self.proc=p
        def worker():
            raw=None
            try: raw=self._read(p.stdout,self.frame_bytes)
            except Exception: pass
            finally:
                try:p.stdout.close()
                except Exception:pass
                try:p.wait(timeout=.5)
                except Exception:
                    try:p.kill()
                    except Exception:pass
            if raw and gen==self.generation and self.winfo_exists(): self.after(0,lambda raw=raw:self._show_frame(raw,pos,gen))
        threading.Thread(target=worker,daemon=True).start()
    def _show_frame(self,raw,pos,gen):
        if gen!=self.generation or not Image:return
        try: img=Image.frombytes("RGB",(self.frame_w,self.frame_h),raw); self.photo=ImageTk.PhotoImage(img); self.canvas.config(image=self.photo,text=""); self.pos=pos; self.update_time(); self.status.config(text="预览就绪")
        except Exception:pass
    def set_start(self): self.app.preview_start=self.pos; self.update_selection()
    def set_end(self):
        if self.app.preview_start is None: self.app.preview_start=self.pos; self.update_selection(); return
        a,b=sorted((self.app.preview_start,self.pos))
        if b<=a: messagebox.showwarning("删除区间","结束位置必须大于开始位置",parent=self); return
        self.app.cuts.append((a,b)); self.app.cuts.sort(); self.app._refresh_cuts(); self.app.preview_start=None; self.update_selection()
    def clear_selection(self): self.app.preview_start=None; self.update_selection()
    def update_selection(self):
        a=self.app.preview_start; self.selection.config(text=f"开始：{self.fmt(a)}，移动指针后点击“设置结束”" if a is not None else (self.app.cut_text() or "未选择删除区间"))
    def close(self):
        self.playing=False; self._stop()
        try:self.destroy()
        except Exception:pass
