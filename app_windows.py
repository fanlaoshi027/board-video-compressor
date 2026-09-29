#!/usr/bin/env python3
"""Windows EXE 启动入口：使用可靠预览播放器，不弹 FFmpeg 黑框。"""
from __future__ import annotations

import app as _app
from preview_controls import PreviewWindow as _BasePreviewWindow


class PreviewWindow(_BasePreviewWindow):
    """Windows 预览增强：键盘控制。"""

    def __init__(self, app, path, duration, info):
        super().__init__(app, path, duration, info)
        self.bind("<space>", self._key_play_pause)
        self.bind("<Left>", self._key_left)
        self.bind("<Right>", self._key_right)
        self.bind("<Shift-Left>", self._key_shift_left)
        self.bind("<Shift-Right>", self._key_shift_right)
        self.bind("<Home>", self._key_home)
        self.bind("<End>", self._key_end)
        self.focus_set()

    def _key_play_pause(self, event=None):
        self.toggle_play()
        return "break"

    def _key_left(self, event=None):
        self._keyboard_seek(-5.0)
        return "break"

    def _key_right(self, event=None):
        self._keyboard_seek(5.0)
        return "break"

    def _key_shift_left(self, event=None):
        self._keyboard_seek(-1.0)
        return "break"

    def _key_shift_right(self, event=None):
        self._keyboard_seek(1.0)
        return "break"

    def _key_home(self, event=None):
        self._keyboard_seek_to(0.0)
        return "break"

    def _key_end(self, event=None):
        self._keyboard_seek_to(self.duration)
        return "break"

    def _keyboard_seek(self, delta):
        target = min(self.duration, max(0.0, self.pos + delta))
        was_playing = bool(self.playing)
        self.playing = False
        self.play_btn.config(text="▶ 播放")
        self._stop_proc()
        self.seek_to(target, autoplay=was_playing)

    def _keyboard_seek_to(self, target):
        was_playing = bool(self.playing)
        self.playing = False
        self.play_btn.config(text="▶ 播放")
        self._stop_proc()
        self.seek_to(target, autoplay=was_playing)


_app.PreviewWindow = PreviewWindow
App = _app.App

if __name__ == "__main__":
    App().mainloop()
