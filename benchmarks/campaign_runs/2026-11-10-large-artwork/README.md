# Arquivos grandes: medições de 2026-11-10

[Escopo, resultados e limites](../../../docs/refinements/LARGE-ARTWORK.md).
Base: v0.8.18 (`95a8ea5483403301d9501b478cd15299f30d16a9`).

| Relatório | Repetições por lado | CPUs | Comparação |
| --- | ---: | --- | --- |
| report.json | 3 | 0–3 | Exploratória, 24 cenários/fases |
| confirmation.json | 3 | 0–3 | Confirmação, 26 cenários/fases |
| aa-small.json | 9 | 0–3 | Base contra ela mesma, arquivo pequeno |
| small-confirmation.json | 9 | 0 | Base contra candidata, arquivo pequeno |
| aa-large.json | 3 | 0–3 | Base contra ela mesma, RGB completo e CMYK RIP |
| cmyk-preview-confirmation.json | 9 | 0 | Base contra candidata, prévia CMYK |
| aa-cmyk-preview.json | 9 | 0 | Base contra ela mesma, prévia CMYK |

São 384 processos novos, com ordem aleatória e primeiro trabalho por Rip.
Tempos negativos e amostras ruidosas foram mantidos. Não há filtro de outliers,
promessa de ganho universal ou inferência de causa para a variação do host.

Cada JSON registra versões, afinidade, seed, script/fontes por SHA256, fontes
de imagem/perfil por hash, dimensões e configurações, cada amostra, mediana,
CPU, VmHWM e saídas. PRT/metadados/JPEGs foram conferidos em todas as amostras;
o SHA256 da entrada foi conferido após cada processamento. As saídas dos cenários
correspondentes também foram comparadas entre todos os sete relatórios.

Os dados exploratórios usam engine/server/script de `510a00a`. Os demais usam
engine/server/script de `6817994`, salvo os controles A/A, cujos dois lados são
a base. A engine é idêntica nos dois commits; o ajuste posterior de server
reproduz reducing_gap do Pillow 11/12, mantendo 2.0 no Pillow 13 destas medições.
O script posterior acrescenta os casos de impressão 25,4 cm e ICC real de saída.
Não houve edição do código medido durante as baterias.

As fontes sintéticas de 30/90 MP são geradas pelo script; arquivos gigantes não
estão versionados. Os caminhos absolutos dos JSONs identificam a execução original.
Uma reprodução gera suas próprias fontes e manifest local:

```bash
taskset -c 0-3 python benchmarks/benchmark_large_artwork.py --baseline-ref v0.8.18 --fixtures /tmp/autorip-large-fixtures --icc 'Sublinks_DTF_E602 LM720x2400 8Pass .icc' --repeat 3 --seed 991 --output /tmp/autorip-large-confirmation.json
```

Depois de gerar as fontes, é possível usar `--only cmyk_icc_30mp/preview` ou
`--only small_rgb_icc/job`, `--repeat 9`, e `--aa` para os controles. Use a mesma
afinidade nos lados comparados e execute as baterias sem outros testes locais.
