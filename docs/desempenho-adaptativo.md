# CPU, memória, branco e ICC de entrada

Implementação local sobre a main `718438e`. Mantém os mesmos cálculos de cor,
fases da retícula, canais, cabeçalhos e gravação durável do PRT. Não acrescenta
dependências nem limites fixos de pixels.

## Escalonamento

O motor escolhe o número de workers conforme CPUs utilizáveis, quantidade de
tiras e memória disponível. Pode usar vinte threads quando há trabalho e RAM
suficientes, em vez do teto anterior de quatro. Afinidade disponível e quotas
CPU de cgroup são respeitadas. No Windows, a RAM disponível é consultada pela
API `GlobalMemoryStatusEx`; no Linux também se considera a memória do container.

O orçamento de buffers de trabalho é o menor valor entre 1/8 da RAM disponível
e 2 GiB. Se a medição de memória estiver indisponível, usa até 512 MiB. Esse
orçamento estima os buffers das etapas, não o RSS total do programa: a imagem
de origem e bibliotecas também ocupam memória.

**A grade das tiras permanece a da versão de base.** Alterar sua altura muda
as janelas/arredondamentos do Lanczos no Pillow e pode produzir pixels
diferentes. A referência histórica de quatro workers no cálculo dessa grade
preserva a geometria; a concorrência é calculada separadamente e pode passar
de quatro. O motor reduz a concorrência se faltar memória. Quando nem uma
tira dessa grade cabe no orçamento, informa falta de RAM em vez de alterar
a geometria de impressão. O teste de regressão cobre 345 linhas por tira em
uma saída de 2.880 pontos de largura, com diferentes orçamentos de memória.

O ProcessPool experimental divide as CPUs entre seus processos para evitar
multiplicar processos e threads usando todas as CPUs em cada nível.

## Branco automático

- Uma máscara cheia usa a distância exata até as quatro bordas externas,
  calculada em vetores por eixo, dispensando EDT nesse caso.
- Objetos cujo retângulo de suporte ocupa menos de 75% da máscara podem ter
  fechamento/erosão calculados nessa região. O padding físico e o exterior
  vazio são preservados; o resultado volta para as coordenadas originais.
- A componente horizontal da EDT usa scratch de aproximadamente 1 MiB
  (ou uma linha para larguras maiores), evitando um segundo raster float64
  completo. A ordem das operações que determina a distância permanece igual.

Os oráculos verificam distâncias, máscaras anisotrópicas, furos, objetos nas
quatro bordas e dimensões de uma única linha/coluna. A comparação do RIP também
verifica bytes do arquivo e metadados.

## Preparação de imagens grandes

Imagens RGB/RGBA a partir de quatro megapixels com ICC embutido podem usar
conversão em faixas de até 256 linhas. O thread principal cria faixas privadas
e as publica em ordem. Cada worker usa transformações LittleCMS privadas,
com os mesmos perfis, intent e compensação de ponto preto do caminho serial.
Alfa e perfil de saída são preservados. A concorrência das faixas é limitada
por CPU, memória e número de faixas.

Falhas esperam os workers antes de liberar buffers em uso; faixas concluídas
ou canceladas são fechadas. Entradas mapeadas/somente de leitura são copiadas
antes da transformação para não alterar os arquivos de origem.

A decodificação do arquivo continua no Pillow e ainda mantém o raster da
origem em RAM. Esta alteração paraleliza a conversão ICC de entrada; não
introduz um novo decoder TIFF nem promete streaming da entrada completa.

## Conversão CMYK

Quando não há ICC de saída e todos os limites de tinta são 100%, o motor usa
diretamente os valores float32 já normalizados, evitando multiplicação por
um e clipping redundantes. Limites personalizados e ICC de saída seguem o
cálculo existente. O atalho consulta a configuração atual a cada conversão.

## Validação e reprodução

```sh
python -m pytest -q
python benchmarks/benchmark_main_refinements.py --baseline-ref 718438e --pairs 15 --output /tmp/refinements.json
```

O benchmark carrega **engine, morph e prt da mesma revisão de base**, evitando
comparar o motor antigo com a morfologia nova por engano. Alterna seis ordens
de base/candidato/controle, descarta um aquecimento, mede o RIP completo e
confere SHA-256 e metadados de toda saída. A leitura de hashes fica fora do
tempo medido. `--cases-json` aceita uma lista de objetos com `name`, `path`,
`width_cm` e `settings` para medir arquivos grandes existentes.

As ferramentas de tuning reconhecem o escalonamento automático. O profiler
também preserva a identidade do loader nativo ao instrumentá-lo, mantendo
o caminho RGB opaco usado no programa.

A validação local foi feita em Linux com quota de quatro CPUs. Os testes
simulam o planejamento para vinte threads e as chamadas de memória do
Windows; isso não substitui medir a execução nativa no Windows/Xeon.

### Resultado local de 15/11/2026

1.262 testes aprovados. Nos benchmarks finais, 300 saídas foram verificadas,
incluindo aquecimento e controles, com hashes e metadados iguais à base.

| Cenário | Redução mediana no RIP completo | Grupos medidos |
| --- | ---: | ---: |
| RGBA com branco, suporte compacto | 34,5% | 15 |
| RGB com ICC de saída e branco | 17,6% | 15 |
| RGB pequeno, sem branco | 4,8% | 15 |
| PNG RGB de 90 MP, ICC de entrada e EXIF | 32,2% | 7 |
| TIFF RGBA de 30 MP, ICC de entrada | 16,1% | 7 |

Esses cenários tiveram intervalos bootstrap de 95% das razões pareadas
base/candidato e controle/candidato acima de 1. RGB sem branco maior e limites
de tinta personalizados tiveram variação suficiente para não concluir um
ganho geral nesses dois casos. A checagem adicional de largura de 10,16 cm
teve um grupo por cenário e serve como equivalência, não como prova estatística
de desempenho. As porcentagens são do ambiente de teste, após aquecimento;
não são uma previsão de duração no computador do usuário.
