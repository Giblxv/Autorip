# RIP: menos buffers na conversão de entrada com ICC e alfa

Continuação na v0.8.18: [remoção do teto de pixels das artes](INPUT-PIXELS.md).
Os limites de entrada citados abaixo descrevem a etapa histórica.

Base de comparação: `feb3214`. Implementação: `7718ba1`.

Continuação: [conversão direta RGBA](DIRECT-RGBA-ICC.md). As medições
abaixo continuam documentando esta etapa histórica e não devem ser somadas ou
multiplicadas pelos resultados posteriores.

A restauração do alfa copiava a fonte RGBA inteira antes de extrair um único
canal. Além disso, os dois rasters RGB intermediários permaneciam vivos durante
a criação do RGBA final e a restauração do alfa. Agora RGBA, LA e PA usam
`getchannel("A")` diretamente, e cada buffer temporário é fechado após seu último
uso. O chamador continua sendo dono da fonte; a imagem retornada é independente.

Paletas e imagens RGB com chave de transparência continuam expandindo a fonte
para RGBA pelo Pillow, preservando a interpretação anterior. A expansão, o canal
alfa e o resultado incompleto são fechados também quando ocorre uma falha. Isso
evita reter rasters grandes em tracebacks de erros de conversão/composição.

As transformações ICC, cache por thread, intenção, BPC, tratamento EXIF/DPI,
reamostragem, separação, retícula e escrita de PRT permanecem os mesmos. Os módulos
server/watermarks/prt/morph/watcher são idênticos à base. Não há dependência nova.

## RIP completo e igualdade de saída

Duas baterias independentes, sete repetições pareadas por cenário, aquecimento e
ordem alternada. Cada execução compara SHA-256 e metadados de todos os PRTs com
a base. São **11 cenários e 23 PRTs por execução**; os resultados também coincidem
entre as duas baterias.

| Cenário | Fator inicial | Confirmação: base → refinado | Fator da confirmação |
| --- | ---: | ---: | ---: |
| Dois TIFFs RGBA 4096 × 3072 com ICC | 1,027× | **1181,23 → 1123,60 ms** | **1,051×** |
| Dois TIFFs RGB 4096 × 3072 com ICC | 1,012×* | 1061,54 → 1054,69 ms | 1,006×* |
| Dois PNGs RGBA 2048 × 1536 com ICC | 1,074× | **474,51 → 452,10 ms** | **1,050×** |
| Dois TIFFs RGBA orientados com ICC | 1,032×* | 514,70 → 516,75 ms | 0,996×* |
| Quatro PNGs RGBA pequenos com ICC | 1,009×* | 200,80 → 204,01 ms | 0,984×* |
| Dois TIFFs RGBA grandes sem ICC | 1,055×* | 605,61 → 598,14 ms | 1,012×* |
| Dois PNGs de paleta/transparência com ICC | 1,011×* | 169,48 → 166,61 ms | 1,017×* |
| Dois PNGs RGB/chave de cor com ICC | 1,000×* | 175,44 → 171,56 ms | 1,023×* |
| Dois TIFFs LAB com ICC | 0,994×* | 402,41 → 404,44 ms | 0,995×* |
| Primeiro uso: um TIFF RGBA grande com ICC | 1,053× | **579,74 → 548,28 ms** | **1,057×** |
| Dois PNGs RGBA com ICC de entrada e saída | 1,073×* | 479,07 → 461,23 ms | 1,039×* |

*O intervalo pareado de 95% inclui 1 em pelo menos uma bateria: não se afirma
ganho de tempo confirmado nesses oito casos. Nos três demais, o limite inferior
ficou acima de 1 nas duas baterias. Nenhuma mediana ficou mais de 6% lenta.
Sem ICC, o caminho de produção é idêntico: a diferença observada é ruído da medição.

Fator geométrico dos 11 cenários: **1,0307×**, confirmado em **1,0207×**.
Intervalos pareados agregados: [1,0094; 1,0305] e [1,0012; 1,0233]. Os fatores são
razões das medianas; os intervalos descrevem a mediana das razões pareadas.
O principal benefício desta alteração é a redução de memória das fontes RGBA
com perfil, com uma aceleração menor e dependente do cenário.

