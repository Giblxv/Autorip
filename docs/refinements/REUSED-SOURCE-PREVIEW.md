# Reutilização da leitura de origem na prévia

Base: v0.8.19 (`e4728c7`). O worker fazia RIP e depois abria/decodificava a arte
novamente para publicar as duas miniaturas JPEG. O protótipo captura uma miniatura
durante a primeira leitura e conserva somente esse raster pequeno até o RIP terminar.

## Contrato de pixels e posse

`Rip.process(..., source_ready=...)` oferece a origem já orientada e ainda sem
conversão ICC. O observador pode lê-la durante a chamada; não deve alterá-la nem
reter o raster. O carregador mantém sua responsabilidade de fechar os arquivos
e todos os buffers que não foram entregues ao renderizador.

Capturar antes do ICC preserva a aparência anterior da prévia, que também não
aplicava o ICC de entrada. O raster de impressão continua seguindo a conversão
de cor normal. JPEGs e PRTs são comparados à base, inclusive com gamma não identidade.

O worker usa a captura apenas para RGB/cinza opacos e RGBA em buffers mutáveis.
Um wrapper Pillow sobre o core carregado evita copiar a imagem inteira antes de
reduzir. As operações usadas alocam a saída; se uma RGBA já couber nos limites,
ela é copiada para que o ICC in-place do RIP não altere a miniatura. O resultado
guardado mede no máximo 220 × 220 pixels e fica privado ao job ativo.

Rasters read-only/mapeados, paleta, LA, CMYK, modos restantes e chave de cor
conservam a leitura independente depois do RIP. Esses caminhos evitam reter a
origem junto a uma expansão RGBA de tamanho completo. Não há novo limite para
os pixels da arte admitida no programa.

O wrapper usa a API interna `_new` do Pillow. Os testes verificam que tamanho,
core, pixels e metadados da origem continuam intactos, e que a miniatura permanece
independente após modificar/fechar a imagem processada. O caminho foi exercitado
nos Pillow 12.3 e 13. Falhas na captura opcional deixam o worker tentar a leitura
habitual; não impedem o RIP.

## Finalização do job

A captura não escreve arquivos. A publicação ocorre depois de o RIP retornar,
mantendo composição de alfa, fundo, marca, uma codificação JPEG e duas gravações
atômicas. Falha, pausa e cancelamento descartam a captura. `_thumb` consome e
fecha a imagem recebida, inclusive em falha de publicação ou retorno antecipado.
O objeto Pillow não entra no journal, metadados JSON, integrações ou resposta HTTP.

## Verificação e medição

O protótipo inicial passou com 1.013 testes completos no Pillow 13 e 206 focados
no Pillow 12.3. Depois do guard de read-only, os 209 focados passaram nos dois.
O smoke local do aplicativo também conferiu planejamento de 400 MP, três uploads,
ICC, alfa e marca. A base final 0.8.20 passou em 1.016 testes locais completos
e novo smoke do aplicativo. Os cinco testes posteriores do verificador e a
correção do fechamento de mmap no oráculo dos testes passaram na matriz
Linux/Windows, Python 3.10/3.12, além do executável e instalador Windows reais.

`benchmarks/benchmark_reused_preview.py` compara processos novos, com ordem
aleatória, a mesma afinidade e saídas conferidas. Mede `Rip.process` e as duas
publicações JPEG, incluindo captura quando disponível; não inclui upload, fila,
journal, arquivamento, integrações ou impressora física. `Image.open` da origem
é contado; essa contagem não representa todas as aberturas internas do sistema.
RSS inclui buffers nativos e Python do worker isolado. Hashes e conferências
ficam fora do cronômetro, e a entrada deve continuar inalterada.

A primeira exploração revelou aumento de RSS no TIFF RGBA mapeado (377 → 489 MiB).
Essa variante foi rejeitada e o dado foi preservado. O guard posterior mantém
esses rasters no caminho independente; na bateria seguinte o pico voltou a
cerca de 377 MiB. Os tempos de casos pequenos e fallbacks também são preservados,
com controles adicionais A/A antes da conclusão.

