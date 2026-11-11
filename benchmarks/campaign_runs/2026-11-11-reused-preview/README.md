# Prévia capturada no decode do RIP — 2026-11-11

[Análise, escopo e limites](../../../docs/refinements/REUSED-SOURCE-PREVIEW.md).
Base: v0.8.19 (`e4728c776c303d2d079c8c2da5e62e092fd032c8`).

| Relatório | Cenários | Pares por cenário | Observação |
| --- | ---: | ---: | --- |
| report.json | 8 | 3 | Exploração em 5780e37; variante com regressão de RAM em mmap, rejeitada |
| guarded.json | 13 | 3 | Candidata 2e72e58, guard para read-only |
| confirmation.json | 6 | 5 | Mesma candidata, outra ordem |
| small.json | 1 | 9 | Pequeno, afinidade CPU 0 |
| extra-tiff.json | 2 | 5 | TIFF deflate e TIFF orientado, 30 MP |
| aa-large.json | 2 | 3 | Base contra ela mesma, RGB e CMYK |
| aa-small.json | 1 | 9 | Base contra ela mesma, CPU 0 |
| aa-rgba.json | 3 | 5 | Base contra ela mesma, RGBA/EXIF e mmap |

São **284 workers em processos novos**, com primeiro trabalho por Rip. As demais
baterias têm afinidade CPUs 0–3. Os JSONs preservam cada amostra, inclusive
tempos negativos, a variante rejeitada e controles ruidosos. Não há exclusão
de outliers nem inferência de causa para as oscilações do host compartilhado.

Todos os PRTs/metadados/JPEGs coincidiram entre os lados; cenários correspondentes
coincidiram também entre relatórios. O SHA256 da origem foi conferido depois de
cada trabalho. Image.open da origem caiu de duas chamadas para uma nos caminhos
elegíveis; fallbacks mantêm duas. Isso não conta inspeção/upload nem aberturas
internas do SO. Pico RSS é VmHWM do processo inteiro, incluindo buffers nativos.
O tempo inclui RIP e duas publicações JPEG, com fsync; exclui importação/init,
conferência, upload, fila, journal, arquivamento, integrações e impressora.

As fontes medem 30/90 MP e são sintéticas, com cores/alpha variados, gamma 1,8,
JPEG, cinza, EXIF, CMYK com perfil real, TIFF mapeado e controles de saída maior.
As dimensões/configurações e hashes dos perfis estão nos relatórios. Arquivos
gigantes não estão versionados. As fontes adicionais podem ser regeneradas:

```bash
python benchmarks/benchmark_reused_preview.py --baseline-ref v0.8.19 --fixtures /tmp/preview-fixtures --icc 'Sublinks_DTF_E602 LM720x2400 8Pass .icc' --repeat 3 --only rgb_icc_90mp/job --output /tmp/preview-rgb.json
python benchmarks/make_reused_preview_tiff.py --fixtures /tmp/preview-fixtures --output /tmp/preview-tiff
python benchmarks/benchmark_reused_preview.py --baseline-ref v0.8.19 --fixtures /tmp/preview-tiff --repeat 5 --only deflate_rgba_icc_30mp/job oriented_tiff_rgba_icc_30mp/job --output /tmp/preview-tiff.json
```

Use taskset/afinidade igual nos lados e execute sem outros testes locais. `--aa`
compara dois lados da base. Caminhos absolutos nos JSONs são da execução original;
uma reprodução gera suas fontes, perfis e manifest. O script medido é o de
5780e37 (idêntico em 2e72e58). O gerador TIFF posterior reproduziu os dois arquivos
originais com SHA256 idêntico.

`validation.json` identifica testes e smokes dos protótipos. A suíte completa de
1.013 testes antecede o guard; os 209 focados posteriores o incluem. A validação
final do código a integrar é registrada separadamente após a campanha de 25 rodadas.
O smoke local usa Python, e não substitui os smokes do executável/instalador Windows.
