#!/usr/bin/env python3
from __future__ import annotations
import argparse
from pathlib import Path
from batch_queue import BatchQueue

VIDEO_EXTS={'.mp4','.mov','.mkv','.m4v','.avi','.webm','.wmv'}

def discover(folder): return sorted(p for p in Path(folder).iterdir() if p.is_file() and p.suffix.lower() in VIDEO_EXTS)

def main():
    ap=argparse.ArgumentParser(description='Board video batch queue')
    ap.add_argument('paths',nargs='+')
    ap.add_argument('--output-dir',default=None)
    args=ap.parse_args()
    q=BatchQueue(); paths=[]
    for raw in args.paths:
        p=Path(raw); paths.extend(discover(p) if p.is_dir() else [p])
    q.add(paths)
    for item in q.items:
        out_dir=Path(args.output_dir) if args.output_dir else item.source.parent
        item.output=out_dir/(item.source.stem+'_board.mp4')
        item.status='等待'
    for item in q.items:
        print(f'等待: {item.source.name} -> {item.output}')
    print(f'共 {len(q.items)} 个视频进入队列。')

if __name__=='__main__': main()
