# 樊老师板书视频压缩器

专门针对 **白底黑字数学板书 / 手写公式 / 网课录屏** 的 MP4 压缩工具。

目标不是单纯“把视频压小”，而是寻找板书视频的最佳压缩甜点区：

- 尽量保持数学公式、笔迹边缘清晰
- 尽量减少快速书写时的断裂、拖影和闪烁
- 重点利用“大面积静止 + 局部书写”的板书特征
- 支持 H.264 / H.265 / AV1
- 输出帧率可选 15 / 20 / 24 / 25 / 30 / 50 / 60 FPS
- 分辨率可自定义，并支持锁定宽高比
- 智能反色为可选项：黑白灰反转，彩色笔迹保持原色
- Windows + macOS 共用一套核心

## 当前桌面 GUI

`app.py` 已提供桌面界面，包含：

- 多视频选择
- 视频信息检测
- 压缩方案：高清 / 均衡 / 极致压缩
- H.264 / H.265 / AV1
- 智能帧率
- 自定义分辨率 + 锁定比例
- 板书优化开关
- 智能反色（彩色不变）
- 输出目录选择
- 视频预览与删除时间段
- 批量压缩
- 编码器能力检测

### Windows

双击 `run.bat` 启动 GUI。

### macOS

双击 `run.command` 启动 GUI。若系统提示没有执行权限，可在终端执行：

```bash
chmod +x run.command
./run.command
```

macOS 需要 Python 3、FFmpeg，并安装 Python GUI 依赖：

```bash
python3 -m pip install -r requirements.txt
brew install ffmpeg
```

## 命令行

```bash
python compress.py input.mp4 --preset board-balanced --codec h265
```

## 板书优化原则

真正的目标不是简单降低码率，而是利用数学板书视频的特点：

> 大部分画面长期静止，只有笔尖附近和少量板书区域发生变化。

后续会继续针对 1920×1080 / 60fps 原始录课素材测试 15fps、20fps、30fps，以及 H.265 / AV1 的体积与书写连续性。
