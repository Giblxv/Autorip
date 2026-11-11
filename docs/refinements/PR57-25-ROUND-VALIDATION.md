# Validação reproduzível do PR 57 — 25 rodadas

Base da campanha: commit `438e090a4b72c39efaea52b50f6c682ed259d47c`.

A campanha foi executada sem aplicar protótipos ao checkout, usando o próprio
SHA atual como base:

```bash
python benchmarks/rip_campaign.py \
  --work-dir /tmp/autorip-campaign-25-438e090 \
  --baseline-ref HEAD \
  --rounds-without-gain 25 \
  --repeats 7 \
  --suite standard
```

Resultado: **25 rodadas completas**, **25 recusas consecutivas sem ganho aceito**,
**0 hipóteses aceitas** e nenhuma falha de infraestrutura. A rodada 6 foi
marcada como `inconclusive-aa-noise`; a rodada 25 foi rejeitada por
`different-output`/`halftone-boundary`, portanto nenhuma alteração experimental
foi incorporada.

A verificação independente foi executada com:

```bash
python benchmarks/verify_rip_campaign.py \
  --work-dir /tmp/autorip-campaign-25-438e090 \
  --check-checkout
```

Saída: `verified: true`, `rounds: 25`, `consecutive_without_gain: 25`,
`identical_prt_cases: 10`. O `--check-checkout` confirmou que os módulos finais
coincidem com o checkout do PR. Os artefatos completos estão em
[`benchmarks/campaign_runs/2026-11-11-pr57/`](../../benchmarks/campaign_runs/2026-11-11-pr57/).

Esta campanha encerra a busca automática de hipóteses sobre o motor nesta base;
não é uma prova de ótimo global para todo hardware, imagem, perfil ICC ou
impressora. A matriz do GitHub Actions continua obrigatória para Linux/Windows,
Python 3.10/3.12 e empacotamento Windows. A compatibilidade física com PrintExp,
perfis proprietários, canais e branco continua exigindo ensaio controlado.
