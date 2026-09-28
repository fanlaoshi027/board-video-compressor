#!/usr/bin/env python3
"""樊老师板书视频压缩器 - Windows / macOS GUI。"""
from __future__ import annotations
import queue, re, subprocess, sys, threading
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from compress import build_command, probe, PRESETS, available_encoders, estimate_output_size, format_bytes
from gpu_detect import detect

PRESET_LABELS={"高清":"board-high","均衡":"board-balanced","极致压缩":"board-extreme"}
VIDEO_EXTS="*.mp4 *.avi *.mov *.mkv *.m4v *.webm *.wmv"
TIME_RE=re.compile(r"time=(\d+):(\d+):(\d+(?:\.\d+)?)")
SPEED_RE=re.compile(r"speed=\s*([0-9.]+)x")

def app_dir():
    return Path(getattr(sys,"_MEIPASS",Path(sys.executable).parent)) if getattr(sys,"frozen",False) else Path(__file__).resolve().parent

def bundled_binary(name):
    suffix=".exe" if sys.platform.startswith("win") else ""
    for p in (app_dir()/"bin"/f"{name}{suffix}",app_dir()/f"{name}{suffix}"):
        if p.exists(): return str(p)
    return name

def run_text(cmd,timeout=15):
    return subprocess.run(cmd,capture_output=True,text=True,encoding="utf-8",errors="replace",timeout=timeout)

