#!/usr/bin/env python3
from __future__ import annotations
import threading
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from board_analyzer import analyze_video, analysis_summary
from batch_queue import BatchQueue
from smart_runner import build_smart_command, run

VIDEO_TYPES=[("视频文件","*.mp4 *.mov *.mkv *.m4v *.avi *.webm *.wmv"),("所有文件","*")]

class SmartBoardGUI(tk.Tk):
    def __init__(self):
        super().__init__(); self.title("樊老师板书视频压缩器"); self.geometry("980x760"); self.minsize(900,680)
        self.queue=BatchQueue(); self.result=None; self.running=False; self.cancel_event=threading.Event(); self.current=None; self._build()
    def _build(self):
        outer=ttk.Frame(self,padding=18); outer.pack(fill="both",expand=True)
        ttk.Label(outer,text="樊老师板书视频压缩器",font=("Arial",21,"bold")).pack(anchor="w")
        ttk.Label(outer,text="白底黑字 · 局部书写 · 每个视频独立智能 VFR · Windows / macOS",foreground="#627d98").pack(anchor="w",pady=(2,10))
        toolbar=ttk.Frame(outer); toolbar.pack(fill="x",pady=6)
        ttk.Button(toolbar,text="添加视频",command=self.add_files).pack(side="left"); ttk.Button(toolbar,text="添加文件夹",command=self.add_folder).pack(side="left",padx=6); ttk.Button(toolbar,text="删除选中",command=self.remove_selected).pack(side="left"); ttk.Button(toolbar,text="清空等待",command=self.clear_waiting).pack(side="left",padx=6)
        self.start_btn=ttk.Button(toolbar,text="开始全部",command=self.start_queue); self.start_btn.pack(side="right"); self.stop_btn=ttk.Button(toolbar,text="停止",command=self.stop_queue,state="disabled"); self.stop_btn.pack(side="right",padx=6)
        qbox=ttk.LabelFrame(outer,text="处理队列",padding=8); qbox.pack(fill="both",expand=False,pady=6)
        cols=("file","status","output"); self.tree=ttk.Treeview(qbox,columns=cols,show="headings",height=8); self.tree.heading("file",text="视频"); self.tree.heading("status",text="状态"); self.tree.heading("output",text="输出"); self.tree.column("file",width=400); self.tree.column("status",width=110,anchor="center"); self.tree.column("output",width=360); self.tree.pack(side="left",fill="both",expand=True); sb=ttk.Scrollbar(qbox,orient="vertical",command=self.tree.yview); sb.pack(side="right",fill="y"); self.tree.configure(yscrollcommand=sb.set)
        box=ttk.LabelFrame(outer,text="当前视频分析",padding=10); box.pack(fill="x",pady=6); self.analysis_label=ttk.Label(box,text="等待队列开始"); self.analysis_label.pack(anchor="w"); self.detail_label=ttk.Label(box,text="",foreground="#627d98"); self.detail_label.pack(anchor="w",pady=(4,0))
        settings=ttk.LabelFrame(outer,text="统一输出设置",padding=10); settings.pack(fill="x",pady=6)
        r=ttk.Frame(settings); r.pack(fill="x",pady=3); ttk.Label(r,text="帧率",width=9).pack(side="left"); self.fps=tk.StringVar(value="智能 VFR"); ttk.Combobox(r,textvariable=self.fps,values=["智能 VFR","15","20","24","25","30","50","60"],state="readonly",width=15).pack(side="left"); ttk.Label(r,text="智能模式：每个视频单独分析",foreground="#627d98").pack(side="left",padx=10)
        ttk.Label(r,text="分辨率",width=9).pack(side="left",padx=(30,0)); self.width=tk.StringVar(); self.height=tk.StringVar(); ttk.Entry(r,textvariable=self.width,width=8).pack(side="left"); ttk.Label(r,text=" × ").pack(side="left"); ttk.Entry(r,textvariable=self.height,width=8).pack(side="left"); self.lock_ratio=tk.BooleanVar(value=True); ttk.Checkbutton(r,text="锁定比例",variable=self.lock_ratio).pack(side="left",padx=7)
        r=ttk.Frame(settings); r.pack(fill="x",pady=3); self.board=tk.BooleanVar(value=True); self.invert=tk.BooleanVar(value=False); ttk.Checkbutton(r,text="板书优化",variable=self.board).pack(side="left"); ttk.Checkbutton(r,text="智能反色（彩色保持原色）",variable=self.invert).pack(side="left",padx=16); ttk.Label(r,text="编码",width=8).pack(side="left",padx=(30,0)); self.codec=tk.StringVar(value="h265"); ttk.Combobox(r,textvariable=self.codec,values=["h265","h264","av1"],state="readonly",width=13).pack(side="left"); ttk.Label(r,text="质量",width=7).pack(side="left",padx=(20,0)); self.preset=tk.StringVar(value="board-balanced"); ttk.Combobox(r,textvariable=self.preset,values=["board-high","board-balanced","board-extreme"],state="readonly",width=17).pack(side="left")
        pbox=ttk.LabelFrame(outer,text="当前进度",padding=8); pbox.pack(fill="x",pady=6); self.progress=ttk.Progressbar(pbox,maximum=100); self.progress.pack(fill="x"); self.progress_text=ttk.Label(pbox,text="等待开始",foreground="#627d98"); self.progress_text.pack(anchor="w",pady=(3,0))
        self.log=tk.Text(outer,height=9,relief="flat",bg="#f8fafc"); self.log.pack(fill="both",expand=True,pady=(5,0))
    def refresh_tree(self):
        self.tree.delete(*self.tree.get_children())
        for i,item in enumerate(self.queue.items):
            out=str(item.output) if item.output else ""
            self.tree.insert("","end",iid=str(i),values=(item.source.name,item.status,Path(out).name if out else ""))
    def add_files(self):
        paths=filedialog.askopenfilenames(title="添加板书视频",filetypes=VIDEO_TYPES)
        if paths:self.queue.add(paths); self.refresh_tree(); self.log.insert("end",f"已加入 {len(paths)} 个视频\n")
    def add_folder(self):
        folder=filedialog.askdirectory(title="选择视频文件夹")
        if not folder:return
        paths=sorted(p for p in Path(folder).iterdir() if p.is_file() and p.suffix.lower() in {'.mp4','.mov','.mkv','.m4v','.avi','.webm','.wmv'}); self.queue.add(paths); self.refresh_tree(); self.log.insert("end",f"已从文件夹加入 {len(paths)} 个视频\n")
    def remove_selected(self):
        selected={int(i) for i in self.tree.selection()}; self.queue.items=[x for i,x in enumerate(self.queue.items) if i not in selected]; self.refresh_tree()
    def clear_waiting(self): self.queue.clear_waiting(); self.refresh_tree()
    def start_queue(self):
        if self.running or not self.queue.items:return
        self.running=True; self.cancel_event.clear(); self.start_btn.config(state="disabled"); self.stop_btn.config(state="normal"); threading.Thread(target=self.worker_queue,daemon=True).start()
    def worker_queue(self):
        while not self.cancel_event.is_set():
            item=self.queue.next_waiting()
            if item is None:break
            self.current=item; item.status="分析中"; self.after(0,self.refresh_tree)
            try:
                result=analyze_video(str(item.source)); self.result=result; self.after(0,lambda r=result,s=item.source.name:self.show_analysis(r,s));
                lo=getattr(result,"recommended_min_fps",15); hi=getattr(result,"recommended_max_fps",30)
                item.output=item.source.with_name(item.source.stem+"_board.mp4"); item.status="压缩中"; self.after(0,self.refresh_tree)
                args=build_smart_command(str(item.source),str(item.output),codec=self.codec.get(),fps=self.fps.get(),width=int(self.width.get() or result.width),height=int(self.height.get() or result.height),keep_aspect=self.lock_ratio.get(),board_opt=self.board.get(),invert=self.invert.get(),preset=self.preset.get(),min_fps=lo,max_fps=hi,duration=float(getattr(result,"duration",0) or 0))
                code,cancelled=run(args,duration=float(getattr(result,"duration",0) or 0),cancel_event=self.cancel_event,cleanup_output=str(item.output),on_progress=lambda p,s:self.after(0,lambda x=p,st=s:self.update_progress(x,st,item.source.name)),on_line=lambda s:self.after(0,lambda t=s:self.log_line(t)))
                if cancelled: item.status="等待"; break
                if code==0 and item.output.exists(): item.status="完成"; self.after(0,lambda it=item:self.log_line(f"完成：{it.source.name}"))
                else: item.status="失败"; item.error=f"FFmpeg {code}"
            except Exception as exc: item.status="失败"; item.error=str(exc)
            self.after(0,self.refresh_tree)
        self.after(0,self.queue_finished)
    def show_analysis(self,result,name):
        self.analysis_label.config(text=f"{name}：{analysis_summary(result)}"); self.detail_label.config(text=f"本视频智能范围：{getattr(result,'recommended_min_fps',15)}～{getattr(result,'recommended_max_fps',30)} FPS")
        self.width.set(str(result.width)); self.height.set(str(result.height))
    def update_progress(self,p,state,name): self.progress["value"]=p; self.progress_text.config(text=f"{name}  ·  {p:.1f}%  ·  {state.get('out_time','--:--:--')}  ·  {state.get('speed','?')}")
    def log_line(self,s): self.log.insert("end",s+"\n"); self.log.see("end")
    def queue_finished(self): self.running=False; self.start_btn.config(state="normal"); self.stop_btn.config(state="disabled"); self.progress_text.config(text="队列处理完成")
    def stop_queue(self):
        if self.running:self.cancel_event.set(); self.stop_btn.config(state="disabled"); self.progress_text.config(text="正在停止当前任务并清理临时文件…")

if __name__=="__main__": SmartBoardGUI().mainloop()
