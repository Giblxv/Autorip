# Meio-tom RGB opaco com tabelas e limiares exatos

Base: `a310ee3`, AutoRIP 0.8.35. A otimização usa os bytes CMYK produzidos pela
mesma conversão Pillow/LittleCMS, sem expandir o raster CMYK inteiro para
float32. O caminho anterior permanece para transparência, regiões pequenas,
ratio NumPy e ganchos personalizados de conversão, meio-tom ou limiar.

## Equivalência numérica

Cada canal CMYK tem 256 entradas possíveis. Para cada limite de tinta e razão
de gota, a tabela calcula a mesma normalização, multiplicação, clip e fórmulas
float32 da implementação anterior, na mesma ordem. A conversão ICC e seus
flags/intenções permanecem antes dessa etapa, produzindo os mesmos bytes CMYK.
Não há uma tabela de aproximação do perfil ICC.

A retícula original é uma permutação de `(k + 0,5) / 65536`, com k entre 0 e
65535. Guardar k como uint16 é uma representação sem perda. Para uma
probabilidade p já arredondada pelo cálculo float32 anterior, a comparação
estrita equivale a `k < ceil(p * 65536 - 0,5)`, com o limite cortado em 0..65536.
Esse cálculo é feito em float64 para preservar exatamente o valor de p.
O limite usa uint32, pois 65536 não cabe em uint16. O teste independente usa
`searchsorted` sobre todos os 65.536 limiares originais, para os 256 valores
de cada canal, vários limites e razões de gota.

O padrão, a fase e a grade da retícula não mudam. O cache por instância cria
os ranks apenas quando necessário e valida sua reconstrução exata; ruído
personalizado ou não representável mantém o caminho anterior. As tabelas são
somente leitura, em LRU de até 16 combinações de ratio/limites, aproximadamente
128 KiB de dados. Os ranks por Rip ocupam 128 KiB no padrão 256 × 256. Não
retêm pixels de artes, perfis ou chaves de IA.

O atalho é selecionado para regiões opacas de pelo menos 512 × 1024 pixels,
com métodos nativos e ruído original imutável. Essa é uma seleção de algoritmo,
não um limite de tamanho de imagem. Regiões menores continuam no cálculo
anterior, que foi mais rápido nelas durante a exploração. RGBA, alfa, branco,
labels, mirror, grade/halo das tiras, workers, PRT, SHA, journal e publicação
permanecem com suas regras anteriores.

## Medição e limites

Dois ensaios independentes, sete pares AB/BA por caso, com aquecimento e sem
pytest concorrente. Linux/Python 3.12.14, Pillow 13, NumPy 2.5.4, quatro CPUs
disponíveis pela quota. `prt.py` e `morph.py` são idênticos à referência.

O cronômetro inclui abrir/preparar, renderizar, gravar, fsync e publicar via
`Rip.process`. Construção inicial, espera de fila, upload, prévias, journal e
hash de conferência ficam fora. O perfil CMYK usado no caso ICC pertence ao
repositório e tem seu hash registrado. Entradas são imagens sintéticas.

| Caso | Ensaio: base → nova | Confirmação: base → nova |
| --- | ---: | ---: |
| RGB pequeno, controle | 23,00 → 23,40 ms | 22,52 → 22,25 ms |
| RGB redimensionado | 138,48 → 123,39 ms | 131,55 → 118,61 ms |
| RGB com limites de tinta | 136,86 → 120,42 ms | 130,05 → 108,87 ms |
| RGB largo, saída de 4000 colunas | 353,34 → 326,16 ms | 349,39 → 320,76 ms |
| RGB 1:1 | 66,23 → 67,62 ms | 67,33 → 67,61 ms |
| JPEG de 4096 × 3072 | 215,40 → 223,31 ms | 220,72 → 209,25 ms |
| RGBA, controle | 448,63 → 496,95 ms | 488,82 → 492,21 ms |
| RGB com ICC e branco | 413,58 → 395,78 ms | 408,90 → 393,12 ms |

Ganhos confirmados nos dois ensaios: **9,8–10,9% menos tempo** no RGB
redimensionado, **12,0–16,3%** com limites de tinta e **7,7–8,2%** no largo.
Os intervalos pareados de 95% ficaram acima de 1x nesses três casos. Nos
demais, não houve ganho consistente nas duas medições; o JPEG chegou a ficar
3,7% mais lento no primeiro ensaio antes de inverter na confirmação. Controles
A/A ficaram em 1,030x e 1,025x, com intervalos incluindo 1x.

| Pico RSS | Ensaio: base → nova | Confirmação: base → nova |
| --- | ---: | ---: |
| RGB redimensionado | 167,2 → 112,5 MiB | 181,1 → 121,9 MiB |
| RGB com limites | 190,8 → 115,9 MiB | 178,9 → 122,4 MiB |
| RGB largo | 348,4 → 184,6 MiB | 354,5 → 185,9 MiB |
| RGB 1:1 | 155,2 → 124,1 MiB | 161,9 → 124,3 MiB |
| JPEG grande | 234,9 → 162,7 MiB | 232,5 → 164,1 MiB |
| RGB com ICC/branco | 216,1 → 171,1 MiB | 213,6 → 175,6 MiB |
| RGBA, controle | 262,8 → 279,2 MiB | 257,4 → 276,9 MiB |

RSS é o pico nativo em workers novos, duas amostras por versão/caso, incluindo
imports, decoder e leitura do PRT para conferência após o cronômetro. Não é um
limite fixo de RAM nem a medição de uma sessão Windows longa. A redução no RGB
largo foi aproximadamente 47–48%. Não se afirma redução universal de memória:
o controle RGBA oscilou 6–8% para cima nessas medições.

Um diagnóstico adicional com tracemalloc e seis workers por grupo confirmou
que o controle RGBA não chamou o novo método nem criou ranks. As medianas RSS
foram 259,4 MiB (base), 259,9 MiB (alteração) e 259,1 MiB (controle A/A).
Instrumentação e concorrência alteram picos; esses dados complementam, sem
substituir, as medições originais. [Dados do diagnóstico](opaque-rgba-diagnostic.json).

Foram comparados **112 pares de PRTs medidos**, mais aquecimentos, controles e
64 saídas de workers RSS, todos com SHA-256 e metadados iguais. Os
[dados do ensaio](opaque-lut-benchmark.json) e da
[confirmação](opaque-lut-confirmation.json) incluem amostras, hashes e limites.

## Verificação e reprodução

**1.559 testes locais aprovados**, incluindo 51 novos casos: todos os 256
valores e limites adjacentes, ranks/periodicidade sem perda, cache limitado,
ruído e hooks personalizados, promoção escalar NumPy e 12 RIPs com o atalho
comprovadamente ativo, razão de gota variável, ICC, branco, uma/quatro threads,
canais remapeados, margens, etiquetas e mirror.

```sh
python -m pytest -q
python benchmarks/benchmark_opaque_lut.py --baseline-ref v0.8.35 --pairs 7 --icc 'Sublinks_DTF_E602 LM720x2400 8Pass .icc' --output /tmp/opaque.json
python benchmarks/benchmark_opaque_lut.py --baseline-ref v0.8.35 --pairs 7 --icc 'Sublinks_DTF_E602 LM720x2400 8Pass .icc' --output /tmp/opaque-confirmation.json
python benchmarks/benchmark_rgba_fallback.py --baseline-ref v0.8.35 --repeat 6 --output /tmp/rgba-memory.json
```

Não houve medição no Xeon do usuário, telefone ou impressora física.