def seconds_from_hms(h,m,s): return int(h)*3600+int(m)*60+float(s)

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("樊老师板书压缩器")
        self.geometry("900x790"); self.minsize(820,700); self.configure(bg="#f5f7fb")
        self.files=[]; self.events=queue.Queue(); self.running=False; self.stop_requested=False; self.current_process=None
        self.src_info=None; self.src_ratio=None; self.src_duration=0; self._updating_size=False; self.current_index=0; self.total_files=0
        self._style(); self._ui(); self._poll(); self.after(200,self._hardware)

    def _style(self):
        s=ttk.Style(self)
        try:s.theme_use("clam")
        except tk.TclError: pass
        s.configure("App.TFrame",background="#f5f7fb")
        s.configure("Card.TLabelframe",background="#ffffff",borderwidth=1,relief="solid")
        s.configure("Card.TLabelframe.Label",background="#ffffff",foreground="#18324a",font=("Arial",10,"bold"))
        s.configure("Card.TFrame",background="#ffffff")
        s.configure("Card.TLabel",background="#ffffff",foreground="#334e68",font=("Arial",10))
        s.configure("Title.TLabel",background="#f5f7fb",foreground="#102a43",font=("Arial",21,"bold"))
        s.configure("Sub.TLabel",background="#f5f7fb",foreground="#627d98",font=("Arial",10))
        s.configure("Primary.TButton",font=("Arial",10,"bold"),padding=(18,9))
        s.configure("Stop.TButton",font=("Arial",10,"bold"),padding=(18,9))
        s.configure("Modern.Horizontal.TProgressbar",thickness=9,troughcolor="#e7edf3",background="#1976d2",borderwidth=0)

    def _ui(self):
        root=ttk.Frame(self,style="App.TFrame",padding=(26,22)); root.pack(fill="both",expand=True)
        head=ttk.Frame(root,style="App.TFrame"); head.pack(fill="x")
        ttk.Label(head,text="樊老师板书压缩器",style="Title.TLabel").pack(anchor="w")
        ttk.Label(head,text="专为数学板书视频设计 · FFmpeg 内置 · Windows / macOS",style="Sub.TLabel").pack(anchor="w",pady=(3,15))

        files=ttk.LabelFrame(root,text=" ① 视频 ",style="Card.TLabelframe",padding=13); files.pack(fill="x",pady=(0,10))
        self.file_label=ttk.Label(files,text="选择一个或多个视频开始",style="Card.TLabel"); self.file_label.pack(side="left",fill="x",expand=True)
        ttk.Button(files,text="选择视频",command=self.choose).pack(side="right")
        self.hardware=ttk.Label(root,text="正在检测编码能力…",style="Sub.TLabel"); self.hardware.pack(anchor="w",pady=(0,9))

        settings=ttk.LabelFrame(root,text=" ② 压缩设置 ",style="Card.TLabelframe",padding=13); settings.pack(fill="x",pady=(0,10))
        left=ttk.Frame(settings,style="Card.TFrame"); left.pack(side="left",fill="both",expand=True,padx=(0,18))
        right=ttk.Frame(settings,style="Card.TFrame"); right.pack(side="left",fill="both",expand=True)
        self._combo(left,"压缩方案","preset",["高清","均衡","极致压缩"],"均衡")
        self._combo(left,"编码格式","codec",["h265","h264","av1"],"h265")
        self._combo(left,"输出帧率","fps",["智能","15","20","24","25","30","50","60"],"智能")
        self._combo(right,"输出目录","out_dir",[],"与原视频放在同一目录",combo_width=25)
        # Replace the output-directory combo with a compact button/label row.
        self.out_dir=tk.StringVar(value="与原视频放在同一目录")
        for child in right.winfo_children(): child.destroy()
        row=ttk.Frame(right,style="Card.TFrame"); row.pack(fill="x",pady=4)
        ttk.Label(row,text="输出目录",style="Card.TLabel",width=10).pack(side="left")
        ttk.Label(row,textvariable=self.out_dir,style="Card.TLabel").pack(side="left",fill="x",expand=True)
        ttk.Button(row,text="选择",command=self.output_dir).pack(side="right")
        r=ttk.Frame(right,style="Card.TFrame"); r.pack(fill="x",pady=4)
        ttk.Label(r,text="分辨率",style="Card.TLabel",width=10).pack(side="left")
        self.width=tk.StringVar(); self.height=tk.StringVar(); self.keep=tk.BooleanVar(value=True)
        self.width.trace_add("write",lambda *_:self._size_changed("width")); self.height.trace_add("write",lambda *_:self._size_changed("height")); self.keep.trace_add("write",lambda *_:self._lock_changed())
        ttk.Entry(r,textvariable=self.width,width=8).pack(side="left"); ttk.Label(r,text=" × ",style="Card.TLabel").pack(side="left"); ttk.Entry(r,textvariable=self.height,width=8).pack(side="left")
        ttk.Checkbutton(r,text="锁定比例",variable=self.keep).pack(side="left",padx=(9,0)); ttk.Button(r,text="原始尺寸",command=self.reset).pack(side="left",padx=(8,0))
        r=ttk.Frame(right,style="Card.TFrame"); r.pack(fill="x",pady=4)
        ttk.Label(r,text="画面优化",style="Card.TLabel",width=10).pack(side="left")
        self.board=tk.BooleanVar(value=True); ttk.Checkbutton(r,text="板书优化",variable=self.board).pack(side="left")
        self.invert=tk.BooleanVar(value=False); ttk.Checkbutton(r,text="智能反色（彩色保持原色）",variable=self.invert).pack(side="left",padx=(10,0))

        est=ttk.LabelFrame(root,text=" ③ 预估 ",style="Card.TLabelframe",padding=11); est.pack(fill="x",pady=(0,10))
        self.estimate=ttk.Label(est,text="选择视频后自动估算输出大小",style="Card.TLabel"); self.estimate.pack(anchor="w")
        self.analysis=ttk.Label(est,text="",style="Sub.TLabel"); self.analysis.pack(anchor="w",pady=(3,0))

        progress=ttk.LabelFrame(root,text=" ④ 处理进度 ",style="Card.TLabelframe",padding=11); progress.pack(fill="x",pady=(0,10))
        self.progress=ttk.Progressbar(progress,style="Modern.Horizontal.TProgressbar",mode="determinate",maximum=100,value=0); self.progress.pack(fill="x")
        meta=ttk.Frame(progress,style="Card.TFrame"); meta.pack(fill="x",pady=(6,0))
        self.progress_text=ttk.Label(meta,text="等待开始",style="Card.TLabel"); self.progress_text.pack(side="left")
        self.speed_text=ttk.Label(meta,text="",style="Card.TLabel"); self.speed_text.pack(side="right")

        actions=ttk.Frame(root,style="App.TFrame"); actions.pack(fill="x",pady=(0,10))
        self.start_btn=ttk.Button(actions,text="开始压缩",style="Primary.TButton",command=self.start); self.start_btn.pack(side="left")
        self.stop_btn=ttk.Button(actions,text="停止压缩",style="Stop.TButton",command=self.stop,state="disabled"); self.stop_btn.pack(side="left",padx=(8,0))

        logbox=ttk.LabelFrame(root,text=" ⑤ 处理结果 ",style="Card.TLabelframe",padding=9); logbox.pack(fill="both",expand=True)
        self.log=tk.Text(logbox,height=7,wrap="word",relief="flat",bg="#f8fafc",fg="#334e68",font=("Menlo",9),highlightthickness=0); self.log.pack(fill="both",expand=True)
        self.write("等待选择视频…")

    def _combo(self,parent,label,attr,values,default,combo_width=18):
        row=ttk.Frame(parent,style="Card.TFrame"); row.pack(fill="x",pady=4)
        ttk.Label(row,text=label,style="Card.TLabel",width=10).pack(side="left")
        var=tk.StringVar(value=default); setattr(self,attr,var)
        ttk.Combobox(row,textvariable=var,values=values,state="readonly",width=combo_width).pack(side="left")
        var.trace_add("write",lambda *_:self._refresh_estimate())

    def _hardware(self):
        ffmpeg=bundled_binary("ffmpeg")
        try:
            enc=detect(ffmpeg).get("recommended","libx265")
            label={"hevc_qsv":"Windows · Intel QSV（H.265）","av1_qsv":"Windows · Intel QSV（AV1）","hevc_videotoolbox":"macOS · VideoToolbox（HEVC）","libx265":"CPU x265"}.get(enc,enc)
            self.hardware.config(text=f"编码能力：{label}")
            if enc in ("hevc_qsv","hevc_videotoolbox"): self.codec.set("h265")
        except Exception as e:self.hardware.config(text=f"编码检测失败：{e}")

    def write(self,text):
        self.log.insert("end",text+"\n"); self.log.see("end")

    def choose(self):
        p=filedialog.askopenfilenames(title="选择视频",filetypes=[("视频文件",VIDEO_EXTS),("所有文件","*")])
        if p:
            self.files=list(p); self.total_files=len(p)
            self.file_label.config(text=f"已选择 {len(p)} 个视频：{Path(p[0]).name}"+(" 等" if len(p)>1 else "")); self._load(Path(p[0]))

    def _load(self,p):
        self.src_info=None; self.src_ratio=None; self.src_duration=0
        try:
            info=probe(p,bundled_binary("ffprobe")); self.src_info=info; v=next(s for s in info["streams"] if s.get("codec_type")=="video")
            w,h=int(v["width"]),int(v["height"]); self.src_ratio=w/h; self._set_size(w,h)
            self.src_duration=float(info.get("format",{}).get("duration") or 0)
            self.write(f"检测：{w}×{h} · {self._fps(v):.1f} FPS · {self.src_duration/60:.1f} 分钟 · {format_bytes(p.stat().st_size)}")
            self._refresh_estimate()
        except Exception as e:
            self.estimate.config(text="暂时无法估算：视频信息读取失败"); self.analysis.config(text="请检查 FFprobe/视频文件后重新选择"); self.write(f"视频信息读取失败：{e}")

    def _set_size(self,w,h):
        self._updating_size=True; self.width.set(str(w)); self.height.set(str(h)); self._updating_size=False; self._refresh_estimate()

    def _size_changed(self,changed):
        if self._updating_size or not self.keep.get() or not self.src_ratio:return
        try:
            value=int(self.width.get() if changed=="width" else self.height.get())
            if value<=0:return
            self._updating_size=True
            if changed=="width": self.height.set(str(max(2,round(value/self.src_ratio))))
            else: self.width.set(str(max(2,round(value*self.src_ratio))))
            self._updating_size=False; self._refresh_estimate()
        except ValueError: pass

    def _lock_changed(self):
        if self._updating_size or not self.keep.get() or not self.src_ratio:return
        try:
            value=int(self.width.get())
            if value>0:
                self._updating_size=True; self.height.set(str(max(2,round(value/self.src_ratio)))); self._updating_size=False
        except ValueError: pass
        self._refresh_estimate()

    def _fps(self,v):
        try:
            a,b=(v.get("avg_frame_rate") or v.get("r_frame_rate") or "30/1").split("/"); return float(a)/float(b) if float(b) else 30
        except:return 30

    def _selected_fps(self,src):
        if self.fps.get()=="智能": return 15 if src>=45 else (20 if src>=24 else max(15,round(src)))
        return int(self.fps.get())

    def _refresh_estimate(self):
        if not self.files or not self.src_info:return
        try:
            v=next(s for s in self.src_info["streams"] if s.get("codec_type")=="video"); sw,sh=int(v["width"]),int(v["height"]); sf=self._fps(v); tf=self._selected_fps(sf); w=int(self.width.get()); h=int(self.height.get())
            est=estimate_output_size(Path(self.files[0]).stat().st_size,sf,tf,sw,sh,w,h,self.codec.get(),PRESET_LABELS[self.preset.get()])
            self.estimate.config(text=f"预计输出：{format_bytes(est[0])} ～ {format_bytes(est[1])}")
            self.analysis.config(text=f"原始 {sw}×{sh} · {sf:.1f} FPS  →  目标 {w}×{h} · {tf} FPS · {self.codec.get().upper()}")
        except (ValueError,KeyError,ZeroDivisionError) as e:
            self.estimate.config(text=f"暂时无法估算：{e}"); self.analysis.config(text="请检查分辨率、帧率或编码设置")

    def reset(self):
        if self.src_info:
            v=next(s for s in self.src_info["streams"] if s.get("codec_type")=="video"); self._set_size(int(v["width"]),int(v["height"])); self.keep.set(True)

    def output_dir(self):
        p=filedialog.askdirectory(title="选择输出目录")
        if p:self.out_dir.set(p)

    def start(self):
        if self.running:return
        if not self.files:messagebox.showinfo("提示","请先选择视频。");return
        self.running=True; self.stop_requested=False; self.current_process=None; self.current_index=0
        self.start_btn.config(state="disabled"); self.stop_btn.config(state="normal"); self.progress.config(value=0); self.progress_text.config(text="准备压缩…"); self.speed_text.config(text="")
        threading.Thread(target=self._worker,daemon=True).start()

    def stop(self):
        if not self.running:return
        self.stop_requested=True
        p=self.current_process
        if p and p.poll() is None:
            self.progress_text.config(text="正在停止…")
            try:p.terminate()
            except OSError:pass

    def _validate_ffmpeg(self,ffmpeg):
        r=run_text([ffmpeg,"-hide_banner","-version"])
        if r.returncode!=0:raise RuntimeError(f"内置 FFmpeg 无法启动：{r.stderr.strip() or r.stdout.strip()}")
        return r.stdout.splitlines()[0] if r.stdout else "FFmpeg 可用"

    def _validate_output(self,out,ffprobe):
        if not out.exists():return False,"输出文件没有生成"
        if out.stat().st_size<=0:return False,"输出文件为 0 KB"
        try:
            info=probe(out,ffprobe); v=next(s for s in info.get("streams",[]) if s.get("codec_type")=="video")
            return True,f"有效视频：{v.get('width')}×{v.get('height')}"
        except Exception as e:return False,f"输出文件不是有效视频：{e}"

    def _worker(self):
        ffmpeg=bundled_binary("ffmpeg"); ffprobe=bundled_binary("ffprobe"); preset=PRESET_LABELS[self.preset.get()]; codec=self.codec.get(); success=0; failure=0; stopped=False
        try:
            self.events.put(("log",f"FFmpeg：{ffmpeg}")); self.events.put(("log",self._validate_ffmpeg(ffmpeg)))
            info=probe(Path(self.files[0]),ffprobe); v=next(s for s in info["streams"] if s.get("codec_type")=="video"); sf=self._fps(v); fps=self._selected_fps(sf); encs=available_encoders(ffmpeg)
            enc=None
            if codec=="h265":enc="hevc_qsv" if sys.platform.startswith("win") and "hevc_qsv" in encs else ("hevc_videotoolbox" if sys.platform=="darwin" and "hevc_videotoolbox" in encs else None)
            elif codec=="h264":enc="h264_qsv" if sys.platform.startswith("win") and "h264_qsv" in encs else ("h264_videotoolbox" if sys.platform=="darwin" and "h264_videotoolbox" in encs else None)
            elif codec=="av1" and sys.platform.startswith("win") and "av1_qsv" in encs:enc="av1_qsv"
            self.events.put(("log",f"可用编码器：{', '.join(sorted(encs)) or '未检测到'}")); self.events.put(("log",f"选择编码器：{enc or PRESETS[preset].get('preset','CPU')}"))
        except Exception as e:
            self.events.put(("log",f"初始化失败：{e}")); self.events.put(("done",0,1,True)); return

        for idx,src in enumerate(self.files,1):
            if self.stop_requested:stopped=True;break
            self.current_index=idx; sp=Path(src); od=sp.parent if self.out_dir.get()=="与原视频放在同一目录" else Path(self.out_dir.get()); od.mkdir(parents=True,exist_ok=True); out=od/f"{sp.stem}_压缩_{codec}_{fps}fps.mp4"
            try:
                if out.exists():out.unlink()
                inf=probe(sp,ffprobe); vv=next(s for s in inf["streams"] if s.get("codec_type")=="video"); duration=float(inf.get("format",{}).get("duration") or 0)
                cmd=build_command(sp,out,codec,preset,fps=fps,width=int(self.width.get()),height=int(self.height.get()),keep_aspect=self.keep.get(),invert="on" if self.invert.get() else "off",src_w=int(vv["width"]),src_h=int(vv["height"]),encoder=enc,ffmpeg=ffmpeg,board_optimized=self.board.get())
                self.events.put(("log",f"开始 {idx}/{len(self.files)}：{sp.name}")); self.events.put(("log","命令："+subprocess.list2cmdline(cmd)))
                p=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding="utf-8",errors="replace",bufsize=1)
                self.current_process=p; last_log=""
                for line in p.stdout or []:
                    line=line.strip()
                    tm=TIME_RE.search(line); sm=SPEED_RE.search(line)
                    if tm and duration>0:
                        current=seconds_from_hms(*tm.groups()); pct=max(0,min(100,current/duration*100)); speed=sm.group(1)+"×" if sm else ""
                        self.events.put(("progress",pct,current,duration,speed,idx,len(self.files)))
                    if line and ("Error" in line or "error" in line.lower() or "failed" in line.lower()): last_log=line
                code=p.wait(); self.current_process=None
                if self.stop_requested:
                    stopped=True
                    if out.exists():
                        try:out.unlink()
                        except OSError:pass
                    break
                valid,detail=self._validate_output(out,ffprobe)
                if code!=0 or not valid:
                    failure+=1; self.events.put(("log",f"失败：{sp.name}（FFmpeg 返回 {code}）")); self.events.put(("log",detail));
                    if last_log:self.events.put(("log",last_log))
                    if out.exists() and out.stat().st_size==0:out.unlink()
                else:
                    success+=1; before=sp.stat().st_size; after=out.stat().st_size; self.events.put(("progress",100,duration,duration,"完成",idx,len(self.files))); self.events.put(("log",f"完成：{out.name}")); self.events.put(("log",f"原视频 {format_bytes(before)} → {format_bytes(after)} · 节省 {(before-after)/before*100:.1f}%"))
            except Exception as e:
                failure+=1; self.events.put(("log",f"错误：{sp.name}：{e}"))
                if out.exists() and out.stat().st_size==0:
                    try:out.unlink()
                    except OSError:pass
        self.events.put(("done",success,failure,stopped))

    def _poll(self):
        try:
            while True:
                event=self.events.get_nowait(); kind=event[0]
                if kind=="log":self.write(event[1])
                elif kind=="progress":
                    _,pct,current,total,speed,idx,count=event; self.progress.config(value=pct); self.progress_text.config(text=f"{idx}/{count}  {self._fmt_time(current)} / {self._fmt_time(total)}  ·  {pct:.0f}%"); self.speed_text.config(text=f"{speed}" if speed else "")
                elif kind=="done":
                    ok,bad,stopped=event[1:]; self.running=False; self.current_process=None; self.start_btn.config(state="normal"); self.stop_btn.config(state="disabled")
                    if stopped:
                        self.progress_text.config(text="已停止"); self.speed_text.config(text=""); self.write("已停止压缩，未完成文件已清理。")
                    elif bad==0 and ok>0:
                        self.progress.config(value=100); self.progress_text.config(text="全部完成 · 100%"); self.speed_text.config(text=""); self.write(f"全部处理完成：{ok} 个视频。")
                    else:
                        self.progress_text.config(text="处理完成，但有失败项目"); self.speed_text.config(text=""); self.write(f"处理完成：成功 {ok} 个，失败 {bad} 个。")
        except queue.Empty:pass
        self.after(80,self._poll)

    def _fmt_time(self,seconds):
        seconds=max(0,int(seconds)); h,rem=divmod(seconds,3600); m,s=divmod(rem,60); return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"

    def write(self,text):
        self.log.insert("end",text+"\n"); self.log.see("end")

    def _close(self):
        if self.running:
            if not messagebox.askyesno("正在压缩","当前视频还在压缩，确定停止并退出吗？"):return
            self.stop_requested=True
            if self.current_process and self.current_process.poll() is None:
                try:self.current_process.terminate()
                except OSError:pass
        self.destroy()

if __name__=="__main__":
    app=App(); app.protocol("WM_DELETE_WINDOW",app._close); app.mainloop()
