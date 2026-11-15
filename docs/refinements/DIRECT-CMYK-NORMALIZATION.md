# Normalização CMYK direta em float32

Base: `bbb98da`, AutoRIP 0.8.39. A conversão para CMYK continua sendo a mesma
operação Pillow/LittleCMS. Nas regiões de pelo menos 512 × 1024 pixels que
usam o caminho em ponto flutuante, a normalização dos bytes passa a usar
`divide(raw, float32(255), dtype=float32)`. Isso evita manter uma matriz
float32 inteira de entrada e outra de saída para a mesma divisão.

A matriz uint8 que o Pillow fornece ainda existe temporariamente; o cálculo
não é zero-copy. A saída float32 é privada, contígua e gravável, como antes.
Nenhum cache novo retém pixels ou perfis de uma arte.

## Precisão e seleção do caminho

Os inteiros de 0 a 255 são exatamente representáveis em float32. O dtype
explícito força a conversão e a mesma divisão nessa precisão. Não se troca
a divisão por multiplicação por recíproco. Os limites de tinta continuam
sendo multiplicados e cortados na mesma ordem, depois da normalização.

A prova verifica todos os 256 valores em cada canal e compara os bits
uint32 dos resultados float32, com limites de tinta variados e simulando
saídas da conversão com/sem perfil. Os testes completos também exercitam
perfis ICC reais do repositório e conferem os bytes PRT.

Regiões menores mantêm a expressão anterior. A versão exploratória que
forçava a conversão direta em todos os tamanhos ficou cerca de 5% mais lenta
no caso RGBA 1:1 menor em uma medição; isso motivou a seleção por área. O
limiar escolhe o algoritmo, sem rejeitar tamanhos de imagem. O atalho RGB
opaco por tabelas permanece independente e pode evitar esse cálculo por
completo nas regiões elegíveis.

Alfa, probabilidades das gotas, retícula, ICC, branco, morfologia, canais,
etiquetas, grade/halo das tiras, workers, SHA, journal e formato PRT mantêm
suas regras anteriores. Artes enviadas pelo celular usam o mesmo motor
no servidor; o cliente nativo não muda nesta versão.

## Verificação

**1.802 testes locais aprovados**, incluindo 42 novos: todos os valores
CMYK, comparação dos bits float32 após limites de tinta, regiões grandes e
pequenas, dados de entrada preservados, saída privada e ativação da divisão
float32 direta somente quando elegível. Dezesseis RIPs completos exercitam
RGB pequeno/RGBA maior, ICC opcional, uma/quatro threads, limites de tinta,
branco, etiquetas, mirror, margens e canais remapeados.

## RIP completo e limites

Dois ensaios independentes de nove casos, sete pares AB/BA por caso,
aquecimento e controle A/A. Linux/Python 3.12.14, NumPy 2.5.4, Pillow 13,
quatro CPUs disponíveis pela quota. Sem pytest concorrente. `prt.py` e
`morph.py` são idênticos à 0.8.39. As imagens são sintéticas, incluindo
uma origem RGBA de 4096 × 3072 pixels e saída larga de 4000 colunas; o
perfil ICC pertence ao repositório e tem seu hash registrado.

O cronômetro inclui abrir/preparar, renderizar, gravar, fsync e publicar
via `Rip.process`. Construção do motor, fila, upload, prévias e conferência
SHA ficam fora. Tempos são medianas por versão; os intervalos reamostram
a mediana das razões pareadas, um estimador diferente.

| Caso | Ensaio: base → nova | Confirmação: base → nova |
| --- | ---: | ---: |
| RGBA redimensionado | 144.26 → 138.66 ms | 155.47 → 151.20 ms |
| RGBA redimensionado com branco | 547.32 → 476.26 ms | 475.16 → 442.68 ms |
| RGBA largo, 4000 colunas | 297.01 → 289.55 ms | 306.03 → 299.58 ms |
| RGBA largo com branco | 944.51 → 942.70 ms | 1061.49 → 1054.38 ms |
| RGBA 1:1 menor | 23.89 → 23.18 ms | 23.18 → 23.05 ms |
| Origem RGBA 4096 × 3072 | 1268.97 → 1240.83 ms | 1153.65 → 1138.68 ms |
| RGB pequeno, controle | 18.56 → 18.11 ms | 18.44 → 18.66 ms |
| RGB com predomínio de tabelas, controle | 100.63 → 96.57 ms | 92.57 → 93.20 ms |
| RGBA com ICC e branco | 559.79 → 439.79 ms | 666.28 → 635.17 ms |

O RGBA redimensionado com branco levou **6,8–13,0% menos tempo** nas duas
medianas, com intervalos pareados de 95% acima de 1x. Nos demais casos, não
houve ganho de tempo estatisticamente consistente nos dois ensaios. O caso
1:1 menor, mantido no cálculo anterior, não repetiu a lentidão da versão
exploratória. O controle RGB pequeno alternou de sinal; no segundo ensaio
levou 1,2% mais tempo, com intervalo de 0,944–0,994x. Não há uma aceleração
universal. O controle RGB maior usa principalmente as tabelas opacas; uma
cauda menor ainda pode usar o caminho float32.

