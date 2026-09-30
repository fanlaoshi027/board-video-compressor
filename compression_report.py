#!/usr/bin/env python3
from __future__ import annotations
from pathlib import Path
from datetime import datetime


def format_size(value: int | float) -> str:
    units = ['B', 'KB', 'MB', 'GB']
    size = float(value)
    for unit in units:
        if size < 1024:
            return f'{size:.1f} {unit}'
        size /= 1024
    return f'{size:.1f} TB'


def make_report(src: str, dst: str, analysis=None, extra=None) -> str:
    src_p = Path(src)
    dst_p = Path(dst)
    lines = [
        '樊老师板书视频压缩报告',
        '=' * 30,
        f'生成时间: {datetime.now():%Y-%m-%d %H:%M:%S}',
        '',
        '文件:',
        f'原视频: {src_p.name}',
        f'输出视频: {dst_p.name}',
        f'原大小: {format_size(src_p.stat().st_size) if src_p.exists() else "-"}',
        f'输出大小: {format_size(dst_p.stat().st_size) if dst_p.exists() else "-"}',
    ]
    if analysis:
        lines += [
            '',
            '板书分析:',
            f'模式: {getattr(analysis, "mode", "-")}',
            f'白底比例: {getattr(analysis, "white_ratio", 0):.2%}',
            f'局部变化比例: {getattr(analysis, "local_change_ratio", 0):.2%}',
        ]
    if extra:
        lines += ['', '编码设置:']
        lines += [f'{k}: {v}' for k, v in extra.items()]
    return '\n'.join(lines) + '\n'
