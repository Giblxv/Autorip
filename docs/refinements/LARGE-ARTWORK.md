# Rasters e prévias de arquivos muito grandes

Base: v0.8.18 (`95a8ea5`). O teto de pixels continua desativado. Esta etapa
reduz cópias e a vida útil dos rasters, preservando os PRTs e as prévias.

## Caminhos alterados

As transformações ICC entregam RGBA diretamente. Em RGB, RGBX, LAB, CMYK e
cinza opaco, o alfa é definido como 255: padding ou um canal não inicializado
não podem virar transparência. LA/PA/paleta/chave de cor mantêm a restauração
anterior do alfa. Intenção, BPC, flags e limites do cache permanecem iguais.

O carregador pode entregar o próprio RGBA que acabou de decodificar e aplicar
ICC no mesmo buffer, usando `ImageCms.applyTransform(inPlace=True)`. Isso exige
RGBA mutável e posse privada; imagens read-only/mapeadas seguem o caminho com
saída independente. A API interna continua devolvendo cópia independente por
padrão, e o arquivo de entrada permanece inalterado.

Após EXIF, a origem anterior à rotação é fechada antes das conversões seguintes.
O arquivo é fechado ao entregar a imagem. O raster de processamento é fechado
em `finally`, inclusive em falha/cancelamento e quando o traceback é retido.

A prévia reduz RGB/cinza opaco antes de expandir para RGBA e libera as origens
após converter/rotacionar. Filtro, proporção, transparência, espelhamento da
prévia, marca e bytes JPEG são preservados. Até o Pillow 12, o resize de RGBA
ignorava reducing_gap ao converter para RGBa; o caminho opaco reproduz essa
regra. No Pillow 13, conserva o padrão 2.0. Não se usa JPEG draft ou redução da
resolução do arquivo para acelerar a impressão.

## Verificação funcional

A suíte local final passou com **923 testes no Pillow 13**. No Pillow 12.3,
a bateria completa anterior passou com **915 testes**; os 16 casos de ICC
in-place, incluindo os oito casos novos de cor repetida/alfa variável, passaram
depois nos dois runtimes. Não houve alteração de produção entre essas baterias.
Os casos novos verificam cores não identidade, RGBX com padding variável,
perfil cinza real em L/LA, todas as intenções/BPC e alfa 0–255. Também verificam
raster read-only, TIFF mapeado inalterado, arquivo movível enquanto o resultado
está em uso e fechamento dos rasters em erros de geometria, disco, preparação,
render, publicação e prévia, com traceback retido.

As prévias grandes incluem RGB/cinza PNG/JPEG, dimensões ímpares, orientações,
redução em duas etapas e chave de transparência, comparadas pixel a pixel.
A primeira execução Windows revelou que o decoder TIFF pode chamar EXIF no
próprio buffer e retornar None; a instrumentação do teste foi corrigida para
registrar apenas imagens, sem enfraquecer as verificações de fechamento.
Um build posterior encontrou outra corrida no teste de recuperação de upload:
o arquivo já estava arquivado, mas o watcher ainda não havia removido a pasta.
O teste agora espera os dois resultados dentro do mesmo prazo de dez segundos,
preservando ambas as asserções. O fluxo de recuperação de produção não mudou.

O smoke local do aplicativo 0.8.19 passou com login, planejamento de duas peças
e leitura de metadados de uma arte de 400 MP, assets, três uploads, ICC, alfa e
prévia com marca. Esse smoke local usa um launcher Python; o empacotamento e a
instalação Windows têm verificações próprias no workflow de build. Outro smoke
decodificou e ripou um RGBA/ICC real de 90 MP e conferiu PRT idêntico a uma
referência sólida menor, com alfa 127 preservado na prévia.

## Medição

`benchmarks/benchmark_large_artwork.py` compara a versão anterior com fontes de
**30 e 90 milhões de pixels**. Cada lado/amostra roda em um processo novo,
com ordem aleatória e afinidade nas mesmas CPUs. O cronômetro exclui importação,
construção do Rip e conferência, mas inclui primeiro uso do perfil, leitura,
cor, reamostragem, render, gravação/fsync e publicação. A prévia inclui as duas
publicações JPEG reais. O fluxo completo soma RIP e prévia; não inclui upload,
estabilidade, journal, arquivamento, integrações de saída ou impressora física.

O pico RSS é VmHWM do processo isolado, incluindo Python/bibliotecas e buffers
nativos. Não é tracemalloc ou RAM de todo o aplicativo. Os dados de cada amostra
são preservados. Cada execução exige PRT/metadados e/ou JPEGs idênticos à base;
o hash da entrada é conferido após o processamento para detectar escrita indevida.

