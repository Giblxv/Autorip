# RIP: conversão direta de RGBA com perfil ICC

Base de comparação: `b5b0228` (main após a revisão dos pull requests).
Implementação inicial: `ac8166a`. O benefício demonstrado é reduzir buffers de preparação; os tempos são indicativos.

## Alteração e limites

A entrada RGBA com perfil ICC agora usa uma transformação nativa RGBA → RGBA.
Isso elimina dois rasters RGB e a extração/restauração manual do alfa. A imagem
retornada continua independente da fonte; Pillow/LittleCMS preservam seu alfa.

RGB/paleta usam o contexto RGB e RGBA passa a ter um contexto próprio. O cache
continua local à instância e à thread, com oito entradas e 2 MiB de payloads de
perfil por cache. Um lote frio alternando RGB e RGBA com o mesmo perfil pode
compilar duas transformações em vez de uma; os dois formatos são reaproveitados
nos lotes seguintes. Não se alteram intenção, BPC ou flags nativos.

Sem ICC, a produção permanece idêntica. LA, PA, paleta, chave de transparência,
LAB/CMYK, EXIF, DPI, reamostragem, retícula, branco e escrita de PRT mantêm seus
caminhos anteriores. Não há nova dependência ou configuração de produção.

## Medição e controles

O cronômetro cobre `Rip.process`: abrir/decodificar, converter cor, preparar,
renderizar, gravar/fsync e publicar. A construção do Rip e a conferência dos PRTs
ficam fora. Cada execução exige SHA-256 e metadados idênticos à base. A instância
persiste entre lotes, exceto no controle de primeiro uso.

A bateria rgba-direct tem 13 cenários e 29 PRTs por execução quando se informa
um ICC CMYK externo de saída. Mantém os 11 controles de source-alpha e acrescenta
RGBA com perfil RGB não identidade e um lote alternando RGB/RGBA. O perfil não
identidade é um sRGB sintético cuja TRC paramétrica recebe gamma 1,8; não representa
uma calibração de impressora. O perfil CMYK externo é identificado por hash e
não redistribuído.

As fontes grandes têm 4096 × 3072 pixels, PNGs/TIFF orientado/LAB 2048 × 1536,
paleta/chave de cor 1024 × 768 e as pequenas 320 × 240. DPI da fonte 100 × 200,
saída 720 × 2400 dpi com largura 1,27 cm, margens 0,05 polegada, branco padrão e
sem etiqueta. Há redução forte das fontes: essa bateria favorece observar o custo
da preparação. O controle largo usa a mesma fonte RGBA grande em 5,08 e 10,16 cm.
Há também um lote de 16 TIFFs pequenos, RGB/RGBA alternados em oito perfis RGB
distintos, que pressiona a capacidade de oito contextos do cache.
Não se mede envio à impressora, upload, miniaturas, journal ou RAM total do painel.

As primeiras três baterias rodaram as duas versões no mesmo processo e mostraram
variação relevante, inclusive em controles sem mudança. Seus dados são preservados
como exploração; não bastam para afirmar ausência de regressão. A confirmação usa
um processo persistente separado por versão e cenário, ordem alternada, aquecimento
e afinidade nas mesmas quatro CPUs (0–3), sem executar os dois lados simultaneamente.
As 15 repetições são amostras por cenário, separadas da campanha de 15 hipóteses.

Além do tempo de parede, registra-se CPU por `time.process_time`, somado apenas em
`Rip.process`, incluindo threads. Não se interpreta parede menos CPU como tempo de
I/O: CPU inclui paralelismo. Fatores são razões de medianas; os intervalos bootstrap
pareados de 95% estimam a mediana das razões, que pode diferir desse fator.

O pico RSS é VmHWM de dois processos novos por lado/cenário. Inclui bibliotecas,
primeiro e segundo lotes, caches e verificação das saídas, com fixtures criadas fora
dos workers. Não é tracemalloc, limite total de memória ou garantia para toda arte.

## Resultados das duas baterias completas

| Cenário | Fator inicial | Segunda bateria: base → candidato | Fator da segunda |
| --- | ---: | ---: | ---: |
| TIFF RGBA grande | 1.156× | 1506.04 → 1334.90 ms | 1.128× |
| TIFF RGB grande (controle) | 0.962× | 1494.96 → 1499.33 ms | 0.997× |
| PNG RGBA | 1.043× | 689.66 → 556.78 ms | 1.239× |
| RGBA orientado | 1.093× | 755.30 → 713.97 ms | 1.058× |
| Quatro RGBA pequenos | 1.002× | 353.10 → 379.11 ms | 0.931× |
| RGBA grande sem ICC (controle) | 1.031× | 775.55 → 802.24 ms | 0.967× |
| Paleta com transparência | 1.037× | 259.23 → 253.72 ms | 1.022× |
| RGB com chave de cor | 0.955× | 284.99 → 285.93 ms | 0.997× |
| LAB (controle) | 1.025× | 596.51 → 584.89 ms | 1.020× |
| RGBA grande, perfil não identidade | 1.164× | 1502.10 → 1330.24 ms | 1.129× |
| Primeiro uso RGBA grande | 1.096× | 804.29 → 668.68 ms | 1.203× |
| RGB/RGBA alternados | 1.018× | 534.95 → 540.33 ms | 0.990× |
| ICC de entrada e saída | 1.145× | 970.79 → 967.34 ms | 1.004× |

