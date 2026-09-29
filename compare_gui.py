#!/usr/bin/env python3
from __future__ import annotations
import threading
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, ttk, messagebox
from compare_modes import run_one

class CompareGUI(tk.Tk):
    def __init__(self):
        super().__init__(); self.title("板书压缩模式对比"); self.geometry("900x620"); self.src=None; self.stop_event=threading.Event(); self.running=False; self._build()
    def _build(self):
        root=ttk.Frame(self,padding=18); root.pack(fill='both',expand=True)
        ttk.Label(root,text='板书压缩模式对比测试',font=('Arial',20,'bold')).pack(anchor='w')
        ttk.Label(root,text='同一个原视频分别测试固定15 / 普通智能VFR / 板书自适应VFR',foreground='#627d98').pack(anchor='w',pady=(2,12))
        top=ttk.Frame(root); top.pack(fill='x'); ttk.Button(top,text='选择原视频',command=self.choose).pack(side='left'); self.file_label=ttk.Label(top,text='未选择'); self.file_label.pack(side='left',padx=10); self.start=ttk.Button(top,text='开始三模式测试',command=self.start_test,state='disabled'); self.start.pack(side='right'); self.stop=ttk.Button(top,text='停止',command=self.stop_test,state='disabled'); self.stop.pack(side='right',padx=8)
        box=ttk.LabelFrame(root,text='测试结果',padding=8); box.pack(fill='both',expand=True,pady=12)
        cols=('mode','status','size','time','file'); self.tree=ttk.Treeview(box,columns=cols,show='headings');
        for c,t,w in [('mode','模式',150),('status','状态',100),('size','文件大小',110),('time','耗时',100),('file','输出文件',380)]: self.tree.heading(c,text=t); self.tree.column(c,width=w,anchor='center' if c!='file' else 'w')
        self.tree.pack(fill='both',expand=True)
        self.progress=ttk.Progressbar(root,maximum=3); self.progress.pack(fill='x'); self.info=ttk.Label(root,text='等待开始',foreground='#627d98'); self.info.pack(anchor='w',pady=5)
        self.log=tk.Text(root,height=8,relief='flat',bg='#f8fafc'); self.log.pack(fill='both',expand=False)
    def choose(self):
        p=filedialog.askopenfilename(title='选择原始板书视频',filetypes=[('视频','*.mp4 *.mov *.mkv *.m4v *.avi *.webm'),('所有文件','*')]);
        if p:self.src=Path(p);self.file_label.config(text=self.src.name);self.start.config(state='normal')
    def start_test(self):
        if not self.src or self.running:return
        self.running=True;self.stop_event.clear();self.start.config(state='disabled');self.stop.config(state='normal');self.tree.delete(*self.tree.get_children());self.progress['value']=0
        threading.Thread(target=self.worker,daemon=True).start()
    def worker(self):
        outdir=self.src.parent/(self.src.stem+'_compare');outdir.mkdir(exist_ok=True);modes=('fixed15','smart_vfr','board_vfr')
        for idx,mode in enumerate(modes,1):
            if self.stop_event.is_set():break
            out=outdir/f'{self.src.stem}_{mode}.mp4';self.after(0,lambda m=mode,o=out:self.tree.insert('','end',iid=m,values=(m,'压缩中','—','—',str(o))))
            r=run_one(self.src,mode,out)
            self.after(0,lambda m=mode,r=r:self.update_row(m,r));self.after(0,lambda x=idx:self.progress.configure(value=x))
        self.after(0,self.done)
    def update_row(self,mode,r):
        status='完成' if r.ok else ('停止' if self.stop_event.is_set() else '失败');size=f'{r.size_bytes/1024/1024:.1f} MB' if r.ok else '—';time=f'{r.elapsed_seconds:.1f}s';self.tree.item(mode,values=(mode,status,size,time,r.output));self.log.insert('end',f'{mode}: {status} {size} {time}\n');self.log.see('end')
    def done(self):self.running=False;self.start.config(state='normal');self.stop.config(state='disabled');self.info.config(text='三模式测试完成' if not self.stop_event.is_set() else '测试已停止')
    def stop_test(self):self.stop_event.set();self.stop.config(state='disabled');self.info.config(text='正在停止当前测试…')
if __name__=='__main__':CompareGUI().mainloop()
