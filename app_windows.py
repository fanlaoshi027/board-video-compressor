#!/usr/bin/env python3
"""Windows 启动壳：在现有 GUI 上增加“打开输出目录”。"""
from __future__ import annotations
import os
from pathlib import Path

from app import App


class WindowsApp(App):
    def _ui(self):
        super()._ui()
        self._compression_started = False
        self.open_output_btn = __import__("tkinter").ttk.Button(
            self.start_btn.master,
            text="打开输出目录",
            command=self.open_output_directory,
            state="disabled",
        )
        self.open_output_btn.pack(side="left", padx=(8, 0))
        self.after(300, self._update_output_button)

    def start(self):
        if self.running or not self.files:
            return super().start()
        self._compression_started = True
        self.open_output_btn.config(state="disabled")
        return super().start()

    def _update_output_button(self):
        try:
            if self._compression_started and not self.running:
                self.open_output_btn.config(state="normal")
        finally:
            self.after(300, self._update_output_button)

    def _output_directory_path(self):
        value = self.out_dir.get().strip()
        if value and value != "与原视频放在同一目录":
            p = Path(value)
            if p.exists():
                return p
        if self.files:
            return Path(self.files[0]).resolve().parent
        return None

    def open_output_directory(self):
        p = self._output_directory_path()
        if not p:
            return
        p.mkdir(parents=True, exist_ok=True)
        os.startfile(str(p))


if __name__ == "__main__":
    app = WindowsApp()
    app.mainloop()
