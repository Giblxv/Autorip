# PR experimental — fusão, scheduler e cache de ruído

## Escopo

Este branch contém um cache limitado para o ruído azul e benchmarks reproduzíveis para:

- fusão experimental de halftone e packing 2-bit;
- matriz de scheduler com 1, 2 e 4 workers;
- tamanhos de tira de 256, 512 e 1024 linhas.

O caminho de produção de halftone/packing não foi substituído neste PR. A fusão é medida apenas pelo benchmark até que o resultado seja confirmado em 25 ciclos e no pipeline completo.

## Resultados iniciais

### Cache do ruído azul

Com 25 criações de `Rip` usando os mesmos parâmetros:

- primeira criação: aproximadamente 3,80 ms;
- mediana após aquecimento: aproximadamente 0,045 ms;
- cache: 24 hits, 1 miss.

O cache é limitado a 16 entradas e retorna arrays somente leitura para evitar mutação acidental compartilhada entre RIPs.

### Fusão halftone + packing

Fixture: 1024 × 4096, 7 repetições.

- baseline: 20,868 ms;
- variante fundida: 18,167 ms;
- ganho: **1,1487x (14,9%)**;
- saída: byte a byte idêntica;
- SHA-256: `624f64bc81edee5741b7d4b1eceee0173c1fdf5902bc8ac049bb509c48dde370`.

O resultado é promissor, mas ainda é somente microbenchmark. A promoção exige medir o RIP completo em múltiplos tamanhos e confirmar a igualdade do PRT.

### Scheduler

A matriz inicial executou 2 repetições por combinação. Todas as combinações produziram saída byte a byte idêntica. Neste ambiente, a melhor combinação inicial foi 4 workers e tira de 256 linhas, com mediana de aproximadamente 0,134 s; 1 worker e tira de 512 linhas ficou em aproximadamente 0,413 s. Esses números são específicos do ambiente e ainda não justificam alterar defaults sem uma campanha maior.

## Próximos gates

1. suíte completa;
2. 25 ciclos independentes de integração e desempenho;
3. checks Linux/Windows e build remoto;
4. revisão cruzada do PR #62 e de qualquer PR aberto adicional;
5. somente depois decidir se a fusão merece um PR de produção separado.
