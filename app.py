#!/usr/bin/env python3
"""樊老师板书视频压缩器 - Windows 简洁版。"""
from __future__ import annotations
import os, queue, subprocess, sys, threading
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from compress import build_command, probe, PRESETS, available_encoders, estimate_output_size, format_bytes

VIDEO_EXTS="*.mp4 *.avi *.mov *.mkv *.m4v *.webm *.wmv"
TIME_RE=__import__('re').compile(r"time=(\d+):(\d+):(\d+(?:\.\d+)?)")
SPEED_RE=__import__('re').compile(r"speed=\s*([0-9.]+)x")
PRESET_LABELS={"高清":"board-high","均衡":"board-balanced","极致压缩":"board-extreme"}

def app_dir():
    return Path(getattr(sys,"_MEIPASS",Path(sys.executable).parent)) if getattr(sys,"frozen",False) else Path(__file__).resolve().parent

def bundled_binary(name):
    suffix=".exe" if sys.platform.startswith("win") else ""
    p=app_dir()/"bin"/f"{name}{suffix}"
    return str(p) if p.exists() else name

def run_text(cmd,timeout=20):
    return subprocess.run(cmd,capture_output=True,text=True,encoding="utf-8",errors="replace",timeout=timeout)

class App(tk.Tk):
    def __init__(self):
        super().__init__(); self.title("樊老师板书视频压缩器"); self.geometry("900x720"); self.minsize(820,650); self.configure(bg="#f5f7fb")
        self.files=[]; self.events=queue.Queue(); self.running=False; self.stop_requested=False; self.current_process=None; self.src_info=None; self.src_duration=0; self.src_ratio=None; self.cuts=[]; self._updating=False
        self._style(); self._ui(); self.after(100,self._poll); self.after(300,self._hardware)
    def _style(self):
        s=ttk.Style(self); s.theme_use("clam"); s.configure("App.TFrame",background="#f5f7fb"); s.configure("Card.TLabelframe",background="#fff",relief="solid"); s.configure("Card.TLabelframe.Label",background="#fff",foreground="#18324a",font=("Arial",10,"bold")); s.configure("Card.TFrame",background="#fff"); s.configure("Card.TLabel",background="#fff",foreground="#334e68",font=("Arial",10)); s.configure("Title.TLabel",background="#f5f7fb",foreground="#102a43",font=("Arial",21,"bold")); s.configure("Sub.TLabel",background="#f5f7fb",foreground="#627d98",font=("Arial",10)); s.configure("Primary.TButton",font=("Arial",10,"bold"),padding=(18,9)); s.configure("Modern.Horizontal.TProgressbar",thickness=9,troughcolor="#e7edf3",background="#1976d2",borderwidth=0)
    def _ui(self):
        root=ttk.Frame(self,style="App.TFrame",padding=20); root.pack(fill="both",expand=True)
        ttk.Label(root,text="樊老师板书视频压缩器",style="Title.TLabel").pack(anchor="w"); ttk.Label(root,text="专为白底黑字板书视频设计 · Windows · FFmpeg 内置",style="Sub.TLabel").pack(anchor="w",pady=(3,12))
        f=ttk.LabelFrame(root,text=" ① 视频 ",style="Card.TLabelframe",padding=10); f.pack(fill="x",pady=5); self.file_label=ttk.Label(f,text="等待选择视频…",style="Card.TLabel"); self.file_label.pack(side="left",fill="x",expand=True); ttk.Button(f,text="选择视频",command=self.choose).pack(side="right")
        self.hardware=ttk.Label(root,text="正在检测编码能力…",style="Sub.TLabel"); self.hardware.pack(anchor="w",pady=3)
        f=ttk.LabelFrame(root,text=" ② 删除时间段（可选） ",style="Card.TLabelframe",padding=10); f.pack(fill="x",pady=5)
        r=ttk.Frame(f,style="Card.TFrame"); r.pack(fill="x"); ttk.Label(r,text="从",style="Card.TLabel").pack(side="left"); self.cut_start=tk.StringVar(); self.cut_end=tk.StringVar(); ttk.Entry(r,textvariable=self.cut_start,width=10).pack(side="left",padx=5); ttk.Label(r,text="秒 到",style="Card.TLabel").pack(side="left"); ttk.Entry(r,textvariable=self.cut_end,width=10).pack(side="left",padx=5); ttk.Label(r,text="秒删除",style="Card.TLabel").pack(side="left"); ttk.Button(r,text="添加",command=self.add_cut).pack(side="left",padx=8); ttk.Button(r,text="清空",command=self.clear_cuts).pack(side="left")
        self.cut_label=ttk.Label(f,text="未设置删除区间；删除后前后内容自动拼接",style="Card.TLabel"); self.cut_label.pack(anchor="w",pady=(7,0))
        self.duration_label=ttk.Label(f,text="视频时长：--",style="Card.TLabel"); self.duration_label.pack(anchor="w",pady=(3,0))
        f=ttk.LabelFrame(root,text=" ③ 压缩设置 ",style="Card.TLabelframe",padding=10); f.pack(fill="x",pady=5)
        left=ttk.Frame(f,style="Card.TFrame"); left.pack(side="left",fill="x",expand=True); right=ttk.Frame(f,style="Card.TFrame"); right.pack(side="left",fill="x",expand=True)
        self._combo(left,"压缩方案","preset",["高清","均衡","极致压缩"],"均衡"); self._combo(left,"编码格式","codec",["h265","h264","av1"],"h265"); self._combo(left,"输出帧率","fps",["智能","15","20","24","25","30","50","60"],"智能")
        self.width=tk.StringVar(); self.height=tk.StringVar(); self.keep=tk.BooleanVar(value=True); self.width.trace_add("write",lambda *_:self._size_changed("w")); self.height.trace_add("write",lambda *_:self._size_changed("h"))
        r=ttk.Frame(right,style="Card.TFrame"); r.pack(fill="x",pady=4); ttk.Label(r,text="分辨率",style="Card.TLabel",width=9).pack(side="left"); ttk.Entry(r,textvariable=self.width,width=8).pack(side="left"); ttk.Label(r,text=" × ",style="Card.TLabel").pack(side="left"); ttk.Entry(r,textvariable=self.height,width=8).pack(side="left"); ttk.Checkbutton(r,text="锁定比例",variable=self.keep).pack(side="left",padx=8); ttk.Button(r,text="原始尺寸",command=self.reset).pack(side="left")
        r=ttk.Frame(right,style="Card.TFrame"); r.pack(fill="x",pady=4); self.board=tk.BooleanVar(value=True); self.invert=tk.BooleanVar(value=False); ttk.Checkbutton(r,text="板书优化",variable=self.board).pack(side="left"); ttk.Checkbutton(r,text="智能反色（彩色不变）",variable=self.invert).pack(side="left",padx=12)
        self.out_dir=tk.StringVar(value="与原视频同目录"); r=ttk.Frame(right,style="Card.TFrame"); r.pack(fill="x",pady=4); ttk.Label(r,text="输出",style="Card.TLabel",width=9).pack(side="left"); ttk.Label(r,textvariable=self.out_dir,style="Card.TLabel").pack(side="left",fill="x",expand=True); ttk.Button(r,text="选择",command=self.choose_output).pack(side="right")
        f=ttk.LabelFrame(root,text=" ④ 预估与进度 ",style="Card.TLabelframe",padding=10); f.pack(fill="x",pady=5); self.estimate=ttk.Label(f,text="选择视频后自动显示",style="Card.TLabel"); self.estimate.pack(anchor="w"); self.analysis=ttk.Label(f,text="",style="Sub.TLabel"); self.analysis.pack(anchor="w",pady=3); self.progress=ttk.Progressbar(f,maximum=100,style="Modern.Horizontal.TProgressbar"); self.progress.pack(fill="x",pady=5); self.progress_text=ttk.Label(f,text="等待开始",style="Card.TLabel"); self.progress_text.pack(anchor="w")
        actions=ttk.Frame(root,style="App.TFrame"); actions.pack(fill="x",pady=8); self.start_btn=ttk.Button(actions,text="开始压缩",style="Primary.TButton",command=self.start); self.start_btn.pack(side="left"); self.stop_btn=ttk.Button(actions,text="停止",command=self.stop,state="disabled"); self.stop_btn.pack(side="left",padx=8); self.open_btn=ttk.Button(actions,text="打开输出目录",command=self.open_output,state="disabled"); self.open_btn.pack(side="left")
        self.log=tk.Text(root,height=8,bg="#f8fafc",fg="#334e68",relief="flat",font=("Menlo",9)); self.log.pack(fill="both",expand=True); self.write("等待选择视频…")
    def _combo(self,p,label,attr,values,default):
        r=ttk.Frame(p,style="Card.TFrame"); r.pack(fill="x",pady=4); ttk.Label(r,text=label,style="Card.TLabel",width=9).pack(side="left"); v=tk.StringVar(value=default); setattr(self,attr,v); ttk.Combobox(r,textvariable=v,values=values,state="readonly",width=16).pack(side="left")
    def write(self,t): self.log.insert("end",t+"\n"); self.log.see("end")
    def _hardware(self):
        try:
            enc=available_encoders(bundled_binary("ffmpeg")); self.hardware.config(text="编码器："+(", ".join(sorted(enc)) if enc else "CPU"))
        except Exception as e:self.hardware.config(text=f"编码检测失败：{e}")
    def choose(self):
        p=filedialog.askopenfilenames(title="选择视频",filetypes=[("视频文件",VIDEO_EXTS),("所有文件","*")])
        if not p:return
        self.files=list(p); self.cuts=[]; self._refresh_cuts(); self.file_label.config(text=f"已选择 {len(p)} 个视频：{Path(p[0]).name}" if len(p)==1 else f"已选择 {len(p)} 个视频：{Path(p[0]).name} 等"); self._load(Path(p[0]))
    def _load(self,p):
        try:
            info=probe(p,bundled_binary("ffprobe"),bundled_binary("ffmpeg")); self.src_info=info; v=next(s for s in info["streams"] if s.get("codec_type")=="video"); w,h=int(v["width"]),int(v["height"]); self.src_ratio=w/h; self.src_duration=float((info.get("format") or {}).get("duration") or 0); self._set_size(w,h); self.duration_label.config(text=f"视频时长：{self._fmt(self.src_duration)}"); self.write(f"检测成功：{w}×{h} · {self._fps(v):.1f} FPS · {self._fmt(self.src_duration)}"); self._estimate()
        except Exception as e:self.src_info=None; self.write(f"视频信息读取失败：{e}")
    def _set_size(self,w,h): self._updating=True; self.width.set(str(w)); self.height.set(str(h)); self._updating=False
    def _size_changed(self,which):
        if self._updating or not self.keep.get() or not self.src_ratio:return
        try:
            n=int(self.width.get() if which=="w" else self.height.get()); self._updating=True; (self.height.set(str(round(n/self.src_ratio))) if which=="w" else self.width.set(str(round(n*self.src_ratio)))); self._updating=False; self._estimate()
        except:pass
    def reset(self):
        if self.src_info:
            v=next(s for s in self.src_info["streams"] if s.get("codec_type")=="video"); self._set_size(int(v["width"]),int(v["height"])); self.keep.set(True); self._estimate()
    def choose_output(self):
        p=filedialog.askdirectory(title="选择输出目录");
        if p:self.out_dir.set(p)
    def add_cut(self):
        try:a=float(self.cut_start.get()); b=float(self.cut_end.get())
        except:messagebox.showwarning("删除时间段","请输入数字秒数，例如 120 和 150");return
        if not self.src_duration or a<0 or b<=a or b>self.src_duration:messagebox.showwarning("删除时间段",f"范围必须是 0～{self.src_duration:.1f} 秒，且结束时间大于开始时间");return
        self.cuts.append((a,b)); self.cuts.sort(); self.cut_start.set(""); self.cut_end.set(""); self._refresh_cuts()
    def clear_cuts(self):self.cuts=[]; self._refresh_cuts()
    def _refresh_cuts(self):self.cut_label.config(text="未设置删除区间；删除后前后内容自动拼接" if not self.cuts else "删除："+"、".join(f"{a:g}s–{b:g}s" for a,b in self.cuts)); self._estimate()
    def _fps(self,v):
        try:a,b=(v.get("avg_frame_rate") or v.get("r_frame_rate") or "30/1").split("/"); return float(a)/float(b) if float(b) else 30
        except:return 30
    def _target_fps(self,src):
        x=self.fps.get(); return 15 if x=="智能" and src>=45 else (20 if x=="智能" and src>=24 else (max(15,round(src)) if x=="智能" else int(x)))
    def _estimate(self):
        if not self.files or not self.src_info:return
        try:
            v=next(s for s in self.src_info["streams"] if s.get("codec_type")=="video"); sw,sh=int(v["width"]),int(v["height"]); sf=self._fps(v); tf=self._target_fps(sf); w=int(self.width.get()); h=int(self.height.get()); e=estimate_output_size(Path(self.files[0]).stat().st_size,sf,tf,sw,sh,w,h,self.codec.get(),PRESET_LABELS[self.preset.get()]); deleted=sum(b-a for a,b in self.cuts); self.estimate.config(text=f"预计输出：{format_bytes(e[0])} ～ {format_bytes(e[1])}"); self.analysis.config(text=f"{sw}×{sh} · {sf:.1f} FPS → {w}×{h} · {tf} FPS · 删除 {self._fmt(deleted)}")
        except:pass
    def start(self):
        if self.running:return
        if not self.files or not self.src_info:messagebox.showinfo("提示","请先选择并成功读取视频");return
        self.running=True; self.stop_requested=False; self.start_btn.config(state="disabled"); self.stop_btn.config(state="normal"); self.open_btn.config(state="disabled"); self.progress.config(value=0); threading.Thread(target=self._worker,daemon=True).start()
    def stop(self):
        self.stop_requested=True
        if self.current_process and self.current_process.poll() is None:
            try:self.current_process.terminate()
            except:pass
    def open_output(self):
        target=self.out_dir.get(); target=str(Path(self.files[0]).parent) if target=="与原视频同目录" else target
        try:
            if sys.platform.startswith("win"):os.startfile(target)
            elif sys.platform=="darwin":subprocess.Popen(["open",target])
            else:subprocess.Popen(["xdg-open",target])
        except Exception as e:messagebox.showerror("打开失败",str(e))
    def _worker(self):
        ffmpeg=bundled_binary("ffmpeg"); ffprobe=bundled_binary("ffprobe")
        try:
            info=probe(Path(self.files[0]),ffprobe,ffmpeg); v=next(s for s in info["streams"] if s.get("codec_type")=="video"); sf=self._fps(v); fps=self._target_fps(sf); encs=available_encoders(ffmpeg); c=self.codec.get(); enc={"h265":"hevc_qsv","h264":"h264_qsv","av1":"av1_qsv"}.get(c); enc=enc if enc in encs else {"h265":"libx265","h264":"libx264","av1":"libsvtav1"}[c]
        except Exception as e:self.events.put(("log",f"初始化失败：{e}")); self.events.put(("done",False)); return
        for i,src in enumerate(self.files,1):
            if self.stop_requested:break
            sp=Path(src); od=sp.parent if self.out_dir.get()=="与原视频同目录" else Path(self.out_dir.get()); od.mkdir(parents=True,exist_ok=True); out=od/f"{sp.stem}_压缩_{fps}fps.mp4"
            try:
                inf=probe(sp,ffprobe,ffmpeg); vv=next(s for s in inf["streams"] if s.get("codec_type")=="video"); duration=float((inf.get("format") or {}).get("duration") or 0); audio=any(s.get("codec_type")=="audio" for s in inf.get("streams",[])); cmd=build_command(sp,out,c,PRESET_LABELS[self.preset.get()],fps=fps,width=int(self.width.get()),height=int(self.height.get()),keep_aspect=self.keep.get(),invert="on" if self.invert.get() else "off",src_w=int(vv["width"]),src_h=int(vv["height"]),encoder=enc,ffmpeg=ffmpeg,board_optimized=self.board.get(),cuts=self.cuts if i==1 else [],duration=duration,has_audio=audio); self.write("开始："+sp.name); p=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding="utf-8",errors="replace",bufsize=1); self.current_process=p; last=""
                for line in p.stdout or []:
                    tm=TIME_RE.search(line); sm=SPEED_RE.search(line); line=line.strip()
                    if tm and duration:
                        cur=int(tm.group(1))*3600+int(tm.group(2))*60+float(tm.group(3)); self.events.put(("progress",min(100,cur/duration*100),f"{sm.group(1)}×" if sm else ""))
                    if line and ("error" in line.lower() or "failed" in line.lower()):last=line
                code=p.wait(); self.current_process=None
                if self.stop_requested:break
                if code==0 and out.exists() and out.stat().st_size>0:self.events.put(("log",f"完成：{out.name}")); self.events.put(("log",f"原视频 {format_bytes(sp.stat().st_size)} → {format_bytes(out.stat().st_size)}")); self.events.put(("open",))
                else:self.events.put(("log",f"压缩失败，FFmpeg 返回码 {code}：{last}"))
            except Exception as e:self.events.put(("log",f"处理失败：{e}"))
        self.events.put(("done",True))
    def _poll(self):
        try:
            while True:
                e=self.events.get_nowait(); k=e[0]
                if k=="log":self.write(e[1])
                elif k=="progress":self.progress.config(value=e[1]); self.progress_text.config(text=f"处理中 {e[1]:.0f}%  {e[2]}")
                elif k=="open":self.open_btn.config(state="normal")
                elif k=="done":self.running=False; self.start_btn.config(state="normal"); self.stop_btn.config(state="disabled"); self.progress_text.config(text="完成" if e[1] else "失败")
        except queue.Empty:pass
        self.after(100,self._poll)
    def _fmt(self,s):
        s=max(0,int(s)); h,s=divmod(s,3600); m,s=divmod(s,60); return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"

if __name__=="__main__":App().mainloop()
