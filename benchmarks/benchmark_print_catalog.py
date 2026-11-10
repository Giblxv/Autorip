"""Compara consultas repetidas da fila com server.py anterior, sem threads/rede."""
import argparse
import importlib.util
import json
from pathlib import Path
import platform
import statistics
import sys
import tempfile
import threading
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import numpy as np
from autorip import prt, prints
from autorip.config import Settings
from autorip.server import App


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline',type=Path,required=True)
    parser.add_argument('--count',type=int,default=200)
    parser.add_argument('--repeat',type=int,default=9)
    args=parser.parse_args()
    if not 1<=args.count<=5000 or args.repeat<1:
        parser.error('count entre 1 e 5000; repeat positivo')
    spec=importlib.util.spec_from_file_location('autorip._catalog_baseline',args.baseline)
    baseline=importlib.util.module_from_spec(spec);spec.loader.exec_module(baseline)
    with tempfile.TemporaryDirectory() as folder:
        app=App.__new__(App)
        app.home=folder
        app.settings_lock=threading.RLock()
        app.s=Settings(output_folder=folder)
        app.print_catalog=prints.PrintCatalog()
        for i in range(args.count):
            path=Path(folder)/f'art{i:04}.PRT'
            writer=prt.PrtWriter(path,300,300,1,32)
            writer.write_block([np.zeros((1,32),np.uint8)]*12);writer.close()
            Path(str(path)+'.meta.json').write_text('{"width_cm":1,"height_cm":1}')
        actions={'baseline':lambda:baseline.App.list_prints(app),'new':app.list_prints}
        result={'python':platform.python_version(),'platform':platform.platform(),
                'files':args.count,'repeat':args.repeat}
        for name,action in actions.items():
            action()
            samples=[]
            for _ in range(args.repeat):
                start=time.perf_counter();action();samples.append(time.perf_counter()-start)
            result[name+'_seconds']=round(statistics.median(samples),6)
            # Conta aberturas de cabeçalho fora do trecho cronometrado.
            with patch.object(prt,'read_header',wraps=prt.read_header) as old_reads, \
                 patch.object(prints,'read_header',wraps=prints.read_header) as new_reads:
                action()
                result[name+'_header_reads']=old_reads.call_count+new_reads.call_count
        result['speedup']=round(result['baseline_seconds']/result['new_seconds'],2)
        print(json.dumps(result,indent=2))


if __name__=='__main__':main()
