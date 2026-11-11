# Confirmação predefinida do caminho estreito

Candidata congelada: round-001-threshold-narrow-fallback da campanha c8ff590.
Sem alterações de produção ainda. As três recusas da campanha aquecida e a
rodada4 parcial ficam preservadas, sem reclassificar seus resultados.

Dois conjuntos independentes de 21 pares em processos novos, primeiro RIP por
objeto, ordem balanceada e aleatória, os 11 casos cronometrados da suite v2.
Controle A/A separado de31pares se houver sinal confirmado. Sem testes locais
concorrentes. Mesma afinidade0–3. Hashes de fontes, PRTs e metadados obrigatórios.
Mede RIP, sem upload/prévia/fila. RSS inclui inicialização/imports e nativos.
O smoke de um par não participa da decisão; não fornece intervalo de confiança.

Regra primária: duas baterias com média geométrica>1,015, limite bootstrap>1,005,
nenhum cenário>6%mais lento, controleA/A geométrico0,985–1,015 e cada caso dentro
±3%. Regra alternativa de escopo estreito (sem anunciar ganho global): duas
baterias com narrow_long_output>=1,10 e limite inferior>=1,05, medium_output sem
regressão>3%, demais casos sem regressão>6%, mesmo controle A/A, e microteste do
helper amplo confirmando sobrecusto<=2microssegundos por chamada. Só vale porque
o algoritmo amplo permanece idêntico exceto pelo despacho condicional; conferir
isso no diff. Conferir ausência de aumento relevante de RSS (mediana+máx8MiB/6%)
e depois validar runtime completo/arquivos30–90MP antes de integrar.

Se inconclusivo, manter a produção intacta e retomar as três recusas salvas.
Se aceito, registrar decisão/escopo, aplicar apenas a candidata conferida,
zerar o contador e continuar até25recusas ou22hSãoPaulo.
