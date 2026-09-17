#!/usr/bin/env python3
"""樊老师板书压缩器 - Windows / macOS 图形界面。"""
from __future__ import annotations
import os, queue, subprocess, sys, threading
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from compress import build_command, probe, PRESETS, available_encoders
from gpu_detect import detect

PRESET_LABELS = {"高清":"board-high", "均衡":"board-balanced", "极致压缩":"board-extreme"}
VIDEO_EXTS = "*.mp4 *.avi *.mov *.mkv *.m4v *.webm *.wmv"


def app_dir() -> Path:
    if getattr(sys, "frozen", False): return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent


def bundled_binary(name: str) -> str:
    suffix = ".exe" if sys.platform.startswith("win") else ""
    candidate = app_dir()/"bin"/f"{name}{suffix}"
    return str(candidate) if candidate.exists() else name


class App(tk.Tk):
    def __init__(self):
        super().__init__(); self.title("樊老师板书压缩器"); self.geometry("800x720"); self.minsize(740,650); self.configure(bg="#f6f8fb")
        self.files=[]; self.events=queue.Queue(); self.running=False; self.src_ratio=None
        self._build_style(); self._build_ui(); self._poll_events()
        self.after(200, self._detect_hardware)

    def _build_style(self):
        s=ttk.Style(self)
        try:s.theme_use("clam")
        except tk.TclError:pass
        s.configure("Title.TLabel",font=("Arial",22,"bold"),background="#f6f8fb",foreground="#102a43")
        s.configure("Sub.TLabel",font=("Arial",11),background="#f6f8fb",foreground="#627d98")
        s.configure("Card.TLabelframe",background="#fff",borderwidth=1,relief="solid")
        s.configure("Card.TLabelframe.Label",background="#fff",foreground="#102a43",font=("Arial",11,"bold"))
        s.configure("Card.TFrame",background="#fff"); s.configure("Card.TLabel",background="#fff",foreground="#243b53",font=("Arial",11)); s.configure("Primary.TButton",font=("Arial",11,"bold"),padding=(18,10))

    def _build_ui(self):
        root=ttk.Frame(self,padding=28); root.pack(fill="both",expand=True)
        ttk.Label(root,text="樊老师板书压缩器",style="Title.TLabel").pack(anchor="w")
        ttk.Label(root,text="专为数学板书录课视频设计 · Windows / macOS · FFmpeg内置",style="Sub.TLabel").pack(anchor="w",pady=(4,18))
        fb=ttk.LabelFrame(root,text=" ① 视频文件 ",style="Card.TLabelframe",padding=16); fb.pack(fill="x")
        self.file_label=ttk.Label(fb,text="支持 MP4 / AVI / MOV / MKV 等格式",style="Card.TLabel"); self.file_label.pack(side="left",fill="x",expand=True)
        ttk.Button(fb,text="选择视频",command=self.choose_files).pack(side="right")
        self.hardware=ttk.Label(root,text="正在检测编码能力……",style="Sub.TLabel"); self.hardware.pack(anchor="w",pady=(8,0))
        settings=ttk.LabelFrame(root,text=" ② 压缩设置 ",style="Card.TLabelframe",padding=16); settings.pack(fill="x",pady=14)
        self._combo_row(settings,"方案","preset",["高清","均衡","极致压缩"],"均衡")
        self._combo_row(settings,"编码","codec",["h265","h264","av1"],"h265")
        self._combo_row(settings,"输出帧率","fps",["智能","15","20","24","25","30","50","60"],"智能")
        r=ttk.Frame(settings,style="Card.TFrame"); r.pack(fill="x",pady=5)
        ttk.Label(r,text="分辨率",style="Card.TLabel",width=12).pack(side="left")
        self.width=tk.StringVar(); self.height=tk.StringVar(); self.keep=tk.BooleanVar(value=True)
        ttk.Entry(r,textvariable=self.width,width=9).pack(side="left"); ttk.Label(r,text=" × ",style="Card.TLabel").pack(side="left"); ttk.Entry(r,textvariable=self.height,width=9).pack(side="left")
        ttk.Checkbutton(r,text="锁定比例",variable=self.keep).pack(side="left",padx=(12,0))
        ttk.Button(r,text="原始尺寸",command=self.reset_size).pack(side="left",padx=(12,0))
        r=ttk.Frame(settings,style="Card.TFrame"); r.pack(fill="x",pady=5)
        ttk.Label(r,text="画面优化",style="Card.TLabel",width=12).pack(side="left")
        self.board=tk.BooleanVar(value=True); ttk.Checkbutton(r,text="板书优化",variable=self.board).pack(side="left")
        self.invert=tk.BooleanVar(value=False); ttk.Checkbutton(r,text="智能反色（彩色笔迹保持原色）",variable=self.invert).pack(side="left",padx=(14,0))
        r=ttk.Frame(settings,style="Card.TFrame"); r.pack(fill="x",pady=5)
        ttk.Label(r,text="输出目录",style="Card.TLabel",width=12).pack(side="left")
        self.out_dir=tk.StringVar(value="与原视频放在同一目录"); ttk.Label(r,textvariable=self.out_dir,style="Card.TLabel").pack(side="left",fill="x",expand=True); ttk.Button(r,text="选择目录",command=self.choose_output).pack(side="right")
        action=ttk.Frame(root); action.pack(fill="x",pady=(4,12)); self.start_btn=ttk.Button(action,text="开始压缩",style="Primary.TButton",command=self.start); self.start_btn.pack(side="left"); self.progress=ttk.Progressbar(action,mode="indeterminate"); self.progress.pack(side="left",fill="x",expand=True,padx=(16,0))
        lb=ttk.LabelFrame(root,text=" ③ 处理状态 ",style="Card.TLabelframe",padding=10); lb.pack(fill="both",expand=True); self.log=tk.Text(lb,height=10,wrap="word",relief="flat",bg="#f8fafc",fg="#334e68",font=("Menlo",10)); self.log.pack(fill="both",expand=True); self.write("等待选择视频……")

    def _combo_row(self,parent,label,attr,values,default):
        row=ttk.Frame(parent,style="Card.TFrame"); row.pack(fill="x",pady=5); ttk.Label(row,text=label,style="Card.TLabel",width=12).pack(side="left"); var=tk.StringVar(value=default); setattr(self,attr,var); ttk.Combobox(row,textvariable=var,values=values,state="readonly",width=18).pack(side="left")

    def _detect_hardware(self):
        ffmpeg=bundled_binary("ffmpeg"); info=detect(ffmpeg); self.hw=info; enc=info.get("recommended","libx265")
        label={"hevc_qsv":"Windows · Intel QSV（优先 H.265）","av1_qsv":"Windows · Intel QSV（优先 AV1）","hevc_videotoolbox":"macOS · VideoToolbox（优先 HEVC）","libx265":"CPU x265"}.get(enc,enc)
        self.hardware.config(text=f"编码能力：{label}")
        if enc in ("hevc_qsv","hevc_videotoolbox"):
            self.codec.set("h265")

    def write(self,text): self.log.insert("end",text+"\n"); self.log.see("end")

    def choose_files(self):
        paths=filedialog.askopenfilenames(title="选择视频",filetypes=[("视频文件",VIDEO_EXTS),("所有文件","*")])
        if paths:
            self.files=list(paths); self.file_label.config(text=f"已选择 {len(self.files)} 个视频：{Path(self.files[0]).name}"+(" 等" if len(self.files)>1 else "")); self._load_dimensions(Path(self.files[0]))

    def _load_dimensions(self,path):
        try:
            info=probe(path,bundled_binary("ffprobe")); v=next(s for s in info["streams"] if s.get("codec_type")=="video"); w,h=int(v["width"]),int(v["height"]); self.src_ratio=w/h; self.width.set(str(w)); self.height.set(str(h)); self.write(f"检测：{w}×{h}，输入格式：{path.suffix.lower()}")
        except Exception as e:self.write(f"视频信息读取失败：{e}")

    def reset_size(self):
        if self.files:self._load_dimensions(Path(self.files[0]))

    def choose_output(self):
        p=filedialog.askdirectory(title="选择输出目录")
        if p:self.out_dir.set(p)

    def start(self):
        if self.running:return
        if not self.files: messagebox.showinfo("提示","请先选择视频。"); return
        self.running=True; self.start_btn.config(state="disabled"); self.progress.start(10); threading.Thread(target=self._worker,daemon=True).start()

    def _worker(self):
        preset_name=PRESET_LABELS[self.preset.get()]; fps=PRESETS[preset_name]["fps"] if self.fps.get()=="智能" else int(self.fps.get()); ffmpeg=bundled_binary("ffmpeg"); ffprobe=bundled_binary("ffprobe")
        try:
            encs=available_encoders(ffmpeg)
            codec=self.codec.get(); encoder=None
            if codec=="h265":
                if sys.platform.startswith("win") and "hevc_qsv" in encs: encoder="hevc_qsv"
                elif sys.platform=="darwin" and "hevc_videotoolbox" in encs: encoder="hevc_videotoolbox"
            elif codec=="h264":
                if sys.platform.startswith("win") and "h264_qsv" in encs: encoder="h264_qsv"
                elif sys.platform=="darwin" and "h264_videotoolbox" in encs: encoder="h264_videotoolbox"
            elif codec=="av1" and sys.platform.startswith("win") and "av1_qsv" in encs: encoder="av1_qsv"
        except Exception: encoder=None
        width=int(self.width.get()) if self.width.get().isdigit() else None; height=int(self.height.get()) if self.height.get().isdigit() else None
        for src in self.files:
            src_path=Path(src); out_dir=src_path.parent if self.out_dir.get()=="与原视频放在同一目录" else Path(self.out_dir.get()); out_dir.mkdir(parents=True,exist_ok=True); output=out_dir/f"{src_path.stem}_压缩_{codec}_{fps}fps.mp4"
            try:
                info=probe(src_path,ffprobe); v=next((s for s in info.get("streams",[]) if s.get("codec_type")=="video"),None)
                if not v:raise RuntimeError("没有找到视频流")
                sw,sh=int(v.get("width") or 0),int(v.get("height") or 0)
                cmd=build_command(src_path,output,codec,preset_name,fps=fps,width=width,height=height,keep_aspect=self.keep.get(),invert="on" if self.invert.get() else "off",src_w=sw,src_h=sh,encoder=encoder,ffmpeg=ffmpeg)
                self.events.put(f"开始：{src_path.name} → {output.name}（编码器：{cmd[cmd.index('-c:v')+1]}）")
                p=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding="utf-8",errors="replace"); assert p.stdout
                for line in p.stdout:
                    if line.strip():self.events.put(line.strip())
                code=p.wait(); self.events.put(f"失败：{src_path.name}" if code else f"完成：{output.name}")
            except Exception as e:self.events.put(f"错误：{src_path.name}：{e}")
        self.events.put("__DONE__")

    def _poll_events(self):
        try:
            while True:
                msg=self.events.get_nowait()
                if msg=="__DONE__":self.running=False; self.start_btn.config(state="normal"); self.progress.stop(); messagebox.showinfo("完成","视频处理完成。")
                else:self.write(msg)
        except queue.Empty:pass
        self.after(100,self._poll_events)

if __name__=="__main__":App().mainloop()
