"""Compara a main com o motor atual, incluindo os módulos morph/prt da base.

python benchmarks/benchmark_main_refinements.py --baseline-ref 718438e --pairs 15 --output /tmp/refinements.json
--cases-json permite medir arquivos grandes existentes sem gerar/copiar suas artes.
"""
import argparse
import hashlib
import importlib.util
import itertools
import json
import platform
from pathlib import Path
import random
import statistics
import subprocess
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import numpy as np
from PIL import Image
from autorip import engine
from autorip.config import Settings


def baseline(ref, root):
    modules={}
    for name in ('morph','prt','engine'):
        source=subprocess.check_output(['git','show',f'{ref}:autorip/{name}.py'],cwd=ROOT)
        path=root/(name+'.py');path.write_bytes(source)
        spec=importlib.util.spec_from_file_location('autorip._refinement_base_'+name,path)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        modules[name]=module
    modules['engine'].morph=modules['morph']
    modules['engine'].PrtWriter=modules['prt'].PrtWriter
    return modules['engine']


def fixtures(root):
    pixels=np.random.default_rng(1507).integers(0,256,(512,768,3),dtype=np.uint8)
    with Image.fromarray(pixels) as image:
        image.save(root/'rgb.png')
        rgba=image.convert('RGBA')
        alpha=np.zeros((512,768),dtype=np.uint8);alpha[90:422,140:628]=255
        alpha[160:210,310:350]=0;alpha[290:320,440:480]=127
        with Image.fromarray(alpha) as channel:rgba.putalpha(channel)
        rgba.save(root/'rgba.png');rgba.close()
    common=dict(label_enabled=False,margin_top_in=0,margin_bottom_in=0)
    cases=[]
    def add(name,file,width,**options):
        cases.append(dict(name=name,path=str(root/file),width_cm=width,settings=common|options))
    add('rgb_no_white','rgb.png',5.08,white_enabled=False)
    add('rgba_white','rgba.png',5.08,white_enabled=True)
    profile=ROOT/'Sublinks_DTF_E602 LM720x2400 8Pass .icc'
    if profile.is_file():add('rgb_output_icc_white','rgb.png',5.08,white_enabled=True,icc_path=str(profile))
    add('small_rgb','rgb.png',1.27,white_enabled=False)
    add('custom_limits','rgb.png',5.08,white_enabled=False,ink_limit=dict(C=35.5,M=0,Y=88.25,K=100))
    return cases


def ratio_interval(a,b):
    values=np.asarray(a)/np.asarray(b)
    samples=np.random.default_rng(7315).choice(values,size=(10000,len(values)),replace=True)
    return np.percentile(np.median(samples,axis=1),[2.5,97.5]).tolist()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-ref',required=True)
    parser.add_argument('--pairs',type=int,default=15)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--cases-json',type=Path)
    args=parser.parse_args()
    if args.pairs<1:parser.error('pairs precisa ser positivo')
    report=dict(baseline_ref=subprocess.check_output(['git','rev-parse',args.baseline_ref],cwd=ROOT,text=True).strip(),
                python=platform.python_version(),numpy=np.__version__,platform=platform.platform(),
                available_cpus=engine._available_cpu_count(),pairs=args.pairs,cases={})
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='autorip-refinements-') as directory:
        root=Path(directory);old=baseline(args.baseline_ref,root)
        cases=json.loads(args.cases_json.read_text()) if args.cases_json else fixtures(root)
        for case in cases:
            instances=[module.Rip(Settings(**case['settings'])) for module in (old,engine,old)]
            samples=[[],[],[]];expected=None;verified=0
            orders=list(itertools.permutations(range(3)));random.Random(7315).shuffle(orders)
            for group in range(-1,args.pairs):
                for side in orders[group%len(orders)]:
                    output=root/'output.PRT';started=time.perf_counter()
                    info=instances[side].process(case['path'],str(output),width_cm=case['width_cm'])
                    elapsed=time.perf_counter()-started
                    actual=Path(info.pop('output_path'))
                    digest=hashlib.sha256(actual.read_bytes()).hexdigest();actual.unlink()
                    signature=(digest,info)
                    if expected is None:expected=signature
                    if signature!=expected:raise RuntimeError(f"PRT/metadados diferentes: {case['name']}, grupo={group}, lado={side}")
                    verified+=1
                    if group>=0:samples[side].append(elapsed)
            medians=list(map(statistics.median,samples))
            result=dict(median_seconds=dict(zip(('baseline','candidate','control'),medians)),
                        reduction_percent=100*(1-medians[1]/medians[0]),
                        baseline_over_candidate_interval95=ratio_interval(samples[0],samples[1]),
                        control_over_candidate_interval95=ratio_interval(samples[2],samples[1]),
                        exact_outputs=verified,sha256=expected[0],metadata=expected[1],samples=samples)
            report['cases'][case['name']]=result
            args.output.write_text(json.dumps(report,indent=2)+'\n')
            print(json.dumps(dict(case=case['name'],**{k:v for k,v in result.items() if k!='samples'})),flush=True)


if __name__=='__main__':main()
