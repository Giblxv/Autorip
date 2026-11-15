# Planos PRT vazios sem cópia e multiplicação

Base: `c543fa1`, AutoRIP 0.8.32. O refinamento reutiliza o máximo já calculado
pela validação dos planos `uint8`. Quando ele é zero, todos os níveis são zero:
o gravador pode produzir diretamente o resultado zerado, incluindo o padding,
sem copiar e multiplicar uma matriz inteira. Não acrescenta outra varredura.

Planos sem tinta aparecem em canais não usados, áreas transparentes e margens.
O gravador continua emitindo todos os canais e bytes declarados no cabeçalho;
não elimina planos do arquivo nem depende de cache persistente. O resultado
zerado tem memória própria, é contíguo e pode ser alterado pelo chamador sem
modificar a entrada ou resultados posteriores.

Planos com algum ponto seguem o empacotamento vetorial da v0.8.32, com a mesma
validação de níveis antes do despacho. Outros dtypes conservam seu fallback.
Não altera ICC, retícula, branco, geometria, tiras, concorrência, pausa,
cancelamento, sincronização, publicação do PRT ou recuperação por hash.

## Medição

Dois ensaios independentes de 11 pares alternados AB/BA por cenário, após
aquecimento. Os testes completos não concorrem com os benchmarks. Linux,
Python 3.12.14, NumPy 2.5.4, quota de quatro CPUs, cinco CPUs informadas.
O microbenchmark executa dez empacotamentos por amostra e confere SHA-256.

O RIP completo usa oito casos: seis controles RGB/RGBA da bateria anterior,
com branco, etiquetas, imagem pequena e saídas largas, além de RGBA totalmente
transparente e RGB preto sem branco. São PNGs sintéticos sem perfil embutido.
O cronômetro inclui abrir, renderizar, gravar, fsync e publicar; exclui hash e
remoção de conferência. A única troca entre os grupos é `PrtWriter` da base
ou da alteração. Cada par verifica SHA-256 e metadados do PRT completo.

| Plano vazio | Ensaio: base → nova | Confirmação: base → nova | Pico rastreado: base → nova |
| --- | ---: | ---: | ---: |
| 8 × 37 | 3,6 → 1,3 µs | 3,9 → 1,3 µs | 1080 → 248 B |
| 128 × 1417 | 31,9 → 4,5 µs | 41,2 → 4,9 µs | 230904 → 46232 B |
| 512 × 5669 | 1072,4 → 173,2 µs | 834,3 → 151,1 µs | 3645976 → 729272 B |
| 512 × 12000 | 1526,5 → 290,3 µs | 1592,7 → 303,4 µs | 7680536 → 1536184 B |

O empacotamento vazio ficou **2,85–7,07x** mais rápido no ensaio e
**2,95–8,43x** na confirmação. A redução de pico rastreado foi aproximadamente
80% nos três planos maiores e 77% no pequeno. Os intervalos pareados de 95%
dos oito cenários de RIP completo incluíram 1x nos dois ensaios: **não houve
ganho confirmado no tempo total**. As medianas variaram entre 0,7% mais lento
e 6,7% menos tempo no primeiro ensaio; entre 5,1% mais lento e 4,8% menos tempo
na confirmação. Os controles A/A tiveram razões 0,995x e 1,011x, com intervalos
abrangendo 1x. Os **176 pares de PRTs** medidos (88 por ensaio, 352 arquivos)
tiveram SHA-256 e metadados iguais.

Os [dados do ensaio](prt-empty-benchmark.json) e da
[confirmação](prt-empty-confirmation.json) ficam versionados para revisão.

O benefício confirmado é evitar trabalho e alocações no empacotamento vazio.
Não se afirma que a redução de memória da etapa seja a mesma redução da RAM
total, nem que sua aceleração se repita no RIP inteiro ou na impressora.
O pico dos planos não vazios permanece essencialmente igual à v0.8.32.

## Validação

**1.455 testes locais aprovados**, incluindo 51 novos casos: planos vazios com
padding, várias larguras, layouts C/F, strides negativos, broadcast e readonly;
independência entre chamadas; um ponto no último pixel; níveis inválidos;
e escrita multibloco com planos compartilhados e um canal com tinta.
O oráculo da escrita confere os bytes diretamente, sem depender de `unpack2()`.
Os 67 casos de equivalência do empacotamento vetorial também continuam passando.

```sh
python -m pytest -q
python benchmarks/benchmark_prt_pack.py --baseline-ref v0.8.32 --pairs 11 --output /tmp/empty-pack.json
python benchmarks/benchmark_prt_pack.py --baseline-ref v0.8.32 --pairs 11 --output /tmp/empty-pack-confirmation.json
```

Os relatórios registram amostras, medianas, intervalos pareados de 95%, hashes
das fontes, pico rastreado da etapa e igualdade dos resultados. O controle A/A
usa duas chamadas à mesma versão de referência. Não houve medição no Xeon do
usuário ou validação física na impressora.

## Hipótese descartada nesta rodada

Antes deste atalho foi testada uma cópia por blocos com scratch de 1 MiB.
Reduziu a memória isolada de planos grandes, mas não justificou o custo e a
complexidade no fluxo completo: a geometria atual já limita os planos das
tiras, e o caso RGB largo oscilou entre 6,7% e 2,4% mais lento. Os intervalos
incluíram 1x, portanto isso não prova regressão universal; também não forneceu
benefício suficiente para incorporá-la. A alteração em blocos ficou fora da main.
