from preview_player import ReliablePreviewWindow


class PreviewWindow(ReliablePreviewWindow):
    """Windows 预览增强层：键盘只用于快速寻找时间点。"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bind("<space>", self._on_space)
        self.bind("<Left>", self._on_left)
        self.bind("<Right>", self._on_right)
        self.bind("<Shift-Left>", self._on_shift_left)
        self.bind("<Shift-Right>", self._on_shift_right)
        self.bind("<Home>", self._on_home)
        self.bind("<End>", self._on_end)
        self.focus_set()
        self.status.config(text="预览就绪 · 空格播放/暂停 · ← → 前后5秒")

    def _on_space(self, event=None):
        self.toggle_play()
        return "break"

    def _on_left(self, event=None):
        self._nudge(-5.0)
        return "break"

    def _on_right(self, event=None):
        self._nudge(5.0)
        return "break"

    def _on_shift_left(self, event=None):
        self._nudge(-1.0)
        return "break"

    def _on_shift_right(self, event=None):
        self._nudge(1.0)
        return "break"

    def _on_home(self, event=None):
        self._seek_keyboard(0.0)
        return "break"

    def _on_end(self, event=None):
        self._seek_keyboard(self.duration)
        return "break"

    def _nudge(self, delta):
        self._seek_keyboard(min(self.duration, max(0.0, self.pos + delta)))

    def _seek_keyboard(self, target):
        was_playing = bool(self.playing)
        self.playing = False
        self.play_btn.config(text="▶ 播放")
        self._stop_proc()
        self.seek_to(target, autoplay=was_playing)
