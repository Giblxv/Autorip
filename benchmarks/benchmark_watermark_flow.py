"""Mede RIP + prévia com marcas repetidas, controles frios e SHA-256 de PRT/JPEG.

python benchmarks/benchmark_watermark_flow.py --baseline-ref 25fd1c0 --output /tmp/watermarks.json
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

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import numpy as np
from PIL import Image,ImageDraw
from autorip.config import Settings
from autorip.engine import Rip


def load(path,name):
    spec=importlib.util.spec_from_file_location('autorip._watermark_bench_'+name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def app_for(module,home,settings):
    app=SimpleNamespace(home=str(home),s=settings)
    if hasattr(module,'WatermarkCache'):app._watermark_cache=module.WatermarkCache()
    return app


def run(module,app,rip,case,root):
    stages=[0.0,0.0];outputs=[]
    if case['cold'] and hasattr(module,'WatermarkCache'):app._watermark_cache=module.WatermarkCache()
    for index in range(case['files']):
        if case.get('versions'):
            # Simule a atualização entre artes; copiar a configuração fica fora do cronômetro.
            Path(case['settings']['watermark_path']).write_bytes(Path(case['versions'][index%2]).read_bytes())
        started=time.perf_counter();info=rip.process(case['source'],str(root/f'out-{index}.PRT'),width_cm=case['width_cm']);stages[0]+=time.perf_counter()-started
        output=Path(info.pop('output_path'));started=time.perf_counter()
        url=module.App._thumb(app,f'job-{index}',case['source'],output_name=f'out-{index}')
        stages[1]+=time.perf_counter()-started;assert url,case['name']
        jpeg=Path(app.home)/'thumbs'/f'job-{index}.jpg';encoded=jpeg.read_bytes()
        assert encoded==(Path(app.home)/'thumbs'/'by_name'/f'out-{index}.jpg').read_bytes()
        try:outputs.append(dict(prt_sha256=hashlib.sha256(output.read_bytes()).hexdigest(),jpeg_sha256=hashlib.sha256(encoded).hexdigest(),metadata=info))
        finally:output.unlink()
    return stages,outputs


def fixtures(root):
    image=Image.new('RGBA',(4096,3072),(0,0,0,0));draw=ImageDraw.Draw(image)
    draw.rounded_rectangle((100,100,3996,2972),radius=450,fill=(25,140,230,190));draw.ellipse((1200,400,3000,2200),fill=(240,55,110,90))
    large=root/'large.png';image.save(large);small=root/'small.png';image.resize((640,480)).save(small)
    jpeg=root/'oriented.jpg';exif=Image.Exif();exif[274]=6
    image.convert('RGB').resize((2048,1536)).save(jpeg,exif=exif,dpi=(100,200));image.close()
    mark=Image.new('RGBA',(2048,2048),(240,55,110,127));draw=ImageDraw.Draw(mark);draw.ellipse((300,300,1748,1748),fill=(30,140,230,190))
    big=root/'mark.png';mark.save(big);tiny=root/'tiny.png';mark.resize((64,64)).save(tiny)
    tiff=root/'mark.tif';mark.save(tiff,exif=exif);mark.close()
    other=root/'other.png';Image.new('RGBA',(2048,2048),(20,140,230,127)).save(other)
    changing=root/'changing.png'
    common=dict(label_enabled=False,margin_top_in=.05,margin_bottom_in=.05,watermark_opacity=.35)
    def case(name,source,watermark,files=4,cold=False,versions=None):
        return dict(name=name,source=str(source),files=files,cold=cold,width_cm=1.27,
                    settings=common|dict(watermark_path=str(watermark) if watermark else ''),versions=[str(p) for p in versions] if versions else None)
    return [case('small_art_large_mark',small,big),case('large_art_large_mark',large,big,files=2),
            case('oriented_art_large_mark',jpeg,big,files=2),case('small_mark',small,tiny),
            case('first_use',small,big,files=1,cold=True),case('without_mark',small,None),
            case('changing_mark',small,changing,files=2,versions=[big,other]),case('oriented_tiff_mark',small,tiff)]


def rss():
    if sys.platform.startswith('linux'):
        line=next(s for s in Path('/proc/self/status').read_text().splitlines() if s.startswith('VmHWM:'))
        return int(line.split()[1])/1024
    try:
        import resource
        value=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return value/(1024**2 if sys.platform=='darwin' else 1024)
    except ImportError:return None


def reads(module,case,root):
    original=module._load_thumbnail;count=0
    def track(*args,**kwargs):
        nonlocal count
        if kwargs.get('orient') is False:count+=1
        return original(*args,**kwargs)
    module._load_thumbnail=track
    settings=Settings(**case['settings']);app=app_for(module,root/'counts',settings);rip=Rip(settings)
    try:
        _,outputs=run(module,app,rip,case,root);first=count
        if case['cold']:return dict(first_batch=first,next_batch=None)
        count=0;run(module,app,rip,case,root);return dict(first_batch=first,next_batch=count)
    finally:module._load_thumbnail=original


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-ref',default='25fd1c0');parser.add_argument('--repeat',type=int,default=7)
    parser.add_argument('--output',type=Path);parser.add_argument('--rss-worker',type=Path);parser.add_argument('--case',type=Path)
    args=parser.parse_args()
    if args.rss_worker:
        module=load(args.rss_worker,'rss');case=json.loads(args.case.read_text());settings=Settings(**case['settings']);rip=Rip(settings)
        with tempfile.TemporaryDirectory(prefix='autorip-wm-rss-') as folder:
            root=Path(folder);app=app_for(module,root/'app',settings);_,outputs=run(module,app,rip,case,root)
            if not case['cold']:_,outputs=run(module,app,rip,case,root)
            cache=getattr(app,'_watermark_cache',None)
            print(json.dumps(dict(peak_rss_mib=rss(),cache_entries=len(cache._images) if cache else 0,cached_pixel_bytes=cache._bytes if cache else 0,outputs=outputs)))
        return
    if args.output is None or args.repeat<5:parser.error('Use --output e pelo menos cinco repetições')
    commit=subprocess.check_output(['git','rev-parse',args.baseline_ref],cwd=ROOT,text=True).strip()
    original=subprocess.check_output(['git','show',commit+':autorip/server.py'],cwd=ROOT,text=True)
    shared={}
    for name in ['engine','prt','morph']:
        data=subprocess.check_output(['git','show',commit+':autorip/'+name+'.py'],cwd=ROOT,text=True)
        if (ROOT/'autorip'/(name+'.py')).read_text()!=data:parser.error('Este benchmark exige engine/prt/morph idênticos à base')
        shared[name]=hashlib.sha256(data.encode()).hexdigest()
    candidate=ROOT/'autorip/server.py'
    report=dict(baseline_ref=commit,repeat=args.repeat,python=platform.python_version(),platform=platform.platform(),pillow=Image.__version__,numpy=np.__version__,cpu_count=os.cpu_count(),
                source_sha256=dict(baseline=hashlib.sha256(original.encode()).hexdigest(),candidate=hashlib.sha256(candidate.read_bytes()).hexdigest(),watermarks=hashlib.sha256((ROOT/'autorip/watermarks.py').read_bytes()).hexdigest()),shared_modules_sha256=shared,
                rss_metric='VmHWM in fresh Linux workers; ru_maxrss on other Unix; unavailable on Windows',scenarios={})
    with tempfile.TemporaryDirectory(prefix='autorip-wm-bench-') as folder:
        root=Path(folder);baseline=root/'baseline.py';baseline.write_text(original);modules=[load(baseline,'baseline'),load(candidate,'candidate')]
        for case in fixtures(root):
            settings=Settings(**case['settings']);apps=[app_for(module,root/('old' if i==0 else 'new'),settings) for i,module in enumerate(modules)];rips=[Rip(settings),Rip(settings)]
            samples=[[],[]];stages=[[],[]];oracle=None
            for side in range(2):
                _,outputs=run(modules[side],apps[side],rips[side],case,root)
                if oracle is None:oracle=outputs
                assert outputs==oracle,case['name']
            for iteration in range(args.repeat):
                for side in ((0,1) if iteration%2==0 else (1,0)):
                    elapsed,outputs=run(modules[side],apps[side],rips[side],case,root);assert outputs==oracle,case['name']
                    samples[side].append(sum(elapsed));stages[side].append(elapsed)
            old,new=map(statistics.median,samples);ratios=np.asarray(samples[0])/np.asarray(samples[1]);rng=np.random.default_rng(194)
            bootstrap=np.median(ratios[rng.integers(0,args.repeat,(3000,args.repeat))],axis=1)
            peaks={};counts={};case_path=root/'case.json';case_path.write_text(json.dumps(case))
            for side,path in [('baseline',baseline),('candidate',candidate)]:
                values=[];last=None
                for _ in range(2):
                    last=json.loads(subprocess.check_output([sys.executable,str(Path(__file__).resolve()),'--rss-worker',str(path),'--case',str(case_path)],text=True));assert last['outputs']==oracle,case['name'];values.append(last['peak_rss_mib'])
                peaks[side]=dict(samples_mib=values,median_mib=statistics.median(values) if all(v is not None for v in values) else None,cache_entries=last['cache_entries'],cached_pixel_bytes=last['cached_pixel_bytes'])
            for side,module in zip(['baseline','candidate'],modules):counts[side]=reads(module,case,root)
            result=dict(files=case['files'],cold=case['cold'],baseline_seconds=old,candidate_seconds=new,speedup=old/new,raw_seconds=samples,raw_stages_rip_preview=stages,
                        median_stage_seconds={side:dict(rip=statistics.median(s[0] for s in stages[i]),preview=statistics.median(s[1] for s in stages[i])) for i,side in enumerate(['baseline','candidate'])},
                        paired_bootstrap_95=[float(v) for v in np.percentile(bootstrap,[2.5,97.5])],peak_rss=peaks,watermark_reads=counts,outputs=oracle)
            report['scenarios'][case['name']]=result;print(json.dumps({case['name']:result}),flush=True)
        report['geomean_speedup']=math.exp(statistics.mean(math.log(r['speedup']) for r in report['scenarios'].values()))
        paired=[math.exp(statistics.mean(math.log(r['raw_seconds'][0][i]/r['raw_seconds'][1][i]) for r in report['scenarios'].values())) for i in range(args.repeat)]
        rng=np.random.default_rng(194);bootstrap=np.median(np.asarray(paired)[rng.integers(0,args.repeat,(3000,args.repeat))],axis=1)
        report['paired_geomean_bootstrap_95']=[float(v) for v in np.percentile(bootstrap,[2.5,97.5])]
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':main()
