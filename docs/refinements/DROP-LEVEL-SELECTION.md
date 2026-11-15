# Seleção vetorial dos níveis de gota

Base: `009d99b`, AutoRIP 0.8.38. O motor combina os mapas booleanos de gota
pequena e grande em uma única saída uint8, usando multiplicação inteira e
máximo. A seleção é compartilhada pelo meio-tom em ponto flutuante, tabelas
RGB opacas e base branca binária. Não depende do tamanho da arte.

## Equivalência

Se S e L são os resultados booleanos das comparações anteriores, a saída era
`where(L, 3, S.astype(uint8))`. Agora ela é `max(3*L, S)`, calculada em uint8:

| S | L | Saída |
| --- | --- | --- |
| falso | falso | 0 |
| verdadeiro | falso | 1 |
| falso | verdadeiro | 3 |
| verdadeiro | verdadeiro | 3 |

Isso cobre também a combinação L verdadeiro com S falso; não se presume uma
relação entre os dois mapas. Não há overflow: os operandos inteiros estão em
0..3. As probabilidades de tinta, comparações estritas, valores dos limiares,
retícula e sua fase permanecem iguais. Densidade, alfa, ICC, morfologia,
resolução, canais, etiquetas, grade/halo das tiras, workers e PRT não mudam.

A saída é uma matriz uint8 privada. Multiplicação e máximo escrevem nela;
os mapas de entrada são somente lidos. Isso evita manter simultaneamente a
cópia uint8 do mapa pequeno e outra saída da seleção. O NumPy pode executar
as operações vetoriais adequadas à CPU, sem uma nova dependência ou requisito
de GPU/AVX específico. O ganho medido varia com o padrão e tamanho dos mapas.

## Verificação

**1.760 testes locais aprovados**, incluindo 56 novos: todas as combinações
booleanas; matrizes C/F, não contíguas, invertidas, broadcast, vazias e escalares;
entradas somente de leitura; saída independente; bytes booleanos não canônicos;
arrays mascarados com a mesma semântica de dados do `where`; volumes float16,
float32 e float64, limiares arbitrários e não finitos e razões de gota variadas.
Dezesseis RIPs completos exercitam RGB/RGBA, ICC opcional, uma/quatro threads,
branco, canais remapeados, limites de tinta, etiquetas, mirror e margens, com
a seleção nova comprovadamente ativa e PRTs/metadados idênticos.

## RIP completo e limites

Dois ensaios independentes, oito casos e sete pares AB/BA por caso, com
aquecimento e controle A/A. Linux/Python 3.12.14, NumPy 2.5.4, Pillow 13,
quatro CPUs disponíveis pela quota. Sem pytest concorrente. `prt.py` e
`morph.py` são idênticos à 0.8.38. Entradas sintéticas; o perfil ICC do
repositório tem seu hash registrado nos dados.

O cronômetro inclui abrir/preparar, renderizar, gravar, fsync e publicar
via `Rip.process`. Construção inicial do motor, espera de fila, upload,
prévias e conferência SHA ficam fora. Tempos são medianas por versão; os
intervalos reamostram a mediana das razões pareadas, um estimador diferente.

| Caso | Ensaio: base → nova | Confirmação: base → nova |
| --- | ---: | ---: |
| RGB pequeno | 20.60 → 18.00 ms | 21.38 → 18.15 ms |
| RGB redimensionado | 117.35 → 98.12 ms | 111.01 → 90.18 ms |
| RGB com limites de tinta | 107.83 → 105.05 ms | 103.47 → 95.96 ms |
| RGB largo, 4000 colunas | 351.70 → 307.77 ms | 358.45 → 294.73 ms |
| RGB 1:1 | 67.06 → 60.26 ms | 66.36 → 59.52 ms |
| JPEG 4096 × 3072 | 235.62 → 194.43 ms | 235.47 → 213.71 ms |
| RGBA com branco | 520.89 → 486.30 ms | 565.16 → 589.05 ms |
| RGB com ICC e branco | 350.97 → 336.30 ms | 370.77 → 328.27 ms |

Reduções de tempo nas duas medianas: **12,6–15,1%** no RGB pequeno,
**16,4–18,8%** no RGB redimensionado, **12,5–17,8%** no largo,
**10,1–10,3%** no 1:1 e **9,2–17,5%** no JPEG grande. Os intervalos pareados
de 95% ficaram acima de 1x nesses cinco casos nos dois ensaios. Limites de
tinta e ICC tiveram medianas menores, mas nem todos os intervalos excluíram 1x.

No RGBA, o primeiro ensaio levou 6,6% menos tempo e o segundo 4,2% mais, com
intervalos em sentidos opostos. Isso motivou a conferência adicional abaixo;
não há um ganho uniforme confirmado nesse caso. Controles A/A dos ensaios
principais ficaram em 0,995x e 0,998x, com intervalos incluindo 1x.

