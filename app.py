import os, sys, queue, subprocess, threading, tkinter as tk
from pathlib import Path
from tkinter import ttk, filedialog, messagebox
from compress import build_command, probe, available_encoders, PRESETS
from size_estimator import estimate_output_size, format_bytes

VIDEO_EXTS=("*.mp4","*.mov","*.mkv","*.avi","*.webm","*.m4v")
PRESET_LABELS={"高清":"board-high","均衡":"board-balanced","极致压缩":"board-extreme"}

def hidden_kwargs():
    if sys.platform.startswith("win"):
        si=subprocess.STARTUPINFO(); si.dwFlags |= subprocess.STARTF_USESHOWWINDOW; si.wShowWindow=0
        return {"startupinfo":si,"creationflags":subprocess.CREATE_NO_WINDOW}
    return {}

def bundled_binary(name):
    base=Path(getattr(sys,"_MEIPASS",Path(__file__).resolve().parent)); suffix=".exe" if sys.platform.startswith("win") else ""; p=base/"bin"/(name+suffix)
    return str(p if p.exists() else name)

class App(tk.Tk):
    def __init__(self):
        super().__init__(); self.title("板书视频压缩器"); self.geometry("900x760"); self.minsize(820,680)
        self.files=[]; self.cuts=[]; self.preview_start=None; self.src_info=None; self.src_ratio=None; self.src_duration=0; self.current_process=None; self.output_files=[]; self.running=False; self.events=queue.Queue(); self._updating=False
        self._style(); self._build(); self.after(100,self._poll); threading.Thread(target=self._hardware,daemon=True).start()
    def _style(self):
        s=ttk.Style(self); s.theme_use("clam"); s.configure("App.TFrame",background="#eef4f8"); s.configure("Card.TFrame",background="#ffffff"); s.configure("Card.TLabel",background="#ffffff",foreground="#183b56",font=("Microsoft YaHei UI",10)); s.configure("Sub.TLabel",background="#eef4f8",foreground="#627d98",font=("Microsoft YaHei UI",9)); s.configure("Card.TLabelframe",background="#ffffff",foreground="#183b56"); s.configure("Card.TLabelframe.Label",background="#ffffff",foreground="#183b56"); s.configure("Primary.TButton",font=("Microsoft YaHei UI",11,"bold"),padding=(16,8))
    def _build(self):
        root=ttk.Frame(self,padding=14,style="App.TFrame"); root.pack(fill="both",expand=True)
        ttk.Label(root,text="板书视频压缩器",font=("Microsoft YaHei UI",18,"bold"),background="#eef4f8",foreground="#183b56").pack(anchor="w")
        ttk.Label(root,text="压缩 · 裁切 · 板书优化 · 智能反色",style="Sub.TLabel").pack(anchor="w",pady=(0,8))
        f=ttk.LabelFrame(root,text=" ① 视频 ",style="Card.TLabelframe",padding=10); f.pack(fill="x",pady=5)
        r=ttk.Frame(f,style="Card.TFrame"); r.pack(fill="x"); self.file_label=ttk.Label(r,text="未选择视频",style="Card.TLabel"); self.file_label.pack(side="left",fill="x",expand=True); self.preview_btn=ttk.Button(r,text="预览 / 裁切",command=self.open_preview,state="disabled"); self.preview_btn.pack(side="right",padx=5); ttk.Button(r,text="选择视频",command=self.choose).pack(side="right")
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
        try:self.hardware.config(text="编码器："+(", ".join(sorted(available_encoders(bundled_binary("ffmpeg")))) or "CPU"))
        except Exception as e:self.hardware.config(text=f"编码检测失败：{e}")
    def choose(self):
        p=filedialog.askopenfilenames(title="选择视频",filetypes=[("视频文件",VIDEO_EXTS),("所有文件","*")])
        if not p:return
        self.files=list(p); self.cuts=[]; self.preview_start=None; self._refresh_cuts(); self.file_label.config(text=f"已选择 {len(p)} 个视频：{Path(p[0]).name}" if len(p)==1 else f"已选择 {len(p)} 个视频：{Path(p[0]).name} 等"); self._load(Path(p[0]))
    def _load(self,p):
        try:
            info=probe(p,bundled_binary("ffprobe"),bundled_binary("ffmpeg")); self.src_info=info; v=next(s for s in info["streams"] if s.get("codec_type")=="video"); w,h=int(v["width"]),int(v["height"]); self.src_ratio=w/h; self.src_duration=float((info.get("format") or {}).get("duration") or 0); self._set_size(w,h); self.duration_label.config(text=f"视频时长：{self.fmt_time(self.src_duration)}"); self.preview_btn.config(state="normal"); self.write(f"检测成功：{w}×{h} · {self._fps(v):.1f} FPS · {self.fmt_time(self.src_duration)}"); self._estimate()
        except Exception as e:self.src_info=None; self.preview_btn.config(state="disabled"); self.write(f"视频信息读取失败：{e}")
    def _set_size(self,w,h): self._updating=True; self.width.set(str(w)); self.height.set(str(h)); self._updating=False
    def _size_changed(self,which):
        if self._updating or not self.keep.get() or not self.src_ratio:return
        try:
            n=int(self.width.get() if which=="w" else self.height.get()); self._updating=True; self.height.set(str(round(n/self.src_ratio))) if which=="w" else self.width.set(str(round(n*self.src_ratio))); self._updating=False; self._estimate()
        except Exception:pass
    def reset(self):
        if self.src_info:
            v=next(s for s in self.src_info["streams"] if s.get("codec_type")=="video"); self._set_size(int(v["width"]),int(v["height"])); self.keep.set(True); self._estimate()
    def choose_output(self):
        p=filedialog.askdirectory(title="选择输出目录")
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
        except Exception:pass
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
            encs=available_encoders(ffmpeg); codec=self.codec.get(); encoder={"h265":"hevc_qsv","h264":"h264_qsv","av1":"av1_qsv"}.get(codec,codec); fallback={"h265":"libx265","h264":"libx264","av1":"libsvtav1"}[codec]; encoder=encoder if encoder in encs else fallback; out_dir=None
            total=len(self.files)
            for idx,src in enumerate(self.files,1):
                src=Path(src); info=probe(src,ffprobe,ffmpeg); v=next(s for s in info["streams"] if s.get("codec_type")=="video"); sw,sh=int(v["width"]),int(v["height"]); sf=self._fps(v); tf=self._target_fps(sf); w,h=sw,sh
                if self.files and idx==1 and self.src_info: w,h=int(self.width.get()),int(self.height.get())
                has_audio=any(s.get("codec_type")=="audio" for s in info.get("streams",[])); duration=float((info.get("format") or {}).get("duration") or 0); cuts=self.cuts if idx==1 else []
                if self.out_dir.get()=="与原视频同目录": out_dir=src.parent
                else: out_dir=Path(self.out_dir.get())
                out_dir.mkdir(parents=True,exist_ok=True); dst=out_dir/(src.stem+"_压缩.mp4"); self.write(f"开始：{src.name} · {sw}×{sh} · {sf:.1f} FPS"); cmd=build_command(src,dst,codec,PRESET_LABELS[self.preset.get()],fps=tf,width=w,height=h,keep_aspect=True,invert=self.invert.get(),src_w=sw,src_h=sh,encoder=encoder,ffmpeg=ffmpeg,board_optimized=self.board.get(),cuts=cuts,duration=duration,has_audio=has_audio)
                cmd[2:2]=["-progress","pipe:1","-nostats"]; self.current_process=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding="utf-8",errors="replace",bufsize=1,**hidden_kwargs())
                for line in self.current_process.stdout:
                    line=line.strip()
                    if not line:continue
                    if line.startswith("out_time_ms="):
                        try:
                            t=float(line.split("=",1)[1])/1000000.0; base=(idx-1)/total*100; value=base+min(100.0,t/max(0.1,duration)*100.0)/total; self.events.put(("progress",value)); self.events.put(("status",f"正在处理 {idx}/{total}：{self.fmt_time(t)} / {self.fmt_time(duration)}"))
                        except Exception:pass
                    elif line.startswith("progress=") and line.endswith("end"):self.events.put(("progress",idx/total*100))
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
                elif kind=="status":self.progress_text.config(text=ev[1])
                elif kind=="progress":self.progress.config(value=max(0,min(100,ev[1])))
                elif kind=="done":self.write(f"完成：{Path(ev[1]).name}"); self.progress.config(value=ev[2]/ev[3]*100)
                elif kind=="finish":self.running=False; self.current_process=None; self.start_btn.config(state="normal"); self.stop_btn.config(state="disabled"); self.open_btn.config(state="normal" if ev[1] else "disabled"); self.progress_text.config(text="全部完成"); self.write("全部压缩完成，可点击“打开输出目录”。")
                elif kind=="error":self.running=False; self.current_process=None; self.start_btn.config(state="normal"); self.stop_btn.config(state="disabled"); self.progress_text.config(text="压缩失败"); self.write("压缩失败："+ev[1]); messagebox.showerror("压缩失败",ev[1])
        except queue.Empty:pass
        self.after(100,self._poll)

if __name__=="__main__": App().mainloop()
