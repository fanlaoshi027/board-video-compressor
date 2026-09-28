from __future__ import annotations

import subprocess
import threading
import time
from pathlib import Path

import tkinter as tk
from tkinter import messagebox

try:
    from PIL import Image, ImageTk
except ImportError:
    Image = ImageTk = None


class ReliablePreviewWindow(tk.Toplevel):
    """稳定的视频预览：单一播放管道、最新帧缓冲、拖动时彻底丢弃旧帧。"""

    FPS = 12

    def __init__(self, app, path, duration, info):
        super().__init__(app)
        self.app = app
        self.path = Path(path)
        self.duration = max(0.0, float(duration))
        self.pos = 0.0
        self.playing = False
        self.dragging = False
        self.was_playing = False
        self.photo = None
        self.preview_proc = None
        self.generation = 0
        self.seek_job = None
        self.ui_job = None
        self.frame_lock = threading.Lock()
        self.pending_frame = None
        self.closed = False

        v = next(s for s in info.get("streams", []) if s.get("codec_type") == "video")
        src_w, src_h = int(v["width"]), int(v["height"])
        self.frame_w = min(800, max(320, src_w))
        self.frame_h = max(2, int(round(self.frame_w * src_h / src_w)))
        if self.frame_h % 2:
            self.frame_h -= 1
        self.frame_bytes = self.frame_w * self.frame_h * 3

        self.title("视频预览与删除区间")
        self.geometry("900x650")
        self.minsize(760, 560)
        self.configure(bg="#111")
        self.protocol("WM_DELETE_WINDOW", self.close)

        self.canvas = tk.Label(self, bg="#111", fg="white", text="正在加载预览…")
        self.canvas.pack(fill="both", expand=True, padx=10, pady=10)

        bar = tk.Frame(self, bg="#111")
        bar.pack(fill="x", padx=12)
        self.time_label = tk.Label(bar, text="00:00 / 00:00", bg="#111", fg="white", font=("Arial", 11))
        self.time_label.pack(side="left")
        self.scale = tk.Scale(bar, from_=0, to=max(0.1, self.duration), orient="horizontal", resolution=0.1, showvalue=0, bg="#111", fg="white", highlightthickness=0, troughcolor="#555", command=self.on_seek)
        self.scale.pack(side="left", fill="x", expand=True, padx=12)
        self.scale.bind("<ButtonPress-1>", self.on_seek_press)
        self.scale.bind("<ButtonRelease-1>", self.on_seek_release)

        controls = tk.Frame(self, bg="#111")
        controls.pack(fill="x", padx=12, pady=(4, 12))
        self.play_btn = tk.Button(controls, text="▶ 播放", command=self.toggle_play, width=10)
        self.play_btn.pack(side="left", padx=4)
        tk.Button(controls, text="设置开始", command=self.set_start, width=10).pack(side="left", padx=4)
        tk.Button(controls, text="设置结束", command=self.set_end, width=10).pack(side="left", padx=4)
        tk.Button(controls, text="清除当前选择", command=self.clear_selection, width=12).pack(side="left", padx=4)
        self.selection = tk.Label(controls, text="未选择删除区间", bg="#111", fg="#ddd")
        self.selection.pack(side="left", padx=12)
        self.status = tk.Label(self, text="预览就绪", bg="#111", fg="#aaa", anchor="w")
        self.status.pack(fill="x", padx=12, pady=(0, 8))

        self.update_time()
        self.seek_to(0.0, autoplay=False)

    def fmt(self, x):
        x = max(0.0, float(x))
        h = int(x // 3600)
        m = int((x % 3600) // 60)
        s = int(x % 60)
        return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"

    def update_time(self):
        if self.closed:
            return
        self.scale.set(min(self.duration, max(0.0, self.pos)))
        self.time_label.config(text=f"{self.fmt(self.pos)} / {self.fmt(self.duration)}")

    def _stop_process(self):
        self.generation += 1
        with self.frame_lock:
            self.pending_frame = None
        p = self.preview_proc
        self.preview_proc = None
        if p and p.poll() is None:
            try:
                p.terminate()
                p.wait(timeout=0.5)
            except Exception:
                try:
                    p.kill()
                except Exception:
                    pass

    def _read_exact(self, stream, size):
        data = bytearray()
        while len(data) < size:
            chunk = stream.read(size - len(data))
            if not chunk:
                return None
            data.extend(chunk)
        return bytes(data)

    def _start_process(self, start):
        self._stop_process()
        self.generation += 1
        generation = self.generation
        cmd = [
            self.app._bundled_binary("ffmpeg") if hasattr(self.app, "_bundled_binary") else self._binary("ffmpeg"),
            "-hide_banner", "-loglevel", "error", "-re",
            "-ss", f"{start:.3f}", "-i", str(self.path), "-an",
            "-vf", f"scale={self.frame_w}:{self.frame_h},fps={self.FPS}",
            "-pix_fmt", "rgb24", "-f", "rawvideo", "pipe:1",
        ]
        try:
            p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=self.frame_bytes * 2, **self._hidden_kwargs())
        except Exception as e:
            self.status.config(text=f"预览启动失败：{e}")
            self.playing = False
            self.play_btn.config(text="▶ 播放")
            return
        self.preview_proc = p
        threading.Thread(target=self._reader, args=(p, generation, start), daemon=True).start()

    def _reader(self, proc, generation, start):
        frame_index = 0
        try:
            while generation == self.generation and proc.poll() is None and not self.closed:
                raw = self._read_exact(proc.stdout, self.frame_bytes)
                if raw is None:
                    break
                frame_pos = min(self.duration, start + frame_index / self.FPS)
                frame_index += 1
                with self.frame_lock:
                    if generation == self.generation:
                        self.pending_frame = (raw, frame_pos, generation)
                self._schedule_ui()
        except Exception:
            pass
        finally:
            if generation == self.generation and not self.closed:
                self.after(0, lambda g=generation: self._playback_finished(g))

    def _schedule_ui(self):
        if self.closed:
            return
        try:
            if self.ui_job is None:
                self.ui_job = self.after(15, self._consume_latest_frame)
        except Exception:
            pass

    def _consume_latest_frame(self):
        self.ui_job = None
        if self.closed:
            return
        with self.frame_lock:
            item = self.pending_frame
            self.pending_frame = None
        if not item:
            return
        raw, pos, generation = item
        if generation != self.generation or not self.playing:
            return
        if Image:
            try:
                img = Image.frombytes("RGB", (self.frame_w, self.frame_h), raw)
                photo = ImageTk.PhotoImage(img)
                self._show_frame(photo, pos, generation)
            except Exception:
                pass

    def _show_frame(self, photo, pos, generation):
        if self.closed or generation != self.generation:
            return
        self.photo = photo
        self.pos = min(self.duration, max(0.0, pos))
        self.canvas.config(image=photo, text="")
        self.update_time()

    def _playback_finished(self, generation):
        if self.closed or generation != self.generation:
            return
        self.preview_proc = None
        if self.pos >= self.duration - 0.05:
            self.pos = self.duration
        self.playing = False
        self.play_btn.config(text="▶ 播放")
        self.status.config(text="预览结束")
        self.update_time()

    def toggle_play(self):
        if self.playing:
            self.playing = False
            self.play_btn.config(text="▶ 播放")
            self._stop_process()
            self.status.config(text="已暂停")
            return
        if self.pos >= self.duration - 0.05:
            self.pos = 0.0
        self.playing = True
        self.play_btn.config(text="⏸ 暂停")
        self.status.config(text="正在播放…")
        self._start_process(self.pos)

    def on_seek_press(self, _event=None):
        self.dragging = True
        self.was_playing = self.playing
        if self.playing:
            self.playing = False
            self.play_btn.config(text="▶ 播放")
            self._stop_process()
        self.status.config(text="正在定位…")

    def on_seek(self, value):
        if self.closed:
            return
        self.pos = min(self.duration, max(0.0, float(value)))
        self.update_time()

    def on_seek_release(self, _event=None):
        self.dragging = False
        self.seek_to(self.pos, autoplay=self.was_playing)
        self.was_playing = False

    def seek_to(self, pos, autoplay=False):
        if self.seek_job:
            try:
                self.after_cancel(self.seek_job)
            except Exception:
                pass
        self.seek_job = self.after(60, lambda: self._seek_now(pos, autoplay))

    def _seek_now(self, pos, autoplay=False):
        self.seek_job = None
        if self.closed:
            return
        self._stop_process()
        self.pos = min(self.duration, max(0.0, float(pos)))
        self.update_time()
        if autoplay:
            self.playing = True
            self.play_btn.config(text="⏸ 暂停")
            self.status.config(text="正在播放…")
            self._start_process(self.pos)
            return
        self.playing = False
        self.play_btn.config(text="▶ 播放")
        self._show_single_frame(self.pos)

    def _show_single_frame(self, pos):
        self.generation += 1
        generation = self.generation
        cmd = [
            self._binary("ffmpeg"), "-hide_banner", "-loglevel", "error", "-ss", f"{pos:.3f}",
            "-i", str(self.path), "-frames:v", "1", "-vf", f"scale={self.frame_w}:{self.frame_h}",
            "-pix_fmt", "rgb24", "-f", "rawvideo", "pipe:1",
        ]
        try:
            p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, **self._hidden_kwargs())
        except Exception as e:
            self.status.config(text=f"定位失败：{e}")
            return

        def worker():
            try:
                raw = self._read_exact(p.stdout, self.frame_bytes)
                try:
                    p.terminate()
                except Exception:
                    pass
                if raw and generation == self.generation and Image:
                    self.after(0, lambda: self._display_single(raw, pos, generation))
            except Exception:
                pass

        threading.Thread(target=worker, daemon=True).start()

    def _display_single(self, raw, pos, generation):
        if self.closed or generation != self.generation or not Image:
            return
        try:
            img = Image.frombytes("RGB", (self.frame_w, self.frame_h), raw)
            self.photo = ImageTk.PhotoImage(img)
            self._show_frame(self.photo, pos, generation)
            self.status.config(text="预览就绪")
        except Exception:
            pass

    def set_start(self):
        self.app.preview_start = self.pos
        self.update_selection()

    def set_end(self):
        if self.app.preview_start is None:
            self.app.preview_start = self.pos
            self.update_selection()
            return
        a, b = sorted((self.app.preview_start, self.pos))
        if b <= a:
            messagebox.showwarning("删除区间", "结束位置必须大于开始位置", parent=self)
            return
        self.app.cuts.append((a, b))
        self.app.cuts.sort()
        self.app._refresh_cuts()
        self.app.preview_start = None
        self.update_selection()

    def clear_selection(self):
        self.app.preview_start = None
        self.update_selection()

    def update_selection(self):
        a = self.app.preview_start
        self.selection.config(text=f"开始：{self.fmt(a)}，移动指针后点击“设置结束”" if a is not None else (self.app.cut_text() or "未选择删除区间"))

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.playing = False
        if self.ui_job:
            try:
                self.after_cancel(self.ui_job)
            except Exception:
                pass
            self.ui_job = None
        self._stop_process()
        self.destroy()

    def _binary(self, name):
        try:
            return self.app._bundled_binary(name)
        except Exception:
            suffix = ".exe" if __import__("sys").platform.startswith("win") else ""
            p = Path(getattr(__import__("sys"), "_MEIPASS", Path(__file__).resolve().parent)) / "bin" / f"{name}{suffix}"
            return str(p) if p.exists() else name

    def _hidden_kwargs(self):
        import sys
        if sys.platform.startswith("win"):
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = 0
            return {"startupinfo": si, "creationflags": subprocess.CREATE_NO_WINDOW}
        return {}
