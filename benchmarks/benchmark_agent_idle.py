"""Varreduras ociosas do agente em modo seguro; não abre nem imprime PRTs.

python benchmarks/benchmark_agent_idle.py --baseline-ref 0eee88f --output /tmp/agent-idle.json
A estabilidade da base é substituída por True para excluir esperas do cronômetro.
"""
import argparse
import importlib.util
import json
import logging
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from agent import print_agent as current


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--baseline-ref",required=True)
    parser.add_argument("--output",type=Path,required=True);parser.add_argument("--pairs",type=int,default=9)
    args=parser.parse_args()
    if args.pairs<1:parser.error("pairs deve ser positivo")
    logger=logging.Logger("idle-benchmark");logger.addHandler(logging.NullHandler())
    with tempfile.TemporaryDirectory(prefix="autorip-agent-idle-") as directory:
        root=Path(directory);source=root/"baseline.py"
        source.write_bytes(subprocess.check_output(["git","show",args.baseline_ref+":agent/print_agent.py"],cwd=ROOT))
        spec=importlib.util.spec_from_file_location("agent._idle_baseline",source)
        baseline=importlib.util.module_from_spec(spec);sys.modules[spec.name]=baseline;spec.loader.exec_module(baseline)
        folder=root/"PRTs";folder.mkdir()
        size=64*1024;count=128;rounds=8
        for index in range(count):(folder/f"{index:04}.PRT").write_bytes(bytes([index])*size)
        config=current.Config(root,root/"agent.exe",None,folder,root/"printed",root/"errors",root/"state.sqlite3",root/"agent.log",network_discovery=False)
        config.validate();baseline.stable=lambda *args:True
        counters=[dict(hashes=0,bytes=0),dict(hashes=0,bytes=0)]
        originals=[baseline.sha256,current.sha256]
        def tracked(side):
            def call(path,*values,**options):
                counters[side]["hashes"]+=1;counters[side]["bytes"]+=size
                return originals[side](path,*values,**options)
            return call
        baseline.sha256=tracked(0);current.sha256=tracked(1)
        states=[baseline.State(root/"old.sqlite3"),current.State(root/"new.sqlite3")]
        tracker=current.SafeFileTracker(0)
        try:
            for path in folder.glob("*.PRT"):baseline.process(path,config,states[0],None,logger)
            tracker.ready(current.scan_prts(folder))
            for path,signature in tracker.ready(current.scan_prts(folder)):
                assert current.process(path,config,states[1],None,logger,settled_signature=signature)
                tracker.handled(path,signature)
            for counter in counters:counter.update(hashes=0,bytes=0)
            samples=[[],[]]
            for pair in range(args.pairs):
                for side in ([0,1] if pair%2==0 else [1,0]):
                    started=time.perf_counter()
                    for _ in range(rounds):
                        if side==0:
                            for path in sorted(folder.glob("*.PRT"),key=lambda path:path.stat().st_mtime):baseline.process(path,config,states[0],None,logger)
                        else:
                            assert tracker.ready(current.scan_prts(folder))==[]
                    samples[side].append(time.perf_counter()-started)
            rows=[state.connection.execute("SELECT filename,sha256,state,attempts FROM jobs ORDER BY filename").fetchall() for state in states]
            assert rows[0]==rows[1]
            medians=list(map(statistics.median,samples))
            report=dict(baseline=args.baseline_ref,pairs=args.pairs,files=count,file_bytes=size,scans_per_sample=rounds,
                        safe_mode_only=True,baseline_stability_sleep_excluded=True,identical_job_states=True,
                        median_seconds=dict(baseline=medians[0],candidate=medians[1]),
                        reduction_percent=100*(1-medians[1]/medians[0]),work=counters,samples=samples)
            args.output.write_text(json.dumps(report,indent=2)+"\n");print(json.dumps(report,indent=2))
        finally:
            for state in states:state.close()
            current.sha256=originals[1]


if __name__=="__main__":main()
