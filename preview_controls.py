from preview_player import ReliablePreviewWindow


class PreviewWindow(ReliablePreviewWindow):
    """Windows 预览增强层：快捷键和更直观的定位控制。"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bind("<space>", lambda _e: self.toggle_play())
        self.bind("<Left>", lambda _e: self._nudge(-5))
        self.bind("<Right>", lambda _e: self._nudge(5))
        self.bind("<Shift-Left>", lambda _e: self._nudge(-1))
        self.bind("<Shift-Right>", lambda _e: self._nudge(1))
        self.bind("<Home>", lambda _e: self.seek_to(0.0, autoplay=False))
        self.bind("<End>", lambda _e: self.seek_to(self.duration, autoplay=False))
        self.focus_set()
        self.status.config(text="预览就绪 · 空格播放/暂停 · ← → 前后5秒")

    def _nudge(self, delta):
        was_playing = self.playing
        if was_playing:
            self.playing = False
            self.play_btn.config(text="▶ 播放")
            self._stop_process()
        self.pos = min(self.duration, max(0.0, self.pos + delta))
        self.seek_to(self.pos, autoplay=was_playing)
