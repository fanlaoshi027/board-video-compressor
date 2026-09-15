#!/usr/bin/env python3
"""樊老师板书压缩器 - Windows / macOS 图形界面。"""

from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

PRESETS = {
    "高清": ("board-high", 30),
    "均衡": ("board-balanced", 15),
    "极致压缩": ("board-extreme", 15),
}


def app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent


def bundled_binary(name: str) -> str:
    suffix = ".exe" if sys.platform.startswith("win") else ""
    candidate = app_dir() / "bin" / f"{name}{suffix}"
    if candidate.exists():
        return str(candidate)
    return name


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("樊老师板书压缩器")
        self.geometry("760x620")
        self.minsize(700, 560)
        self.configure(bg="#f6f8fb")
        self.files: list[str] = []
        self.events: queue.Queue[str] = queue.Queue()
        self.running = False
        self._build_style()
        self._build_ui()
        self.after(100, self._poll_events)

    def _build_style(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("Title.TLabel", font=("Arial", 22, "bold"), background="#f6f8fb", foreground="#102a43")
        style.configure("Sub.TLabel", font=("Arial", 11), background="#f6f8fb", foreground="#627d98")
        style.configure("Card.TLabelframe", background="#ffffff", borderwidth=1, relief="solid")
        style.configure("Card.TLabelframe.Label", background="#ffffff", foreground="#102a43", font=("Arial", 11, "bold"))
        style.configure("Card.TFrame", background="#ffffff")
        style.configure("Card.TLabel", background="#ffffff", foreground="#243b53", font=("Arial", 11))
        style.configure("Primary.TButton", font=("Arial", 11, "bold"), padding=(18, 10))

    def _build_ui(self) -> None:
        root = ttk.Frame(self, padding=28)
        root.pack(fill="both", expand=True)

        ttk.Label(root, text="樊老师板书压缩器", style="Title.TLabel").pack(anchor="w")
        ttk.Label(root, text="专为数学板书录课视频设计 · Windows / macOS", style="Sub.TLabel").pack(anchor="w", pady=(4, 18))

        files_box = ttk.LabelFrame(root, text=" ① 视频文件  ", style="Card.TLabelframe", padding=16)
        files_box.pack(fill="x")
        self.file_label = ttk.Label(files_box, text="还没有选择视频", style="Card.TLabel")
        self.file_label.pack(side="left", fill="x", expand=True)
        ttk.Button(files_box, text="选择视频", command=self.choose_files).pack(side="right")

        settings = ttk.LabelFrame(root, text=" ② 压缩设置  ", style="Card.TLabelframe", padding=16)
        settings.pack(fill="x", pady=14)

        row1 = ttk.Frame(settings, style="Card.TFrame")
        row1.pack(fill="x", pady=5)
        ttk.Label(row1, text="方案", style="Card.TLabel", width=12).pack(side="left")
        self.preset = tk.StringVar(value="均衡")
        ttk.Combobox(row1, textvariable=self.preset, values=list(PRESETS), state="readonly", width=18).pack(side="left")

        row2 = ttk.Frame(settings, style="Card.TFrame")
        row2.pack(fill="x", pady=5)
        ttk.Label(row2, text="编码", style="Card.TLabel", width=12).pack(side="left")
        self.codec = tk.StringVar(value="h265")
        ttk.Combobox(row2, textvariable=self.codec, values=["h265", "h264", "av1"], state="readonly", width=18).pack(side="left")

        row3 = ttk.Frame(settings, style="Card.TFrame")
        row3.pack(fill="x", pady=5)
        ttk.Label(row3, text="输出帧率", style="Card.TLabel", width=12).pack(side="left")
        self.fps = tk.StringVar(value="跟随方案")
        ttk.Combobox(row3, textvariable=self.fps, values=["跟随方案", "15", "20", "24", "25", "30", "50", "60"], state="readonly", width=18).pack(side="left")

        row4 = ttk.Frame(settings, style="Card.TFrame")
        row4.pack(fill="x", pady=5)
        ttk.Label(row4, text="智能反色", style="Card.TLabel", width=12).pack(side="left")
        self.invert = tk.BooleanVar(value=False)
        ttk.Checkbutton(row4, text="开启（黑白反色，彩色笔迹保持原色）", variable=self.invert).pack(side="left")

        row5 = ttk.Frame(settings, style="Card.TFrame")
        row5.pack(fill="x", pady=5)
        ttk.Label(row5, text="输出目录", style="Card.TLabel", width=12).pack(side="left")
        self.out_dir = tk.StringVar(value="与原视频放在同一目录")
        ttk.Button(row5, text="选择目录", command=self.choose_output).pack(side="right")
        ttk.Label(row5, textvariable=self.out_dir, style="Card.TLabel").pack(side="left", fill="x", expand=True)

        action = ttk.Frame(root)
        action.pack(fill="x", pady=(4, 12))
        self.start_btn = ttk.Button(action, text="开始压缩", style="Primary.TButton", command=self.start)
        self.start_btn.pack(side="left")
        self.progress = ttk.Progressbar(action, mode="indeterminate")
        self.progress.pack(side="left", fill="x", expand=True, padx=(16, 0))

        log_box = ttk.LabelFrame(root, text=" ③ 处理状态  ", style="Card.TLabelframe", padding=10)
        log_box.pack(fill="both", expand=True)
        self.log = tk.Text(log_box, height=10, wrap="word", relief="flat", bg="#f8fafc", fg="#334e68", font=("Menlo", 10))
        self.log.pack(fill="both", expand=True)
        self.write("等待选择视频……")

    def write(self, text: str) -> None:
        self.log.insert("end", text + "\n")
        self.log.see("end")

    def choose_files(self) -> None:
        paths = filedialog.askopenfilenames(title="选择视频", filetypes=[("视频", "*.mp4 *.mov *.mkv *.m4v"), ("所有文件", "*")])
        if paths:
            self.files = list(paths)
            self.file_label.config(text=f"已选择 {len(self.files)} 个视频：{Path(self.files[0]).name}" + (" 等" if len(self.files) > 1 else ""))

    def choose_output(self) -> None:
        path = filedialog.askdirectory(title="选择输出目录")
        if path:
            self.out_dir.set(path)

    def start(self) -> None:
        if self.running or not self.files:
            if not self.files:
                messagebox.showinfo("提示", "请先选择视频。")
            return
        self.running = True
        self.start_btn.config(state="disabled")
        self.progress.start(10)
        threading.Thread(target=self._worker, daemon=True).start()

    def _worker(self) -> None:
        preset_name, preset_fps = PRESETS[self.preset.get()]
        fps = preset_fps if self.fps.get() == "跟随方案" else int(self.fps.get())
        for src in self.files:
            src_path = Path(src)
            if self.out_dir.get() == "与原视频放在同一目录":
                out_dir = src_path.parent
            else:
                out_dir = Path(self.out_dir.get())
            out_dir.mkdir(parents=True, exist_ok=True)
            output = out_dir / f"{src_path.stem}_压缩_{self.codec.get()}_{fps}fps.mp4"
            cmd = [
                sys.executable, str(app_dir() / "compress.py"), str(src_path),
                "--preset", preset_name, "--codec", self.codec.get(), "--fps", str(fps),
                "--invert", "on" if self.invert.get() else "off", "--output", str(output),
            ]
            # 打包后没有独立 Python 解释器，因此 GUI 直接调用同目录的 CLI 可执行体。
            cli = app_dir() / "bin" / ("board-compress.exe" if sys.platform.startswith("win") else "board-compress")
            if cli.exists():
                cmd = [str(cli), str(src_path), "--preset", preset_name, "--codec", self.codec.get(), "--fps", str(fps), "--invert", "on" if self.invert.get() else "off", "--output", str(output)]
            try:
                self.events.put(f"开始：{src_path.name}")
                process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
                assert process.stdout is not None
                for line in process.stdout:
                    line = line.strip()
                    if line:
                        self.events.put(line)
                code = process.wait()
                if code != 0:
                    self.events.put(f"失败：{src_path.name}")
                else:
                    self.events.put(f"完成：{output.name}")
            except Exception as exc:
                self.events.put(f"错误：{exc}")
        self.events.put("__DONE__")

    def _poll_events(self) -> None:
        try:
            while True:
                msg = self.events.get_nowait()
                if msg == "__DONE__":
                    self.running = False
                    self.start_btn.config(state="normal")
                    self.progress.stop()
                    messagebox.showinfo("完成", "视频处理完成。")
                else:
                    self.write(msg)
        except queue.Empty:
            pass
        self.after(100, self._poll_events)


if __name__ == "__main__":
    App().mainloop()
