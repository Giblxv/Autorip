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

A suíte local passou com **915 testes no Pillow 13** e **915 no Pillow 12.3**.
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

```bash
python benchmarks/benchmark_large_artwork.py --baseline-ref v0.8.18 --fixtures /tmp/large-fixtures --icc /caminho/cmyk.icc --repeat 3 --output /tmp/large-report.json
python -m pytest -q
```