O cronômetro cobre `Rip.process`: abrir/decodificar, converter cor, preparar a
fonte, renderizar, gravar/fsync e publicar o PRT. Construir o Rip e conferir hashes
ficam fora. A mesma instância é reutilizada nos lotes; o primeiro uso cria um Rip
novo por amostra. A compilação do perfil dentro de `process` é cronometrada no
primeiro uso. Ambas as implementações já possuem o cache ICC da etapa anterior.
As contagens de compilações são verificadas separadamente, fora do cronômetro.

As fontes são sintéticas, com cores variadas e alfa de 0 a 255. As pequenas têm
320 × 240 pixels; paleta/chave de cor, 1024 × 768; PNGs, LAB e TIFF orientado,
2048 × 1536. Os grandes têm 4096 × 3072. O TIFF orientado usa EXIF 6. Fontes usam
DPI 100 × 200; a saída tem largura de 1,27 cm e 720 × 2400 dpi, branco padrão,
sem etiqueta e margens de 0,05 polegada. São reduções substanciais das fontes.
Outras dimensões de impressão podem mudar a proporção do custo de preparação.

Dez cenários usam CMYK genérico; o último usa um ICC CMYK externo de saída,
identificado por SHA-256 sem distribuí-lo. Perfis de entrada sRGB/LAB são criados
pelo Pillow. Não inclui upload, estabilidade, prévias, journal, arquivamento ou
impressora física. Os fatores desta etapa não se multiplicam pelos anteriores.

## Pico de memória

VmHWM de processos Linux novos: dois workers por implementação/cenário em cada
bateria. Inclui Python/bibliotecas, primeiro lote e lote seguinte nos casos
aquecidos, caches e conferência dos PRTs. Fixtures são criadas fora dos workers.
São picos do RIP isolado, não RAM total do aplicativo com painel e outros serviços.

| Cenário | RSS inicial: base → refinado | RSS da confirmação: base → refinado |
| --- | ---: | ---: |
| TIFF RGBA grande | 302,59 → 194,58 MiB | **303,12 → 194,79 MiB (−35,7%)** |
| PNG RGBA com ICC | 113,74 → 86,33 MiB | **113,98 → 86,52 MiB (−24,1%)** |
| TIFF RGBA orientado | 138,03 → 111,01 MiB | **138,13 → 110,63 MiB (−19,9%)** |
| Primeiro uso RGBA grande | 302,75 → 194,50 MiB | **302,15 → 193,85 MiB (−35,8%)** |
| PNG RGBA com ICC de saída | 114,18 → 88,14 MiB | **114,63 → 87,61 MiB (−23,6%)** |

RGB grande, LAB e ausência de ICC não mostram redução relevante de RSS. Os valores
completos incluem as duas amostras de cada worker; há variação do alocador entre
processos. Não se altera o orçamento estimado das tiras ou o limite de pixels.

## Regressões e reprodução

**659 testes locais passaram em 57,73 s.** Os 43 novos casos verificam 32
combinações de RGBA/PA/paleta/chave de cor × quatro intenções × BPC, em cache frio
e quente, com alfa de 0 a 255, pixels exatos e fonte preservada; dez casos verificam
fechamento de temporários em sucesso/falha com traceback retido; um isola o canal
alfa LA com transformação simulada, sem usar sRGB como perfil cinza. As regressões
anteriores continuam comparando PRTs completos com ICC, orientação e cache.

O smoke local usa três uploads com alfa variável, sem ICC e com primeiro/repetido
sRGB. Os três PRTs e as três prévias com marca são idênticos; login, medidas e
encerramento também passam. O mesmo script verifica o executável Windows no CI.

- [Primeira bateria](../../benchmarks/campaign_runs/2026-11-10-input-alpha/report.json).
- [Confirmação independente](../../benchmarks/campaign_runs/2026-11-10-input-alpha/confirmation.json).
- [Ambiente, módulos e validação local](../../benchmarks/campaign_runs/2026-11-10-input-alpha/environment.json).

```bash
python benchmarks/benchmark_source_icc.py --suite alpha --baseline-ref feb3214 --icc /caminho/cmyk.icc --output /tmp/input-alpha.json
python benchmarks/benchmark_source_icc.py --suite alpha --baseline-ref feb3214 --icc /caminho/cmyk.icc --output /tmp/input-alpha-confirmation.json
python -m pytest -q
```

Sem `--icc`, o último cenário é omitido. A ferramenta exige prt/morph idênticos
à base e registra os hashes dos módulos. RSS usa VmHWM no Linux, ru_maxrss nos
demais Unix e fica indisponível no Windows. As baterias de prévias e interface
permanecem registradas nas etapas anteriores; esta mudança atua na entrada do RIP.

