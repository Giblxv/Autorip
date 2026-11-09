"""Compara a geração completa de miniaturas e o RSS em processos separados.

python benchmarks/benchmark_thumbnails.py --baseline-ref 57aea5b --output /tmp/thumbs.json
"""
import argparse
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
from PIL import Image, ImageDraw
from autorip.config import Settings


def load(path, name):
    spec=importlib.util.spec_from_file_location('autorip._thumb_'+name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def run(module, home, image, watermark=''):
    app=SimpleNamespace(home=str(home),s=Settings(watermark_path=watermark,watermark_opacity=.35))
    start=time.perf_counter()
    url=module.App._thumb(app,'bench',str(image),output_name='bench')
    elapsed=time.perf_counter()-start
    assert url=='/api/thumb?id=bench'
    first=(home/'thumbs'/'bench.jpg').read_bytes()
    assert first==(home/'thumbs'/'by_name'/'bench.jpg').read_bytes()
    return elapsed,hashlib.sha256(first).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-ref',default='57aea5b')
    parser.add_argument('--repeat',type=int,default=7)
    parser.add_argument('--output',type=Path)
    parser.add_argument('--rss-worker',type=Path)
    parser.add_argument('--image',type=Path)
    parser.add_argument('--watermark',default='')
    args=parser.parse_args()
    if args.rss_worker:
        module=load(args.rss_worker,'rss')
        with tempfile.TemporaryDirectory(prefix='autorip-thumb-rss-') as folder:
            _,digest=run(module,Path(folder),args.image,args.watermark)
            try:
                # ru_maxrss pode carregar o máximo do pai através de fork/exec.
                # VmHWM pertence ao espaço de memória atual do worker Linux.
                if sys.platform.startswith('linux'):
                    line=next(line for line in Path('/proc/self/status').read_text().splitlines() if line.startswith('VmHWM:'))
                    peak=int(line.split()[1])/1024
                else:
                    import resource
                    peak=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
                    peak/=1024**2 if sys.platform=='darwin' else 1024
            except (ImportError,OSError,StopIteration):
                peak=None
            print(json.dumps(dict(peak_rss_mib=peak,sha256=digest)))
        return
    if args.repeat<5 or args.output is None:parser.error('Use --output e pelo menos cinco repetições')
    commit=subprocess.check_output(['git','rev-parse',args.baseline_ref],cwd=ROOT,text=True).strip()
    with tempfile.TemporaryDirectory(prefix='autorip-thumbnails-') as folder:
        root=Path(folder)
        baseline_source=subprocess.check_output(['git','show',commit+':autorip/server.py'],cwd=ROOT,text=True)
        baseline=root/'baseline.py';baseline.write_text(baseline_source)
        candidate=ROOT/'autorip'/'server.py'
        modules=[load(baseline,'baseline'),load(candidate,'candidate')]
        for side in ('baseline','candidate'):(root/side).mkdir()
        image=Image.new('RGBA',(4096,3072),(0,0,0,0))
        draw=ImageDraw.Draw(image)
        draw.rounded_rectangle((100,100,3996,2972),radius=450,fill=(25,140,230,190))
        draw.ellipse((1200,400,3000,2200),fill=(240,55,110,90))
        large=root/'large.png';image.save(large)
        small=root/'small.png';image.resize((640,480)).save(small)
        jpeg=root/'rgb.jpg';image.convert('RGB').resize((3072,2048)).save(jpeg,quality=93)
        oriented=root/'oriented.jpg';exif=Image.Exif();exif[274]=6
        image.convert('RGB').resize((3072,2048)).save(oriented,quality=93,exif=exif)
        mark=root/'mark.png';Image.new('RGBA',(2048,2048),(250,80,50,127)).save(mark)
        del image,draw
        cases=[('small_rgba',small,''),('large_rgba',large,''),('rgb_jpeg',jpeg,''),
               ('oriented_jpeg',oriented,''),('watermark',large,str(mark))]
        report=dict(baseline_ref=commit,python=platform.python_version(),platform=platform.platform(),
                    pillow=Image.__version__,repeat=args.repeat,cpu_count=os.cpu_count(),
                    rss_metric='VmHWM of fresh Linux process; ru_maxrss on other Unix; unsupported on Windows',
                    source_sha256=dict(baseline=hashlib.sha256(baseline_source.encode()).hexdigest(),
                                       candidate=hashlib.sha256(candidate.read_bytes()).hexdigest()),scenarios={})
        for name,path,watermark in cases:
            samples=[[],[]];oracle=None
            for side in range(2):
                _,digest=run(modules[side],root/('baseline' if side==0 else 'candidate'),path,watermark)
                if oracle is None:oracle=digest
                assert oracle==digest,name
            for iteration in range(args.repeat):
                for side in ((0,1) if iteration%2==0 else (1,0)):
                    elapsed,digest=run(modules[side],root/('baseline' if side==0 else 'candidate'),path,watermark)
                    assert digest==oracle,name
                    samples[side].append(elapsed)
            ratios=np.array(samples[0])/np.array(samples[1])
            rng=np.random.default_rng(194)
            bootstrap=np.median(ratios[rng.integers(0,args.repeat,(3000,args.repeat))],axis=1)
            old,new=map(statistics.median,samples)
            peaks={}
            for side,source in (('baseline',baseline),('candidate',candidate)):
                command=[sys.executable,str(Path(__file__).resolve()),'--rss-worker',str(source),'--image',str(path),
                         '--watermark',watermark]
                peak=json.loads(subprocess.check_output(command,text=True))
                assert peak['sha256']==oracle,name
                peaks[side]=peak['peak_rss_mib']
            result=dict(baseline_seconds=old,candidate_seconds=new,speedup=old/new,raw_seconds=samples,
                        paired_bootstrap_95=[float(v) for v in np.percentile(bootstrap,[2.5,97.5])],
                        peak_rss_mib=peaks,jpeg_sha256=oracle)
            report['scenarios'][name]=result
            print(json.dumps({name:result}),flush=True)
        report['geomean_speedup']=math.exp(statistics.mean(math.log(v['speedup']) for v in report['scenarios'].values()))
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':main()
