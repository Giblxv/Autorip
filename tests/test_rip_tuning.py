"""Audit planning equivalence and transactional candidate validation."""
import importlib
import os
from pathlib import Path
import py_compile
import subprocess
import zipfile

import pytest
from PIL import Image


@pytest.fixture
def campaign(monkeypatch):
    root = Path(__file__).resolve().parents[1]
    monkeypatch.syspath_prepend(str(root/'benchmarks'))
    return importlib.import_module('rip_campaign')


def test_semantic_hash_ignores_formatting_but_keeps_operations(campaign):
    a = {'engine': 'x = 1\n', 'prt': '', 'morph': ''}
    b = dict(a, engine='# tuning alias\nx=1\n')
    assert campaign.digest(a) != campaign.digest(b)
    assert campaign.semantic_digest(a) == campaign.semantic_digest(b)
    assert campaign.semantic_digest(a) != campaign.semantic_digest(dict(a, engine='x=2\n'))


def make_case(tmp_path):
    from autorip.config import Settings
    path=tmp_path/'source.png'
    Image.new('RGB',(32,24),(20,100,180)).save(path)
    return dict(name='planning',path=path,width=2.54,timed=True,cpu_limit=4,
                settings=Settings(label_enabled=False,white_choke_mm=.1,white_fill_holes_mm=.3))


def bundle(campaign):
    # Test the benchmark helpers against a stable 0.8.24 fixture, even while
    # validating a proposal that legitimately changes production strip settings.
    path=Path(__file__).parent/'fixtures/rip-tuning-baseline.zip'
    with zipfile.ZipFile(path) as archive:
        result={key:archive.read(key+'.py').decode() for key in campaign.FILES}
    assert campaign.digest(result)=='4931ab0acb27b5753a0a78e2aaef4dbd1ed5306096afc4b61ef9de1bec8dedd5'
    return result


def test_probes_never_execute_stale_bytecode(campaign,tmp_path,monkeypatch):
    first=bundle(campaign)
    second=dict(first,engine=first['engine'].replace('STRIP = 512','STRIP = 128',1))
    assert len(first['engine'])==len(second['engine']) and first!=second
    folder=tmp_path/'same-path'
    campaign.load(first,folder,'first_probe')
    target=folder/'engine.py'
    info=target.stat()
    py_compile.compile(str(target),doraise=True)
    original=Path.write_text
    def rewrite(path,*args,**kwargs):
        result=original(path,*args,**kwargs)
        if path==target:
            os.utime(path,ns=(info.st_atime_ns,info.st_mtime_ns))
        return result
    monkeypatch.setattr(Path,'write_text',rewrite)
    assert campaign.load(second,folder,'second_probe')['engine'].STRIP==128