## Mais 15 rodadas após a otimização

Após incorporar a redução de buffers, a suíte `source-alpha` concluiu **15
rodadas consecutivas sem nova melhoria aceitável**, com zero aceites. Parte de
`7718ba1` e mantém a suíte input-icc anterior, acrescentando fonte RGBA com perfil,
RGBA grande com perfil e paleta com transparência/ICC. São **21 PRTs comparados e
12 cenários cronometrados**, incluindo fontes RGB/LAB/CMYK, largura ampliada e
limites de CPU. A auditoria independente confirmou os 21 PRTs e a identidade de
engine/prt/morph com o checkout.

Cada hipótese passa primeiro pelas fronteiras de retícula, empacotamento e
morfologia e pela igualdade de todos os PRTs. Cinco repetições pareadas por rodada,
aquecimento e ordem alternada. Aceitar exige ganho geométrico >1,5%, limite pareado
inferior >1,005× e nenhum caso mais de 6% lento, com confirmação independente.
A alternativa de memória exige redução de pelo menos 8% do maior pico rastreado,
fator geométrico ≥0,99 e os mesmos limites por caso, com pico rastreado ≤512 MiB.
Essa alternativa usa tracemalloc, separadamente dos workers de RSS acima.

| Rodada | Hipótese | Resultado |
| --- | --- | --- |
| 1 | Erosão exata de máscara cheia pelas distâncias às bordas | Sem ganho confirmado |
| 2 | Branco 100% opaco convertido diretamente para níveis 0/3 | Sem ganho confirmado |
| 3 | Normalização CMYK no próprio buffer float32 | Sem ganho confirmado |
| 4 | Eliminar cópia redundante da densidade float32 | Sem ganho confirmado |
| 5 | Aplicar máscara de densidade no próprio buffer | Sem ganho confirmado |
| 6 | Evitar multiplicação e alocação do alfa quando é opaco | Sem ganho confirmado |
| 7 | Tela exata float32 em largura e concorrência ampliadas | Sem ganho confirmado |
| 8 | Três trabalhadores em artes largas, preservando o plano de tiras | Sem ganho confirmado |
| 9 | Dois trabalhadores em artes largas, preservando o plano de tiras | Sem ganho confirmado |
| 10 | Reavaliar orçamento de buffers em 80 bytes por pixel | PRT largo com transparência diferente |
| 11 | Reavaliar orçamento de buffers em 64 bytes por pixel | PRT largo com transparência diferente |
| 12 | Comparar EDT transposta sob largura ampliada | Sem ganho confirmado |
| 13 | Duas ufuncs no lugar de clip | Sem ganho confirmado |
| 14 | Paralelismo a partir de 500 mil pixels | Sem ganho confirmado |
| 15 | Paralelismo a partir de dois milhões de pixels | Sem ganho confirmado |

As duas alterações do orçamento foram rejeitadas por divergência antes de
cronometrar. A hipótese de cópia EXIF já incorporada é pulada e não conta como
rodada. Engine/prt/morph permaneceram idênticos a `7718ba1`; a comparação final da
campanha é um controle com o mesmo código, sem atribuir ganho às oscilações.
São 15 rodadas novas além das 71 anteriores, somando **86**, em bases e cargas
registradas separadamente. O critério de parada foi atendido novamente; não
constitui prova de ótimo global.

- [Resultados das 15 rodadas](../../benchmarks/campaign_runs/2026-11-10-input-alpha/campaign.json).
- [Auditoria dos 21 PRTs e dos módulos](../../benchmarks/campaign_runs/2026-11-10-input-alpha/verification.json).

```bash
python benchmarks/rip_campaign.py --suite source-alpha --baseline-ref 7718ba1 --work-dir /tmp/source-alpha-campaign --icc /caminho/cmyk.icc --repeats 5 --apply
python benchmarks/verify_rip_campaign.py --work-dir /tmp/source-alpha-campaign --icc /caminho/cmyk.icc --check-checkout
```

Use um checkout limpo de `7718ba1` para reproduzir a campanha com `--apply`, que
pode aplicar um candidato se ele passar pelos critérios. Não faz commit, push,
merge ou publicação. A suíte exige um perfil CMYK válido via `--icc`.