Os RGB/RGBA grandes usam PNG com cores variadas em dois eixos, gamma sintética
1,8 quando há ICC e alfa 0–255 em RGBA. Há EXIF 6, JPEG, cinza, LAB/CMYK TIFF,
TIFF RGBA mapeado e um controle pequeno. Os perfis de saída/CMYK são identificados
por hash. As larguras usuais são 5,08 cm, com controles maiores e ICC de saída;
720 × 2400 dpi, margens de 0,05 polegada e branco padrão. Essas cargas não
representam toda impressão real nem processamento out-of-core de qualquer tamanho.

A primeira bateria é exploratória. Tempos variaram inclusive em controles;
não se atribui a causa a I/O ou alocador como fato comprovado, nem se promete
aceleração universal. A confirmação usa novos processos e outra ordem.

## Resultados e limites

Foram preservados [sete relatórios completos](../../benchmarks/campaign_runs/2026-11-10-large-artwork/README.md),
com **384 processos de medição**: bateria inicial com 24 cenários/fases,
confirmação com 26 e controles adicionais. Todos os PRTs, metadados e JPEGs
coincidiram entre os lados e entre as baterias correspondentes; todas as
entradas mantiveram seu hash. A confirmação abaixo tem três amostras por lado,
com afinidade nas CPUs 0–3, Python 3.12.14 e Pillow 13.0.0 em Linux compartilhado.
Valores são medianas; os valores individuais constam dos JSONs.

| Entrada / operação | Segundos: base → candidata | Pico RSS MiB: base → candidata |
| --- | ---: | ---: |
| RGB ICC 90 MP / RIP | 8,671 → 8,910 | 1082,4 → 739,2 |
| RGB ICC 90 MP / prévia | 2,136 → 0,656 | 1082,4 → 395,7 |
| RGB ICC 90 MP / RIP + prévia | 8,641 → 7,140 | 1175,0 → 739,3 |
| Cinza 90 MP / prévia | 2,203 → 0,192 | 824,9 → 137,4 |
| RGBA EXIF 90 MP / RIP + prévia | 19,598 → 18,628 | 1132,3 → 785,7 |
| JPEG RGB ICC 90 MP / RIP + prévia | 11,218 → 8,362 | 1133,4 → 739,6 |
| RGB 90 MP, impressão 25,4 cm / RIP + prévia | 48,682 → 45,415 | 1116,1 → 750,1 |
| RGB 90 MP, ICC real de saída / RIP + prévia | 9,069 → 7,084 | 1134,5 → 740,8 |
| CMYK ICC 30 MP / RIP + prévia | 4,381 → 4,581 | 439,3 → 381,9 |
| TIFF RGBA mapeado 30 MP / RIP + prévia | 2,559 → 2,942 | 377,4 → 377,4 |

A redução de RAM de RGB grande apareceu nas duas baterias: no fluxo completo,
1133 → 739 MiB na primeira e 1175 → 739 MiB na confirmação. A prévia RGB foi
2,40×/3,26× mais rápida e a cinza 7,87×/11,48× nessas cargas. O caso de 25,4 cm
gera um PRT de cerca de 238 MB (7200 × 11040, 720 × 2400 dpi) e conserva a
economia de RAM. São resultados dessas fontes e dimensões, sem extrapolação
para todo arquivo ou toda impressora.

Os controles impedem uma conclusão universal sobre tempo:

- A/A compara a base com ela mesma. RGB 90 MP completo deu razão 0,993×;
  CMYK 30 MP RIP deu 1,167×, mesmo sem alteração de código.
- O pequeno deu 0,376× na primeira bateria e 1,409× na segunda. Nove repetições
  adicionais, presas à CPU 0, deram 1,077×; A/A com nove repetições nas CPUs 0–3
  deu 0,994×. A lentidão inicial não se reproduziu de forma consistente.
- Prévia CMYK deu 1,013×/0,662× nas baterias. Nove repetições na CPU 0 deram
  0,923×, contra 0,937× no A/A com a mesma afinidade. Os tempos permanecem
  inconclusivos; a redução de RSS de cerca de 399 para 284 MiB se repetiu.
- RGBA sem rotação e TIFF mapeado não tiveram redução consistente de pico RSS.
  Tempos negativos, inclusive os do TIFF mapeado, permanecem nos dados.

O decodificador e a preparação ainda precisam de rasters completos. Esta mudança
não implementa leitura por tiles/out-of-core, não garante arquivos arbitrariamente
grandes em RAM limitada e não altera o orçamento das tiras de renderização.

```bash
python benchmarks/benchmark_large_artwork.py --baseline-ref v0.8.18 --fixtures /tmp/large-fixtures --icc /caminho/cmyk.icc --repeat 3 --output /tmp/large-report.json
python -m pytest -q
```