def test_planning_fingerprint_matches_real_render_ranges(campaign,tmp_path,monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    import concurrent.futures
    from rip_tuning_candidates import tune,execution_plan
    candidate=tune(bundle(campaign),3,192,1000000)
    modules=campaign.load(candidate,tmp_path/'candidate','actual_plan')
    case=make_case(tmp_path)
    _,plans=execution_plan(candidate,modules['engine'],[case])
    observed=[]; workers=[]
    original=modules['engine'].Rip._render
    def render(self,im,a0,a1,top,art_rows,n_dots,labels):
        observed.append((a0,a1,n_dots))
        return original(self,im,a0,a1,top,art_rows,n_dots,labels)
    class Pool(ThreadPoolExecutor):
        def __init__(self,*args,**kwargs):
            workers.append(kwargs['max_workers'])
            super().__init__(*args,**kwargs)
    monkeypatch.setattr(modules['engine'].Rip,'_render',render)
    monkeypatch.setattr(concurrent.futures,'ThreadPoolExecutor',Pool)
    campaign.render(campaign.new_rip(modules['engine'],case),case,tmp_path/'out.PRT',True)
    plan=plans[0]
    assert workers==[plan['workers']]==[3]
    expected=[(max(0,y-plan['halo']),min(plan['n_rows'],y+plan['strip_rows']+plan['halo']),plan['n_dots'])
              for y in range(0,plan['n_rows'],plan['strip_rows'])]
    assert sorted(observed)==expected


def test_single_worker_threshold_alias_has_same_execution_plan(campaign,tmp_path):
    from rip_tuning_candidates import tune,execution_plan
    case=make_case(tmp_path)
    first=tune(bundle(campaign),1,192,100000)
    second=tune(bundle(campaign),1,192,12000000)
    a=campaign.load(first,tmp_path/'a','plan_a')
    b=campaign.load(second,tmp_path/'b','plan_b')
    assert campaign.semantic_digest(first)!=campaign.semantic_digest(second)
    assert execution_plan(first,a['engine'],[case])==execution_plan(second,b['engine'],[case])


def test_old_scheduling_families_receive_same_inert_plan_filter(campaign):
    from rip_tuning_candidates import is_scheduling_proposal
    for name in ('strip-256','pipeline-2','wide-limit-2','pixel-estimate-80',
                 'parallel-threshold-500k','memory-budget-256','tune-w2-s192-t1000000'):
        assert is_scheduling_proposal(name)
    assert not is_scheduling_proposal('cmyk-lut')


def test_oversized_single_strip_values_have_same_plan(campaign,tmp_path):
    from autorip.config import Settings
    from rip_tuning_candidates import tune,execution_plan
    case=make_case(tmp_path)
    case['settings']=Settings(label_enabled=False,dpi_x=72,dpi_y=72,
                               margin_top_in=.05,margin_bottom_in=.05)
    first=tune(bundle(campaign),1,128,1000000)
    second=tune(bundle(campaign),1,256,1000000)
    a=campaign.load(first,tmp_path/'a','one_strip_a')
    b=campaign.load(second,tmp_path/'b','one_strip_b')
    assert execution_plan(first,a['engine'],[case])==execution_plan(second,b['engine'],[case])


def test_late_wide_worker_cap_is_part_of_plan(campaign,tmp_path):
    from rip_tuning_candidates import execution_plan
    from rip_wide_candidates import fewer_wide
    candidate=fewer_wide(bundle(campaign),3)
    modules=campaign.load(candidate,tmp_path/'wide','late_cap')
    case=make_case(tmp_path)
    case['width']=6000/720*2.54
    _,plans=execution_plan(candidate,modules['engine'],[case])
    assert plans[0]['workers']==3 and plans[0]['n_dots']==6000


@pytest.mark.parametrize('change_source',[False,True])
def test_regression_checker_restores_only_its_own_edits(campaign,tmp_path,monkeypatch,change_source):
    monkeypatch.setattr(campaign,'ROOT',tmp_path)
    monkeypatch.setattr(campaign,'DEADLINE',None)
    before={key:f'# original {key}\n' for key in campaign.FILES}
    candidate={key:f'# proposed {key}\n' for key in campaign.FILES}
    for key,path in campaign.FILES.items():
        target=tmp_path/path; target.parent.mkdir(exist_ok=True)
        target.write_text(before[key])
    def check(*args,**kwargs):
        assert {k:(tmp_path/p).read_text() for k,p in campaign.FILES.items()}==candidate
        kwargs['stdout'].write('1 failed\n')
        if change_source:
            (tmp_path/campaign.FILES['engine']).write_text('# user edit\n')
        return subprocess.CompletedProcess(args[0],1)
    monkeypatch.setattr(campaign.subprocess,'run',check)
    if change_source:
        with pytest.raises(RuntimeError,match='user edits preserved'):
            campaign.validate_candidate_checkout(candidate,tmp_path)
    else:
        assert not campaign.validate_candidate_checkout(candidate,tmp_path)['passed']
    for key,path in campaign.FILES.items():
        assert (tmp_path/path).read_text()==('# user edit\n' if key=='engine' and change_source else before[key])
