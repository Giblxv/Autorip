"""Confere a contagem de rodadas e os PRTs finais contra a base imutável."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile

from rip_campaign import ROOT, FILES, digest, load, make_cases, micro_correct, render, new_rip


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work-dir',type=Path,required=True)
    parser.add_argument('--icc',type=Path)
    parser.add_argument('--check-checkout',action='store_true',help='Exige que os modulos do checkout coincidam com o resultado')
    args=parser.parse_args()
    work=args.work_dir.resolve()
    report=json.loads((work/'report.json').read_text())
    assert report['complete']
    count=0
    for record in report['rounds']:
        assert record['reason'] not in ('exception','infrastructure-error')
        count=0 if record['accepted'] else count+1
        assert record['consecutive_without_gain']==count
    assert count>=15 and count==report['consecutive_without_gain']
    assert not any(r['accepted'] for r in report['rounds'][-15:])
    current={key:(work/'final_modules'/f'{key}.py').read_text() for key in FILES}
    if args.check_checkout:
        checkout={key:(ROOT/path).read_text() for key,path in FILES.items()}
        assert digest(checkout)==digest(current)
    initial={key:(work/'initial'/f'{key}.py').read_text() for key in FILES}
    assert digest(current)==report['leader_hash']
    with tempfile.TemporaryDirectory(prefix='autorip-verify-') as folder:
        folder=Path(folder)
        baseline=load(initial,folder/'baseline','verify-old')
        final=load(current,folder/'final','verify-final')
        assert micro_correct(baseline,final) is None
        cases=make_cases(folder,str(args.icc.resolve()) if args.icc else None,report.get('suite','standard'))
        hashes={}
        for case in cases:
            old=new_rip(baseline['engine'],case)
            new=new_rip(final['engine'],case)
            a=render(old,case,folder/'x.PRT',True)
            b=render(new,case,folder/'x.PRT',True)
            assert a==b,case['name']
            hashes[case['name']]={'baseline':a,'final':b,'equal':True}
    result={'rounds':len(report['rounds']),'consecutive_without_gain':count,
            'accepted':sum(r['accepted'] for r in report['rounds']),
            'icc_sha256':hashlib.sha256(args.icc.read_bytes()).hexdigest() if args.icc else None,
            'final_source_hash':digest(current),'checkout_checked':args.check_checkout,'prt_sha256':hashes}
    (work/'verification.json').write_text(json.dumps(result,indent=2))
    print(json.dumps({'verified':True,'rounds':len(report['rounds']),
                      'consecutive_without_gain':count,'identical_prt_cases':len(hashes)}))


if __name__=='__main__':main()
