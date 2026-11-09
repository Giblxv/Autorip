# AutoRIP v0.8.13

Esta release incorpora à `main` o [PR #48](https://github.com/Giblxv/Autorip/pull/48), com o patch de morfologia física e melhorias de desempenho e operação.

- Base branca com disco em milímetros por transformada euclidiana de distância, respeitando DPI horizontal e vertical; correções para máscaras vazias, bordas e emendas entre tiras.
- Uploads manuais preservam a largura escolhida após reinício antes ou durante o RIP, com parâmetros persistidos e identidade da imagem verificada.
- Menos reconstruções das filas e downloads repetidos de miniaturas; aviso de perda de conexão e reconexão automática.
- Painel com configurações responsivas, contraste melhorado, teclado no interruptor, progresso correto e movimento reduzido.
- Janela nativa com estado da fila e botão para abrir painel/configurações.
- Bibliotecas opcionais de encaixe e remoção de fundo disponíveis no código-fonte; remoção de fundo exige modelo ONNX local. O painel e o executável padrão usam o fluxo RIP local habitual.

No benchmark sintético Linux, 720 × 2400 dpi, a mediana do RIP de uma arte de 5 × 3,75 cm passou de **7,45 s para 1,70 s (4,39×)**. O resultado depende da arte, do hardware e do ICC. Sem branco, os arquivos comparados foram idênticos byte a byte.

A geometria do branco muda nos cantos. **Não validado fisicamente em impressora/PrintExp/Hoson**: faça uma prova antes de produção.

## Downloads

- `AutoRIP_Setup.exe`: instalador Windows x64 por usuário.
- `AutoRIP.exe`: executável Windows x64 portátil.
- `SHA256SUMS.txt`: hashes SHA-256 dos dois arquivos.

Os arquivos desta release são compilados a partir da tag `v0.8.13`, baseada na linha `main`. A tag `v0.8.12` pertence a uma linha divergente; esta publicação preserva as releases anteriores e os pacotes Ubuntu/Mobile nelas disponibilizados.

## Verificações

220 testes locais aprovados; as quatro verificações do PR #48 passaram em Windows 2022/Ubuntu e Python 3.10/3.12. A automação de build desta versão executa novamente a suíte, valida a versão Python/Inno Setup e testa o executável empacotado com upload, geração de PRT e encerramento pelo painel antes de publicar os binários.

A sessão de remoção de fundo foi simulada nos testes; não houve inferência com modelo real. Detalhes e reprodução do benchmark em [MORPH-PERFORMANCE.md](https://github.com/Giblxv/Autorip/blob/v0.8.13/docs/refinements/MORPH-PERFORMANCE.md).
