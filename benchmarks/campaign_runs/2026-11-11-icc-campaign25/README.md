# Campanha final com ICC e RGBA — 11/11/2026

Base imutável: `23d4c106bfb2adf10e69292f9d71182b88284b60`, após incorporar a
melhoria de prévias da v0.8.20. **25 hipóteses únicas por líder, 25 recusas
consecutivas, nenhum aceite e nenhum erro de infraestrutura contabilizado.**
Início 13:30:57 UTC; conclusão 15:11:35 UTC (12:11:35 em São Paulo), antes do
prazo de 22h. Encerra pelo critério de 25, sem alegação de ótimo global.

São 23 casos de correção e 14 cronometrados, nove pares por caso, Python 3.12.14,
Linux compartilhado, CPUs 0–3, perfil CMYK real cujo SHA256 está na verificação.
A campanha usa Rips aquecidos no mesmo processo (retomado uma vez); não equivale
aos 284 workers isolados da investigação da prévia. Mede RIP, sem publicação das
prévias. Pico aqui é tracemalloc, não RSS nativo. A comparação final usa código
idêntico dos dois lados; a razão 1,008 é variação de medição, não ganho do motor.

As nove recusas anteriores em v0.8.19 foram interrompidas para investigar a
prévia e **não entram** nesta sequência. O checkpoint completo foi preservado.
A retomada desta campanha conserva as primeiras 13 recusas. A proposta parcial
`parallel-threshold-500k` foi excluída antes de contar: não altera o número de
workers em nenhum caso do corpus. As propostas de relaxar a estimativa de RAM
(`pixel-estimate-80/64`) também foram excluídas. `pipeline-2/3` foram recusadas
por diferença de saída; as demais, por ganho não confirmado ou regressão.
Nenhuma atingiu os critérios para iniciar confirmação/A/A nesta campanha.
Não são removidas amostras ruidosas do relatório.

## Evidência e reprodução

`report.json` contém amostras individuais; `verification.json` confere a contagem,
a cadeia de hashes dos protótipos, o checkout e PRTs idênticos em **23 casos**,
além das comparações de fronteiras. `source-snapshots.zip` guarda apenas fontes
iniciais/finais e das 25 propostas realmente contadas, relatório e verificação.
O manifesto registra SHA256 de cada entrada. Não contém imagens, PRTs, cache ou
a proposta parcial excluída. `provenance.json` identifica scripts, perfil e ZIP.
Os logs preservam a interrupção e a retomada, sem contar a rodada incompleta.

Com as dependências instaladas no checkout v0.8.20, extraia em uma pasta nova:

```bash
python -m zipfile -e benchmarks/campaign_runs/2026-11-11-icc-campaign25/source-snapshots.zip /tmp/autorip-icc25
python benchmarks/verify_rip_campaign.py --work-dir /tmp/autorip-icc25 --icc 'Sublinks_DTF_E602 LM720x2400 8Pass .icc' --check-checkout
```

Para repetir as medições em pasta nova (não espera tempos iguais no outro host):

```bash
taskset -c 0-3 python benchmarks/rip_campaign.py --suite rgba-direct --baseline-ref 23d4c106bfb2adf10e69292f9d71182b88284b60 --work-dir /tmp/autorip-icc25-new --icc 'Sublinks_DTF_E602 LM720x2400 8Pass .icc' --rounds-without-gain 25 --repeats 9 --exclude pixel-estimate-80 pixel-estimate-64 parallel-threshold-500k
```

O prazo original só se aplica à execução histórica; um novo `--deadline` precisa
ser futuro e incluir fuso. O teste de prazo curto também está arquivado. Uma
[outra campanha standard de 25](../../../docs/refinements/PR57-25-ROUND-VALIDATION.md)
foi integrada por outro commit; ambas são preservadas, sem somar suas contagens.

| Rodada | Hipótese | Recusa | Razão geométrica de tempo base/candidata |
| --- | --- | --- | ---: |
| 1 | rgba-no-pixel-cache | no-confirmed-gain-or-regression | 1.023 |
| 2 | rgba-copied-in-place | no-confirmed-gain-or-regression | 1.003 |
| 3 | full-erode-analytic | no-confirmed-gain-or-regression | 1.036 |
| 4 | white-opaque-direct | no-confirmed-gain-or-regression | 1.009 |
| 5 | cmyk-normalize-inplace | no-confirmed-gain-or-regression | 0.990 |
| 6 | density-copy-false | no-confirmed-gain-or-regression | 0.991 |
| 7 | density-mask-inplace | no-confirmed-gain-or-regression | 0.998 |
| 8 | opaque-alpha | no-confirmed-gain-or-regression | 1.018 |
| 9 | rank32-wide | no-confirmed-gain-or-regression | 0.995 |
| 10 | wide-limit-3 | no-confirmed-gain-or-regression | 0.961 |
| 11 | wide-limit-2 | no-confirmed-gain-or-regression | 0.960 |
| 12 | edt-transpose-wide | no-confirmed-gain-or-regression | 0.972 |
| 13 | clip-ufunc | no-confirmed-gain-or-regression | 1.008 |
| 14 | parallel-threshold-2m | no-confirmed-gain-or-regression | 0.936 |
| 15 | zero-halftone | no-confirmed-gain-or-regression | 1.015 |
| 16 | subpixel-morph | no-confirmed-gain-or-regression | 1.020 |
| 17 | pipeline-2 | different-output | — |
| 18 | pipeline-3 | different-output | — |
| 19 | threshold-take | no-confirmed-gain-or-regression | 1.017 |
| 20 | threshold-tile | no-confirmed-gain-or-regression | 1.027 |
| 21 | threshold-tile2d | no-confirmed-gain-or-regression | 1.022 |
| 22 | threshold-broadcast | no-confirmed-gain-or-regression | 0.967 |
| 23 | pack-tree | no-confirmed-gain-or-regression | 0.996 |
| 24 | pack-direct | no-confirmed-gain-or-regression | 1.024 |
| 25 | pack-dot | no-confirmed-gain-or-regression | 0.979 |

As propostas com saída diferente não foram cronometradas.