O programa ainda usa rasters completos. Não há leitura out-of-core, promessa de
aceleração em todos os formatos ou extrapolação dos tempos Linux para Windows,
armazenamento de rede, dispositivos móveis ou impressão física.

## Resultados preservados

Os oito relatórios (artefato histórico não versionado)
registram 284 workers isolados, incluindo a variante inicial rejeitada e controles
A/A. Os casos correspondentes coincidiram também entre baterias. São Python
3.12.14/Pillow 13 em Linux compartilhado, CPUs 0–3; controles pequenos adicionais
usam CPU 0. As razões abaixo são tempo da base dividido pelo tempo da candidata;
valores menores que 1 indicam tempo maior. Medianas e amostras individuais estão
nos JSONs, sem remoção de outliers.

| Fluxo RIP + duas prévias | Bateria 3 pares | Confirmação 5 pares | RSS MiB aproximado: base → candidata |
| --- | ---: | ---: | ---: |
| RGB ICC 90 MP | 1,059× | 1,037× | 740 → 740 |
| RGBA ICC 90 MP | 1,335× | 1,296× | 790 → 740 |
| RGBA ICC EXIF 6, 90 MP | 1,428× | 1,326× | 785–789 → 740 |
| RGBA sem ICC 90 MP | 1,521× | — | 790 → 740 |
| JPEG RGB ICC 90 MP | 1,191× | 1,136× | 740 → 740 |
| CMYK ICC 30 MP, fallback | 0,995× | 1,039× | 382 → 382 |
| TIFF RGBA mapeado 30 MP, fallback | 0,926× | 1,023× | 377 → 378 |
| RGB 90 MP, impressão 25,4 cm / PRT 238 MB | 1,000× | — | 740 → 740 |

Os dois controles TIFF adicionais têm cinco pares cada: deflate RGBA 30 MP deu
1,195×, RSS 378 → 378 MiB; TIFF orientado deu 1,114×, RSS 496 → 396 MiB. São
controles adicionais de uma bateria, sem extrapolar seus tempos para todo TIFF.

Nos caminhos elegíveis, as chamadas Image.open da origem passaram de duas para
uma. Nos fallbacks permaneceram duas. A abertura do upload/inspeção não integra
essa contagem: o escopo é RIP seguido de prévia. Os bytes da entrada permaneceram
inalterados após todos os trabalhos.

Os A/A comparam a base com ela mesma: RGB 90 MP deu 0,926×; CMYK 1,031×;
RGBA 1,043×; RGBA EXIF 1,013×; TIFF mapeado 1,076×. No pequeno, nove pares
base/candidata deram 1,008×, mas nove pares A/A deram 0,806×. Portanto não se
atribui uma melhora/regressão consistente ao pequeno ou aos fallbacks, nem se
anuncia como ganho robusto a diferença pequena de RGB. O efeito mais claro e
repetido foi RGBA de 90 MP, cerca de 1,30–1,43× nessas cargas e 45–50 MiB menos
de RSS. A impressão de 25,4 cm ficou empatada; render e saída ainda dominam.

O modo direto da janela e o painel usam o mesmo worker do App. A CLI que produz
somente PRT continua sem precisar da captura, com source_ready ausente.

## Encerramento do refinamento

Após aceitar esta melhoria, o contador foi zerado. A
campanha final com ICC/RGBA (artefato histórico não versionado)
terminou às 12:11:35 de 11/11/2026 em São Paulo, antes das 22h, com 25 hipóteses
únicas consecutivas sem novo ganho validado. Não houve mudança adicional no
motor. A verificação independente conferiu fontes, contagem e 23 PRTs idênticos.
As nove recusas exploratórias anteriores e a proposta interrompida na retomada
não foram somadas à sequência. Há também uma campanha standard independente
preservada no repositório; os números das duas campanhas não são combinados.

A conclusão vale para os critérios e cargas registrados, não demonstra máximo
global de desempenho. O ganho desta versão é o reaproveitamento da prévia
medido acima, e não a comparação final do motor com seu próprio código.
