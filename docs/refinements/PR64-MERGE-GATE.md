# PR 64 — gate de merge

A implementação reduz alocações intermediárias para artes RGB opacas, preservando o caminho RGBA quando há transparência ou conversor customizado.

- Suíte local no SHA `873d3e5`: 1086 testes aprovados.
- Regressão independente: 25/25 rodadas aprovadas.
- Checks Linux/Windows: aprovados.
- Build Windows: primeira tentativa falhou somente no upload de artefato por resposta HTML inválida da infraestrutura; o rerun do mesmo job passou em todas as etapas, incluindo empacotamento, smoke tests e upload.
- Saída: a validação deve confirmar equivalência byte a byte nos cenários existentes antes do merge.
