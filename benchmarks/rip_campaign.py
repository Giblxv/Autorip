"""Campanha adaptativa com sequência de recusas e prazo absoluto opcionais.

Não publica nem faz merge. --apply grava somente engine.py, prt.py e morph.py.
Hipóteses não aplicáveis não contam como rodadas. Os PRTs devem ser idênticos
à base inicial em todos os cenários; cada aceite zera a sequência de recusas.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import platform
import statistics
import struct
import subprocess
import sys
import time
import tracemalloc

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import numpy as np
from PIL import Image, ImageCms
from autorip.config import Settings
from rip_candidates import CANDIDATES

FILES={'engine':'autorip/engine.py','prt':'autorip/prt.py','morph':'autorip/morph.py'}
DEADLINE = None
REPORT_PATH = None


class CampaignDeadline(Exception):
    pass


def check_deadline():
    if DEADLINE is not None and time.time() >= DEADLINE:
        raise CampaignDeadline('Prazo da campanha atingido; rodada incompleta não contabilizada')


def digest(bundle):
    return hashlib.sha256(''.join(bundle[k] for k in sorted(bundle)).encode()).hexdigest()


def load(bundle,folder,index):
    folder.mkdir(parents=True,exist_ok=True)
    loaded={}
    for key in ('prt','morph','engine'):
        path=folder/f'{key}.py';path.write_text(bundle[key])
        spec=importlib.util.spec_from_file_location(f'autorip._campaign_{index}_{key}',path)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        loaded[key]=module
    loaded['engine'].PrtWriter=loaded['prt'].PrtWriter
    loaded['engine'].morph=loaded['morph']
    return loaded


def make_cases(folder,icc,suite="standard"):
    rng=np.random.default_rng(20261109)
    h,w=216,288
    data=rng.integers(0,256,(h,w,4),dtype=np.uint8)
    data[...,3]=np.linspace(0,255,w,dtype=np.uint8)[None,:]
    source=folder/'alpha.png';Image.fromarray(data,'RGBA').save(source)
    rgb=folder/'opaque.png';Image.fromarray(data[...,:3],'RGB').save(rgb)
    sparse=np.zeros_like(data);sparse[70:100,100:150]=data[70:100,100:150];sparse[70:100,100:150,3]=255
    sparse_path=folder/'sparse.png';Image.fromarray(sparse,'RGBA').save(sparse_path)
    large=folder/'large.png';Image.fromarray(rng.integers(0,256,((2000,2400,4) if suite in ('extended','input-icc','source-alpha','rgba-direct') else (1000,1200,4)),dtype=np.uint8),'RGBA').save(large)
    oriented=folder/'oriented.jpg';exif=Image.Exif();exif[274]=6
    Image.fromarray(data[...,:3],'RGB').save(oriented,exif=exif,dpi=(100,200))
    tiff=folder/'input.tiff';Image.fromarray(data,'RGBA').save(tiff,dpi=(100,200))
    common=dict(label_enabled=False,margin_top_in=.05,margin_bottom_in=.05,
                white_choke_mm=.1,white_fill_holes_mm=.3)
    def case(name,path,width=2.54,timed=True,cpu_limit=None,**kwargs):
        return dict(name=name,path=path,width=width,timed=timed,cpu_limit=cpu_limit,settings=Settings(**(common|kwargs)))
    cases = [case('alpha',source),case('icc',rgb,icc_path=icc or ''),
            case('no_white',rgb,white_enabled=False,mirror=False),
            case('sparse',sparse_path),case('large_source',large),
            case('low_dpi',source,timed=False,dpi_x=72,dpi_y=72),
            case('anisotropic',oriented,timed=False,dpi_x=300,dpi_y=600,label_enabled=True),
            case('tiff',tiff,timed=False,dpi_x=300,dpi_y=300),
            case('white_planes',source,timed=False,dpi_x=300,dpi_y=720,
                 channel_order=['M','Y','K','C'],white_planes=[4,7],white_density=.55),
            case('narrow',source,width=.013,timed=False,dpi_x=300,dpi_y=300)]
    if suite in ('extended','input-icc','source-alpha','rgba-direct'):
        for item in cases:
            item['timed'] = item['name'] in ('alpha','large_source')
        line=rng.integers(0,256,(1,400,3),dtype=np.uint8)
        banner=folder/'wide-opaque.png'
        Image.fromarray(np.repeat(line,40,axis=0),'RGB').save(banner)
        wide=folder/'wide-alpha.png'
        pixels=rng.integers(0,256,(80,400,4),dtype=np.uint8)
        pixels[...,3]=np.linspace(0,255,400,dtype=np.uint8)[None,:]
        Image.fromarray(pixels,'RGBA').save(wide)
        flat=folder/'flat-icc.png';Image.new('RGB',(100,100),(20,120,210)).save(flat)
        cases.extend([case('wide_opaque',banner,width=6000/720*2.54),
                      case('wide_alpha',wide,width=3000/720*2.54),
                      case('icc_two_cpu',rgb,icc_path=icc or '',cpu_limit=2),
                      case('icc_single_cpu',flat,width=1.7,icc_path=icc or '',cpu_limit=1,white_enabled=False),
                      case('wide_edges',source,width=3500/720*2.54,timed=False,dpi_y=300)])
    if suite in ('input-icc', 'source-alpha', 'rgba-direct'):
        if not icc:
            raise ValueError('A suite input-icc exige um perfil CMYK válido via --icc')
        srgb = ImageCms.createProfile('sRGB')
        rgb_image = Image.fromarray(data[..., :3].copy(), 'RGB')
        for name, mode, profile in [('source_rgb_icc', 'RGB', srgb),
                                    ('source_lab_icc', 'LAB', ImageCms.createProfile('LAB')),
                                    ('source_cmyk_icc', 'CMYK', ImageCms.getOpenProfile(icc))]:
            colored = ImageCms.profileToProfile(rgb_image, srgb, profile, outputMode=mode)
            wrapper = profile if isinstance(profile, ImageCms.ImageCmsProfile) else ImageCms.ImageCmsProfile(profile)
            embedded = wrapper.tobytes()
            path = folder / (name + '.tif')
            colored.save(path, icc_profile=embedded)
            colored.close()
            cases.append(case(name, path, width=1.27))
        rgb_image.close()
    if suite in ('source-alpha', 'rgba-direct'):
        embedded = ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
        for name, pixels in [('source_rgba_icc', data),
                             ('large_rgba_icc', rng.integers(0, 256, (1536, 2048, 4), dtype=np.uint8))]:
            image = Image.fromarray(pixels, 'RGBA')
            path = folder / (name + '.tif')
            image.save(path, icc_profile=embedded)
            image.close()
            cases.append(case(name, path, width=1.27))
        palette = Image.fromarray(data, 'RGBA').convert('P')
        path = folder / 'source_palette_icc.png'
        palette.save(path, icc_profile=embedded, transparency=bytes(range(256)))
        palette.close()
        cases.append(case('source_palette_icc', path, width=1.27))
    if suite == 'rgba-direct':
        embedded = bytearray(ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes())
        for index in range(struct.unpack_from('>I', embedded, 128)[0]):
            pos = 132 + index * 12
            if embedded[pos:pos + 4] == b'rTRC':
                offset = struct.unpack_from('>I', embedded, pos + 4)[0]
                assert embedded[offset:offset + 4] == b'para'
                struct.pack_into('>i', embedded, offset + 12, round(1.8 * 65536))
                break
        else:
            raise AssertionError('Perfil sem TRC paramétrica')
        for name, flat_color in [('rgba_gamma', False), ('rgba_gamma_flat', True)]:
            pixels = rng.integers(0, 256, (1536, 2048, 4), dtype=np.uint8)
            if flat_color:
                pixels[..., :3] = (100, 150, 200)
            pixels[..., 3] = np.linspace(0, 255, pixels.shape[1], dtype=np.uint8)[None, :]
            image = Image.fromarray(pixels, 'RGBA')
            path = folder / (name + '.tif')
            image.save(path, icc_profile=bytes(embedded), dpi=(100, 200))
            image.close()
            cases.append(case(name, path, width=1.27))
    return cases



def new_rip(module,case):
    original_cpu=os.cpu_count
    try:
        if case.get('cpu_limit'):os.cpu_count=lambda:case['cpu_limit']
        return module.Rip(case['settings'])
    finally:os.cpu_count=original_cpu


def render(rip,case,output,checksum=False):
    check_deadline()
    original_cpu=os.cpu_count
    try:
        if case.get('cpu_limit'):os.cpu_count=lambda:case['cpu_limit']
        info=rip.process(str(case['path']),str(output),width_cm=case['width'],
                         control=check_deadline if DEADLINE is not None else None)
    finally:os.cpu_count=original_cpu
    path=Path(info['output_path'])
    try:
        if checksum:return hashlib.sha256(path.read_bytes()).hexdigest()
    finally:path.unlink()


def micro_correct(original,candidate):
    rng=np.random.default_rng(127)
    for ratio in (.05,.4,.95):
        a=original['engine'].Rip(Settings(small_drop_ratio=ratio))
        b=candidate['engine'].Rip(Settings(small_drop_ratio=ratio))
        for y in (0,253,1025):
            t=a._thresholds(17,301,y)
            for values in (rng.random((17,301),dtype=np.float32),
                           np.asarray(t*ratio,dtype=np.float32),
                           np.asarray(t*(1-ratio)+ratio,dtype=np.float32)):
                for v in (values,np.nextafter(values,np.float32(0)),np.nextafter(values,np.float32(1))):
                    if not np.array_equal(a._halftone(v,y),b._halftone(v,y)):
                        return 'halftone-boundary'
    for dots in (1,3,4,31,32,37,129):
        a=rng.integers(0,4,(7,dots),dtype=np.uint8)
        pb=(dots+3)//4+3
        for view in (a,a[:,::-1],a.astype(np.int16)):
            if not np.array_equal(original['prt'].pack2(view,pb),candidate['prt'].pack2(view,pb)):
                return 'pack2-padding-strides'
    for dx,dy in ((300,300),(720,2400),(72,9600)):
        masks=[rng.random((23,37))>.4,np.zeros((1,1),bool),np.ones((13,19),bool)]
        for mm in (0,.01,.1,.3):
            for mask in masks:
                for method in ('erode','close_holes'):
                    a=getattr(original['morph'],method)(mask,mm,dx,dy)
                    b=getattr(candidate['morph'],method)(mask,mm,dx,dy)
                    if not np.array_equal(a,b):return f'{method}-physical-boundary'
    return None


def timed_pair(reference,candidate,cases,output,repeats):
    samples={c['name']:[[],[]] for c in cases}
    for c in cases:
        render(reference[c['name']],c,output);render(candidate[c['name']],c,output)
    for iteration in range(repeats):
        for ci,c in enumerate(cases):
            for side in ((0,1) if (iteration+ci)%2==0 else (1,0)):
                rip=(reference,candidate)[side][c['name']]
                start=time.perf_counter();render(rip,c,output)
                samples[c['name']][side].append(time.perf_counter()-start)
    ratios=[]
    for iteration in range(repeats):
        ratios.append(math.exp(statistics.mean(math.log(s[0][iteration]/s[1][iteration]) for s in samples.values())))
    rng=np.random.default_rng(447)
    bootstrap=np.median(np.asarray(ratios)[rng.integers(0,repeats,(3000,repeats))],axis=1)
    stats={name:{'reference_seconds':statistics.median(s[0]),'candidate_seconds':statistics.median(s[1]),
                 'speedup':statistics.median(s[0])/statistics.median(s[1])} for name,s in samples.items()}
    return {'scenarios':stats,'geomean_speedup':math.exp(statistics.mean(math.log(s['speedup']) for s in stats.values())),
            'paired_median_speedup':statistics.median(ratios),
            'bootstrap_95_low':float(np.percentile(bootstrap,2.5)),
            'bootstrap_95_high':float(np.percentile(bootstrap,97.5)),'raw_seconds':samples}


def peak(rips,cases,output):
    result={}
    for c in cases:
        tracemalloc.start()
        try:
            render(rips[c['name']],c,output)
            result[c['name']]=tracemalloc.get_traced_memory()[1]/1024**2
        finally:tracemalloc.stop()
    return result


def main():
    global DEADLINE, REPORT_PATH
    started_at = datetime.now(timezone.utc).isoformat()
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work-dir',type=Path,required=True)
    parser.add_argument('--icc',type=Path)
    parser.add_argument('--rounds-without-gain',type=int,default=15)
    parser.add_argument('--repeats',type=int,default=7)
    parser.add_argument('--apply',action='store_true')
    parser.add_argument('--suite',choices=['standard','extended','input-icc','source-alpha','rgba-direct'],default='standard')
    parser.add_argument('--resume',action='store_true')
    parser.add_argument('--baseline-ref',help='Commit/tag Git da base; leitura sem checkout')
    parser.add_argument('--deadline',help='Prazo ISO 8601 com fuso, por exemplo 2026-11-11T22:00:00-03:00')
    args=parser.parse_args()
    if args.deadline:
        try:
            deadline = datetime.fromisoformat(args.deadline)
            if deadline.tzinfo is None or deadline.utcoffset() is None:
                raise ValueError('Informe o fuso horário no prazo')
            DEADLINE = deadline.timestamp()
        except ValueError as error:
            parser.error(str(error))
        if DEADLINE <= time.time():
            parser.error('O prazo informado já terminou')
    if args.suite in ('extended','input-icc','source-alpha','rgba-direct'):
        from rip_wide_candidates import CANDIDATES as proposals
    else:
        proposals=CANDIDATES
    if args.suite == 'rgba-direct':
        from rip_rgba_candidates import CANDIDATES as proposals
    if args.suite in ('input-icc','source-alpha','rgba-direct') and not args.icc:
        parser.error('Esta suíte exige --icc com um perfil CMYK válido')
    if args.repeats<5 or args.rounds_without_gain<15:parser.error('Minimos: 5 repeticoes e 15 rodadas sem ganho')
    work=args.work_dir.resolve();work.mkdir(parents=True,exist_ok=True)
    REPORT_PATH = work/'report.json'
    previous_report = json.loads((work/'report.json').read_text()) if args.resume else None
    if args.resume:
        initial={k:(work/'initial'/f'{k}.py').read_text() for k in FILES}
    elif args.baseline_ref:
        initial={k:subprocess.check_output(['git','show',f'{args.baseline_ref}:{path}'],cwd=ROOT,text=True)
                 for k,path in FILES.items()}
    else:
        initial={k:(ROOT/path).read_text() for k,path in FILES.items()}
    leader = {k:(ROOT/p).read_text() for k,p in FILES.items()} if args.resume else dict(initial)
    if args.resume and digest(leader) != previous_report['leader_hash']:
        raise RuntimeError('Codigo local diverge do lider salvo; retomada recusada')
    if not args.resume:
        for k,source in initial.items():
            path=work/'initial'/f'{k}.py';path.parent.mkdir(exist_ok=True);path.write_text(source)
    original=load(initial,work/'initial_modules','initial')
    cases=make_cases(work,str(args.icc.resolve()) if args.icc else None,args.suite)
    timed=[c for c in cases if c['timed']]
    output=work/'output.PRT'
    baseline_rips={c['name']:new_rip(original['engine'],c) for c in cases}
    oracle={c['name']:render(baseline_rips[c['name']],c,output,True) for c in cases}
    for rip in baseline_rips.values():
        if rip.icc_error:raise RuntimeError(rip.icc_error)
    report={'base_commit':subprocess.check_output(['git','rev-parse',args.baseline_ref or 'HEAD'],cwd=ROOT,text=True).strip(),
            'python':platform.python_version(),'platform':platform.platform(),'cpu_count':os.cpu_count(),
            'cpu_affinity':sorted(os.sched_getaffinity(0)) if hasattr(os,'sched_getaffinity') else None,
            'benchmark_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'correctness_case_count':len(cases),'timed_case_count':len(timed),
            'icc_used':bool(args.icc),'suite':args.suite,'repeats':args.repeats,'required_without_gain':args.rounds_without_gain,
            'acceptance':{'minimum_speedup':1.015,'bootstrap_low_minimum':1.005,'max_case_slowdown':1.06,
                          'memory_alternative_reduction':.08,'peak_limit_mib':512},
            'rounds':[],'consecutive_without_gain':0,'complete':False}
    if previous_report:
        if previous_report.get('suite','standard') != args.suite:
            raise RuntimeError('Suite diferente da campanha persistida')
        report=previous_report
    report['deadline_utc'] = datetime.fromtimestamp(DEADLINE, timezone.utc).isoformat() if DEADLINE else None
    report.setdefault('started_at_utc', started_at)
    report['unique_candidate_per_leader'] = True
    index=len(report['rounds']);cursor=0;skips=0;accepted_hashes={digest(initial)}
    accepted_hashes.update(r['candidate_hash'] for r in report['rounds'] if r['accepted'])
    if report['rounds']:
        last=report['rounds'][-1]['candidate']
        cursor=next(i+1 for i,c in enumerate(proposals) if c[0]==last)
    tested = {(r['leader_before'], r['candidate_hash']) for r in report['rounds']}
    def save():
        report['leader_hash']=digest(leader)
        temporary=work/'report.tmp';temporary.write_text(json.dumps(report,indent=2));temporary.replace(work/'report.json')
    while report['consecutive_without_gain']<args.rounds_without_gain:
        check_deadline()
        name,hypothesis,proposal=proposals[cursor%len(proposals)];cursor+=1
        bundle=proposal(leader)
        key = (digest(leader), digest(bundle)) if bundle is not None else None
        if bundle is None or bundle==leader or key in tested:
            skips+=1
            if skips>len(proposals)*2:raise RuntimeError('Sem hipoteses aplicaveis suficientes; nao declarar convergencia')
            continue
        skips=0;index+=1
        tested.add(key)
        record={'round':index,'candidate':name,'hypothesis':hypothesis,'leader_before':digest(leader),
                'candidate_hash':digest(bundle),'accepted':False}
        directory=work/f'round-{index:03}-{name}'
        (work/'status.json').write_text(json.dumps({'round':index,'candidate':name,'phase':'correctness',
                                                   'consecutive_without_gain':report['consecutive_without_gain']}))
        try:
            module=load(bundle,directory,index)
            mismatch=micro_correct(original,module)
            candidate_rips={c['name']:new_rip(module['engine'],c) for c in cases}
            if mismatch is None:
                for c in cases:
                    if render(candidate_rips[c['name']],c,output,True)!=oracle[c['name']]:
                        mismatch='PRT-'+c['name'];break
            if mismatch:
                record['reason']='different-output';record['failure']=mismatch
            else:
                reference_module=load(leader,work/'leader_modules',f'leader{index}')
                reference_rips={c['name']:new_rip(reference_module['engine'],c) for c in timed}
                (work/'status.json').write_text(json.dumps({'round':index,'candidate':name,'phase':'measurement'}))
                measurement=timed_pair(reference_rips,candidate_rips,timed,output,args.repeats)
                record['measurement']=measurement
                fastest=measurement['geomean_speedup']>1.015 and measurement['bootstrap_95_low']>1.005
                stable=all(s['speedup']>=1/1.06 for s in measurement['scenarios'].values())
                # Meça memória fora do cronômetro. Não inclui RSS não rastreado.
                candidate_peak=peak(candidate_rips,timed,output)
                reference_peak=peak(reference_rips,timed,output)
                record['peak_mib']={'reference':reference_peak,'candidate':candidate_peak}
                memory_gain=max(candidate_peak.values())<=.92*max(reference_peak.values())
                memory_safe=max(candidate_peak.values())<=512
                memory_only=memory_gain and measurement['geomean_speedup']>=.99 and stable
                if (fastest or memory_only) and stable and memory_safe and digest(bundle) not in accepted_hashes:
                    # Segunda bateria e controle A/A antes de alterar o líder.
                    (work/'status.json').write_text(json.dumps({'round':index,'candidate':name,'phase':'confirmation'}))
                    confirmation=timed_pair(reference_rips,candidate_rips,timed,output,args.repeats)
                    record['confirmation']=confirmation
                    confirmed_speed=(confirmation['geomean_speedup']>1.015 and confirmation['bootstrap_95_low']>1.005)
                    confirmed_memory=(memory_gain and confirmation['geomean_speedup']>=.99)
                    confirmed_stable=all(s['speedup']>=1/1.06 for s in confirmation['scenarios'].values())
                    noise_stable = False
                    if (confirmed_speed or confirmed_memory) and confirmed_stable:
                        (work/'status.json').write_text(json.dumps({'round':index,'candidate':name,'phase':'aa-control'}))
                        aa = timed_pair(reference_rips,reference_rips,timed,output,args.repeats)
                        record['aa_control'] = aa
                        noise_stable = (.985 <= aa['geomean_speedup'] <= 1.015
                                        and all(1/1.03 <= s['speedup'] <= 1.03 for s in aa['scenarios'].values()))
                        record['aa_control_stable'] = noise_stable
                    if (confirmed_speed or confirmed_memory) and confirmed_stable and noise_stable:
                        leader=bundle;accepted_hashes.add(digest(bundle));record['accepted']=True
                        record['reason']='confirmed-speed' if confirmed_speed else 'confirmed-memory'
                        report['consecutive_without_gain']=0
                        if args.apply:
                            for key,path in FILES.items():(ROOT/path).write_text(leader[key])
                if not record['accepted']:
                    record['reason']=('inconclusive-aa-noise' if record.get('aa_control_stable') is False
                                      else 'no-confirmed-gain-or-regression')
        except CampaignDeadline:
            raise
        except Exception as error:
            record['reason']='infrastructure-error';record['failure']=f'{type(error).__name__}: {error}'
            (work/'error.json').write_text(json.dumps(record,indent=2))
            raise  # Erro de implementação/infraestrutura não conta como rodada sem ganho.
        if not record['accepted']:report['consecutive_without_gain']+=1
        record['consecutive_without_gain']=report['consecutive_without_gain']
        report['rounds'].append(record);save()
        print(json.dumps({k:record.get(k) for k in ('round','candidate','accepted','reason','failure','consecutive_without_gain')}),flush=True)
    report['complete']=True
    report['stop_reason']='consecutive-without-gain'
    report['accepted_count']=sum(r['accepted'] for r in report['rounds'])
    final=load(leader,work/'final_modules','final')
    final_rips={c['name']:new_rip(final['engine'],c) for c in timed}
    report['final_comparison']=timed_pair(baseline_rips,final_rips,timed,output,args.repeats)
    report['final_peak_mib']={'baseline':peak(baseline_rips,timed,output),'final':peak(final_rips,timed,output)}
    report['stopped_at_utc'] = datetime.now(timezone.utc).isoformat()
    save()
    print(json.dumps({'complete':True,'rounds':index,'accepted':report['accepted_count'],
                      'consecutive_without_gain':report['consecutive_without_gain']}),flush=True)


if __name__=='__main__':
    try:
        main()
    except CampaignDeadline as error:
        report = json.loads(REPORT_PATH.read_text()) if REPORT_PATH and REPORT_PATH.exists() else {'rounds':[],'consecutive_without_gain':0}
        converged = report['consecutive_without_gain'] >= report.get('required_without_gain',float('inf'))
        report.update(complete=converged,stop_reason='consecutive-without-gain' if converged else 'deadline',
                      interrupted_round_counted=False,stopped_at_utc=datetime.now(timezone.utc).isoformat())
        if converged:
            report['final_validation_interrupted_by_deadline'] = True
        if REPORT_PATH:
            REPORT_PATH.write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps({'stop_reason':'deadline','message':str(error)}),flush=True)
