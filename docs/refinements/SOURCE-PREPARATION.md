# RIP: reutilização da imagem preparada para as tiras

Base: `ced6b2f`, após as [correções de consultas do painel](POLLING.md).
A preparação reutilizável entrou em `a9e4406`. Esta etapa mede o RIP completo,
da abertura da imagem até a publicação durável do PRT, com os mesmos bytes de
saída, dimensões físicas, perfil, canais, branco e controles de trabalho.

## Trabalho eliminado

O carregamento anterior criava uma cópia completa via EXIF transpose mesmo sem
rotação/reflexão. A variável que guardava essa cópia permanecia viva durante o
render. O carregamento agora só transforma orientações 2–8 e fecha explicitamente
os rasters de origem e orientação após produzir um RGBA independente, inclusive
em falhas de ICC. O context manager de uma imagem Pillow fecha o arquivo, mas
não é suficiente para descartar seu raster decodificado.

Há outro custo para artes grandes: `Image.resize` em RGBA com Lanczos converte
a imagem inteira para alfa pré-multiplicado (`RGBa`) antes de redimensionar cada
tira. O motor passa a fazer essa conversão uma vez por arte e compartilhar a
imagem preparada, somente para leitura, entre as tiras. Cada tira volta a RGBA
antes do espelhamento, da separação CMYK e do branco, na mesma ordem do Pillow.
Isso elimina conversões completas repetidas e buffers simultâneos dessas
conversões no processamento paralelo.

A geometria 1:1 permanece no caminho anterior. Quando tamanho e região coincidem,
o Pillow copia a imagem sem o ciclo RGBA → RGBa → RGBA; forçar esse ciclo pode
quantizar cores com alfa parcial. O teste compara esse caso e redimensionamentos
para ambos os lados, com uma e várias tiras. Não há troca de filtro, redução de
qualidade ou alteração dos limites de tiras, memória estimada ou trabalhadores.

## Medições pareadas e confirmação

Linux, Python 3.12/Pillow 13, quota de quatro CPUs e cinco CPUs informadas.
Duas baterias independentes, cada uma com sete repetições pareadas e aquecimento,
alternando a ordem. Reutiliza a instância Rip, como no servidor. Inclui leitura,
conversão de origem/ICC, render, gravação, fsync e publicação; o hash de conferência
fica fora do cronômetro. Não inclui espera de estabilidade, upload, miniaturas,
journal de admissão, hashing externo ou impressora física.

Os JPEG/PNG/TIFF grandes têm 4096 × 3072 pixels. As saídas usam 720 × 2400 dpi,
largura 1,27 cm, salvo o cenário paralelo RGBA de 2,54 cm. EXIF/DPI de origem
mudam a proporção física do JPEG orientado e do TIFF; os metadados exatos estão
nos relatórios. As artes são sintéticas: retângulo arredondado, elipse, bordas
vazias e alfa parcial; o JPEG deriva da versão RGB. O caso pequeno é RGBA 640 × 480. O ICC de saída usado é um perfil
CMYK instalado no ambiente, identificado por SHA-256, sem adicioná-lo ao programa.

| Cenário | Primeira bateria | Confirmação: base → refinado | Fator da confirmação |
| --- | ---: | ---: | ---: |
| RGBA pequeno | 1,034×* | 91,76 → 89,44 ms | 1,026×* |
| RGBA grande | 1,309× | 597,71 → 448,04 ms | 1,334× |
| RGBA grande, paralelo | 1,019×* | 387,67 → 348,05 ms | 1,114×* |
| JPEG grande | 1,421× | 489,86 → 342,23 ms | 1,431× |
| JPEG orientado | 1,281× | 358,44 → 271,25 ms | 1,321× |
| TIFF RGBA | 1,248× | 366,84 → 289,70 ms | 1,266× |
| RGBA com ICC de saída | 1,319× | 618,55 → 466,93 ms | 1,325× |

*O intervalo pareado de 95% do pequeno inclui 1 na confirmação; o do paralelo
inclui 1 na primeira bateria. Não se afirma ganho de tempo confirmado nas duas
baterias para esses casos. Os cinco demais ficaram acima de 1 em ambas. O fator
geométrico do conjunto foi **1,225×**, confirmado em **1,253×**. Esses fatores
valem para esta carga e não se multiplicam pelos ganhos das campanhas anteriores.
Os intervalos dos relatórios descrevem a mediana das razões pareadas; a coluna
acima usa a razão das medianas de duração, estimadores que podem diferir.

## Memória do RIP completo

Cada caso também roda em dois processos novos por implementação, sem criar a
arte dentro do worker. O pico é `VmHWM` do processo Linux atual, incluindo Python,
Pillow, SciPy e buffers nativos, até a leitura do PRT para conferir o hash.
Não usa o máximo herdado do processo pai. O quadro traz a mediana dos dois picos
da confirmação; as amostras de ambas as baterias estão nos dados.

