#!/usr/bin/env python3
from __future__ import annotations
import argparse
import json
from pathlib import Path
from dataclasses import dataclass,asdict
from smart_runner import build_smart_command,run
from compression_modes import get_mode
from adaptive_vfr_filter import build_profile,build_select_filter

@dataclass
class Result:
    mode:str
    output:str
    ok:bool
    size_bytes:int=0
    elapsed_seconds:float=0
    error:str=''

def run_one(src,mode_key,output,codec='h265',preset='board-balanced',width=None,height=None):
    import time
    src=Path(src); output=Path(output); mode=get_mode(mode_key); started=time.time()
    try:
        if mode_key=='board_vfr':
            profile=build_profile(str(src),min_fps=mode.min_fps,max_fps=mode.max_fps)
            filt=build_select_filter(profile,min_fps=mode.min_fps,max_fps=mode.max_fps)
            args=build_smart_command(str(src),str(output),codec=codec,fps='15',width=width,height=height,preset=preset,board_opt=True,duration=0)
            if '-vf' in args: args[args.index('-vf')+1]=filt
        else:
            fps='15' if mode_key=='fixed15' else '智能 VFR'
            args=build_smart_command(str(src),str(output),codec=codec,fps=fps,width=width,height=height,preset=preset,board_opt=True,duration=0)
        code,cancelled=run(args,cleanup_output=str(output))
        ok=(code==0 and not cancelled and output.exists())
        return Result(mode_key,str(output),ok,output.stat().st_size if ok else 0,time.time()-started,'' if ok else f'ffmpeg exit {code}')
    except Exception as e:
        return Result(mode_key,str(output),False,0,time.time()-started,str(e))

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('input'); ap.add_argument('--output-dir',default=None); ap.add_argument('--codec',default='h265'); ap.add_argument('--preset',default='board-balanced'); ap.add_argument('--width',type=int); ap.add_argument('--height',type=int); args=ap.parse_args()
    src=Path(args.input); outdir=Path(args.output_dir or src.parent); outdir.mkdir(parents=True,exist_ok=True)
    results=[]
    for mode in ('fixed15','smart_vfr','board_vfr'):
        out=outdir/f'{src.stem}_{mode}.mp4'; print(f'[{mode}] -> {out}')
        r=run_one(src,mode,out,args.codec,args.preset,args.width,args.height); results.append(r)
        print('  OK' if r.ok else f'  FAIL: {r.error}',f'{r.size_bytes/1024/1024:.1f} MB',f'{r.elapsed_seconds:.1f}s')
    report=outdir/f'{src.stem}_compression_compare.json'; report.write_text(json.dumps([asdict(x) for x in results],ensure_ascii=False,indent=2),encoding='utf-8'); print(f'Report: {report}')
if __name__=='__main__': main()
