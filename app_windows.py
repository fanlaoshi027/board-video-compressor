#!/usr/bin/env python3
"""Windows EXE 启动入口：使用可靠预览播放器，不弹 FFmpeg 黑框。"""
from __future__ import annotations

import app as _app
from preview_controls import PreviewWindow

# App.open_preview() 使用 app 模块的 PreviewWindow 全局变量。
# 在 Windows 入口替换为增强版预览，不修改压缩主流程。
_app.PreviewWindow = PreviewWindow
App = _app.App

if __name__ == "__main__":
    App().mainloop()
