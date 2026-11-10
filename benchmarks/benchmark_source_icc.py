"""Compara lotes de RIP com perfis ICC embutidos, incluindo cache frio e RSS.

python benchmarks/benchmark_source_icc.py --baseline-ref dd490f9 --icc /caminho/cmyk.icc --output /tmp/input-icc.json
python benchmarks/benchmark_source_icc.py --suite alpha --baseline-ref feb3214 --icc /caminho/cmyk.icc --output /tmp/input-alpha.json
"""
import argparse
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import platform
import queue
import statistics
import struct
import subprocess
import sys
import tempfile
import threading
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import numpy as np
from PIL import Image,ImageCms
from autorip.config import Settings


def load(path,name):
    spec=importlib.util.spec_from_file_location('autorip._input_icc_'+name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def run(rip,case,root):
    elapsed=0;cpu_elapsed=0;outputs=[]
    for index,source in enumerate(case['files']):
        started=time.perf_counter()
        cpu_started=time.process_time()
        info=rip.process(source,str(root/f'output-{index}.PRT'),width_cm=case['width_cm'])
        cpu_elapsed+=time.process_time()-cpu_started
        elapsed+=time.perf_counter()-started
        path=Path(info.pop('output_path'))
        try:outputs.append(dict(sha256=hashlib.sha256(path.read_bytes()).hexdigest(),metadata=info))
        finally:path.unlink()
    rip._benchmark_cpu_seconds=cpu_elapsed
    return elapsed,outputs


def peak_rss():
    if sys.platform.startswith('linux'):
        line=next(s for s in Path('/proc/self/status').read_text().splitlines() if s.startswith('VmHWM:'))
        return int(line.split()[1])/1024
    try:
        import resource
        value=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return value/(1024**2 if sys.platform=='darwin' else 1024)
    except ImportError:return None


class TimingWorker:
    """Um Rip persistente por processo, sem compartilhar o alocador entre versões."""
    def __init__(self, module_path, case_path):
        self.errors = tempfile.TemporaryFile(mode='w+t', encoding='utf-8')
        try:
            self.process = subprocess.Popen([sys.executable, str(Path(__file__).resolve()),
                '--timing-worker', str(module_path), '--case', str(case_path)],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.errors,
                text=True, bufsize=1)
        except BaseException:
            self.errors.close()
            raise
        self.responses = queue.Queue()
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()

    def _read(self):
        try:
            for line in self.process.stdout:
                self.responses.put(json.loads(line))
        except Exception as error:
            self.responses.put(error)
        finally:
            self.responses.put(None)

    def run(self):
        self.process.stdin.write('{}\n');self.process.stdin.flush()
        try:
            response = self.responses.get(timeout=180)
        except queue.Empty as error:
            raise TimeoutError('Worker de medição excedeu 180 segundos') from error
        if response is None or isinstance(response, Exception):
            self.errors.seek(0)
            raise RuntimeError('Worker de medição falhou: ' + self.errors.read()[-5000:])
        return response['seconds'], response['outputs'], response['cpu_seconds']

    def close(self):
        try:
            self.process.stdin.close()
        except (BrokenPipeError, OSError):
            pass
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill();self.process.wait(timeout=5)
        self.reader.join(timeout=1)
        self.process.stdout.close();self.errors.close()


def alpha_fixtures(root, icc, direct=False):
    """Grandes fontes com alfa, controles e transparência por paleta/chave."""
    profiles = {name: ImageCms.ImageCmsProfile(ImageCms.createProfile(name)).tobytes()
                for name in ('sRGB', 'LAB')}
    if direct:
        gamma = bytearray(profiles['sRGB'])
        for index in range(struct.unpack_from('>I', gamma, 128)[0]):
            pos = 132 + index * 12
            if gamma[pos:pos + 4] == b'rTRC':
                offset = struct.unpack_from('>I', gamma, pos + 4)[0]
                assert gamma[offset:offset + 4] == b'para'
                struct.pack_into('>i', gamma, offset + 12, round(1.8 * 65536))
                break
        else:
            raise AssertionError('Perfil sem TRC paramétrica')
        profiles['gamma_rgb'] = bytes(gamma)
    paths = {}
    kinds = [('large_rgba', 'RGBA', 'TIFF', (4096, 3072)),
             ('large_rgb', 'RGB', 'TIFF', (4096, 3072)),
             ('png_rgba', 'RGBA', 'PNG', (2048, 1536)),
             ('oriented_rgba', 'RGBA', 'TIFF', (2048, 1536)),
             ('small_rgba', 'RGBA', 'PNG', (320, 240)),
             ('no_icc', 'RGBA', 'TIFF', (4096, 3072)),
             ('palette', 'P', 'PNG', (1024, 768)),
             ('color_key', 'RGB', 'PNG', (1024, 768)),
             ('lab_control', 'LAB', 'TIFF', (2048, 1536))]
    if direct:
        kinds.append(('large_rgba_gamma', 'RGBA', 'TIFF', (4096, 3072)))
    for name, mode, fmt, size in kinds:
        files = []
        for index in range(4 if name == 'small_rgba' else 2):
            width, height = size
            y, x = np.indices((height, width), dtype=np.uint16)
            pixels = np.empty((height, width, 4), np.uint8)
            pixels[..., 0] = (x * 3 + y + index * 17) % 256
            pixels[..., 1] = (x + y * 2 + index * 11) % 256
            pixels[..., 2] = (x * 5 + y * 3) % 256
            pixels[..., 3] = np.linspace(0, 255, width, dtype=np.uint8)[None, :]
            image = Image.fromarray(pixels, 'RGBA')
            if mode == 'LAB':
                image = ImageCms.profileToProfile(image.convert('RGB'),
                    ImageCms.createProfile('sRGB'), ImageCms.createProfile('LAB'), outputMode='LAB')
            elif mode != 'RGBA':
                image = image.convert(mode)
            options = dict(icc_profile=profiles['LAB' if mode == 'LAB' else 'sRGB'], dpi=(100, 200))
            if name == 'large_rgba_gamma':
                options['icc_profile'] = profiles['gamma_rgb']
            if name == 'no_icc':
                options['icc_profile'] = b''
            if name == 'oriented_rgba':
                exif = Image.Exif(); exif[274] = 6; options['exif'] = exif
            if name == 'palette':
                options['transparency'] = bytes(range(256))
            if name == 'color_key':
                options['transparency'] = (0, 0, 0)
            path = root / f'{name}-{index}.{fmt.lower()}'
            image.save(path, **options); image.close(); files.append(str(path))
            del pixels, x, y
        paths[name] = files
    common = dict(label_enabled=False, margin_top_in=.05, margin_bottom_in=.05)
    cases = [dict(name=name, files=files, width_cm=1.27, settings=common, cold=False)
             for name, files in paths.items()]
    cases.append(dict(name='first_rgba', files=paths['large_rgba'][:1], width_cm=1.27,
                      settings=common, cold=True))
    if direct:
        mixed = []
        for index, source in enumerate(paths['small_rgba'][:2]):
            path = root / f'small_rgb-{index}.tif'
            with Image.open(source) as image:
                rgb = image.convert('RGB')
                try:
                    rgb.save(path, icc_profile=profiles['sRGB'], dpi=(100, 200))
                finally:
                    rgb.close()
            mixed.extend((source, str(path)))
        cases.append(dict(name='mixed_rgb_rgba', files=mixed, width_cm=1.27,
                          settings=common, cold=False))
    if icc:
        profiles['output_CMYK'] = Path(icc).read_bytes()
        cases.append(dict(name='rgba_output_icc', files=paths['png_rgba'], width_cm=1.27,
                          settings=dict(common, icc_path=icc), cold=False))
    return cases, {name: hashlib.sha256(data).hexdigest() for name, data in profiles.items()}


def fixtures(root,icc,suite='profiles'):
    if suite in ('alpha', 'rgba-direct'):
        return alpha_fixtures(root, icc, direct=suite == 'rgba-direct')
    profiles={name:ImageCms.ImageCmsProfile(ImageCms.createProfile(name)).tobytes() for name in ('sRGB','LAB')}
    oversized=bytearray(profiles['LAB']);oversized.extend(b'\0'*(2*1024*1024+256-len(oversized)));oversized[:4]=len(oversized).to_bytes(4,'big')
    profiles['large']=bytes(oversized)
    if icc:profiles['CMYK']=Path(icc).read_bytes()
    paths={}
    for name,mode,size in [('rgb','RGBA',(320,240)),('lab','LAB',(320,240)),('plain','RGBA',(320,240)),
                           ('large_lab','LAB',(2048,1536)),('large_flat_lab','LAB',(2048,1536)),
                           ('oversized','LAB',(320,240))]+([('cmyk','CMYK',(320,240))] if icc else []):
        files=[]
        for index in range(2 if name.startswith('large') else 8):
            width,height=size
            y,x=np.indices((height,width),dtype=np.uint16)
            pixels=np.empty((height,width,4),np.uint8)
            pixels[...,0]=(x*3+y+index*17)%256;pixels[...,1]=(x+y*2+index*11)%256
            pixels[...,2]=(x*5+y*3)%256;pixels[...,3]=np.linspace(0,255,width,dtype=np.uint8)[None,:]
            if name=='large_flat_lab':pixels[:]=(150,180,200,255)
            if mode=='LAB':image=Image.fromarray(pixels[...,:3].copy(),'LAB')
            elif mode=='CMYK':image=Image.fromarray(pixels,'CMYK')
            else:image=Image.fromarray(pixels,'RGBA')
            profile=profiles['LAB'] if mode=='LAB' else profiles['CMYK'] if mode=='CMYK' else profiles['sRGB']
            if name=='plain':profile=b''
            if name=='oversized':profile=profiles['large']
            path=root/f'{name}-{index}.tif';image.save(path,icc_profile=profile);image.close();files.append(str(path))
        paths[name]=files
    common=dict(label_enabled=False,margin_top_in=.05,margin_bottom_in=.05)
    def case(name,files,cold=False):return dict(name=name,files=files,width_cm=1.27,settings=common,cold=cold)
    cases=[case('rgb_repeated',paths['rgb']),case('lab_repeated',paths['lab'])]
    if icc:cases.append(case('cmyk_repeated',paths['cmyk']))
    kinds=['rgb','lab']+(['cmyk'] if icc else [])
    mixed=[paths[kinds[index%len(kinds)]][index] for index in range(8)]
    cases.extend([case('mixed_profiles',mixed),case('first_lab',paths['lab'][:1],cold=True),
                  case('no_icc',paths['plain']),case('large_lab',paths['large_lab']),
                  case('large_flat_lab',paths['large_flat_lab']),case('over_budget',paths['oversized'])])
    return cases,{name:hashlib.sha256(data).hexdigest() for name,data in profiles.items()}


def builds(module,case,root):
    rip=module.Rip(Settings(**case['settings']))
    original=ImageCms.ImageCmsTransform;count=0
    def track(*args,**kwargs):
        nonlocal count
        count+=1;return original(*args,**kwargs)
    ImageCms.ImageCmsTransform=track
    try:
        run(rip,case,root);cold=count
        if case['cold']:return dict(first_batch=cold,next_batch=None)
        count=0;run(rip,case,root);return dict(first_batch=cold,next_batch=count)
    finally:ImageCms.ImageCmsTransform=original


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-ref',default='dd490f9');parser.add_argument('--repeat',type=int,default=7)
    parser.add_argument('--icc',type=Path);parser.add_argument('--output',type=Path)
    parser.add_argument('--suite',choices=['profiles','alpha','rgba-direct'],default='profiles')
    parser.add_argument('--rss-worker',type=Path);parser.add_argument('--case',type=Path)
    parser.add_argument('--timing-worker',type=Path)
    parser.add_argument('--paired-workers',action='store_true',help='Isolar as duas versões em processos persistentes por cenário')
    args=parser.parse_args()
    if args.timing_worker:
        case=json.loads(args.case.read_text());module=load(args.timing_worker,'timing')
        rip=module.Rip(Settings(**case['settings']))
        with tempfile.TemporaryDirectory(prefix='autorip-input-icc-timing-') as folder:
            for line in sys.stdin:
                json.loads(line)
                if case['cold']:rip=module.Rip(Settings(**case['settings']))
                seconds,outputs=run(rip,case,Path(folder))
                print(json.dumps(dict(seconds=seconds,outputs=outputs,cpu_seconds=rip._benchmark_cpu_seconds)),flush=True)
        return
    if args.rss_worker:
        case=json.loads(args.case.read_text());module=load(args.rss_worker,'rss');rip=module.Rip(Settings(**case['settings']))
        with tempfile.TemporaryDirectory(prefix='autorip-input-icc-rss-') as folder:
            _,outputs=run(rip,case,Path(folder))
            if not case['cold']:_,outputs=run(rip,case,Path(folder))
            local=getattr(rip,'_source_transforms',None)
            cache=getattr(local,'cache',{})
            print(json.dumps(dict(peak_rss_mib=peak_rss(),outputs=outputs,cache_entries=len(cache),
                                  cached_profile_bytes=getattr(local,'profile_bytes',0))))
        return
    if args.output is None or args.repeat<5:parser.error('Use --output e pelo menos cinco repetições')
    commit=subprocess.check_output(['git','rev-parse',args.baseline_ref],cwd=ROOT,text=True).strip()
    source=subprocess.check_output(['git','show',commit+':autorip/engine.py'],cwd=ROOT,text=True)
    shared={}
    for name in ('morph','prt'):
        original=subprocess.check_output(['git','show',commit+':autorip/'+name+'.py'],cwd=ROOT,text=True)
        if (ROOT/'autorip'/(name+'.py')).read_text()!=original:parser.error('morph.py/prt.py precisam ser idênticos à base')
        shared[name]=hashlib.sha256(original.encode()).hexdigest()
    candidate=ROOT/'autorip/engine.py'
    report=dict(baseline_ref=commit,suite=args.suite,repeat=args.repeat,python=platform.python_version(),platform=platform.platform(),
                pillow=Image.__version__,numpy=np.__version__,cpu_count=os.cpu_count(),
                source_sha256=dict(baseline=hashlib.sha256(source.encode()).hexdigest(),candidate=hashlib.sha256(candidate.read_bytes()).hexdigest()),
                benchmark_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                timing_processes='separate persistent workers per implementation/case' if args.paired_workers else 'shared parent process',
                cpu_affinity=sorted(os.sched_getaffinity(0)) if hasattr(os,'sched_getaffinity') else None,
                cpu_metric='time.process_time summed around Rip.process, including threads; verification excluded',
                shared_modules_sha256=shared,rss_metric='VmHWM of fresh Linux workers; ru_maxrss on other Unix; unavailable on Windows',scenarios={})
    with tempfile.TemporaryDirectory(prefix='autorip-input-icc-') as folder:
        root=Path(folder);baseline=root/'baseline.py';baseline.write_text(source)
        cases,profiles=fixtures(root,str(args.icc.resolve()) if args.icc else None,args.suite);report['profile_sha256']=profiles
        modules=[load(baseline,'baseline'),load(candidate,'candidate')]
        for case in cases:
            rips=[] if args.paired_workers else [module.Rip(Settings(**case['settings'])) for module in modules]
            oracle=None;samples=[[],[]];cpu_samples=[[],[]];workers=[]
            case_path=root/'timing-case.json';case_path.write_text(json.dumps(case))
            try:
                if args.paired_workers:
                    for path in (baseline,candidate):workers.append(TimingWorker(path,case_path))
                def measured(side):
                    if workers:return workers[side].run()
                    if case['cold']:rips[side]=modules[side].Rip(Settings(**case['settings']))
                    seconds,outputs=run(rips[side],case,root)
                    return seconds,outputs,rips[side]._benchmark_cpu_seconds
                for side in range(2):
                    _,outputs,_=measured(side)
                    if oracle is None:oracle=outputs
                    assert outputs==oracle,case['name']
                for iteration in range(args.repeat):
                    for side in ((0,1) if iteration%2==0 else (1,0)):
                        elapsed,outputs,cpu_elapsed=measured(side)
                        assert outputs==oracle,case['name'];samples[side].append(elapsed)
                        cpu_samples[side].append(cpu_elapsed)
            finally:
                for worker in workers:worker.close()
            old,new=map(statistics.median,samples);ratios=np.asarray(samples[0])/np.asarray(samples[1]);rng=np.random.default_rng(194)
            bootstrap=np.median(ratios[rng.integers(0,args.repeat,(3000,args.repeat))],axis=1)
            cpu_old,cpu_new=map(statistics.median,cpu_samples)
            cpu_ratios=np.asarray(cpu_samples[0])/np.asarray(cpu_samples[1])
            cpu_bootstrap=np.median(cpu_ratios[rng.integers(0,args.repeat,(3000,args.repeat))],axis=1)
            peaks={};counts={};case_path=root/'case.json';case_path.write_text(json.dumps(case))
            for side,path in [('baseline',baseline),('candidate',candidate)]:
                values=[];cache=None
                for _ in range(2):
                    result=json.loads(subprocess.check_output([sys.executable,str(Path(__file__).resolve()),'--rss-worker',str(path),'--case',str(case_path)],text=True))
                    assert result['outputs']==oracle,case['name'];values.append(result['peak_rss_mib']);cache={k:result[k] for k in ['cache_entries','cached_profile_bytes']}
                peaks[side]=dict(samples_mib=values,median_mib=statistics.median(values) if all(v is not None for v in values) else None,**cache)
            for side,module in zip(['baseline','candidate'],modules):counts[side]=builds(module,case,root)
            result=dict(files=len(case['files']),cold=case['cold'],baseline_seconds=old,candidate_seconds=new,speedup=old/new,raw_seconds=samples,
                        baseline_cpu_seconds=cpu_old,candidate_cpu_seconds=cpu_new,cpu_speedup=cpu_old/cpu_new,cpu_raw_seconds=cpu_samples,
                        cpu_paired_bootstrap_95=[float(v) for v in np.percentile(cpu_bootstrap,[2.5,97.5])],
                        paired_bootstrap_95=[float(v) for v in np.percentile(bootstrap,[2.5,97.5])],peak_rss=peaks,transform_builds=counts,outputs=oracle)
            report['scenarios'][case['name']]=result;print(json.dumps({case['name']:result}),flush=True)
        report['geomean_speedup']=math.exp(statistics.mean(math.log(r['speedup']) for r in report['scenarios'].values()))
        report['cpu_geomean_speedup']=math.exp(statistics.mean(math.log(r['cpu_speedup']) for r in report['scenarios'].values()))
        paired=[math.exp(statistics.mean(math.log(r['raw_seconds'][0][i]/r['raw_seconds'][1][i])
                    for r in report['scenarios'].values())) for i in range(args.repeat)]
        rng=np.random.default_rng(194)
        bootstrap=np.median(np.asarray(paired)[rng.integers(0,args.repeat,(3000,args.repeat))],axis=1)
        report['paired_geomean_median']=statistics.median(paired)
        report['paired_geomean_bootstrap_95']=[float(v) for v in np.percentile(bootstrap,[2.5,97.5])]
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':main()
