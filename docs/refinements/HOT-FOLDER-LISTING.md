# Consultas da hot folder com menos trabalho de disco

Base: AutoRIP 0.8.43, commit `fb47c76970009a1b269bb1c1985664624cbcd68e`.
A consulta da hot folder ordenava todos os nomes da pasta e, para cada arte
regular, consultava os metadados duas vezes: `lstat` e `islink`. Agora usa
`scandir`, filtra os nomes antes da consulta e faz `entry.stat` sem seguir
links. O teste de arquivo regular usa esse mesmo resultado.

A leitura consome cada entrada dentro do contexto de `scandir`, sem
manter objetos DirEntry e seus stat_result no cache após a varredura.
A resposta é ordenada pela mesma chave `casefold` do nome original; os
campos `name`, `size` e `mtime` e a sanitização do nome permanecem iguais.

Consultas simultâneas dessa lista são coordenadas por um lock exclusivo
da hot folder. Cada pedido executa uma varredura nova, sem TTL ou cache
de respostas. O lock de configurações é liberado antes da leitura; os
locks de estado, controle de trabalhos e impressão são independentes.
O teste concorrente confirma quatro leituras distintas, uma por vez,
e a disponibilidade do lock de configurações enquanto a varredura espera.

A primeira experiência usava somente `scandir`. Ela melhorou o caso
isolado, mas piorou o teste com quatro clientes em 1.000 artes. Isso
motivou a coordenação das varreduras. A experiência inicial não foi
integrada isoladamente.

## Precisão e comportamento

Os testes conferem filtros de extensões/dotfiles, ordenação, nomes Unicode,
sanitização, tamanho/mtime exatos, pastas ausentes ou inválidas, arquivos
removidos/substituídos, links normais/quebrados, falhas de enumeração,
fechamento do iterador e troca da pasta configurada. As respostas HTTP
continuam autenticadas e o ETag muda ao alterar um arquivo. Nenhum corpo
é enviado no 304; clientes sem login continuam recebendo 401.

A consulta não decodifica as artes nem altera arquivos de entrada.
O motor de RIP, PRT, protocolo PrintExp, cadência de polling e número
permitido de sessões de telefone mantêm suas regras anteriores.

## Método

Linux/Python 3.12.14, quatro CPUs disponíveis pela quota. Duas execuções
independentes do benchmark, sem concorrência com pytest ou strace.
Cada uma mede seis pastas (0, 100, 1.000 e 10.000 artes, incluindo
casos com igual quantidade de arquivos ignorados). São 11 grupos
base/nova/controle por pasta e cinco chamadas por lado/grupo, com ordem
balanceada entre as seis permutações e embaralhada. Todos os dados são
temporários, sem interferir nas artes do usuário.

O teste HTTP usa os handlers reais e quatro cenários: 1.000/10.000 artes
com um/quatro clientes. São sete grupos de base/nova/controle e duas
consultas por cliente/grupo. A chamada inicial de cada servidor verifica
corpo JSON e ETag iguais; as chamadas medidas enviam o ETag e verificam
304 sem corpo. Os clientes usam tokens distintos. A CPU dessa etapa inclui
servidor e clientes de loopback no mesmo processo; não é CPU exclusiva do
servidor. Importação e criação das pastas ficam fora dos tempos medidos.

As tabelas usam medianas das medianas por grupo. Os intervalos bootstrap
reamostram as razões pareadas dessas medianas. As contagens de syscalls
são feitas separadamente, sem strace nas execuções cronometradas.

## Listagem direta

| Artes / arquivos ignorados | Ensaio: base → nova | Confirmação: base → nova |
| --- | ---: | ---: |
| `0_images_0_ignored` | 0.010 → 0.011 ms | 0.010 → 0.010 ms |
| `100_images_0_ignored` | 0.513 → 0.333 ms | 0.529 → 0.336 ms |
| `1000_images_0_ignored` | 5.713 → 3.805 ms | 5.859 → 4.075 ms |
| `1000_images_1000_ignored` | 6.798 → 4.759 ms | 6.356 → 4.516 ms |
| `10000_images_0_ignored` | 62.444 → 43.792 ms | 88.501 → 71.413 ms |
| `10000_images_10000_ignored` | 70.187 → 50.803 ms | 80.868 → 59.420 ms |

A pasta vazia tem custo fixo semelhante, sem benefício relevante. O ganho
em pastas com arquivos vem da menor quantidade de consultas de metadados
e da ordenação somente dos resultados aceitos.