Controles A/A tiveram razões entre medianas de 1,040x e 1,000x, com intervalos
incluindo 1x. Os tempos individuais e intervalos completos estão nos JSONs.

| Pico RSS | Ensaio: base → nova | Confirmação: base → nova |
| --- | ---: | ---: |
| RGBA redimensionado | 203.1 → 189.4 MiB | 203.6 → 180.7 MiB |
| RGBA redimensionado com branco | 239.8 → 208.5 MiB | 248.6 → 227.5 MiB |
| RGBA largo, 4000 colunas | 338.6 → 295.5 MiB | 325.0 → 289.2 MiB |
| RGBA largo com branco | 352.1 → 333.5 MiB | 334.7 → 317.0 MiB |
| RGBA 1:1 menor | 73.0 → 74.2 MiB | 73.0 → 74.2 MiB |
| Origem RGBA 4096 × 3072 | 312.3 → 291.2 MiB | 312.4 → 286.8 MiB |
| RGB pequeno, controle | 59.2 → 59.2 MiB | 59.2 → 59.1 MiB |
| RGB com predomínio de tabelas, controle | 114.3 → 113.7 MiB | 111.9 → 113.9 MiB |
| RGBA com ICC e branco | 237.1 → 228.2 MiB | 234.1 → 218.2 MiB |

A redução de pico foi **8,5–13,1% no RGBA redimensionado com branco**,
**11,0–12,7% no RGBA largo sem branco**, **5,3% no largo com branco** e
**6,8–8,2% no caso de origem de 12,6 MP**. No RGBA redimensionado sem branco
a redução foi 6,8–11,2%. O pico não diminuiu em todos os controles pequenos.

RSS é medido em processos novos, duas amostras por versão/caso, incluindo
imports, decoder e leitura do PRT depois do cronômetro. Não é uma medição
de uma sessão Windows longa nem uma promessa de RAM fixa por arquivo.

## Conversão CMYK isolada

O benchmark de `_to_cmyk` usa 21 grupos base/nova/controle, três tamanhos
e limites de tinta unitários ou personalizados. Mede a conversão Pillow,
normalização e limites; não inclui alfa, meio-tom, EDT, escrita ou fsync.
Tracemalloc mede alocações em chamadas separadas do cronômetro e não mede
toda a RAM nativa do processo.

| Bloco e limites | Tempo base → nova | Pico temporário rastreado base → nova |
| --- | ---: | ---: |
| 1440x512_unity | 4.736 → 3.307 ms | 22.501 → 14.095 MiB |
| 1440x512_limits | 9.188 → 8.006 ms | 22.501 → 14.095 MiB |
| 4000x512_unity | 13.218 → 8.831 ms | 62.501 → 39.095 MiB |
| 4000x512_limits | 25.203 → 22.602 ms | 62.501 → 39.095 MiB |

Nesses blocos grandes, o pico temporário rastreado caiu aproximadamente
**37,4%**. As medianas de tempo da etapa foram 10–33% menores; controles A/A
também oscilaram, e esses percentuais não representam o RIP completo.
Nos blocos 32 × 32, que usam a expressão anterior, os tempos ficaram na
ordem de dezenas de microssegundos. [Dados da etapa](cmyk-direct-stage.json).

## Verificação e reprodução

Foram **126 pares de PRTs medidos** nos dois ensaios completos, mais
aquecimentos, controles A/A e **72 saídas de workers RSS**, todos com SHA-256
e metadados iguais. Também foram comparadas **30 artes distintas** PNG/TIFF
RGB/RGBA byte a byte com a 0.8.39, com 30 hashes de saída diferentes.
[Registro das 30 artes](cmyk-direct-equivalence-30.json).

[Ensaio principal](cmyk-direct-benchmark.json) e
[confirmação](cmyk-direct-confirmation.json) incluem todas as amostras,
intervalos, hashes e metadados. Não houve medição no hardware do usuário
ou prova física de impressão. O APK e o agente mantêm suas versões nativas.

```sh
python -m pytest -q
python benchmarks/verify_threshold_tiles.py --baseline-ref v0.8.39 --output /tmp/cmyk-30.json
python benchmarks/benchmark_cmyk_direct.py --baseline-ref v0.8.39 --pairs 7 --icc 'Sublinks_DTF_E602 LM720x2400 8Pass .icc' --output /tmp/cmyk.json
python benchmarks/benchmark_cmyk_direct.py --baseline-ref v0.8.39 --pairs 7 --icc 'Sublinks_DTF_E602 LM720x2400 8Pass .icc' --output /tmp/cmyk-confirmation.json
python benchmarks/benchmark_cmyk_stage.py --baseline-ref v0.8.39 --pairs 21 --output /tmp/cmyk-stage.json
```
