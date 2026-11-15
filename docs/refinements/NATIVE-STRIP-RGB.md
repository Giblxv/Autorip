# Extração RGB nativa de faixas RGBA

Base: AutoRIP 0.8.40, commit `4786fc94fd4306e42ade5f0e832ea53d0a0fc89d`.
O motor extraía RGB com `Image.fromarray(arr[..., :3], "RGB")`. Essa visão
NumPy não contígua exige empacotar os canais em um buffer RGB antes de
copiá-los para o Pillow. Agora `strip.convert("RGB")` extrai os mesmos
bytes diretamente para uma imagem Pillow privada. O alfa continua separado;
não há composição sobre fundo nem alteração da cor escondida por alfa zero.

`rgb.info.clear()` preserva o contrato anterior: a imagem RGB intermediária
não carrega ICC, EXIF, DPI ou outros metadados herdados. Isso também preserva
o comportamento de conversores personalizados. A origem e seus metadados
não são modificados. O tratamento anterior de orientação e dos perfis dos
arquivos continua no carregamento e na transformação de cor.

A alteração evita um buffer empacotado de três bytes por pixel da faixa.
A imagem RGB nativa continua sendo alocada, assim como a matriz RGBA usada
pelo alfa. Portanto, isso não elimina todas as cópias nem garante redução
do pico de RAM do RIP. Retícula, branco, cálculos CMYK, workers, `prt.py` e
`morph.py` permanecem iguais à base.

## Verificação

**1.845 testes locais aprovados**, incluindo 43 novos: valores RGB/alfa,
pixels transparentes, formas pequenas e largas, metadados, saída privada,
origem preservada e descarte de faixas totalmente transparentes. Dezesseis
RIPs completos verificam PNG/TIFF, EXIF 1/6, ICC real opcional, uma/quatro
threads, branco, etiquetas, espelhamento, margens e canais remapeados.

Além disso, 30 artes RGB/RGBA distintas em PNG/TIFF produziram os mesmos
bytes e metadados da 0.8.40. Todos os PRTs das medições abaixo também têm
SHA e metadados iguais entre as versões.

## RIP com motor aquecido

Dois ensaios independentes de nove casos, 11 pares AB/BA por caso, com
aquecimento e controle A/A: **198 pares medidos**, além dos aquecimentos,
controles e 72 saídas em processos separados para medir RSS. Ambiente:
Linux, Python 3.12.14, NumPy 2.5.4 e Pillow 13; quatro CPUs disponíveis pela
quota, cinco visíveis ao sistema. Nenhum pytest rodou junto das medições.

O tempo cobre abrir/preparar, renderizar, gravar, fsync e publicar via
`Rip.process`. Construção do motor, fila, upload, prévia e cálculo do SHA
de conferência ficam fora. O ICC já existente no repositório tem seu hash
registrado nos relatórios.

| Caso | Ensaio: base → nova | Confirmação: base → nova |
| --- | ---: | ---: |
| RGBA redimensionado | 148,55 → 143,01 ms | 161,36 → 147,54 ms |
| RGBA redimensionado com branco | 486,12 → 542,18 ms | 486,42 → 516,76 ms |
| RGBA largo sem branco | 315,30 → 282,52 ms | 307,13 → 283,42 ms |
| RGBA largo com branco | 915,30 → 887,42 ms | 980,00 → 1023,44 ms |
| RGBA 1:1 sem branco | 23,63 → 22,08 ms | 23,04 → 21,75 ms |
| Origem RGBA de 12,6 MP | 1102,47 → 1081,77 ms | 1137,07 → 1153,74 ms |
| Controle RGB pequeno | 17,98 → 17,79 ms | 18,03 → 17,97 ms |
| Controle RGB grande | 91,46 → 80,28 ms | 106,57 → 101,25 ms |
| RGBA com ICC e branco | 593,43 → 533,15 ms | 631,22 → 586,83 ms |

Os resultados repetidos mais consistentes foram **7,7–10,4% menos tempo
no RGBA largo sem branco** e **5,6–6,6% no RGBA 1:1 sem branco**. Os
intervalos bootstrap de 95% das razões pareadas ficaram acima de 1 nos
dois ensaios para esses dois casos. Não se conclui ganho uniforme nos
demais arquivos. Os controles RGB não usam a nova extração; suas oscilações
não são ganhos atribuíveis à mudança.

No redimensionado com branco, as medianas ficaram **11,5% e 6,2% mais
lentas**, respectivamente. Os intervalos pareados incluem 1 nos dois
ensaios (0,863–1,092 e 0,888–1,077), portanto a medição não distingue esse
resultado de variação. Essa incerteza não deve ser omitida ao avaliar a
versão. Os controles A/A também incluem 1 (0,891–1,089 e 0,962–1,087).

