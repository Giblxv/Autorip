# RIP: reutilização limitada das transformações ICC de entrada

Base: `dd490f9`, após a [preparação reutilizável das tiras](SOURCE-PREPARATION.md).
Esta etapa reduz a compilação repetida dos perfis embutidos nas artes. Não muda
a transformação de saída, o tratamento de transparência, o filtro ou a geometria.

## Cache e isolamento

Antes, cada arquivo com ICC embutido passava por `profileToProfile`, que cria uma
transformação nova. Agora o motor reutiliza a transformação de entrada → sRGB
quando o conteúdo completo do perfil, modo de cor, intenção e compensação de
ponto preto coincidem. RGB, RGBA e paleta podem compartilhar a transformação RGB;
o alfa continua sendo restaurado separadamente, com os mesmos pixels anteriores.

O cache é local a cada instância Rip e thread. Transformações LittleCMS de entrada
mantêm seu cache nativo de pixels e nunca são compartilhadas entre threads.
Isso permite conservar os flags anteriores e aplicar cor em threads independentes,
sem compartilhar o estado mutável do cache nativo de pixels.

Cada cache retém no máximo **oito transformações** e **2 MiB de soma do tamanho
dos perfis por entrada**, com expulsão LRU. O mesmo perfil em contextos diferentes
conta novamente nesse orçamento. O limite cobre payloads de perfil das chaves,
sem medir buffers nativos compilados ou a RAM total. Ele se aplica por instância
e thread; as threads internas de render não fazem a conversão ICC de entrada.

Perfis acima do orçamento continuam sendo convertidos, sem retenção no cache.
Artes sem ICC seguem seu caminho direto. Perfis inválidos e modos incompatíveis
continuam falhando explicitamente, sem fallback de cor silencioso. Uma falha de
compilação não vira entrada de cache. As referências são liberadas ao terminar
a thread ou descartar a instância, inclusive ao substituir o motor por configuração.

## Medição do RIP completo em lotes

Duas baterias independentes, com sete repetições pareadas e aquecimento por
cenário, alternando a ordem. O Rip persiste entre arquivos, como no worker do
painel e no observador CLI. Nos cenários aquecidos, a mesma instância é usada
entre os lotes; no controle de primeiro uso, cada medição recebe um Rip novo.
A construção da instância fica fora do cronômetro em ambos os lados.

Os tempos somam abrir/decodificar cada arte, converter cor, preparar/redimensionar,
gerar canais/branco, gravar, fsync e publicar o PRT. A conferência de SHA-256 e
metadados fica fora do cronômetro, mas ocorre em cada arquivo de cada execução.
Não inclui upload, estabilidade de entrada, miniaturas, journal ou impressora.

As artes pequenas são TIFFs sintéticos 320 × 240 com cores variadas; os grandes
são LAB 2048 × 1536, com cores variadas ou preenchimento sólido. Os lotes pequenos
têm oito arquivos e os grandes, dois. A largura é 1,27 cm, em 720 × 2400 dpi,
com margens de 0,05 polegada e branco padrão. O caso de primeiro uso tem uma arte.
Os perfis RGB/LAB são criados pelo Pillow; o CMYK usa um perfil instalado no
ambiente, identificado por SHA-256 e não distribuído nesta mudança. A saída usa
a conversão CMYK genérica nestes tempos; configurar outro ICC de saída pode
mudar o tempo total e a proporção do ganho.

| Cenário | Primeira bateria | Confirmação: base → refinado | Fator da confirmação |
| --- | ---: | ---: | ---: |
| Oito RGB com perfil repetido | 1,030×* | 688,71 → 672,78 ms | 1,024×* |
| Oito LAB com perfil repetido | 1,109× | 772,83 → 703,06 ms | 1,099× |
| Oito CMYK com perfil repetido | 1,328× | 949,12 → 704,29 ms | 1,348× |
| Oito arquivos, três perfis alternados | 1,153× | 781,20 → 695,34 ms | 1,123× |
| Primeiro uso LAB | 0,986×* | 94,40 → 94,22 ms | 1,002×* |
| Oito sem ICC | 1,013×* | 672,15 → 667,30 ms | 1,007×* |
| Dois LAB grandes com cores variadas | 1,048× | 488,58 → 475,05 ms | 1,028× |
| Dois LAB grandes sólidos | 1,024×* | 411,60 → 384,18 ms | 1,071×* |
| Oito LAB com perfil acima do orçamento | 1,011×* | 772,22 → 760,55 ms | 1,015×* |

