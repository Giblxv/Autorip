# Empacotamento PRT por multiplicacao inteira

Base: `b6b2619` (v0.8.31). A alteracao afeta `pack2()` na escrita, nao o
leitor de PRT do PR #73 nem o modelo de reticula. O RIP entrega planos `uint8`;
outros tipos inteiros conservam o algoritmo anterior.

## Operacao e propriedade da memoria

Quatro niveis `a0..a3`, todos entre zero e tres, formam a palavra little-endian
`x = a0 + 256*a1 + 65536*a2 + 16777216*a3`. O byte alto de
`x * 0x40100401` modulo `2**32` e `64*a0 + 16*a1 + 4*a2 + a3`.
Os coeficientes dos bytes inferiores sao limitados a 3, 15 e 63, portanto nao
ha carries para alterar esse byte. A view usa `"<u4"` explicitamente.

A multiplicacao NumPy ocorre em uma copia privada contigua de um plano. Os
bytes de padding sao zerados antes da operacao; o resultado final tambem e
uma copia contigua independente. Nao modifica planos compartilhados, strides,
memmaps somente de leitura ou buffers do chamador. Nenhum cache persiste
dados entre blocos. A validacao `uint8` usa `max() > 3`, evitando criar duas
mascaras booleanas do tamanho da entrada. Validacoes de forma, largura,
tipos, cabecalho e niveis dos demais dtypes permanecem.

O gravador ainda escreve os canais/linhas na mesma ordem, sincroniza com
`fsync` e publica o temporario somente apos sucesso. ICC, meio-tom, branco,
geometria, scheduler, pausa/cancelamento, fila e aplicativos moveis nao mudam.

## Medicao

Dois ensaios independentes, sem a suite de testes concorrendo por CPU,
com 11 pares alternados AB/BA por cenario, aquecimento e controle A/A.
O microbenchmark executa dez empacotamentos por amostra. O RIP completo
inclui abertura, renderizacao, escrita, `fsync` e publicacao; o tempo de
hash/conferencia/remocao fica fora do cronometro. Cada par compara SHA-256
e metadados dos PRTs completos. A unica diferenca do motor entre os grupos
e a classe `PrtWriter` da base ou da alteracao.

Linux, Python 3.12, NumPy 2.5.4, quota de quatro CPUs, cinco CPUs informadas
pelo sistema. As fontes sao PNG RGB/RGBA sinteticos sem perfil ICC embutido.
O cenario largo tem aproximadamente 6000 colunas; outros incluem arte pequena,
branco e etiquetas. Nao e uma medicao no computador Windows do usuario.

O empacotamento isolado ficou de **2,32 a 7,40 vezes mais rapido** no primeiro
ensaio e de **2,48 a 7,39 vezes** na confirmacao. No RIP completo:

| Cenario | Ensaio: base → nova | Confirmacao: base → nova |
| --- | ---: | ---: |
| RGB pequeno | 8,11 → 7,94 ms | 8,37 → 7,75 ms |
| RGBA com branco | 428,94 → 414,04 ms | 432,39 → 411,57 ms |
| RGB sem branco | 110,01 → 100,31 ms | 109,69 → 101,16 ms |
| RGB largo | 375,16 → 363,63 ms | 385,88 → 357,95 ms |
| RGBA largo com branco | 1655,08 → 1570,32 ms | 1555,91 → 1480,25 ms |
| RGBA com etiquetas e branco | 425,53 → 431,53 ms | 410,66 → 399,31 ms |

RGB sem branco reduziu o tempo em 8,8% e 7,8%; RGBA com branco, em 3,5% e
4,8%. Nos dois cenarios, os intervalos pareados de 95% ficaram acima de 1x
nos dois ensaios. Os demais casos tiveram intervalos incluindo 1x em pelo
menos um ensaio: nao se afirma ganho confirmado neles. Com etiquetas, a
mediana oscilou de 1,4% mais lenta a 2,8% mais rapida. Controles A/A ficaram
em 1,0002x e 1,0010x, com intervalos abrangendo 1x. As **132 comparacoes
pareadas de PRTs** medidos (66 por ensaio, 264 arquivos) tiveram SHA e metadados iguais.

O pico de memoria rastreada depende do alinhamento. Para o plano contiguo
512 x 5669, passou de 4.376.593 para 3.645.976 bytes, cerca de 17% menos.
Para 512 x 12000, ja alinhado, aumentou de 6.144.265 para 7.680.536 bytes,
cerca de 25% mais: a copia privada troca memoria por velocidade. Estes sao
picos somente de `pack2()`, sem contar a entrada existente, o resto do motor
ou todo o RSS nativo. Nao se alega reducao universal de memoria.

## Validacao e reproducao

A suite local passou com **1.404 testes**, incluindo 67 casos novos. A prova
do empacotamento usa um oraculo de shifts independente do leitor de producao:
todos os 256 grupos de quatro niveis, padding, largura minima, layouts C/F,
strides positivos/negativos, broadcast, readonly, memmap desalinhado, tipos
inteiros com byteorder explicito, entradas invalidas, multiplos blocos e
alias entre canais. Os arquivos de entrada continuam intactos.

```sh
python -m pytest -q
python benchmarks/benchmark_prt_pack.py --baseline-ref v0.8.31 --pairs 11 --output /tmp/pack.json
python benchmarks/benchmark_prt_pack.py --baseline-ref v0.8.31 --pairs 11 --output /tmp/pack-confirmation.json
```

Os [dados do ensaio](prt-pack-benchmark.json) e da
[confirmacao](prt-pack-confirmation.json) incluem hashes das fontes Python, amostras, medianas, intervalos
bootstrap pareados de 95%, memoria rastreada e igualdade das saidas.
Nao ha limite fixo de velocidade usado como teste de CI. O ganho de uma etapa
nao deve ser apresentado como o mesmo ganho no RIP completo ou na impressora.
Nao houve validacao fisica no PrintExp/impressora nem em big-endian real.
