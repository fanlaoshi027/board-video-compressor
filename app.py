#!/usr/bin/env python3
"""樊老师板书视频压缩器 - Windows 简洁版。"""
from __future__ import annotations
import os, queue, subprocess, sys, threading
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

try:
    from PIL import Image, ImageTk
except ImportError:
    Image = ImageTk = None

from compress import build_command, probe, PRESETS, available_encoders, estimate_output_size, format_bytes

VIDEO_EXTS = "*.mp4 *.avi *.mov *.mkv *.m4v *.webm *.wmv"
PRESET_LABELS = {"高清": "board-high", "均衡": "board-balanced", "极致压缩": "board-extreme"}


def app_dir():
    return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)) if getattr(sys, "frozen", False) else Path(__file__).resolve().parent


def bundled_binary(name):
    suffix = ".exe" if sys.platform.startswith("win") else ""
    p = app_dir() / "bin" / f"{name}{suffix}"
    return str(p) if p.exists() else name


def hidden_kwargs():
    if sys.platform.startswith("win"):
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 0
        return {"startupinfo": si, "creationflags": subprocess.CREATE_NO_WINDOW}
    return {}


class PreviewWindow(tk.Toplevel):
    """可靠的轻量预览：播放时只启动一个 FFmpeg 管道，暂停/拖动时停止并按时间重新定位。"""

    FPS = 12

    def __init__(self, app, path, duration, info):
        super().__init__(app)
        self.app = app
        self.path = Path(path)
        self.duration = max(0.0, float(duration))
        self.pos = 0.0
        self.playing = False
        self.dragging = False
        self.was_playing = False
        self.photo = None
        self.preview_proc = None
        self.generation = 0
        self.seek_job = None

        v = next(s for s in info.get("streams", []) if s.get("codec_type") == "video")
        src_w, src_h = int(v["width"]), int(v["height"])
        self.frame_w = min(800, max(320, src_w))
        self.frame_h = max(2, int(round(self.frame_w * src_h / src_w)))
        if self.frame_h % 2:
            self.frame_h -= 1
        self.frame_bytes = self.frame_w * self.frame_h * 3

        self.title("视频预览与删除区间")
        self.geometry("900x650")
        self.minsize(760, 560)
        self.configure(bg="#111")
        self.protocol("WM_DELETE_WINDOW", self.close)

        self.canvas = tk.Label(self, bg="#111", fg="white", text="正在加载预览…")
        self.canvas.pack(fill="both", expand=True, padx=10, pady=10)

        bar = tk.Frame(self, bg="#111")
        bar.pack(fill="x", padx=12)
        self.time_label = tk.Label(bar, text="00:00 / 00:00", bg="#111", fg="white", font=("Arial", 11))
        self.time_label.pack(side="left")
        self.scale = tk.Scale(bar, from_=0, to=max(0.1, self.duration), orient="horizontal", resolution=0.1, showvalue=0, bg="#111", fg="white", highlightthickness=0, troughcolor="#555", command=self.on_seek)
        self.scale.pack(side="left", fill="x", expand=True, padx=12)
        self.scale.bind("<ButtonPress-1>", self.on_seek_press)
        self.scale.bind("<ButtonRelease-1>", self.on_seek_release)

        controls = tk.Frame(self, bg="#111")
        controls.pack(fill="x", padx=12, pady=(4, 12))
        self.play_btn = tk.Button(controls, text="▶ 播放", command=self.toggle_play, width=10)
        self.play_btn.pack(side="left", padx=4)
        tk.Button(controls, text="设置开始", command=self.set_start, width=10).pack(side="left", padx=4)
        tk.Button(controls, text="设置结束", command=self.set_end, width=10).pack(side="left", padx=4)
        tk.Button(controls, text="清除当前选择", command=self.clear_selection, width=12).pack(side="left", padx=4)
        self.selection = tk.Label(controls, text="未选择删除区间", bg="#111", fg="#ddd")
        self.selection.pack(side="left", padx=12)
        self.status = tk.Label(self, text="预览就绪", bg="#111", fg="#aaa", anchor="w")
        self.status.pack(fill="x", padx=12, pady=(0, 8))
        self.update_time()
        self.seek_to(self.pos, autoplay=False)

    def fmt(self, x):
        x = max(0.0, float(x)); h = int(x // 3600); m = int((x % 3600) // 60); s = int(x % 60)
        return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"

    def update_time(self):
        if not self.winfo_exists(): return
        self.scale.set(min(self.duration, max(0.0, self.pos)))
        self.time_label.config(text=f"{self.fmt(self.pos)} / {self.fmt(self.duration)}")

    def _stop_process(self):
        self.generation += 1
        p = self.preview_proc
        self.preview_proc = None
        if p and p.poll() is None:
            try:
                p.terminate(); p.wait(timeout=0.4)
            except Exception:
                try: p.kill()
                except Exception: pass

    def _read_exact(self, stream, size):
        data = bytearray()
        while len(data) < size:
            chunk = stream.read(size - len(data))
            if not chunk: return None
            data.extend(chunk)
        return bytes(data)

    def _start_process(self, start):
        self._stop_process(); self.generation += 1; generation = self.generation
        cmd = [bundled_binary("ffmpeg"), "-hide_banner", "-loglevel", "error", "-ss", f"{start:.3f}", "-i", str(self.path), "-an", "-vf", f"scale={self.frame_w}:{self.frame_h},fps={self.FPS}", "-pix_fmt", "rgb24", "-f", "rawvideo", "pipe:1"]
        try:
            p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=self.frame_bytes * 2, **hidden_kwargs())
        except Exception as e:
            self.status.config(text=f"预览启动失败：{e}"); self.playing = False; self.play_btn.config(text="▶ 播放"); return
        self.preview_proc = p
        threading.Thread(target=self._reader, args=(p, generation, start), daemon=True).start()

    def _reader(self, proc, generation, start):
        frame_index = 0
        try:
            while generation == self.generation and proc.poll() is None:
                raw = self._read_exact(proc.stdout, self.frame_bytes)
                if raw is None: break
                frame_pos = min(self.duration, start + frame_index / self.FPS); frame_index += 1
                if Image:
                    img = Image.frombytes("RGB", (self.frame_w, self.frame_h), raw)
                    photo = ImageTk.PhotoImage(img)
                    self.after(0, lambda photo=photo, pos=frame_pos, gen=generation: self._show_frame(photo, pos, gen))
        except Exception:
            pass
        finally:
            if generation == self.generation:
                self.after(0, lambda gen=generation: self._playback_finished(gen))

    def _show_frame(self, photo, pos, generation):
        if not self.winfo_exists() or generation != self.generation: return
        self.photo = photo; self.pos = pos; self.canvas.config(image=photo, text=""); self.update_time()

    def _playback_finished(self, generation):
        if not self.winfo_exists() or generation != self.generation: return
        if self.pos >= self.duration - 0.05: self.pos = self.duration
        self.playing = False; self.preview_proc = None; self.play_btn.config(text="▶ 播放"); self.status.config(text="预览结束")

    def toggle_play(self):
        if self.playing:
            self.playing = False; self.play_btn.config(text="▶ 播放"); self._stop_process(); self.status.config(text="已暂停"); return
        if self.pos >= self.duration - 0.05: self.pos = 0.0
        self.playing = True; self.play_btn.config(text="⏸ 暂停"); self.status.config(text="正在播放…"); self._start_process(self.pos)

    def on_seek_press(self, _event=None):
        self.dragging = True; self.was_playing = self.playing
        if self.playing:
            self.playing = False; self.play_btn.config(text="▶ 播放"); self._stop_process()

    def on_seek(self, value):
        self.pos = min(self.duration, max(0.0, float(value))); self.update_time()
        if not self.dragging: self.seek_to(self.pos, autoplay=self.was_playing)

    def on_seek_release(self, _event=None):
        self.dragging = False; self.seek_to(self.pos, autoplay=self.was_playing); self.was_playing = False

    def seek_to(self, pos, autoplay=False):
        if self.seek_job:
            try: self.after_cancel(self.seek_job)
            except Exception: pass
        self.seek_job = self.after(100, lambda: self._seek_now(pos, autoplay))

    def _seek_now(self, pos, autoplay=False):
        self.seek_job = None; self.pos = min(self.duration, max(0.0, float(pos))); self.update_time()
        if autoplay:
            self.playing = True; self.play_btn.config(text="⏸ 暂停"); self._start_process(self.pos); return
        self._stop_process(); self.generation += 1; generation = self.generation
        cmd = [bundled_binary("ffmpeg"), "-hide_banner", "-loglevel", "error", "-ss", f"{self.pos:.3f}", "-i", str(self.path), "-frames:v", "1", "-vf", f"scale={self.frame_w}:{self.frame_h}", "-pix_fmt", "rgb24", "-f", "rawvideo", "pipe:1"]
        try: p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, **hidden_kwargs())
        except Exception as e: self.status.config(text=f"定位失败：{e}"); return
        def one_frame():
            try:
                raw = self._read_exact(p.stdout, self.frame_bytes); p.terminate()
                if raw and Image:
                    img = Image.frombytes("RGB", (self.frame_w, self.frame_h), raw); photo = ImageTk.PhotoImage(img)
                    self.after(0, lambda: self._show_frame(photo, self.pos, generation))
            except Exception: pass
        threading.Thread(target=one_frame, daemon=True).start()

    def set_start(self):
        self.app.preview_start = self.pos; self.update_selection()

    def set_end(self):
        if self.app.preview_start is None:
            self.app.preview_start = self.pos; self.update_selection(); return
        a, b = sorted((self.app.preview_start, self.pos))
        if b <= a:
            messagebox.showwarning("删除区间", "结束位置必须大于开始位置", parent=self); return
        self.app.cuts.append((a, b)); self.app.cuts.sort(); self.app._refresh_cuts(); self.app.preview_start = None; self.update_selection()

    def clear_selection(self): self.app.preview_start = None; self.update_selection()

    def update_selection(self):
        a = self.app.preview_start
        self.selection.config(text=f"开始：{self.fmt(a)}，移动指针后点击“设置结束”" if a is not None else (self.app.cut_text() or "未选择删除区间"))

    def close(self):
        self.playing = False; self._stop_process(); self.destroy()


