#!/usr/bin/env python3
from __future__ import annotations
import os, subprocess, sys, threading
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from board_analyzer import analyze_video, analysis_summary
from smart_runner import build_smart_command

class SmartBoardGUI(tk.Tk):
    def __init__(self):
        super().__init__(); self.title("樊老师板书视频压缩器"); self.geometry("860x700"); self.minsize(780,620)
        self.video=None; self.result=None; self.process=None; self.running=False; self._build()
    def _build(self):
        outer=ttk.Frame(self,padding=20); outer.pack(fill="both",expand=True)
        ttk.Label(outer,text="樊老师板书视频压缩器",font=("Arial",21,"bold")).pack(anchor="w")
        ttk.Label(outer,text="白底黑字 · 局部书写 · 智能可变帧率 · Windows / macOS",foreground="#627d98").pack(anchor="w",pady=(2,14))
        row=ttk.Frame(outer); row.pack(fill="x"); ttk.Button(row,text="选择视频",command=self.choose).pack(side="left"); self.file_label=ttk.Label(row,text="尚未选择视频"); self.file_label.pack(side="left",padx=12)
        box=ttk.LabelFrame(outer,text="板书分析",padding=12); box.pack(fill="x",pady=12); self.analysis_label=ttk.Label(box,text="选择视频后自动分析"); self.analysis_label.pack(anchor="w"); self.detail_label=ttk.Label(box,text="",foreground="#627d98"); self.detail_label.pack(anchor="w",pady=(6,0))
        settings=ttk.LabelFrame(outer,text="输出设置",padding=12); settings.pack(fill="x")
        r=ttk.Frame(settings); r.pack(fill="x",pady=4); ttk.Label(r,text="帧率",width=10).pack(side="left"); self.fps=tk.StringVar(value="智能 VFR"); ttk.Combobox(r,textvariable=self.fps,values=["智能 VFR","15","20","24","25","30","50","60"],state="readonly",width=16).pack(side="left"); ttk.Label(r,text="智能：根据书写运动动态保留帧",foreground="#627d98").pack(side="left",padx=10)
        r=ttk.Frame(settings); r.pack(fill="x",pady=4); ttk.Label(r,text="分辨率",width=10).pack(side="left"); self.width=tk.StringVar(); self.height=tk.StringVar(); ttk.Entry(r,textvariable=self.width,width=8).pack(side="left"); ttk.Label(r,text=" × ").pack(side="left"); ttk.Entry(r,textvariable=self.height,width=8).pack(side="left"); self.lock_ratio=tk.BooleanVar(value=True); ttk.Checkbutton(r,text="锁定比例",variable=self.lock_ratio).pack(side="left",padx=8); ttk.Button(r,text="原始尺寸",command=self.reset_size).pack(side="left")
        r=ttk.Frame(settings); r.pack(fill="x",pady=4); self.board=tk.BooleanVar(value=True); self.invert=tk.BooleanVar(value=False); ttk.Checkbutton(r,text="板书优化",variable=self.board).pack(side="left"); ttk.Checkbutton(r,text="智能反色（彩色保持原色）",variable=self.invert).pack(side="left",padx=14)
        r=ttk.Frame(settings); r.pack(fill="x",pady=4); ttk.Label(r,text="编码",width=10).pack(side="left"); self.codec=tk.StringVar(value="h265"); ttk.Combobox(r,textvariable=self.codec,values=["h265","h264","av1"],state="readonly",width=16).pack(side="left"); ttk.Label(r,text="质量",width=8).pack(side="left",padx=(25,0)); self.preset=tk.StringVar(value="board-balanced"); ttk.Combobox(r,textvariable=self.preset,values=["board-high","board-balanced","board-extreme"],state="readonly",width=18).pack(side="left")
        actions=ttk.Frame(outer); actions.pack(fill="x",pady=14); self.analyze_btn=ttk.Button(actions,text="重新分析",command=self.analyze,state="disabled"); self.analyze_btn.pack(side="left"); self.start_btn=ttk.Button(actions,text="开始压缩",command=self.start); self.start_btn.pack(side="left",padx=8); self.stop_btn=ttk.Button(actions,text="停止",command=self.stop,state="disabled"); self.stop_btn.pack(side="left")
        self.progress=ttk.Progressbar(outer,maximum=100); self.progress.pack(fill="x",pady=(0,5)); self.progress_text=ttk.Label(outer,text="等待开始",foreground="#627d98"); self.progress_text.pack(anchor="w")
        self.log=tk.Text(outer,height=10,relief="flat",bg="#f8fafc"); self.log.pack(fill="both",expand=True)
    def choose(self):
        p=filedialog.askopenfilename(title="选择板书视频",filetypes=[("视频","*.mp4 *.mov *.mkv *.m4v *.avi *.webm"),("所有文件","*")]);
        if not p:return
        self.video=Path(p); self.file_label.config(text=self.video.name); self.analyze_btn.config(state="normal"); self.log.delete("1.0","end"); self.log.insert("end",f"已选择：{self.video}\n"); self.analyze()
    def reset_size(self):
        if self.video and self.result:self.width.set(str(self.result.width)); self.height.set(str(self.result.height))
    def analyze(self):
        if not self.video:return
        self.analysis_label.config(text="正在分析板书运动……"); self.detail_label.config(text="抽样检测静止比例、局部变化和连续书写"); self.analyze_btn.config(state="disabled")
        def worker():
            try:self.after(0,lambda r:=analyze_video(str(self.video)):self._analysis_done(r))
            except Exception as exc:self.after(0,lambda e=exc:self._analysis_error(e))
        threading.Thread(target=worker,daemon=True).start()
    def _analysis_done(self,result):
        self.result=result; self.width.set(str(result.width)); self.height.set(str(result.height)); lo,hi=getattr(result,"recommended_min_fps",15),getattr(result,"recommended_max_fps",30); self.analysis_label.config(text=analysis_summary(result)); self.detail_label.config(text=f"推荐智能范围：{lo}～{hi} FPS；快速书写时优先保证连续性"); self.log.insert("end",f"分析完成：推荐 {lo}～{hi} FPS VFR\n"); self.analyze_btn.config(state="normal")
    def _analysis_error(self,exc):self.analysis_label.config(text=f"分析失败：{exc}");self.analyze_btn.config(state="normal")
    def start(self):
        if not self.video:return messagebox.showinfo("提示","请先选择视频")
        if self.running:return
        out=self.video.with_name(self.video.stem+"_board.mp4"); self.running=True; self.start_btn.config(state="disabled"); self.stop_btn.config(state="normal"); self.progress["value"]=0; self.progress_text.config(text="正在压缩…"); self.log.insert("end",f"输出：{out}\n")
        args=build_smart_command(str(self.video),str(out),codec=self.codec.get(),fps=self.fps.get(),width=int(self.width.get()),height=int(self.height.get()),board_opt=self.board.get(),invert=self.invert.get(),preset=self.preset.get())
        def worker():
            try:
                self.process=subprocess.Popen(args,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1)
                assert self.process.stdout
                for line in self.process.stdout:
                    line=line.rstrip()
                    if line:self.after(0,lambda s=line:self._line(s))
                code=self.process.wait(); self.after(0,lambda c=code,o=out:self._done(c,o))
            except Exception as exc:self.after(0,lambda e=exc:self._error(e))
        threading.Thread(target=worker,daemon=True).start()
    def _line(self,line):
        self.log.insert("end",line+"\n"); self.log.see("end")
        if "time=" in line:self.progress_text.config(text=line[-120:])
    def _done(self,code,out):
        self.running=False; self.start_btn.config(state="normal"); self.stop_btn.config(state="disabled")
        if code==0 and out.exists():
            src= self.video.stat().st_size; dst=out.stat().st_size; saved=(1-dst/src)*100 if src else 0; self.progress["value"]=100; self.progress_text.config(text=f"完成：{dst/1024/1024:.1f} MB · 节省 {saved:.1f}%"); self.log.insert("end",f"\n完成：{out}\n原始：{src/1024/1024:.1f} MB\n输出：{dst/1024/1024:.1f} MB\n节省：{saved:.1f}%\n")
        else:self.progress_text.config(text=f"压缩失败，FFmpeg 退出码 {code}")
    def _error(self,exc):self.running=False;self.start_btn.config(state="normal");self.stop_btn.config(state="disabled");messagebox.showerror("压缩失败",str(exc))
    def stop(self):
        if self.process and self.process.poll() is None:self.process.terminate(); self.log.insert("end","已请求停止。\n")

if __name__=="__main__":SmartBoardGUI().mainloop()
