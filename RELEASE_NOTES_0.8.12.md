# AutoRIP v0.8.12

Esta versão melhora a identificação e a ordem de processamento das artes.

Os arquivos PRT agora preservam o nome-base do PNG/TIFF/JPEG e recebem o tamanho calculado e o horário local do RIP. O padrão é `nome_10.50x21.25cm_20261109-215430.PRT`; quando há colisão, o AutoRIP acrescenta um sufixo numérico sem sobrescrever a saída anterior.

A fila do servidor prioriza arquivos menores por tamanho em bytes, normalmente liberando mais rapidamente trabalhos curtos. A hot folder usa a mesma regra; em caso de empate, mantém uma ordenação estável.

A nomenclatura é aplicada ao processamento manual, aos uploads do painel, à hot folder e à recuperação por journal. O journal continua registrando o nome final e o hash do PRT para impedir duplicações após falhas.

Validação: 192 testes passando, Ruff, compilação Python e validações de sintaxe executadas.