class App(tk.Tk):
    def __init__(self):
        super().__init__(); self.title("樊老师板书视频压缩器"); self.geometry("900x760"); self.minsize(820,680); self.configure(bg="#f5f7fb")
        self.files=[]; self.events=queue.Queue(); self.running=False; self.current_process=None; self.src_info=None; self.src_duration=0; self.src_ratio=None; self.cuts=[]; self._updating=False; self.preview_start=None; self.output_files=[]
        self._style(); self._ui(); self.after(100,self._poll); self.after(300,self._hardware)

    def _style(self):
        s=ttk.Style(self); s.theme_use("clam"); s.configure("App.TFrame",background="#f5f7fb"); s.configure("Card.TLabelframe",background="#fff",relief="solid"); s.configure("Card.TLabelframe.Label",background="#fff",foreground="#18324a",font=("Arial",10,"bold")); s.configure("Card.TFrame",background="#fff"); s.configure("Card.TLabel",background="#fff",foreground="#334e68",font=("Arial",10)); s.configure("Title.TLabel",background="#f5f7fb",foreground="#102a43",font=("Arial",21,"bold")); s.configure("Sub.TLabel",background="#f5f7fb",foreground="#627d98",font=("Arial",10)); s.configure("Primary.TButton",font=("Arial",10,"bold"),padding=(18,9))

    def _ui(self):
        root=ttk.Frame(self,style="App.TFrame",padding=20); root.pack(fill="both",expand=True); ttk.Label(root,text="樊老师板书视频压缩器",style="Title.TLabel").pack(anchor="w"); ttk.Label(root,text="专为白底黑字板书视频设计 · Windows · FFmpeg 内置",style="Sub.TLabel").pack(anchor="w",pady=(3,10))
        f=ttk.LabelFrame(root,text=" ① 视频 ",style="Card.TLabelframe",padding=10); f.pack(fill="x",pady=5); self.file_label=ttk.Label(f,text="等待选择视频…",style="Card.TLabel"); self.file_label.pack(side="left",fill="x",expand=True); ttk.Button(f,text="选择视频",command=self.choose).pack(side="right"); self.preview_btn=ttk.Button(f,text="预览 / 设置删除",command=self.open_preview,state="disabled"); self.preview_btn.pack(side="right",padx=8)
        self.hardware=ttk.Label(root,text="正在检测编码能力…",style="Sub.TLabel"); self.hardware.pack(anchor="w",pady=3)
        f=ttk.LabelFrame(root,text=" ② 删除时间段（可选） ",style="Card.TLabelframe",padding=10); f.pack(fill="x",pady=5); ttk.Label(f,text="预览中播放、暂停或拖动播放指针；点击“设置开始”和“设置结束”即可选中要删除的片段。",style="Card.TLabel").pack(anchor="w"); self.cut_label=ttk.Label(f,text="未设置删除区间",style="Card.TLabel"); self.cut_label.pack(anchor="w",pady=(7,0)); ttk.Button(f,text="清空删除区间",command=self.clear_cuts).pack(anchor="w",pady=(5,0)); self.duration_label=ttk.Label(f,text="视频时长：--",style="Card.TLabel"); self.duration_label.pack(anchor="w",pady=(3,0))
        f=ttk.LabelFrame(root,text=" ③ 压缩设置 ",style="Card.TLabelframe",padding=10); f.pack(fill="x",pady=5); left=ttk.Frame(f,style="Card.TFrame"); left.pack(side="left",fill="x",expand=True); right=ttk.Frame(f,style="Card.TFrame"); right.pack(side="left",fill="x",expand=True); self._combo(left,"压缩方案","preset",["高清","均衡","极致压缩"],"均衡"); self._combo(left,"编码格式","codec",["h265","h264","av1"],"h265"); self._combo(left,"输出帧率","fps",["智能","15","20","24","25","30","50","60"],"智能")
        self.width=tk.StringVar(); self.height=tk.StringVar(); self.keep=tk.BooleanVar(value=True); self.width.trace_add("write",lambda *_:self._size_changed("w")); self.height.trace_add("write",lambda *_:self._size_changed("h")); r=ttk.Frame(right,style="Card.TFrame"); r.pack(fill="x",pady=4); ttk.Label(r,text="分辨率",style="Card.TLabel",width=9).pack(side="left"); ttk.Entry(r,textvariable=self.width,width=8).pack(side="left"); ttk.Label(r,text=" × ",style="Card.TLabel").pack(side="left"); ttk.Entry(r,textvariable=self.height,width=8).pack(side="left"); ttk.Checkbutton(r,text="锁定比例",variable=self.keep).pack(side="left",padx=8); ttk.Button(r,text="原始尺寸",command=self.reset).pack(side="left")
        r=ttk.Frame(right,style="Card.TFrame"); r.pack(fill="x",pady=4); self.board=tk.BooleanVar(value=True); self.invert=tk.BooleanVar(value=False); ttk.Checkbutton(r,text="板书优化",variable=self.board).pack(side="left"); ttk.Checkbutton(r,text="智能反色（彩色不变）",variable=self.invert).pack(side="left",padx=12); self.out_dir=tk.StringVar(value="与原视频同目录"); r=ttk.Frame(right,style="Card.TFrame"); r.pack(fill="x",pady=4); ttk.Label(r,text="输出",style="Card.TLabel",width=9).pack(side="left"); ttk.Label(r,textvariable=self.out_dir,style="Card.TLabel").pack(side="left",fill="x",expand=True); ttk.Button(r,text="选择",command=self.choose_output).pack(side="right")
        f=ttk.LabelFrame(root,text=" ④ 预估与进度 ",style="Card.TLabelframe",padding=10); f.pack(fill="x",pady=5); self.estimate=ttk.Label(f,text="选择视频后自动显示",style="Card.TLabel"); self.estimate.pack(anchor="w"); self.analysis=ttk.Label(f,text="",style="Sub.TLabel"); self.analysis.pack(anchor="w",pady=3); self.progress=ttk.Progressbar(f,maximum=100); self.progress.pack(fill="x",pady=5); self.progress_text=ttk.Label(f,text="等待开始",style="Card.TLabel"); self.progress_text.pack(anchor="w")
        actions=ttk.Frame(root,style="App.TFrame"); actions.pack(fill="x",pady=8); self.start_btn=ttk.Button(actions,text="开始压缩",style="Primary.TButton",command=self.start); self.start_btn.pack(side="left"); self.stop_btn=ttk.Button(actions,text="停止",command=self.stop,state="disabled"); self.stop_btn.pack(side="left",padx=8); self.open_btn=ttk.Button(actions,text="打开输出目录",command=self.open_output,state="disabled"); self.open_btn.pack(side="left"); self.log=tk.Text(root,height=7,bg="#f8fafc",fg="#334e68",relief="flat",font=("Consolas",9)); self.log.pack(fill="both",expand=True); self.write("等待选择视频…")

    def _combo(self,p,label,attr,values,default):
        r=ttk.Frame(p,style="Card.TFrame"); r.pack(fill="x",pady=4); ttk.Label(r,text=label,style="Card.TLabel",width=9).pack(side="left"); v=tk.StringVar(value=default); setattr(self,attr,v); ttk.Combobox(r,textvariable=v,values=values,state="readonly",width=16).pack(side="left")
    def write(self,t): self.log.insert("end",t+"\n"); self.log.see("end")
    def _hardware(self):
        try: self.hardware.config(text="编码器："+(", ".join(sorted(available_encoders(bundled_binary("ffmpeg")))) or "CPU"))
        except Exception as e: self.hardware.config(text=f"编码检测失败：{e}")
    def choose(self):
        p=filedialog.askopenfilenames(title="选择视频",filetypes=[("视频文件",VIDEO_EXTS),("所有文件","*")]);
        if not p:return
        self.files=list(p); self.cuts=[]; self.preview_start=None; self._refresh_cuts(); self.file_label.config(text=f"已选择 {len(p)} 个视频：{Path(p[0]).name}" if len(p)==1 else f"已选择 {len(p)} 个视频：{Path(p[0]).name} 等"); self._load(Path(p[0]))
    def _load(self,p):
        try:
            info=probe(p,bundled_binary("ffprobe"),bundled_binary("ffmpeg")); self.src_info=info; v=next(s for s in info["streams"] if s.get("codec_type")=="video"); w,h=int(v["width"]),int(v["height"]); self.src_ratio=w/h; self.src_duration=float((info.get("format") or {}).get("duration") or 0); self._set_size(w,h); self.duration_label.config(text=f"视频时长：{self.fmt_time(self.src_duration)}"); self.preview_btn.config(state="normal"); self.write(f"检测成功：{w}×{h} · {self._fps(v):.1f} FPS · {self.fmt_time(self.src_duration)}"); self._estimate()
        except Exception as e: self.src_info=None; self.preview_btn.config(state="disabled"); self.write(f"视频信息读取失败：{e}")
    def _set_size(self,w,h): self._updating=True; self.width.set(str(w)); self.height.set(str(h)); self._updating=False
    def _size_changed(self,which):
        if self._updating or not self.keep.get() or not self.src_ratio:return
        try:
            n=int(self.width.get() if which=="w" else self.height.get()); self._updating=True; self.height.set(str(round(n/self.src_ratio))) if which=="w" else self.width.set(str(round(n*self.src_ratio))); self._updating=False; self._estimate()
        except Exception: pass
    def reset(self):
        if self.src_info:
            v=next(s for s in self.src_info["streams"] if s.get("codec_type")=="video"); self._set_size(int(v["width"]),int(v["height"])); self.keep.set(True); self._estimate()
    def choose_output(self):
        p=filedialog.askdirectory(title="选择输出目录");
        if p:self.out_dir.set(p)
    def fmt_time(self,x):
        x=max(0.0,float(x)); h=int(x//3600); m=int((x%3600)//60); s=int(x%60); return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"
    def cut_text(self): return "、".join(f"{self.fmt_time(a)}–{self.fmt_time(b)}" for a,b in self.cuts)
    def _refresh_cuts(self): self.cut_label.config(text="未设置删除区间" if not self.cuts else "删除："+self.cut_text()); self._estimate()
    def clear_cuts(self): self.cuts=[]; self.preview_start=None; self._refresh_cuts()
    def open_preview(self):
        if self.files and self.src_duration and self.src_info: PreviewWindow(self,self.files[0],self.src_duration,self.src_info)
    def _fps(self,v):
        try:a,b=(v.get("avg_frame_rate") or v.get("r_frame_rate") or "30/1").split("/"); return float(a)/float(b) if float(b) else 30.0
        except Exception:return 30.0
    def _target_fps(self,src):
        x=self.fps.get(); return 15 if x=="智能" and src>=45 else (20 if x=="智能" and src>=24 else (max(15,round(src)) if x=="智能" else int(x)))
    def _estimate(self):
        if not self.files or not self.src_info:return
        try:
            v=next(s for s in self.src_info["streams"] if s.get("codec_type")=="video"); sw,sh=int(v["width"]),int(v["height"]); sf=self._fps(v); tf=self._target_fps(sf); w,h=int(self.width.get()),int(self.height.get()); e=estimate_output_size(Path(self.files[0]).stat().st_size,sf,tf,sw,sh,w,h,self.codec.get(),PRESET_LABELS[self.preset.get()]); deleted=sum(b-a for a,b in self.cuts); self.estimate.config(text=f"预计输出：{format_bytes(e[0])} ～ {format_bytes(e[1])}"); self.analysis.config(text=f"{sw}×{sh} · {sf:.1f} FPS → {w}×{h} · {tf} FPS · 删除 {self.fmt_time(deleted)}")
        except Exception: pass
    def start(self):
        if self.running:return
        if not self.files or not self.src_info:messagebox.showinfo("提示","请先选择并成功读取视频");return
        self.running=True; self.start_btn.config(state="disabled"); self.stop_btn.config(state="normal"); self.open_btn.config(state="disabled"); self.progress.config(value=0); self.progress_text.config(text="正在压缩…"); threading.Thread(target=self._worker,daemon=True).start()
    def stop(self):
        if self.current_process and self.current_process.poll() is None:
            try:self.current_process.terminate()
            except Exception:pass
    def open_output(self):
        target=str(Path(self.files[0]).parent) if self.out_dir.get()=="与原视频同目录" else self.out_dir.get()
        try:
            if sys.platform.startswith("win"):os.startfile(target)
            elif sys.platform=="darwin":subprocess.Popen(["open",target],**hidden_kwargs())
            else:subprocess.Popen(["xdg-open",target],**hidden_kwargs())
        except Exception as e:messagebox.showerror("打开失败",str(e))
    def _worker(self):
        ffmpeg=bundled_binary("ffmpeg"); ffprobe=bundled_binary("ffprobe")
        try:
            info=probe(Path(self.files[0]),ffprobe,ffmpeg); v=next(s for s in info["streams"] if s.get("codec_type")=="video"); sw,sh=int(v["width"]),int(v["height"]); sf=self._fps(v); tf=self._target_fps(sf); w,h=int(self.width.get()),int(self.height.get()); encs=available_encoders(ffmpeg); codec=self.codec.get(); encoder={"h265":"hevc_qsv","h264":"h264_qsv","av1":"av1_qsv"}.get(codec,codec); fallback={"h265":"libx265","h264":"libx264","av1":"libsvtav1"}[codec]; encoder=encoder if encoder in encs else fallback; has_audio=any(s.get("codec_type")=="audio" for s in info.get("streams",[])); out_dir=Path(self.files[0]).parent if self.out_dir.get()=="与原视频同目录" else Path(self.out_dir.get()); out_dir.mkdir(parents=True,exist_ok=True); self.output_files=[]; total=len(self.files)
            for idx,src in enumerate(self.files,1):
                src=Path(src); dst=out_dir/(src.stem+"_压缩.mp4"); self.write(f"开始：{src.name}"); cmd=build_command(src,dst,codec,PRESET_LABELS[self.preset.get()],fps=tf,width=w,height=h,keep_aspect=True,invert=self.invert.get(),src_w=sw,src_h=sh,encoder=encoder,ffmpeg=ffmpeg,board_optimized=self.board.get(),cuts=self.cuts,duration=float((info.get("format") or {}).get("duration") or 0),has_audio=has_audio); self.current_process=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding="utf-8",errors="replace",bufsize=1,**hidden_kwargs())
                for line in self.current_process.stdout:
                    line=line.strip()
                    if not line:continue
                    if "time=" in line:
                        try:
                            import re; m=re.search(r"time=(\d+):(\d+):(\d+(?:\.\d+)?)",line)
                            if m:
                                t=int(m.group(1))*3600+int(m.group(2))*60+float(m.group(3)); base=(idx-1)/total*100; self.events.put(("progress",base+min(99,t/max(0.1,float(info.get("format",{}).get("duration",0)))*100)/total))
                        except Exception:pass
                    if "error" in line.lower():self.events.put(("log",line))
                rc=self.current_process.wait(); self.current_process=None
                if rc!=0:raise RuntimeError(f"FFmpeg 失败，返回码 {rc}")
                self.output_files.append(str(dst)); self.events.put(("done",str(dst),idx,total))
            self.events.put(("finish",self.output_files))
        except Exception as e:self.current_process=None; self.events.put(("error",str(e)))
    def _poll(self):
        try:
            while True:
                ev=self.events.get_nowait(); kind=ev[0]
                if kind=="log":self.write(ev[1])
                elif kind=="progress":self.progress.config(value=max(0,min(100,ev[1])))
                elif kind=="done":self.write(f"完成：{Path(ev[1]).name}"); self.progress.config(value=ev[2]/ev[3]*100)
                elif kind=="finish":self.running=False; self.current_process=None; self.start_btn.config(state="normal"); self.stop_btn.config(state="disabled"); self.open_btn.config(state="normal" if ev[1] else "disabled"); self.progress_text.config(text="全部完成"); self.write("全部压缩完成，可点击“打开输出目录”。")
                elif kind=="error":self.running=False; self.current_process=None; self.start_btn.config(state="normal"); self.stop_btn.config(state="disabled"); self.progress_text.config(text="压缩失败"); self.write("压缩失败："+ev[1]); messagebox.showerror("压缩失败",ev[1])
        except queue.Empty:pass
        self.after(100,self._poll)

if __name__=="__main__": App().mainloop()
