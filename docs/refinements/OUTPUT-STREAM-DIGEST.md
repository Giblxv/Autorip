# SHA de recuperação durante a escrita do PRT

Base: `ab7ef80`, AutoRIP 0.8.34. O painel e a CLI com arquivamento precisam
registrar o SHA-256 do PRT antes da publicação para recuperar trabalhos após
interrupção. Antes, o callback reabria e relia todo o temporário após o fsync.

## Fluxo e compatibilidade

`PrtWriter` passa a oferecer `hash_output=True`, desativado por padrão. O hash
recebe o cabeçalho e os mesmos buffers contíguos já escritos, em ordem, sem
criar uma cópia completa. `output_sha256` só fica disponível após fechamento
bem-sucedido, com geometria/tamanho completos, flush e fsync. Falhas não expõem
um digest concluído nem permitem a publicação do PRT pelo motor.

O motor reconhece `before_publish.requires_output_sha256 is True` e fornece o
digest apenas no dicionário do callback. O resultado habitual de `process()`
permanece com os mesmos campos. O callback descreve o arquivo concluído pelo
gravador e não modifica seus bytes. Não há cache global de hashes.

O observador solicita o digest; o painel o solicita somente quando precisa
arquivar a origem e manter journal. Motores personalizados antigos continuam
compatíveis: se não fornecerem o digest, o callback faz a leitura anterior.
Callbacks sem solicitação explícita e trabalhos sem journal não ativam o hash
do gravador. Não há novo argumento obrigatório em `Rip.process()`.

O formato do journal e os valores SHA permanecem iguais aos obtidos pela
leitura independente do arquivo. A recuperação continua usando uma **nova
leitura dos bytes do PRT**, detectando alterações posteriores. A função
`file_sha256`, a validação de admissão e o agente PrintExp não foram alterados.
Cabeçalho, canais, ICC, branco, retícula, geometria, tiras, threads, controles,
fsync e publicação exclusiva do PRT preservam o comportamento anterior.

## Medição

Dois ensaios independentes de 11 pares AB/BA por caso, com aquecimento e sem
pytest concorrente. Linux/Python 3.12.14, NumPy 2.5.4/Pillow 13, quatro CPUs
disponíveis pela quota do ambiente. As entradas PNG RGB/RGBA são sintéticas,
sem ICC embutido ou perfil de saída.

O cronômetro inclui journal inicial, `Rip.process`, SHA de recuperação, journal
antes de publicar, metadados auxiliares e journal de sucesso, todos com as
mesmas sincronizações. Exclui importações/construção inicial, espera de
hot-folder, prévias, arquivamento físico da origem, impressora e a leitura
independente usada para conferir a medição. É o fluxo de RIP/hash/journal,
não o tempo de ponta a ponta de uma fila ou de um telefone.

| Caso | Ensaio: base → nova | Confirmação: base → nova |
| --- | ---: | ---: |
| RGB redimensionado, PRT 13,6 MiB | 150,25 → 138,57 ms | 157,22 → 145,67 ms |
| RGBA com branco, PRT 13,6 MiB | 565,43 → 523,10 ms | 550,35 → 534,12 ms |
| RGB, PRT 69,3 MiB | 565,96 → 513,65 ms | 555,73 → 504,85 ms |
| Transparente, PRT 103,8 MiB | 496,80 → 407,29 ms | 443,95 → 371,18 ms |
| Manual pequeno, sem journal | 22,20 → 22,40 ms | 23,13 → 23,71 ms |

Nos dois casos grandes, as reduções foram aproximadamente **9,2%** e
**16,4–18,0%**, com intervalos pareados de 95% acima de 1x nos dois ensaios.
Os outros casos não demonstraram ganho consistente nos dois ensaios. A/A
teve razões 1,043x e 0,994x, com intervalos incluindo 1x.

Cada ensaio evitou 44 releituras integrais para o SHA do journal, somando
2.309.651.520 bytes (cerca de 2,15 GiB) nos grupos medidos. Isso contabiliza
leituras explícitas solicitadas pelo programa, não I/O físico: o sistema
operacional pode servir dados do cache. O SHA continua sendo calculado uma
vez; sua execução é distribuída durante a escrita e pode se sobrepor ao render.

Foram comparados **110 pares de PRTs medidos**, além de aquecimentos e A/A,
com tamanho, SHA-256 e metadados iguais. O hash do journal foi validado por
leitura independente em todas as saídas arquivadas. Os
[dados do ensaio](output-digest-benchmark.json) e da
[confirmação](output-digest-confirmation.json) incluem fontes, amostras e contadores.

## Validação e reprodução

**1.508 testes locais aprovados**, incluindo 24 novos casos: digest multibloco
com padding, canais e views compartilhadas; modo padrão sem hash; falhas de
fechamento/fsync; solicitação explícita; callback sem alterar o resultado público;
falha de journal sem publicação; painel/CLI com e sem arquivamento; fallback de
motor antigo; e recuperação rejeitando conteúdo modificado depois de concluído.

```sh
python -m pytest -q
python benchmarks/benchmark_output_digest.py --baseline-ref v0.8.34 --pairs 11 --output /tmp/digest.json
python benchmarks/benchmark_output_digest.py --baseline-ref v0.8.34 --pairs 11 --output /tmp/digest-confirmation.json
```

Não houve medição no Xeon/NVMe do usuário ou impressão física. O benefício
depende do tamanho do PRT, disco, CPU e possibilidade de sobrepor hash e render.

Uma hipótese anterior de reutilização de buffers numéricos reduziu o pico da
etapa de meio-tom, mas não confirmou melhora no fluxo completo. Permaneceu fora
da main; este refinamento altera somente a produção e o uso do SHA do journal.