*Não houve ganho de tempo confirmado nas duas baterias nesses cinco casos:
o intervalo pareado de 95% incluiu 1 em pelo menos uma. Os quatro demais ficaram
acima de 1 em ambas. O conjunto teve fator geométrico **1,0738×**, confirmado em
**1,0754×**; intervalos pareados agregados [1,0653; 1,0802] e [1,0741; 1,0815].
Os fatores são razões das medianas de duração. Os intervalos por caso descrevem
a mediana das razões pareadas, que pode diferir dessa razão. Nenhum cenário teve
mediana mais de 6% lenta em qualquer das duas baterias. Não se multiplicam estes
fatores pelos ganhos anteriores ou se promete aceleração de toda arte.

A instrumentação das compilações roda separadamente do cronômetro e confirmou:

| Lote de oito | Base: primeiro / seguinte | Refinado: primeiro / seguinte |
| --- | ---: | ---: |
| Um perfil repetido | 8 / 8 | 1 / 0 |
| Três perfis alternados | 8 / 8 | 3 / 0 |
| Perfil acima de 2 MiB | 8 / 8 | 8 / 8 |
| Sem ICC | 0 / 0 | 0 / 0 |

O perfil acima do orçamento é um LAB válido com padding, armazenado em TIFF.
O caso verifica o caminho sem cache, sem limitar a aceitação de perfis válidos.

## Memória e correção

O cache retém perfis e estruturas nativas para evitar recompilação. O RSS é
medido em dois processos novos por implementação/caso em cada bateria, usando
VmHWM no Linux. Inclui Python/bibliotecas, dois lotes nos casos aquecidos, cache
e leitura dos PRTs para conferência. As fixtures são criadas fora dos workers.

Na confirmação, as medianas do pico RSS foram 62,37 → 62,80 MiB no lote CMYK e
62,91 → 63,33 MiB no misto. O cache misto reteve três entradas e cerca de 184 KiB
de payloads de perfil. Há oscilações de alocador entre processos; esses resultados
não demonstram redução de memória. Os dados completos incluem as duas amostras,
quantidade de entradas e bytes retidos, além do hash e metadados de cada saída.

**504 testes locais passaram em 54,71 s**, além da auditoria independente dos
18 PRTs com verificação dos módulos do checkout. Os smokes de fila, miniaturas
e 23 cenários de consultas do painel passaram novamente, sem erros JavaScript.

Os 48 testes novos comparam pixels RGBA e PRTs completos em cache frio/quente
para RGB, RGBA, paleta, LAB e CMYK, nas quatro intenções e com/sem BPC. Também cobrem
conteúdo do perfil e contexto na chave, preservação de alfa, LRU por entradas e
bytes, perfil acima do orçamento, erros sem contaminar entradas válidas, ausência
de cache sem ICC e uso simultâneo em threads. O teste de threads verifica que
cada transformação pertence à sua thread e que ela é liberada quando a thread sai.

O smoke do executável passou a gerar três PRTs iguais: um sem ICC, um com primeiro
uso de sRGB e outro com o mesmo perfil. Verifica bytes, medidas, login e encerramento,
exercitando a primeira compilação e a reutilização no worker empacotado.

```bash
python benchmarks/benchmark_source_icc.py --baseline-ref dd490f9 --icc /caminho/cmyk.icc --output /tmp/input-icc.json
python -m pytest -q
```

Sem `--icc`, a ferramenta omite o lote CMYK e alterna dois perfis no misto.
Exige `morph.py` e `prt.py` idênticos à base e registra seus hashes, isolando esta
alteração. RSS usa VmHWM no Linux, ru_maxrss nos demais Unix e fica indisponível
no Windows. Não há nova dependência de produção ou migração de configuração.

## Campanha adicional com ICC de entrada

