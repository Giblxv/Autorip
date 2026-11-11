# Primeira passagem IO, antes da atualização concorrente da main

Base de execução `4326a12`; driver imutável `7575137`. Início 13:14:46 e término
14:13:59 de 11/11/2026 em São Paulo. Foram **25 hipóteses únicas consecutivas
sem ganho validado**, sem aceite nem erro de infraestrutura contabilizado.
A verificação independente conferiu contagem, hashes, checkout e **28 PRTs**.

A main recebeu a expansão da retícula por broadcast no PR #60 durante essa
passagem. Por isso estes resultados são preservados separadamente e **não**
encerram a campanha sobre a nova base `7095fe0`: o contador seguinte começa em
zero. Não se somam as sequências de bases diferentes.

Nove cenários cronometrados, nove pares cada, CPUs 0–3. O pico é tracemalloc,
sem todo o RSS nativo. A comparação final usa o mesmo código dos dois lados e
deu razão 1,0474: variação de medição, sem alegação de aceleração do motor.
Nenhuma proposta atingiu todos os critérios para iniciar confirmação/A/A.

Foram preparadas 30 propostas e acrescentada uma de blocos vazios. Duas foram
excluídas sem contar: um atalho de identidade que o RIP não exercita e hypot,
que muda a dilatação em uma fronteira física documentada. Quatro propostas
restantes não chegaram a ser cronometradas antes do limite de 25. As duas
interrupções planejadas preservam as rodadas concluídas e não contam as parciais.
Fixtures e oráculo foram regenerados com os mesmos parâmetros nas retomadas.

O ZIP tem os módulos iniciais, finais e das 25 propostas contadas, relatório e
verificação. O manifesto confere suas 83 entradas; fontes medidas do driver e
das duas revisões de propostas ficam nos TXT. Os JSONs preservam amostras, recusas,
exclusões e testemunhos de correção, sem remover outliers.

Extraia o ZIP numa pasta nova e execute o verificador desta revisão:

```bash
python -m zipfile -e benchmarks/campaign_runs/2026-11-11-large-io/first-pass/source-snapshots.zip /tmp/autorip-io-first
python benchmarks/verify_rip_campaign.py --work-dir /tmp/autorip-io-first --icc 'Sublinks_DTF_E602 LM720x2400 8Pass .icc'
```

A verificação histórica usou `--check-checkout` na revisão f5e2390. Não use essa
opção com outra base de execução: a main posterior possui retícula diferente.
Os módulos e seus PRTs continuam verificáveis independentemente do checkout.
Não se conclui ótimo global para todo hardware, formato ou perfil ICC.
