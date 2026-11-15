# Base branca de imagens opacas com máscara booleana

Base: `102a2b3`, AutoRIP 0.8.37. A renderização de regiões RGB opacas passa a
preparar o alfa da base branca em bool, com um byte por pixel em vez de quatro.
Após as mesmas operações de fechamento e erosão, o meio-tom calcula as
probabilidades de uma única densidade e as compara com a retícula nativa.
Isso evita materializar a densidade e suas probabilidades para toda a região.

A mudança atua na base branca. A conversão CMYK, os canais, o tamanho da
imagem, a grade/halo das tiras, a concorrência, os limiares e o formato PRT
permanecem com suas regras anteriores. A especialização também funciona em
regiões pequenas; não há novo limite de pixels.

## Equivalência

Com alfa binário e limiar de alfa estritamente positivo, os pixels da máscara
inicial têm alfa 1, e os demais têm alfa 0. No cálculo anterior, pixels com
alfa 1 recebem a densidade branca configurada; pixels acrescentados pelo
fechamento também recebem essa densidade. Após a máscara final, todo volume
é, portanto, zero ou a mesma densidade convertida para float32.

A versão nova calcula `volume/r` e `(volume-r)/(1-r)` na mesma ordem usando um
array de tamanho 1 com a densidade float32, e usa broadcasting nas comparações.
Manter esse valor como array, em vez de um escalar NumPy, preserva a promoção
de tipos em versões diferentes do NumPy. As comparações estritas continuam
usando os mesmos valores, padrão, fase e dtype dos limiares da 0.8.37. Fora da
máscara, o volume zero produz nível zero, pois os limiares nativos são positivos.

Esse caminho exige ruído original imutável e métodos nativos de meio-tom e
limiar. Com ruído/métodos personalizados ou limiares fornecidos explicitamente,
a entrada booleana é convertida na mesma matriz de volumes float32 completa.
Métodos personalizados de branco recebem o alfa float32 anterior. RGBA com
transparência parcial e limiar de alfa zero usam o caminho geral.

Não se troca a retícula por um branco sólido: densidades como 45% continuam
recebendo o mesmo meio-tom de gotas pequenas e grandes.

## Verificação

**1.704 testes locais aprovados**, incluindo 96 novos casos. Há comparação
booleana/float32 com furos e choke, limiares e densidades variados, uma linha
ou coluna, entrada preservada, limiares externos e métodos/ruído personalizados.
Uma prova exercita todos os 65.536 valores da retícula com densidades vizinhas
às fronteiras de decisão, quatro razões de gota (incluindo escalar NumPy),
máscaras cheias/vazias e vistas não contíguas. Doze RIPs completos exercitam
uma/quatro threads, ICC opcional, branco em 0/45/100%, canais remapeados,
margens, mirror e etiquetas, com a especialização ativa quando elegível.

## Medição e limites

Base 0.8.37, Linux/Python 3.12.14, NumPy 2.5.4 e Pillow 13, quatro CPUs pela
quota. Dois ensaios independentes de dez casos, sete pares AB/BA por caso,
aquecimento, controle A/A e pico RSS em processos novos. Sem testes
concorrentes. `prt.py` e `morph.py` são idênticos à base. Os arquivos são
sintéticos; o perfil ICC pertence ao repositório e tem seu SHA registrado.

O cronômetro inclui abrir/preparar, renderizar, escrever, fsync e publicar
via `Rip.process`. Construção do motor, espera da fila, upload, prévias e hash
de conferência ficam fora. Os tempos são medianas por versão; os intervalos
reamostram a mediana das razões pareadas, um estimador diferente.

| Caso | Ensaio: base → nova | Confirmação: base → nova |
| --- | ---: | ---: |
| RGB pequeno, branco 100% | 73.93 → 72.17 ms | 71.08 → 70.76 ms |
| RGB redimensionado, branco 100% | 270.39 → 257.52 ms | 289.21 → 268.39 ms |
| RGB redimensionado, branco 45% | 271.52 → 267.86 ms | 271.16 → 264.03 ms |
| RGB largo, branco 100% | 665.71 → 620.61 ms | 624.80 → 591.36 ms |
| RGB largo, branco 45% | 679.28 → 626.99 ms | 619.04 → 592.29 ms |
| RGB 1:1, branco 100% | 142.15 → 139.30 ms | 140.68 → 133.42 ms |
| RGBA, controle | 488.07 → 530.86 ms | 511.78 → 523.99 ms |
| RGB com ICC e branco | 352.85 → 341.03 ms | 407.19 → 405.13 ms |
| RGB sem branco, controle | 112.34 → 117.58 ms | 130.81 → 120.93 ms |
| Limiar de alfa zero, controle | 157.47 → 172.69 ms | 167.15 → 163.96 ms |

As medianas tiveram **4,8–7,2% menos tempo** no RGB redimensionado com branco
100%, **5,4–6,8%** no RGB largo com branco 100% e **4,3–7,7%** no largo com
branco 45%. Os intervalos pareados de 95% ficaram acima de 1x nesses três
casos nos dois ensaios. Os demais casos elegíveis não demonstraram ganho
estatístico consistente nos dois ensaios. O controle sem branco e o de limiar
zero alternaram de sinal; o RGBA ficou mais lento nas duas medianas, com
intervalos incluindo 1x. Portanto, não há aceleração universal.

