"""Uma campanha de 25 não pode ser aprovada só com os 15 passos antigos."""
import importlib.util
from pathlib import Path
import sys

import pytest


folder=Path(__file__).resolve().parents[1]/'benchmarks'
spec=importlib.util.spec_from_file_location('autorip_campaign_verifier',folder/'verify_rip_campaign.py')
verifier=importlib.util.module_from_spec(spec)
previous_path=sys.path[:]
sys.path.insert(0,str(folder))
try:
    spec.loader.exec_module(verifier)
finally:
    sys.path[:]=previous_path


def history(rounds, accepted=(), required=25):
    leader='base';count=0;records=[]
    for index in range(1,rounds+1):
        candidate=f'candidate-{index}'
        promoted=index in accepted
        count=0 if promoted else count+1
        records.append(dict(round=index,candidate=f'hypothesis-{index}',
            leader_before=leader,candidate_hash=candidate,accepted=promoted,
            reason='confirmed-speed' if promoted else 'no-confirmed-gain-or-regression',
            consecutive_without_gain=count))
        if promoted:
            leader=candidate
    return dict(complete=True,required_without_gain=required,rounds=records,
                consecutive_without_gain=count,unique_candidate_per_leader=True)


def test_exige_25_recusas_mesmo_quando_ja_ha_mais_de_15():
    with pytest.raises(AssertionError):
        verifier.verify_round_history(history(20))
    assert verifier.verify_round_history(history(25))==25


def test_aceite_reinicia_a_sequencia():
    assert verifier.verify_round_history(history(30,accepted=(5,)))==25
    with pytest.raises(AssertionError):
        verifier.verify_round_history(history(30,accepted=(6,)))


def test_mesma_alteracao_com_outro_nome_nao_conta_duas_vezes():
    report=history(25)
    report['rounds'][1]['candidate_hash']=report['rounds'][0]['candidate_hash']
    with pytest.raises(AssertionError):
        verifier.verify_round_history(report)


def test_erro_de_execucao_nao_completa_rodada_sem_ganho():
    report=history(25)
    report['rounds'][-1]['reason']='infrastructure-error'
    with pytest.raises(AssertionError):
        verifier.verify_round_history(report)


def test_preserva_alvo_de_15_nos_relatorios_anteriores():
    assert verifier.verify_round_history(history(15,required=15))==15
