# PR 59 — validação repetida de integração e desempenho

O PR foi avaliado em 25 processos independentes. Cada processo executou os
mesmos 72 testes:

```text
tests/test_parallel_rip.py
tests/test_engine.py
tests/test_integrations.py
tests/test_cross_pr_integration.py
```

Resultado: **25/25 rodadas aprovadas**, **1800 execuções de teste**, nenhuma falha
ou timeout. A suíte completa no mesmo SHA passou com **1023 testes**.

O benchmark pareado contra o `engine.py` anterior preservou os PRTs com e sem
branco byte a byte e os picos de memória. No host atual, os tempos variaram
entre -1,8% e +0,5%, sem ganho estatístico: a afinidade já expõe seis CPUs e o
teto de quatro workers não muda. O valor desta mudança é respeitar afinidade
menor em contêineres e serviços, evitando oversubscription; ela não promete uma
aceleração universal.

A matriz remota de Linux/Windows e Python 3.10/3.12 continua sendo o gate final.