Os tempos da tabela são medianas separadas por versão. Os intervalos
reamostram a mediana das razões de cada par: são estimadores diferentes.
Por exemplo, no segundo ensaio do largo com branco, a razão das medianas
indica lentidão, enquanto o intervalo pareado fica acima de 1. Não se
declara ganho confirmado nesse caso.

### Pico de RAM residente

Medianas de duas saídas separadas por versão/caso/ensaio, em MiB:

| Caso | Ensaio: base → nova | Confirmação: base → nova |
| --- | ---: | ---: |
| RGBA redimensionado | 177,3 → 172,9 | 182,9 → 171,5 |
| RGBA redimensionado com branco | 212,1 → 216,0 | 210,9 → 227,3 |
| RGBA largo sem branco | 303,7 → 321,9 | 291,7 → 289,5 |
| RGBA largo com branco | 325,5 → 319,6 | 323,9 → 311,3 |
| RGBA 1:1 sem branco | 74,2 → 74,2 | 73,0 → 74,2 |
| Origem RGBA de 12,6 MP | 295,3 → 289,7 | 295,0 → 293,7 |
| Controle RGB pequeno | 59,2 → 59,2 | 59,1 → 59,2 |
| Controle RGB grande | 114,6 → 114,9 | 112,9 → 113,3 |
| RGBA com ICC e branco | 219,8 → 217,1 | 233,2 → 216,6 |

O pico global não caiu em todos os casos; etapas posteriores e os alocadores
nativos também afetam RSS. Remover o buffer RGB não permite prometer uma
porcentagem de economia de memória do programa inteiro.

## Confirmação em processos novos

Mais **132 RIPs**: quatro casos, 11 grupos aleatórios de base/nova/controle
base, cada execução em um processo novo, sem tracemalloc. Os contadores
confirmam a extração nova somente nas versões RGBA candidatas. Tempo de
CPU é medido dentro de `Rip.process`, antes de conferir o hash do arquivo.

| Caso | Base / nova / controle, mediana de tempo |
| --- | ---: |
| RGBA redimensionado com branco | 568,64 / 563,82 / 607,11 ms |
| RGBA largo sem branco | 623,08 / 522,17 / 699,11 ms |
| RGBA 1:1 sem branco | 41,36 / 40,26 / 39,73 ms |
| Controle RGB grande | 135,29 / 130,57 / 130,77 ms |

Os intervalos não confirmam ganho de tempo consistente contra as duas
referências nessa medição. Também não há redução universal de CPU ou RSS.
Os ganhos anunciados acima se referem aos ensaios com motor aquecido;
não são uma promessa de aceleração na primeira execução. O relatório
inclui todos os tempos de CPU, RSS, contadores, amostras e intervalos.

## Etapa isolada e reprodução

O benchmark da extração usa a matriz RGBA já disponível, como no motor,
21 grupos aleatórios base/nova/controle e conferência dos bytes RGB:

| Faixa | Base → nova | Buffer empacotado evitado |
| --- | ---: | ---: |
| 32 × 32 | 11,80 → 3,81 µs | 3.072 bytes |
| 1440 × 512 | 4,39 → 1,58 ms | 2.211.840 bytes |
| 4000 × 512 | 10,71 → 2,84 ms | 6.144.000 bytes |

A etapa foi cerca de 2,8–3,8 vezes mais rápida; isso **não** é a aceleração
do RIP completo. Tracemalloc não contabiliza a imagem nativa Pillow, que
continua existindo. Seus números não representam economia total de RAM.

```bash
python -m pytest -q
python benchmarks/verify_threshold_tiles.py --baseline-ref v0.8.40 --output /tmp/equivalence-30.json
python benchmarks/benchmark_cmyk_direct.py --baseline-ref v0.8.40 --pairs 11 --icc 'Sublinks_DTF_E602 LM720x2400 8Pass .icc' --output /tmp/native-rgb.json
python benchmarks/benchmark_strip_rgb.py --baseline-ref v0.8.40 --pairs 21 --output /tmp/native-rgb-stage.json
python benchmarks/benchmark_strip_rgb_fresh.py --baseline-ref v0.8.40 --pairs 11 --output /tmp/native-rgb-fresh.json
```

Dados completos: [ensaio](native-strip-rgb-benchmark.json),
[confirmação](native-strip-rgb-confirmation.json),
[etapa](native-strip-rgb-stage.json),
[processos novos](native-strip-rgb-fresh.json) e
[30 artes distintas](native-strip-rgb-equivalence-30.json).
O identificador `57ff70f…` nos dois primeiros relatórios é o objeto da tag
anotada v0.8.40, que aponta para o commit base acima. Os hashes do código
comprovam a mesma base e a mesma implementação candidata nos quatro ensaios.

Não houve medição no computador do usuário nem prova física de impressão.
APK 0.2.2 e agente 0.2.1 mantêm suas versões nativas; uploads móveis usam
o motor atualizado no servidor.