O controle A/A teve razões entre medianas de 0,991x e 1,113x, com intervalos
pareados incluindo 1x. Essa variação justifica a conferência adicional em
processos novos abaixo, em vez de tratar pequenas diferenças como ganho certo.

| Pico RSS | Ensaio: base → nova | Confirmação: base → nova |
| --- | ---: | ---: |
| RGB pequeno, branco 100% | 60.3 → 60.3 MiB | 60.3 → 60.3 MiB |
| RGB redimensionado, branco 100% | 150.3 → 143.4 MiB | 150.0 → 145.4 MiB |
| RGB redimensionado, branco 45% | 151.1 → 141.8 MiB | 146.4 → 139.4 MiB |
| RGB largo, branco 100% | 224.5 → 195.9 MiB | 219.2 → 195.5 MiB |
| RGB largo, branco 45% | 217.3 → 201.8 MiB | 203.3 → 200.3 MiB |
| RGB 1:1, branco 100% | 123.0 → 113.8 MiB | 121.2 → 111.8 MiB |
| RGBA, controle | 233.1 → 243.2 MiB | 250.3 → 275.8 MiB |
| RGB com ICC e branco | 143.0 → 144.1 MiB | 150.6 → 141.0 MiB |
| RGB sem branco, controle | 121.5 → 122.5 MiB | 122.8 → 120.8 MiB |
| Limiar de alfa zero, controle | 150.7 → 150.2 MiB | 153.1 → 147.5 MiB |

No RGB largo com branco 100%, o pico total caiu **10,8–12,7%**. O alfa do
branco, isoladamente, usa 75% menos memória; esse percentual não se aplica
a toda a RAM do programa. RSS inclui imports, decoder e leitura do PRT para
conferência após o cronômetro. São duas amostras novas por versão/caso;
não representa uma sessão Windows longa nem garante queda de RAM por arquivo.

### Conferência adicional

O controle RGBA teve picos maiores nas duas medições originais. Uma conferência
sem tracemalloc, em 18 processos novos intercalando base/nova/controle, mediu
medianas de **250,5 / 253,0 / 250,3 MiB**. Nenhum acionou as tabelas RGB ou o
novo caminho branco. As amostras individuais variaram aproximadamente de
224 a 276 MiB. Esses dados complementam as medições originais, sem apagá-las.
[Dados RGBA](opaque-white-rgba-diagnostic.json).

Também foram executados 42 processos novos para os dois casos largos, sete
grupos base/nova/controle por caso, em ordem aleatória, sem tracemalloc. Os
contadores de chamadas comprovam que o caminho branco novo foi usado somente
na alteração; as tabelas de cor RGB da 0.8.36 foram usadas em todos os grupos.

| Caso | Tempo base / nova / controle | RSS base / nova / controle |
| --- | ---: | ---: |
| RGB largo, branco 100% | 692.83 / 658.06 / 694.35 ms | 213.8 / 198.0 / 216.0 MiB |
| RGB largo, branco 45% | 682.21 / 615.66 / 684.15 ms | 206.7 / 194.8 / 209.4 MiB |

Com branco 45%, a mediana levou **9,8% menos tempo** que a base e **10,0%**
menos que o controle; os dois intervalos de 95% ficaram acima de 1x, enquanto
o A/A incluiu 1x. Com branco 100%, houve 5,0% menos tempo na mediana, mas os
intervalos incluíram 1x. O pico total caiu cerca de 7,4% e 5,8% contra a base
nos casos de 100% e 45%, respectivamente. [Dados em processos novos](opaque-white-fresh.json).

Foram **140 pares de PRTs medidos** nos dois ensaios principais, mais
aquecimentos, controles A/A, 80 saídas de workers RSS, 18 saídas do diagnóstico
RGBA e 42 da conferência em processos novos, todos com SHA/metadados iguais.
Uma verificação adicional de 30 artes distintas PNG/TIFF RGB/RGBA comparou
os arquivos byte a byte contra a 0.8.37, com 30 hashes de saída diferentes.
[Registro das 30 artes](opaque-white-equivalence-30.json).

[Ensaio principal](opaque-white-benchmark.json) e
[confirmação](opaque-white-confirmation.json) incluem amostras, intervalos,
hashes e metadados. Não houve medição no hardware do usuário ou validação
física na impressora. Os clientes móveis continuam usando o mesmo motor
no servidor; não há alteração nativa de APK nesta versão.

## Reprodução

```sh
python -m pytest -q
python benchmarks/verify_threshold_tiles.py --baseline-ref v0.8.37 --output /tmp/white-30.json
python benchmarks/benchmark_opaque_white.py --baseline-ref v0.8.37 --pairs 7 --icc 'Sublinks_DTF_E602 LM720x2400 8Pass .icc' --output /tmp/white.json
python benchmarks/benchmark_opaque_white.py --baseline-ref v0.8.37 --pairs 7 --icc 'Sublinks_DTF_E602 LM720x2400 8Pass .icc' --output /tmp/white-confirmation.json
python benchmarks/benchmark_rgba_fallback.py --baseline-ref v0.8.37 --repeat 6 --no-trace --output /tmp/white-rgba.json
python benchmarks/benchmark_white_fresh.py --baseline-ref v0.8.37 --pairs 7 --output /tmp/white-fresh.json
```
