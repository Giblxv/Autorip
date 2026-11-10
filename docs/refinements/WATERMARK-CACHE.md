# Conclusão do trabalho: marcas preparadas reutilizadas nas prévias

Base: `25fd1c0`, após o [cache de ICC de entrada](INPUT-ICC-CACHE.md).
Esta continuação otimiza a etapa que gera a prévia após publicar o PRT. O motor
de impressão, seus arquivos e limites de tiras/trabalhadores permanecem idênticos
à base. Os fatores abaixo descrevem RIP + prévia, sem atribuir aceleração nova
ao renderizador PRT isolado.

## Trabalho eliminado e limites

Cada trabalho abria e redimensionava a mesma marca-d'água, mesmo quando só a arte
mudava. Agora cada instância App guarda versões RGBA pequenas da marca, por
caminho físico/identidade do arquivo e dimensões solicitadas. O cache guarda
até **16 entradas e 1 MiB de pixels RGBA**, com LRU e expiração de 60 segundos
contada desde a preparação, sem renovar o prazo em hits. Há custos adicionais
de objetos Python/Pillow; esse orçamento não limita a RAM total do aplicativo.

Os dados retidos são recriados a partir dos pixels reduzidos: ICC/EXIF e outros
metadados grandes não ficam no cache. Uma prévia acima do orçamento continua
funcionando sem retenção. Não é armazenado o raster original da marca.

Cada consumidor recebe uma cópia independente. A opacidade é aplicada nessa
cópia, permitindo alterá-la sem recarregar a marca ou contaminar os trabalhos
seguintes. O mutex cobre consulta, cópia e alteração do LRU; decodes frios podem
ocorrer simultaneamente e resultam em uma única entrada contabilizada. Expulsões
e expiração fecham explicitamente os buffers retidos.

A assinatura considera caminho físico, dispositivo/inode, modo, tamanho e tempos
mtime/ctime em nanossegundos, além da identidade de um link simbólico quando ele
existe. Só são aceitos arquivos regulares. Uma troca/edição observável invalida
a entrada; a assinatura é conferida novamente após carregar e uma imagem alterada
durante essa etapa não é inserida. O TTL limita a retenção quando o sistema de
arquivos não revela uma mudança pela assinatura. A consulta continua validando
o arquivo real, inclusive antes de devolver um hit.

O carregamento por caminho foi preservado. A prova de equivalência identificou
que trocar o nome por um objeto de arquivo no Pillow mudava alguns TIFF RGBA
orientados; essa variante foi descartada. A orientação da marca segue a regra
anterior: não há EXIF transpose adicional. O comportamento próprio do decoder
TIFF permanece igual ao da base.

## Medição integrada

Duas baterias independentes de sete repetições pareadas, com aquecimento e ordem
alternada. Cada cenário usa o mesmo Rip e App entre trabalhos. O controle de
primeiro uso cria um cache vazio a cada medição. A construção das instâncias
fica fora do cronômetro nos dois lados.

São cronometradas separadamente as chamadas `Rip.process` e `App._thumb` e o
total é a soma dessas etapas. Inclui abrir/decodificar a arte, cor, renderização,
gravação/fsync/publicação de PRT, composição da marca, codificação JPEG e as duas
publicações atômicas da prévia. Não inclui upload, estabilidade de entrada,
journal, metadados auxiliares, integrações, arquivamento ou impressora física.
Hashes e conferência de metadados ficam fora do cronômetro. O caso de marca
alterada copia a nova versão antes da chamada, também fora do tempo medido.

As artes sintéticas têm formas coloridas, alfa parcial e bordas vazias. A pequena
é PNG RGBA 640 × 480; a grande, 4096 × 3072. Há também JPEG RGB 2048 × 1536 com
EXIF 6 e DPI de origem 100 × 200. A saída é 720 × 2400 dpi, largura 1,27 cm,
margens de 0,05 polegada, branco padrão e sem ICC de saída externo. A marca grande
é RGBA 2048 × 2048 com alfa parcial; a pequena tem 64 × 64. Há um controle TIFF
RGBA com EXIF 6 e uma alternância entre duas marcas. Opacidade 0,35 em todos os
cenários com marca. Tamanho e transparência mantêm os valores da base.

Cada execução confere o SHA-256 do PRT e JPEG, metadados do PRT e igualdade dos
JPEGs por ID/por nome. Contagens de carregamento da marca são instrumentadas
separadamente do cronômetro. O programa distribui o mesmo JPEG qualidade 82;
a arte, o filtro, a opacidade e a composição não são simplificados.

## Correção, memória e reprodução

Os testes adicionais incluem 96 combinações de formato/modo, orientação da marca
e opacidade, comparando JPEGs frios/quentes com o caminho anterior sem cache.
Cobrem PNG RGBA/RGB/LA/paleta, JPEG RGB/CMYK e TIFF RGBA/RGB; orientações 1, 3, 6
e 8; opacidades 0, 0,35 e 1. Os testes restantes verificam cópias independentes,
expulsão sem invalidar consumidores, alteração de opacidade, edição/substituição
de arquivos, links, remoção, alteração durante o decode, limites por entradas e
bytes, bypass acima do orçamento, TTL, descarte de metadados grandes, recuperação
após falha, duas chamadas simultâneas e recusa de FIFO sem bloquear o worker.
O teste de FIFO é específico de sistemas que oferecem esse tipo de arquivo.