Fator geométrico: 1.0538× e 1.0489×; CPU: 1.0584× e 1.0494×.
Os intervalos pareados agregados foram [1,0308; 1,0830] e [1,0312; 1,0660].
Cinco cenários tiveram limites pareados acima de 1 nas duas baterias: RGBA grande,
PNG RGBA, orientado, perfil não identidade e primeiro uso. Contudo, os controles A/A
abaixo mostram que esses intervalos, calculados entre amostras do mesmo par de
processos, não capturam toda a variação entre processos. Não são evidência suficiente
para prometer aceleração ou atribuir todas as diferenças ao código. Os intervalos
por caso estão nos JSONs.

**Ressalva de tempo:** o lote pequeno teve
fator 1,002× na primeira bateria e 0,931× na confirmação, com intervalo [0,900; 0,969].
O controle sem ICC também variou, apesar de o código desse caminho ser idêntico.
Os controles adicionais abaixo não reproduziram a lentidão. Também não permitem
certificar ausência de regressão em toda carga ou ganho nos arquivos pequenos.

As duas baterias usam o mesmo hash de engine/prt/morph e do benchmark. Todos os
29 hashes/metadados de PRT também coincidem entre as duas baterias.

## Controles adicionais e limite da inferência de tempo

A mesma fixture pequena foi medida mais duas vezes, com processos separados,
15 repetições e ambos fixados na CPU 0, pois essas saídas já renderizam em uma
thread. Os fatores RGBA foram 1,087× e 1,065×; os controles sem ICC, 0,995× e
1,051×. A aparente regressão dos pequenos não se reproduziu nessa condição.

Foi então executado um **controle A/A com os dois motores idênticos**, comprovado
pelos hashes: ele produziu fatores 1,067× para RGBA e 0,931× sem ICC. O intervalo
RGBA [1,020; 1,112] ficou acima de 1 mesmo sem diferença no código. Isso demonstra
que o intervalo de reamostragem dentro de um único par de processos subestima a
incerteza total neste ambiente compartilhado. Mais amostras do mesmo par não
resolvem esse viés. A causa exata da variação não foi determinada; não se atribui
a I/O, frequência ou alocador como fato confirmado.

Assim, não se aceita outra hipótese com base apenas nessa aparente precisão e
não se afirma aceleração universal. A redução de buffers/RSS, os pixels exatos
e os testes funcionais são evidências separadas e sustentam a proposta de memória.

O lote com oito perfis alternados mostrou **8 / 0 compilações** no primeiro/lote
seguinte na base e **16 / 16** no candidato: os 16 contextos excedem o limite de
oito entradas. Seu fator de tempo foi 0,968×, intervalo [0,958; 1,064], com CPU
0,971×. É um custo real de recompilação, mesmo que sua magnitude de tempo permaneça
incerta. Não se aumenta a retenção de transformações nativas para escondê-lo.

## Memória conforme o tamanho da impressão

| Cenário | RSS inicial: base → candidato | Segunda bateria: base → candidato |
| --- | ---: | ---: |
| RGBA grande | 194.72 → 146.78 MiB | 194.98 → 146.96 MiB |
| PNG RGBA | 86.69 → 74.74 MiB | 86.67 → 74.96 MiB |
| RGBA orientado | 111.12 → 99.14 MiB | 111.22 → 99.01 MiB |
| Perfil não identidade | 194.75 → 146.75 MiB | 194.96 → 146.67 MiB |
| Primeiro uso | 194.38 → 146.41 MiB | 194.60 → 146.63 MiB |
| ICC de saída | 87.55 → 75.43 MiB | 87.45 → 75.64 MiB |

O lote RGBA grande cai aproximadamente de 195 para 147 MiB (cerca de 25%).
Porém, no controle com a mesma fonte em largura de 5,08 cm, o pico é 334,10 →
334,08 MiB; em 10,16 cm, 455,01 → 454,18 MiB. Os buffers da renderização passam
a dominar o pico. Não se promete redução da RAM total do aplicativo ou em toda
largura. Os fatores de tempo nesses controles foram 1,139× e 1,011×, numa única
bateria de 15 repetições, também sujeitos à limitação A/A descrita acima.

## Correção

757 testes locais passaram. O novo teste de conversão não identidade compara
pixels com o caminho anterior nas quatro intenções, com/sem BPC, RGB variado/plano
e alfa 0–255, em cache frio/quente, verificando que a fonte não muda. Os testes de
cache foram adaptados para contextos RGB e RGBA distintos e verificam propriedade
e liberação das transformações por thread; falhas de aplicação continuam explícitas.

## Reprodução

```bash
taskset -c 0-3 python benchmarks/benchmark_source_icc.py --suite rgba-direct --baseline-ref b5b0228 --repeat 15 --paired-workers --icc /caminho/cmyk.icc --output /tmp/rgba-direct.json
taskset -c 0-3 python benchmarks/benchmark_rgba_wide.py --baseline-ref b5b0228 --repeat 15 --output /tmp/rgba-wide.json
taskset -c 0-3 python benchmarks/benchmark_rgba_wide.py --baseline-ref b5b0228 --repeat 15 --cases small_rgba small_no_icc --output /tmp/rgba-small-confirmation.json
taskset -c 0-3 python benchmarks/benchmark_rgba_wide.py --baseline-ref ac8166a --repeat 15 --cases small_rgba small_no_icc --output /tmp/rgba-aa.json
python -m pytest -q
```

`taskset` é opcional e específico de Linux; escolha CPUs permitidas no ambiente.
A ferramenta registra afinidade, versões, hashes dos módulos/perfis e o próprio
script. Exige prt/morph idênticos à base. Sem ICC externo, omite o último cenário.
O controle A/A exige engine.py idêntico a `ac8166a`, como neste checkout;
em outra revisão, escolha a própria revisão limpa e confira os hashes do relatório.
