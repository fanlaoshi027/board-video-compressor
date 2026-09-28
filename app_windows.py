#!/usr/bin/env python3
"""Windows EXE 启动入口。"""
from __future__ import annotations

import app as _app
from preview_player import ReliablePreviewWindow

# 只替换预览窗口，不改压缩主流程。
# 这样可以在不构建 EXE 的情况下持续测试预览逻辑。
_app.PreviewWindow = ReliablePreviewWindow
App = _app.App

if __name__ == "__main__":
    App().mainloop()