RSS é medido em dois workers novos por implementação/cenário em cada bateria,
via VmHWM no Linux. Inclui Python/bibliotecas, o primeiro lote e outro aquecido,
cache e leitura dos arquivos para conferir hashes. Portanto inclui a primeira
preparação da marca; não é um pico de estado aquecido artificialmente. As imagens
de entrada são geradas fora dos workers. Os dados também registram os pixels
retidos e a quantidade de entradas, sem converter esse limite em promessa de RAM.

```bash
python benchmarks/benchmark_watermark_flow.py --baseline-ref 25fd1c0 --output /tmp/watermarks.json
python -m pytest -q
```

A ferramenta exige engine/prt/morph idênticos à base e registra seus hashes, bem
como o hash do servidor e módulo de cache medidos. RSS usa VmHWM no Linux,
ru_maxrss nos demais Unix e fica indisponível no Windows. Não há perfil novo,
dependência de produção ou migração de configuração.

As 71 rodadas históricas do motor, com as últimas 15 sem ganho aceito, continuam
registradas em suas bases. Esta mudança do servidor não modifica esses três
módulos e não acrescenta rodadas à contagem. Seus ganhos são da etapa de prévia
e da soma RIP + prévia medida aqui, em uma carga diferente das baterias anteriores.

## Resultados e validação

| Soma de RIP + prévia do lote | Primeira bateria | Confirmação: base → refinado | Fator da confirmação |
| --- | ---: | ---: | ---: |
| Quatro artes pequenas, marca PNG grande | 1,675× | 701,45 → 413,27 ms | 1,697× |
| Duas artes grandes, marca PNG grande | 1,100× | 1502,26 → 1371,35 ms | 1,095× |
| Duas artes JPEG orientadas, marca PNG grande | 1,455× | 470,88 → 332,19 ms | 1,417× |
| Quatro artes pequenas, marca pequena | 1,003×* | 403,93 → 401,42 ms | 1,006×* |
| Primeiro uso, uma arte pequena/marca grande | 1,013×* | 167,69 → 166,35 ms | 1,008×* |
| Quatro artes pequenas, sem marca | 1,011×* | 397,35 → 393,61 ms | 1,010×* |
| Duas artes pequenas, marca alterada entre elas | 1,010×* | 346,91 → 338,27 ms | 1,026×* |
| Quatro artes pequenas, marca TIFF orientada | 1,477× | 574,40 → 400,20 ms | 1,435× |

*Não houve ganho confirmado nas duas baterias nesses quatro controles: pelo
menos um intervalo pareado de 95% incluiu 1. Nos quatro cenários restantes,
os intervalos ficaram acima de 1 nas duas baterias. Nenhuma mediana de cenário
ficou mais de 6% lenta. Os fatores são razões das medianas de duração; os
intervalos por cenário descrevem medianas das razões pareadas, estimadores que
podem diferir. O fator geométrico do conjunto foi **1,193×**, confirmado em
**1,188×**, com intervalos pareados agregados [1,1708; 1,2012] e [1,1801; 1,2068].
Esses resultados não se multiplicam pelos fatores das etapas anteriores.

No lote pequeno com marca grande, a mediana do componente de prévia da confirmação
caiu de 317,1 para 39,6 ms. O componente de RIP ficou em 381,4 e 372,7 ms, com
código idêntico: essa oscilação não é atribuída à mudança do servidor. As medianas
dos componentes não precisam somar a mediana dos totais, pois vêm de amostras
pareadas diferentes.

A contagem independente confirmou **4/4 → 1/0 carregamentos da marca** no
primeiro/segundo lote de quatro arquivos. O primeiro uso carrega uma vez nos dois
lados; ao alterar a marca a cada arquivo, os dois lados recarregam. Marcas pequenas
também são reutilizadas, mas seu custo não trouxe aceleração confirmada no total.

O cache reteve 26.896 bytes de pixels no caso comum de marca grande. Na confirmação,
o pico RSS mediano isolado foi 88,81 → 88,51 MiB no lote pequeno e 149,42 → 149,32 MiB
no grande. Não se afirma redução de RAM: os picos incluem a primeira preparação,
e o benefício medido é evitar seu trabalho repetido. Há até 1 MiB retido por App
mais overhead; os dados registram também os controles e as amostras individuais.

**616 testes locais passaram em 55,87 s**, incluindo os 112 novos de marca/cache.
O smoke local v0.8.14 passou com login, três uploads, PRTs idênticos sem ICC/com ICC
repetido, três prévias idênticas usando a mesma marca e encerramento. As versões
Python/instalador continuam consistentes. Os smokes de fila, miniaturas e 23 cenários de consultas do painel passaram
novamente, sem erros JavaScript; os detalhes e a CI constam na validação do PR.

- [Primeira bateria de RIP/prévia, contagens, RSS e hashes](../../benchmarks/campaign_runs/2026-11-09-watermarks/report.json).
- [Confirmação independente](../../benchmarks/campaign_runs/2026-11-09-watermarks/confirmation.json).
- [Ambiente e regressões locais](../../benchmarks/campaign_runs/2026-11-09-watermarks/environment.json).

Continuação: [menos buffers na entrada do RIP com ICC e transparência](SOURCE-ALPHA.md).