| Pico RSS | Ensaio: base → nova | Confirmação: base → nova |
| --- | ---: | ---: |
| RGB pequeno | 59.3 → 59.2 MiB | 59.2 → 59.2 MiB |
| RGB redimensionado | 122.8 → 114.0 MiB | 117.2 → 114.2 MiB |
| RGB com limites de tinta | 121.8 → 112.6 MiB | 120.3 → 113.5 MiB |
| RGB largo, 4000 colunas | 188.2 → 180.5 MiB | 179.0 → 179.5 MiB |
| RGB 1:1 | 119.7 → 114.8 MiB | 119.3 → 113.7 MiB |
| JPEG 4096 × 3072 | 159.1 → 159.5 MiB | 165.5 → 160.4 MiB |
| RGBA com branco | 241.4 → 238.8 MiB | 242.1 → 255.6 MiB |
| RGB com ICC e branco | 139.7 → 139.6 MiB | 145.8 → 143.2 MiB |

RSS é medido em processos novos, duas amostras por versão/caso, incluindo
imports, decoder e leitura do PRT depois do cronômetro. A memória total
não caiu em todos os casos; o pico RGBA oscilou para cima na confirmação.
A redução das alocações da seleção, isoladamente, não garante reduzir o
pico de RAM de toda a aplicação.

### Conferência RGBA em processos novos

Foram 21 processos novos intercalando base/nova/controle, sete por grupo,
sem tracemalloc. Os contadores registraram 35 chamadas da seleção nova em
cada execução candidata; os outros grupos não têm esse método. Todos os
PRTs e metadados foram iguais.

| Grupo | Tempo mediano | Pico RSS mediano |
| --- | ---: | ---: |
| Base | 604.35 ms | 243.5 MiB |
| Alteração | 556.87 ms | 232.9 MiB |
| Controle A/A | 583.75 ms | 243.8 MiB |

As medianas indicaram 7,9% menos tempo contra a base e 4,6% contra o controle.
Intervalos de 95%: base/nova 1.056–1.091x,
controle/nova 0.784–1.157x e
base/controle 0.950–1.209x. A comparação com o
controle ainda inclui 1x; esses dados complementam as medições originais
sem substituí-las. [Dados RGBA](drop-selection-rgba-fresh.json).

## Etapa isolada

O benchmark de seleção usa 21 grupos base/nova/controle, três tamanhos e
padrões mistos, sem gotas grandes e apenas gotas grandes. A conferência de
alocações com tracemalloc é feita separadamente dos tempos. Não inclui
conversão de cor, cálculo de probabilidades, EDT, escrita, fsync ou upload.

| Mapas mistos | Tempo base → nova | Pico temporário rastreado base → nova |
| --- | ---: | ---: |
| 512x1440 | 3.068 → 0.137 ms | 1.408 → 0.712 MiB |
| 512x4000 | 8.314 → 0.376 ms | 3.908 → 1.962 MiB |

Nesses mapas mistos grandes, a etapa foi cerca de 22x mais rápida e usou
aproximadamente metade do pico temporário rastreado. Não é uma aceleração de
22x do RIP completo. Em mapas 32 × 32 uniformes, a seleção nova foi cerca de
0,8–0,9 microssegundo mais lenta; o custo fixo predomina em operações tão
curtas. [Todas as amostras da etapa](drop-selection-stage.json).

## Dados e reprodução

Foram **112 pares medidos** nos dois ensaios completos, mais aquecimentos,
controles A/A, 64 saídas de workers RSS e 21 saídas da conferência RGBA, todos
com SHA-256 e metadados iguais. Também foram comparadas **30 artes distintas**
PNG/TIFF RGB/RGBA byte a byte contra a 0.8.38, com 30 hashes de saída diferentes.
[Registro das 30 artes](drop-selection-equivalence-30.json).

[Ensaio principal](drop-selection-benchmark.json) e
[confirmação](drop-selection-confirmation.json) contêm amostras, intervalos,
hashes e metadados. Não houve medição no hardware do usuário ou prova física
de impressão. Os clientes móveis continuam usando o motor no servidor;
as versões nativas do APK e do agente permanecem iguais.

```sh
python -m pytest -q
python benchmarks/verify_threshold_tiles.py --baseline-ref v0.8.38 --output /tmp/drop-30.json
python benchmarks/benchmark_opaque_lut.py --baseline-ref v0.8.38 --pairs 7 --icc 'Sublinks_DTF_E602 LM720x2400 8Pass .icc' --output /tmp/drop.json
python benchmarks/benchmark_opaque_lut.py --baseline-ref v0.8.38 --pairs 7 --icc 'Sublinks_DTF_E602 LM720x2400 8Pass .icc' --output /tmp/drop-confirmation.json
python benchmarks/benchmark_rgba_fallback.py --baseline-ref v0.8.38 --repeat 7 --no-trace --output /tmp/drop-rgba.json
python benchmarks/benchmark_drop_selection.py --pairs 21 --output /tmp/drop-stage.json
```
