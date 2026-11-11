# Threshold broadcast — validação inicial

A campanha ampliada de 48 rodadas encontrou uma única candidata aceita:
`threshold-broadcast`, que substitui a indexação `np.ix_` da tela periódica por
broadcast 4-D e reshape antes do recorte.

Medição inicial, com sete repetições pareadas e cenários de alfa, arte larga,
ICC e duas CPUs:

- média geométrica: **1,63% mais rápida**;
- mediana pareada: **1,30% mais rápida**;
- intervalo bootstrap de 95%: **1,0057–1,0462**;
- confirmação independente: média geométrica **2,66%**, mediana pareada
  **1,72%**, intervalo bootstrap **1,0055–1,0327**;
- todos os PRTs dos cenários da campanha permaneceram idênticos;
- o maior pico observado foi **273,50 MiB**, abaixo do limite de 512 MiB, mas
  acima do baseline em alguns cenários. A validação completa deve preservar
  esse limite e procurar regressões de memória.

A alteração ainda não é considerada apta para merge. O PR só poderá ser mesclado
após a suíte completa, 25 ciclos independentes de integração/desempenho, matriz
Linux/Windows, build Windows e revisão de todos os PRs abertos.