Após o ganho medido, foram executadas **15 rodadas consecutivas sem nova melhoria
aceitável**, com zero aceites, sobre `6eabb44`. A suíte `input-icc` estende a
bateria ampliada: mantém seus 15 cenários e acrescenta fontes RGB, LAB e CMYK com
ICC embutido, totalizando **18 comparações completas de PRT** e **nove cenários
cronometrados**. O CMYK é calibrado com o perfil passado por `--icc`, também usado
na avaliação de saída das duas cargas originais de ICC.

Cada rodada passou pela verificação de retícula, empacotamento e morfologia e
pela igualdade dos arquivos antes de cronometrar. Foram cinco repetições pareadas,
aquecimento, ordem alternada e exigência de confirmação independente antes de
qualquer aceite, com os mesmos critérios da campanha anterior: ganho geométrico
>1,5%, limite pareado inferior >1,005× e nenhum caso mais de 6% lento; ou o critério
alternativo documentado de memória rastreada. Isso é separado do RSS dos workers
e das duas baterias de lotes acima.

| Rodada | Hipótese | Resultado |
| --- | --- | --- |
| 1 | Erosão analítica de máscara preenchida | Sem ganho confirmado |
| 2 | Branco opaco diretamente em níveis 0/3 | Sem ganho confirmado |
| 3 | Normalização CMYK no próprio buffer | Sem ganho confirmado |
| 4 | Densidade sem cópia float32 | Sem ganho confirmado |
| 5 | Máscara de densidade no próprio buffer | Sem ganho confirmado |
| 6 | Evitar multiplicação/alocação de alfa opaco | Sem ganho confirmado |
| 7 | Retícula float32 | Sem ganho confirmado |
| 8 | Três trabalhadores nas artes largas | Sem ganho confirmado |
| 9 | Dois trabalhadores nas artes largas | Sem ganho confirmado |
| 10 | Orçamento estimado de 80 bytes/pixel | PRT largo com transparência diferente |
| 11 | Orçamento estimado de 64 bytes/pixel | PRT largo com transparência diferente |
| 12 | EDT transposta | Sem ganho confirmado |
| 13 | Duas ufuncs no lugar de clip | Sem ganho confirmado |
| 14 | Paralelismo a partir de 500 mil pixels | Sem ganho confirmado |
| 15 | Paralelismo a partir de dois milhões de pixels | Sem ganho confirmado |

As duas saídas divergentes foram recusadas antes de cronometrar. O código final
de engine/prt/morph permaneceu idêntico ao da base desta campanha; sua comparação
final mede o mesmo código e serve de controle, sem atribuir ganho a oscilações.
A hipótese EXIF já implementada não conta como rodada. São 15 rodadas adicionais
às 56 anteriores, somando 71 nas campanhas, em cargas e bases diferentes. O cache
foi avaliado separadamente nas duas baterias de nove cenários. A condição de
parada foi novamente atendida depois de incorporá-lo, nos critérios descritos.

- [Primeira bateria, contagens, memória e PRTs](../../benchmarks/campaign_runs/2026-11-09-input-icc/report.json).
- [Confirmação independente](../../benchmarks/campaign_runs/2026-11-09-input-icc/confirmation.json).
- [Dados das 15 rodadas adicionais](../../benchmarks/campaign_runs/2026-11-09-input-icc/campaign.json).
- [Auditoria dos 18 PRTs e identidade dos módulos](../../benchmarks/campaign_runs/2026-11-09-input-icc/verification.json).
- [Ambiente e validação local](../../benchmarks/campaign_runs/2026-11-09-input-icc/environment.json).

```bash
python benchmarks/rip_campaign.py --suite input-icc --baseline-ref 6eabb44 --work-dir /tmp/input-icc-campaign --icc /caminho/cmyk.icc --repeats 5
python benchmarks/verify_rip_campaign.py --work-dir /tmp/input-icc-campaign --icc /caminho/cmyk.icc
```

Esta suíte exige `--icc` para produzir e avaliar a fonte CMYK. Não substitui a
bateria anterior: acrescenta arquivos com perfil embutido à verificação. As
campanhas históricas continuam registradas com suas bases e cenários originais.

Continuação: [conclusão dos trabalhos com marcas preparadas reutilizadas nas prévias](WATERMARK-CACHE.md).