| Cenário | RSS base → refinado |
| --- | ---: |
| RGBA pequeno | 65,0 → 62,5 MiB |
| RGBA grande | 245,3 → 145,5 MiB |
| RGBA grande, paralelo | 395,8 → 192,1 MiB |
| JPEG grande | 245,7 → 145,7 MiB |
| JPEG orientado | 391,3 → 194,4 MiB |
| TIFF RGBA | 246,6 → 145,8 MiB |
| RGBA com ICC de saída | 246,3 → 146,1 MiB |

O RGBA grande caiu cerca de **40,7%**; o paralelo caiu **51,5%** na confirmação
(52,0% na primeira bateria). São picos de RIPs isolados, não um limite da RAM
total do servidor/painel ou uma promessa para toda arte. O orçamento estimado de
512 MiB continua cobrindo buffers de tiras, sem limitar a RAM total do processo.

## Correção e reprodução

**456 testes locais passaram em 52,54 s.** O smoke do launcher v0.8.14 também
passou: inicialização, login, upload, PRT 720 × 2400 dpi e encerramento; a versão
do instalador permanece consistente. A auditoria independente confirmou os 15
PRTs e a identidade dos módulos do checkout.

Os 74 testes novos cobrem 64 combinações de oito modos/formatos com orientações
EXIF 1–8, incluindo PNG RGB/RGBA/LA/paleta, JPEG, TIFF RGBA/CMYK e perfis RGB/LAB
embutidos. Comparam pixels RGBA, DPI e indicação de alfa e, depois, o PRT completo
e metadados com o carregamento/resize anterior. Incluem canais remapeados, dois
planos brancos, etiquetas, dimensões 1:1, ampliação/redução e fechamento dos
rasters em sucesso e falha.

Em cada execução das duas baterias, os sete PRTs e seus metadados foram idênticos
à base, inclusive nos processos isolados de memória. As regressões existentes
continuam cobrindo perfil inválido, limite antes do decode, falta de espaço,
publicação sem sobrescrita, transparência, morfologia, serial/paralelo e controles.

```bash
python benchmarks/benchmark_source_preparation.py --baseline-ref ced6b2f --icc /caminho/perfil-cmyk.icc --output /tmp/source.json
python -m pytest -q
```

Sem `--icc`, a ferramenta mede os seis casos sem perfil de saída externo. O caso
ICC adicional exige um arquivo válido. RSS é medido via VmHWM no Linux, ru_maxrss
nos demais Unix e fica indisponível no Windows; as medições publicadas são Linux.
Não há nova dependência de produção, perfil distribuído ou migração de configuração.

## Mais 15 rodadas após o ganho incorporado

A campanha ampliada foi repetida sobre `a9e4406`, com cinco repetições pareadas
por cenário, aquecimento e confirmação independente como requisito de aceite.
Compara 15 PRTs e mede seis cenários, incluindo entrada de 4,8 milhões de pixels,
saída de 6000 colunas, transparência e ICC com limites simulados de uma/duas CPUs.
Os cenários e critérios são os da [campanha ampliada anterior](RIP-WIDE-CAMPAIGN.md):
ganho geométrico >1,5%, limite inferior pareado >1,005× e nenhum caso >6% lento;
ou redução de pico rastreado ≥8% com os limites de tempo previstos.

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

Foram **15 rodadas consecutivas sem melhoria aceitável, com zero aceites**.
As duas saídas divergentes foram recusadas antes da medição de tempo. A hipótese
antiga de evitar a cópia EXIF foi pulada, pois já está implementada; não conta
como rodada. O código dos três módulos do motor terminou idêntico ao de
`a9e4406`. A comparação final dessa campanha mede o mesmo código em ambos os
lados, servindo de controle, sem atribuir novo ganho a suas oscilações.

Estas são 15 rodadas adicionais às 41 históricas, totalizando 56 nas campanhas.
A otimização de preparação foi medida separadamente pelas duas baterias de sete
cenários acima. A sequência de parada foi novamente atendida depois desse ganho,
nos cenários e critérios descritos.

- [Primeira bateria de tempo/RSS e SHA-256 dos PRTs](../../benchmarks/campaign_runs/2026-11-09-source/report.json).
- [Confirmação independente](../../benchmarks/campaign_runs/2026-11-09-source/confirmation.json).
- [Dados das 15 rodadas adicionais](../../benchmarks/campaign_runs/2026-11-09-source/campaign.json).
- [Ambiente e validação local](../../benchmarks/campaign_runs/2026-11-09-source/environment.json).
- [Auditoria dos 15 PRTs e identidade dos módulos](../../benchmarks/campaign_runs/2026-11-09-source/verification.json).

```bash
python benchmarks/rip_campaign.py --suite extended --baseline-ref a9e4406 --work-dir /tmp/source-campaign --icc /caminho/perfil-cmyk.icc --repeats 5
python benchmarks/verify_rip_campaign.py --work-dir /tmp/source-campaign --icc /caminho/perfil-cmyk.icc
```

O benchmark de preparação exige `morph.py` e `prt.py` iguais aos da base,
verifica essa condição e registra seus hashes, isolando a preparação da imagem.
Os relatórios foram medidos com esses módulos idênticos. A campanha de hipóteses
é separada e registra o hash conjunto de seus três módulos.

Continuação: [cache limitado de ICC de entrada e nova campanha com 18 PRTs](INPUT-ICC-CACHE.md).
