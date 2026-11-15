"""ICC sem cache persistente: tempo de RIP completo e equivalência byte a byte.

python benchmarks/benchmark_source_workers.py --baseline-ref 5827ec9 --pairs 9 --output /tmp/source-workers.json
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import random
import statistics
import struct
import sys
import tempfile
import threading
import time

from benchmark_main_refinements import baseline, engine, Settings, ratio_interval
import numpy as np
from PIL import Image, ImageCms


def profile(oversize):
    value = bytearray(ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes())
    for index in range(struct.unpack_from(">I", value, 128)[0]):
        pos = 132 + index*12
        if value[pos:pos+4] == b"rTRC":
            offset = struct.unpack_from(">I", value, pos+4)[0]
            struct.pack_into(">i", value, offset+12, round(1.8*65536))
            break
    if oversize:
        value.extend(b"\0"*(2*1024**2+4096-len(value)))
        struct.pack_into(">I", value, 0, len(value))
    return bytes(value)


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--baseline-ref", required=True)
    parser.add_argument("--pairs", type=int, default=9);parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    if args.pairs<1:parser.error("pairs deve ser positivo")
    report={"baseline":args.baseline_ref,"pairs":args.pairs,"cpu_quota":engine._available_cpu_count(),"cases":{}}
    with tempfile.TemporaryDirectory(prefix="autorip-source-benchmark-") as folder:
        root=Path(folder);old=baseline(args.baseline_ref,root)
        for name,mode,oversize,size,white in [
            ("oversize_rgb","RGB",True,(1024,8192),False),
            ("oversize_rgba_white","RGBA",True,(1024,8192),True),
            ("normal_profile_control","RGB",False,(1024,8192),False),
            ("small_serial_control","RGBA",True,(128,128),False),
        ]:
            pixels=np.random.default_rng(8517).integers(0,256,(size[1],size[0],4),dtype=np.uint8)
            source=root/"source.tif"
            with Image.fromarray(pixels).convert(mode) as image:
                image.save(source,icc_profile=profile(oversize),dpi=(300,300))
            del pixels
            settings=Settings(label_enabled=False,white_enabled=white,margin_top_in=0,margin_bottom_in=0)
            rips=[module.Rip(settings) for module in (old,engine,old)]
            counts=[Counter() for _ in rips];samples=[[] for _ in rips]
            for side,rip in enumerate(rips):
                build=rip._build_source_transform
                def tracked(*values, build=build, counter=counts[side]):
                    counter[threading.current_thread().name]+=1
                    return build(*values)
                rip._build_source_transform=tracked
            expected=None;checks=0
            for iteration in range(-1,args.pairs):
                order=list(range(3));random.Random(8517+iteration).shuffle(order)
                for side in order:
                    path=root/"result.PRT";start=time.perf_counter()
                    info=rips[side].process(str(source),str(path),width_cm=1.27)
                    elapsed=time.perf_counter()-start
                    path=Path(info.pop("output_path"))
                    result=(hashlib.sha256(path.read_bytes()).hexdigest(),info)
                    path.unlink()
                    if expected is None:expected=result
                    assert result==expected,(name,side,"PRT ou metadados diferentes")
                    checks+=1
                    if iteration>=0:samples[side].append(elapsed)
            medians=list(map(statistics.median,samples))
            result={"median_seconds":dict(zip(("baseline","candidate","control"),medians)),
                    "reduction_percent":100*(1-medians[1]/medians[0]),
                    "baseline_over_candidate_interval95":ratio_interval(samples[0],samples[1]),
                    "control_over_candidate_interval95":ratio_interval(samples[2],samples[1]),
                    "exact_outputs":checks,"sha256":expected[0],"samples":samples,
                    "builds_including_warmup":list(map(dict,counts))}
            report["cases"][name]=result
            args.output.write_text(json.dumps(report,indent=2)+"\n")
            print(json.dumps({"case":name,**{key:value for key,value in result.items() if key!="samples"}}),flush=True)


if __name__=="__main__":main()