## Polling HTTP autenticado

| Artes / clientes | Ensaio: base → nova | Confirmação: base → nova |
| --- | ---: | ---: |
| `1000_images_1_clients` | 8.63 → 6.70 ms | 8.72 → 7.33 ms |
| `1000_images_4_clients` | 103.70 → 24.44 ms | 118.30 → 26.42 ms |
| `10000_images_1_clients` | 80.19 → 59.20 ms | 87.94 → 72.32 ms |
| `10000_images_4_clients` | 1069.66 → 245.31 ms | 1202.93 → 282.98 ms |

Com quatro clientes, a latência mediana caiu aproximadamente **73–78%**
contra as duas referências (base principal e controle) nos dois ensaios.
Os intervalos pareados contra ambas ficaram acima de 1 em todos os
cenários HTTP. Um controle A/A de 1.000 artes/quatro clientes na segunda
rodada indicou diferença apesar do mesmo código (1,025–1,307), mostrando
variação do ambiente; o efeito de cerca de quatro vezes contra as duas
referências permaneceu maior e se repetiu. Os dados brutos preservam
amostras, CPU de lote, intervalos e controles, sem remover valores extremos.

São medidas de loopback Linux com diretórios e metadados aquecidos.
Não medem Wi-Fi, rede compartilhada/NAS, Android físico, Windows do usuário,
velocidade total do aplicativo ou throughput do RIP. Os resultados não são
uma promessa de mesma porcentagem em cada instalação.

## Chamadas de sistema e memória

O rastreamento Linux de uma varredura de 100 artes e 100 arquivos ignorados
contou **200 → 100 chamadas lstat** referentes às artes, com o mesmo hash
de resposta. Foram rastreadas operações `%file`, filtradas pelos caminhos
exatos da fixture. Importações e consultas à pasta não entram nessa
contagem; strace não foi usado para medir os tempos acima.

Não há redução universal de memória. Na pasta de 10.000 artes sem arquivos
ignorados, o pico tracemalloc foi aproximadamente 3,33 → 3,97 MB: o novo
método mantém chaves de ordenação junto aos resultados, em vez da lista de
nomes anterior. No caso misto, o pico foi semelhante/menor. Os DirEntry e
seus stat_result são descartados durante a leitura, sem cache permanente.
Esses valores não representam o pico de RAM do processo inteiro.

## Verificação

**1.886 testes Python aprovados**, incluindo nove novos. As 51 provas de
polling/painel e os uploads em três clientes móveis simulados passaram.
Os testes concorrentes usam barreiras e snapshots distintos para verificar
coordenação sem cache; os mocks ficam restritos à pasta do próprio teste.
O motor, PRT, morfologia e HTML do painel são idênticos à 0.8.43.

As duas rodadas somam 1.980 chamadas diretas medidas e 840 consultas HTTP
condicionais, além das 12 respostas completas iniciais para comparar JSON
e ETag. Todas as respostas comparadas mantiveram o conteúdo esperado.

## Reprodução

```bash
python -m pytest -q
python benchmarks/benchmark_hot_listing.py --baseline-ref v0.8.43 --pairs 11 --output /tmp/hot-listing.json
# Para rastrear uma única varredura de uma pasta de teste já preparada:
strace -e trace=%file -o /tmp/listing-syscalls.log python benchmarks/benchmark_hot_listing.py --probe autorip/server.py --folder /tmp/artes-de-teste
node tools/smoke_polling_ui.cjs /tmp/hot-polling
node tools/smoke_mobile_uploads.cjs /tmp/hot-uploads
```

As provas de navegador requerem Playwright/Chromium e aceitam os seletores
`AUTORIP_PYTHON`, `AUTORIP_CHROMIUM`, `AUTORIP_PLAYWRIGHT_MODULE` e
`AUTORIP_NO_SANDBOX=1` no ambiente gerenciado. Strace é opcional e somente
para o rastreamento em Linux; não é dependência do programa.

Dados: [ensaio](hot-listing-benchmark.json),
[confirmação](hot-listing-confirmation.json) e
[contagem de syscalls](hot-listing-syscall-counts.json),
[provas de polling](hot-listing-polling.json) e
[uploads móveis](hot-listing-uploads.json).
A atualização chega ao celular pelo servidor; os binários nativos do APK
e do agente mantêm suas versões. Não houve prova física de impressão.
