#!/usr/bin/env python3
"""Smart GUI entry point for the board-video-compressor project.

This module intentionally stays separate from the legacy GUI while the VFR
pipeline is being validated. It provides a small, stable front-end for:
- selecting a board video;
- analyzing board motion;
- showing the recommended VFR range;
- choosing fixed FPS or Smart VFR;
- selecting output resolution while preserving aspect ratio;
- enabling the optional selective black/white inversion.

The actual FFmpeg command construction remains in compress.py/smart_vfr.py.
"""
from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from board_analyzer import analyze_video, analysis_summary


class SmartBoardGUI(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("樊老师板书视频压缩器")
        self.geometry("820x620")
        self.minsize(760, 560)
        self.video: Path | None = None
        self.result = None
        self._build()

    def _build(self) -> None:
        outer = ttk.Frame(self, padding=20)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="樊老师板书视频压缩器", font=("Arial", 21, "bold")).pack(anchor="w")
        ttk.Label(outer, text="白底黑字 · 局部书写 · 智能可变帧率", foreground="#627d98").pack(anchor="w", pady=(2, 14))

        row = ttk.Frame(outer)
        row.pack(fill="x")
        ttk.Button(row, text="选择视频", command=self.choose).pack(side="left")
        self.file_label = ttk.Label(row, text="尚未选择视频")
        self.file_label.pack(side="left", padx=12)

        box = ttk.LabelFrame(outer, text="板书分析", padding=12)
        box.pack(fill="x", pady=12)
        self.analysis_label = ttk.Label(box, text="选择视频后自动分析")
        self.analysis_label.pack(anchor="w")
        self.detail_label = ttk.Label(box, text="", foreground="#627d98")
        self.detail_label.pack(anchor="w", pady=(6, 0))

        settings = ttk.LabelFrame(outer, text="输出设置", padding=12)
        settings.pack(fill="x")
        r = ttk.Frame(settings); r.pack(fill="x", pady=4)
        ttk.Label(r, text="帧率", width=10).pack(side="left")
        self.fps = tk.StringVar(value="智能 VFR")
        ttk.Combobox(r, textvariable=self.fps,
                     values=["智能 VFR", "15", "20", "24", "25", "30", "50", "60"],
                     state="readonly", width=16).pack(side="left")
        ttk.Label(r, text="智能：根据静止/书写运动动态保留帧", foreground="#627d98").pack(side="left", padx=10)

        r = ttk.Frame(settings); r.pack(fill="x", pady=4)
        ttk.Label(r, text="分辨率", width=10).pack(side="left")
        self.width = tk.StringVar(); self.height = tk.StringVar()
        ttk.Entry(r, textvariable=self.width, width=8).pack(side="left")
        ttk.Label(r, text=" × ").pack(side="left")
        ttk.Entry(r, textvariable=self.height, width=8).pack(side="left")
        self.lock_ratio = tk.BooleanVar(value=True)
        ttk.Checkbutton(r, text="锁定比例", variable=self.lock_ratio).pack(side="left", padx=8)
        ttk.Button(r, text="原始尺寸", command=self.reset_size).pack(side="left")

        r = ttk.Frame(settings); r.pack(fill="x", pady=4)
        self.board = tk.BooleanVar(value=True)
        self.invert = tk.BooleanVar(value=False)
        ttk.Checkbutton(r, text="板书优化", variable=self.board).pack(side="left")
        ttk.Checkbutton(r, text="智能反色（彩色保持原色）", variable=self.invert).pack(side="left", padx=14)

        actions = ttk.Frame(outer); actions.pack(fill="x", pady=14)
        self.analyze_btn = ttk.Button(actions, text="重新分析", command=self.analyze, state="disabled")
        self.analyze_btn.pack(side="left")
        ttk.Button(actions, text="开始压缩", command=self.start_placeholder).pack(side="left", padx=8)

        self.log = tk.Text(outer, height=9, relief="flat", bg="#f8fafc")
        self.log.pack(fill="both", expand=True)

    def choose(self) -> None:
        p = filedialog.askopenfilename(
            title="选择板书视频",
            filetypes=[("视频", "*.mp4 *.mov *.mkv *.m4v *.avi *.webm"), ("所有文件", "*")],
        )
        if not p:
            return
        self.video = Path(p)
        self.file_label.config(text=self.video.name)
        self.analyze_btn.config(state="normal")
        self.log.delete("1.0", "end")
        self.log.insert("end", f"已选择：{self.video}\n")
        self.analyze()

    def reset_size(self) -> None:
        # Keep the fields editable; probe is intentionally deferred to analysis.
        if self.video and self.result:
            self.width.set(str(self.result.width))
            self.height.set(str(self.result.height))

    def analyze(self) -> None:
        if not self.video:
            return
        self.analysis_label.config(text="正在分析板书运动……")
        self.detail_label.config(text="抽样检测静止比例、局部变化和连续书写")
        self.analyze_btn.config(state="disabled")

        def worker() -> None:
            try:
                result = analyze_video(str(self.video))
                self.after(0, lambda: self._analysis_done(result))
            except Exception as exc:
                self.after(0, lambda: self._analysis_error(exc))

        threading.Thread(target=worker, daemon=True).start()

    def _analysis_done(self, result) -> None:
        self.result = result
        if getattr(result, "width", None):
            self.width.set(str(result.width)); self.height.set(str(result.height))
        self.analysis_label.config(text=analysis_summary(result))
        lo, hi = getattr(result, "recommended_min_fps", 15), getattr(result, "recommended_max_fps", 30)
        self.detail_label.config(text=f"推荐智能范围：{lo}～{hi} FPS；快速书写时优先保证连续性")
        self.log.insert("end", f"分析完成：推荐 {lo}～{hi} FPS VFR\n")
        self.analyze_btn.config(state="normal")

    def _analysis_error(self, exc: Exception) -> None:
        self.analysis_label.config(text=f"分析失败：{exc}")
        self.analyze_btn.config(state="normal")

    def start_placeholder(self) -> None:
        if not self.video:
            messagebox.showinfo("提示", "请先选择视频")
            return
        mode = self.fps.get()
        self.log.insert("end", f"准备压缩：{self.video.name} · {mode}\n")
        self.log.insert("end", "下一阶段接入最终 FFmpeg 执行器。\n")


if __name__ == "__main__":
    SmartBoardGUI().mainloop()
