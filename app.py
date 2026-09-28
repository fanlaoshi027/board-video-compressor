#!/usr/bin/env python3
"""樊老师板书压缩器 - Windows / macOS GUI。"""
from __future__ import annotations
import json, queue, subprocess, sys, threading
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from compress import build_command, probe, PRESETS, available_encoders, estimate_output_size, format_bytes
from gpu_detect import detect

PRESET_LABELS={"高清":"board-high","均衡":"board-balanced","极致压缩":"board-extreme"}
VIDEO_EXTS="*.mp4 *.avi *.mov *.mkv *.m4v *.webm *.wmv"

def app_dir():
    return Path(getattr(sys,"_MEIPASS",Path(sys.executable).parent)) if getattr(sys,"frozen",False) else Path(__file__).resolve().parent

def bundled_binary(name):
    suffix=".exe" if sys.platform.startswith("win") else ""
    candidates=[app_dir()/"bin"/f"{name}{suffix}",app_dir()/f"{name}{suffix}"]
    for p in candidates:
        if p.exists():
            return str(p)
    return name

def run_text(cmd,timeout=15):
    return subprocess.run(cmd,capture_output=True,text=True,encoding="utf-8",errors="replace",timeout=timeout)

class App(tk.Tk):
    def __init__(self):
        super().__init__(); self.title("樊老师板书压缩器"); self.geometry("820x820"); self.minsize(760,720); self.configure(bg="#f6f8fb")
        self.files=[]; self.events=queue.Queue(); self.running=False; self.src_info=None; self.src_ratio=None; self._updating_size=False
        self._style(); self._ui(); self._poll(); self.after(200,self._hardware)

    def _style(self):
        s=ttk.Style(self)
        try:s.theme_use("clam")
        except tk.TclError:pass
        s.configure("Title.TLabel",font=("Arial",22,"bold"),background="#f6f8fb",foreground="#102a43")
        s.configure("Sub.TLabel",font=("Arial",11),background="#f6f8fb",foreground="#627d98")
        s.configure("Card.TLabelframe",background="#fff",borderwidth=1,relief="solid")
        s.configure("Card.TLabelframe.Label",background="#fff",foreground="#102a43",font=("Arial",11,"bold"))
        s.configure("Card.TFrame",background="#fff")
        s.configure("Card.TLabel",background="#fff",foreground="#243b53",font=("Arial",11))
        s.configure("Primary.TButton",font=("Arial",11,"bold"),padding=(18,10))

    def _ui(self):
        root=ttk.Frame(self,padding=28); root.pack(fill="both",expand=True)
        ttk.Label(root,text="樊老师板书压缩器",style="Title.TLabel").pack(anchor="w")
        ttk.Label(root,text="专为数学板书录课视频设计 · Windows / macOS · FFmpeg内置",style="Sub.TLabel").pack(anchor="w",pady=(4,18))
        fb=ttk.LabelFrame(root,text=" ① 视频文件 ",style="Card.TLabelframe",padding=16); fb.pack(fill="x")
        self.file_label=ttk.Label(fb,text="支持 MP4 / AVI / MOV / MKV 等格式",style="Card.TLabel"); self.file_label.pack(side="left",fill="x",expand=True); ttk.Button(fb,text="选择视频",command=self.choose).pack(side="right")
        self.hardware=ttk.Label(root,text="正在检测编码能力……",style="Sub.TLabel"); self.hardware.pack(anchor="w",pady=(8,0))
        st=ttk.LabelFrame(root,text=" ② 压缩设置 ",style="Card.TLabelframe",padding=16); st.pack(fill="x",pady=14)
        self._combo(st,"方案","preset",["高清","均衡","极致压缩"],"均衡"); self._combo(st,"编码","codec",["h265","h264","av1"],"h265"); self._combo(st,"输出帧率","fps",["智能","15","20","24","25","30","50","60"],"智能")
        r=ttk.Frame(st,style="Card.TFrame"); r.pack(fill="x",pady=5); ttk.Label(r,text="分辨率",style="Card.TLabel",width=12).pack(side="left")
        self.width=tk.StringVar(); self.height=tk.StringVar(); self.keep=tk.BooleanVar(value=True)
        self.width.trace_add("write",lambda *_:self._size_changed("width")); self.height.trace_add("write",lambda *_:self._size_changed("height")); self.keep.trace_add("write",lambda *_:self._lock_changed())
        ttk.Entry(r,textvariable=self.width,width=9).pack(side="left"); ttk.Label(r,text=" × ",style="Card.TLabel").pack(side="left"); ttk.Entry(r,textvariable=self.height,width=9).pack(side="left")
        ttk.Checkbutton(r,text="锁定比例",variable=self.keep).pack(side="left",padx=(12,0)); ttk.Button(r,text="原始尺寸",command=self.reset).pack(side="left",padx=(12,0))
        r=ttk.Frame(st,style="Card.TFrame"); r.pack(fill="x",pady=5); ttk.Label(r,text="画面优化",style="Card.TLabel",width=12).pack(side="left")
        self.board=tk.BooleanVar(value=True); ttk.Checkbutton(r,text="板书优化",variable=self.board).pack(side="left"); self.invert=tk.BooleanVar(value=False); ttk.Checkbutton(r,text="智能反色（彩色笔迹保持原色）",variable=self.invert).pack(side="left",padx=(14,0))
        r=ttk.Frame(st,style="Card.TFrame"); r.pack(fill="x",pady=5); ttk.Label(r,text="输出目录",style="Card.TLabel",width=12).pack(side="left"); self.out_dir=tk.StringVar(value="与原视频放在同一目录"); ttk.Label(r,textvariable=self.out_dir,style="Card.TLabel").pack(side="left",fill="x",expand=True); ttk.Button(r,text="选择目录",command=self.output_dir).pack(side="right")
        est=ttk.LabelFrame(root,text=" ③ 压缩预估 ",style="Card.TLabelframe",padding=14); est.pack(fill="x",pady=(0,14)); self.estimate=ttk.Label(est,text="选择视频后自动估算输出大小",style="Card.TLabel"); self.estimate.pack(anchor="w"); self.analysis=ttk.Label(est,text="",style="Sub.TLabel"); self.analysis.pack(anchor="w",pady=(4,0))
        action=ttk.Frame(root); action.pack(fill="x",pady=(4,12)); self.start_btn=ttk.Button(action,text="开始压缩",style="Primary.TButton",command=self.start); self.start_btn.pack(side="left"); self.progress=ttk.Progressbar(action,mode="indeterminate"); self.progress.pack(side="left",fill="x",expand=True,padx=(16,0))
        lb=ttk.LabelFrame(root,text=" ④ 处理结果 ",style="Card.TLabelframe",padding=10); lb.pack(fill="both",expand=True); self.log=tk.Text(lb,height=10,wrap="word",relief="flat",bg="#f8fafc",fg="#334e68",font=("Menlo",10)); self.log.pack(fill="both",expand=True); self.write("等待选择视频……")

    def _combo(self,parent,label,attr,values,default):
        row=ttk.Frame(parent,style="Card.TFrame"); row.pack(fill="x",pady=5); ttk.Label(row,text=label,style="Card.TLabel",width=12).pack(side="left"); var=tk.StringVar(value=default); setattr(self,attr,var); ttk.Combobox(row,textvariable=var,values=values,state="readonly",width=18).pack(side="left"); var.trace_add("write",lambda *_:self._refresh_estimate())

    def _hardware(self):
        ffmpeg=bundled_binary("ffmpeg")
        try:
            enc=detect(ffmpeg).get("recommended","libx265")
            label={"hevc_qsv":"Windows · Intel QSV（H.265）","av1_qsv":"Windows · Intel QSV（AV1）","hevc_videotoolbox":"macOS · VideoToolbox（HEVC）","libx265":"CPU x265"}.get(enc,enc)
            self.hardware.config(text=f"编码能力：{label} · FFmpeg：{ffmpeg}")
            if enc in ("hevc_qsv","hevc_videotoolbox"):self.codec.set("h265")
        except Exception as e:self.hardware.config(text=f"编码检测失败：{e}")

    def write(self,t):self.log.insert("end",t+"\n");self.log.see("end")

    def choose(self):
        p=filedialog.askopenfilenames(title="选择视频",filetypes=[("视频文件",VIDEO_EXTS),("所有文件","*")])
        if p:self.files=list(p);self.file_label.config(text=f"已选择 {len(p)} 个视频：{Path(p[0]).name}"+(" 等" if len(p)>1 else ""));self._load(Path(p[0]))

    def _load(self,p):
        self.src_info=None; self.src_ratio=None
        try:
            info=probe(p,bundled_binary("ffprobe")); self.src_info=info; v=next(s for s in info["streams"] if s.get("codec_type")=="video"); w,h=int(v["width"]),int(v["height"]); self.src_ratio=w/h
            self._set_size(w,h); d=float(info.get("format",{}).get("duration") or 0); self.write(f"检测：{w}×{h} · {self._fps(v):.1f} FPS · {d/60:.1f} 分钟 · {format_bytes(p.stat().st_size)}"); self._refresh_estimate()
        except Exception as e:
            self.estimate.config(text="暂时无法估算：视频信息读取失败"); self.analysis.config(text="请检查 FFprobe/视频文件，然后重新选择视频"); self.write(f"视频信息读取失败：{e}")

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
            if value>0:self._updating_size=True; self.height.set(str(max(2,round(value/self.src_ratio)))); self._updating_size=False
        except ValueError: pass
        self._refresh_estimate()

    def _fps(self,v):
        try:a,b=(v.get("avg_frame_rate") or v.get("r_frame_rate") or "30/1").split("/");return float(a)/float(b) if float(b) else 30
        except:return 30

    def _selected_fps(self,src):return 15 if self.fps.get()=="智能" and src>=45 else (20 if self.fps.get()=="智能" and src>=24 else (max(15,round(src)) if self.fps.get()=="智能" else int(self.fps.get())))

    def _refresh_estimate(self):
        if not self.files or not self.src_info:return
        try:
            v=next(s for s in self.src_info["streams"] if s.get("codec_type")=="video"); sw,sh=int(v["width"]),int(v["height"]); sf=self._fps(v); tf=self._selected_fps(sf); w=int(self.width.get()); h=int(self.height.get()); est=estimate_output_size(Path(self.files[0]).stat().st_size,sf,tf,sw,sh,w,h,self.codec.get(),PRESET_LABELS[self.preset.get()]); self.estimate.config(text=f"预计输出：{format_bytes(est[0])} ～ {format_bytes(est[1])}（实际大小以压缩结果为准）"); self.analysis.config(text=f"原始：{sw}×{sh} · {sf:.1f} FPS → 目标：{w}×{h} · {tf} FPS · {self.codec.get().upper()}")
        except (ValueError,KeyError,ZeroDivisionError) as e:
            self.estimate.config(text=f"暂时无法估算：{e}"); self.analysis.config(text="请检查分辨率、帧率或编码设置")

    def reset(self):
        if self.files and self.src_info:
            v=next(s for s in self.src_info["streams"] if s.get("codec_type")=="video"); self._set_size(int(v["width"]),int(v["height"])); self.keep.set(True); self._refresh_estimate()

    def output_dir(self):
        p=filedialog.askdirectory(title="选择输出目录")
        if p:self.out_dir.set(p)

    def start(self):
        if self.running:return
        if not self.files:messagebox.showinfo("提示","请先选择视频。");return
        self.running=True;self.start_btn.config(state="disabled");self.progress.start(10);threading.Thread(target=self._worker,daemon=True).start()

    def _validate_ffmpeg(self,ffmpeg):
        r=run_text([ffmpeg,"-hide_banner","-version"])
        if r.returncode!=0: raise RuntimeError(f"内置 FFmpeg 无法启动：{r.stderr.strip() or r.stdout.strip()}")
        return r.stdout.splitlines()[0] if r.stdout else "FFmpeg 可用"

    def _validate_output(self,out,ffprobe):
        if not out.exists(): return False,"输出文件没有生成"
        size=out.stat().st_size
        if size<=0:return False,"输出文件为 0 KB"
        try:
            info=probe(out,ffprobe); v=next(s for s in info.get("streams",[]) if s.get("codec_type")=="video")
            return True,f"有效 MP4：{v.get('width')}×{v.get('height')}"
        except Exception as e:return False,f"输出文件不是有效视频：{e}"

    def _worker(self):
        ffmpeg=bundled_binary("ffmpeg");ffprobe=bundled_binary("ffprobe");preset=PRESET_LABELS[self.preset.get()]; success_count=0; failure_count=0
        try:
            self.events.put(f"FFmpeg：{ffmpeg}"); self.events.put(self._validate_ffmpeg(ffmpeg))
            info=probe(Path(self.files[0]),ffprobe);v=next(s for s in info["streams"] if s.get("codec_type")=="video");sf=self._fps(v);fps=self._selected_fps(sf);encs=available_encoders(ffmpeg);codec=self.codec.get();enc=None
            self.events.put(f"可用编码器：{', '.join(sorted(encs)) or '未检测到'}")
            if codec=="h265":enc="hevc_qsv" if sys.platform.startswith("win") and "hevc_qsv" in encs else ("hevc_videotoolbox" if sys.platform=="darwin" and "hevc_videotoolbox" in encs else None)
            elif codec=="h264":enc="h264_qsv" if sys.platform.startswith("win") and "h264_qsv" in encs else ("h264_videotoolbox" if sys.platform=="darwin" and "h264_videotoolbox" in encs else None)
            elif codec=="av1" and sys.platform.startswith("win") and "av1_qsv" in encs:enc="av1_qsv"
            self.events.put(f"选择编码器：{enc or PRESETS[preset].get('preset','CPU')}")
        except Exception as e:self.events.put(f"初始化失败：{e}");self.events.put("__DONE__");return
        for src in self.files:
            sp=Path(src);od=sp.parent if self.out_dir.get()=="与原视频放在同一目录" else Path(self.out_dir.get());od.mkdir(parents=True,exist_ok=True);out=od/f"{sp.stem}_压缩_{codec}_{fps}fps.mp4"
            try:
                if out.exists():out.unlink()
                inf=probe(sp,ffprobe);vv=next(s for s in inf["streams"] if s.get("codec_type")=="video")
                cmd=build_command(sp,out,codec,preset,fps=fps,width=int(self.width.get()),height=int(self.height.get()),keep_aspect=self.keep.get(),invert="on" if self.invert.get() else "off",src_w=int(vv["width"]),src_h=int(vv["height"]),encoder=enc,ffmpeg=ffmpeg,board_optimized=self.board.get())
                self.events.put(f"开始：{sp.name} → {out.name}"); self.events.put("命令："+subprocess.list2cmdline(cmd))
                p=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding="utf-8",errors="replace")
                for line in p.stdout or []:
                    if line.strip():self.events.put(line.strip())
                code=p.wait(); valid,detail=self._validate_output(out,ffprobe)
                if code!=0 or not valid:
                    failure_count+=1
                    self.events.put(f"失败：{sp.name}（FFmpeg 返回 {code}）")
                    self.events.put(detail)
                    if out.exists() and out.stat().st_size==0:out.unlink()
                else:
                    success_count+=1;before=sp.stat().st_size;after=out.stat().st_size;self.events.put(f"完成：{out.name}");self.events.put(f"原视频：{format_bytes(before)} → 压缩后：{format_bytes(after)} → 节省：{format_bytes(max(0,before-after))}（{(before-after)/before*100:.1f}%）")
            except Exception as e:
                failure_count+=1;self.events.put(f"错误：{sp.name}：{e}")
                if out.exists() and out.stat().st_size==0:
                    try:out.unlink()
                    except OSError:pass
        self.events.put(f"__SUMMARY__{success_count}__{failure_count}")
        self.events.put("__DONE__")

    def _poll(self):
        try:
            while True:
                m=self.events.get_nowait()
                if m.startswith("__SUMMARY__"):
                    _,ok,bad=m.split("__");self.summary=(int(ok),int(bad))
                elif m=="__DONE__":
                    self.running=False;self.start_btn.config(state="normal");self.progress.stop();ok,bad=getattr(self,"summary",(0,1));
                    if bad==0 and ok>0:messagebox.showinfo("完成",f"成功处理 {ok} 个视频。")
                    else:messagebox.showerror("压缩失败",f"成功：{ok} 个，失败：{bad} 个。请查看处理结果中的 FFmpeg 错误信息。")
                else:self.write(m)
        except queue.Empty:pass
        self.after(100,self._poll)

if __name__=="__main__":App().mainloop()
